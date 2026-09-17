"""
atlas.shells.acquire.statcan_table — a whole Statistics Canada table, kept in step with its release.

(Moved from atlas/sources/statcan.py in step S2 of docs/REBUILD.md; unchanged in behaviour.
Card: registry/shells/statcan_table.yaml.)

Bulk download is the primary path. `getFullTableDownloadCSV` returns an entire
cube as one zip in a single request — 6.8 MB for the monthly GDP cube. The
alternative, `getDataFromVectorsAndLatestNPeriods`, needs the vector list up
front, caps at 300 vectors per POST (undocumented; 400 returns HTTP 416), and
would be dozens of requests for the same data.

The `productId` is the 8-digit CUBE, not the 10-digit table view: table
36-10-0434-01 is `pid=3610043401` on the website but `36100434` in the API.

Reading a downloaded cube is not this shell's job; that stays with the code
that knows which columns it needs (atlas/sources/statcan.py).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from atlas.shells.acquire.fetcher import Fetcher

log = logging.getLogger(__name__)

WDS = "https://www150.statcan.gc.ca/t1/wds/rest"


#: How far a WDS `releaseTime` can sit behind UTC. The stamp has no offset
#: ("2026-08-28T08:30") and is Ottawa time — UTC-4 in summer, UTC-5 in winter —
#: so reading it as UTC-5 is the latest the release can have happened.
_RELEASE_LATEST_OFFSET = timedelta(hours=5)


def release_path(zip_path: Path) -> Path:
    """The sidecar naming the release a cube zip was downloaded under."""
    return zip_path.with_suffix(".release")


def recorded_release(zip_path: Path) -> str:
    """The release recorded for `zip_path`, or "" if none was."""
    try:
        return release_path(zip_path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _written_after(zip_path: Path, release: str) -> bool:
    """
    Whether `zip_path` was written after `release` was certainly published — in
    which case it holds that release, since WDS says nothing newer exists.
    An unparseable stamp is never "after": the answer then is to download.
    """
    try:
        stamp = datetime.fromisoformat(release)
    except ValueError:
        return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc) + _RELEASE_LATEST_OFFSET
    return datetime.fromtimestamp(zip_path.stat().st_mtime, tz=timezone.utc) >= stamp


def download_cube(fetch: Fetcher, pid: str, lang: str, dest_dir: Path, *,
                  live_release: str, refresh: bool = False) -> tuple[Path, str]:
    """
    Make sure a whole cube zip is on disk, and say which release it holds.

    Returns (path, release). The release is the one recorded when THIS zip was
    downloaded, never simply what WDS says now; "" means the zip cannot be
    dated and must not be parsed (the path may not even exist).

    `lang` is StatCan's own suffix vocabulary: "eng" or "fra".

    The defect this replaces: an existing zip was always skipped while the stamp
    was fetched live, and `--refresh` reached only the HTTP text cache. The first
    run after a StatCan release therefore wrote the NEW stamp over figures parsed
    from the OLD zip — a file claiming a vintage it did not contain, which
    `verify/` cannot see because a stamp is present and well-formed.

    So the zip follows the release, recorded in a `<pid>-<lang>.release` sidecar:

      no live stamp   keep the zip and its recorded stamp, even under `refresh`.
                      A zip nobody can date is worse than a dated old one.
      `refresh`       download.
      stamps match    keep. SEPH's zips are 129 MB and 141 MB.
      none recorded   a zip from before the sidecar: adopt the live stamp if the
                      file was written after that release was surely out,
                      otherwise download.
      stamps differ   download.

    The sidecar is removed before a download and written only after it
    completes, so a download that dies part-way leaves no stamp vouching for a
    partial file. Not covered: StatCan replacing a zip WITHOUT moving
    `releaseTime`. `--refresh` is for that, and `_cubes.json` hashes show it.
    """
    dest = dest_dir / f"{pid}-{lang}.zip"
    recorded = recorded_release(dest) if dest.exists() else ""

    if not live_release:
        if dest.exists():
            log.warning("cube %s-%s: live release unknown; keeping the zip on disk (%s)",
                        pid, lang, recorded or "no recorded release")
        return dest, recorded
    if dest.exists() and not refresh:
        if recorded == live_release:
            return dest, recorded
        if not recorded and _written_after(dest, live_release):
            release_path(dest).write_text(live_release, encoding="utf-8")
            log.info("cube %s-%s: written after release %s; recorded", pid, lang, live_release)
            return dest, live_release

    api_lang = "en" if lang == "eng" else "fr"
    resp = fetch.json(f"{WDS}/getFullTableDownloadCSV/{pid}/{api_lang}")
    if resp.get("status") != "SUCCESS":
        raise RuntimeError(f"WDS refused cube {pid}: {resp}")

    log.info("cube %s-%s: %s -> release %s; downloading", pid, lang,
             recorded or ("refresh" if refresh else "no zip or no recorded release"), live_release)
    release_path(dest).unlink(missing_ok=True)
    fetch.download(resp["object"], dest, force=True)
    release_path(dest).write_text(live_release, encoding="utf-8")
    return dest, live_release


def release_time(fetch: Fetcher, pid: str) -> str:
    """
    The cube's own publication stamp, via `getCubeMetadata`.

    Recorded beside every series because GDP is revised: two runs a month apart
    legitimately disagree about a recent month, and without the vintage stored
    that reads as a bug rather than a revision. It also travels into
    `country.json` for the sibling repo, where Canada sits beside countries
    whose figures are years stale — the vintage is what makes that comparison
    honest rather than flattering.

    This is the release WDS reports NOW. It decides whether a zip on disk is
    current (`download_cube`); it is never itself the stamp written beside
    figures, which must be the one recorded for the zip they were read from.

    Returns "" on failure rather than raising: a missing vintage should degrade
    the run, not abort it. `download_cube` then keeps the zip it has, and that
    zip's recorded stamp.
    """
    try:
        body = fetch.post_json(f"{WDS}/getCubeMetadata", [{"productId": int(pid)}])
        return (body[0].get("object", {}) or {}).get("releaseTime", "")
    except Exception as exc:                          # noqa: BLE001
        log.warning("no release time for cube %s: %s", pid, exc)
        return ""


def cube_list(fetch: Fetcher) -> list[dict[str, Any]]:
    """Every cube WDS publishes, with its titles and product IDs (`getAllCubesListLite`)."""
    return fetch.json(f"{WDS}/getAllCubesListLite")
