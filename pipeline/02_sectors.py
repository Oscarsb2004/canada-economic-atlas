"""
Stage 02 — the baseline economy: output, investment and employment by sector.

    python pipeline/02_sectors.py [--pull KEY ...] [--skip-provincial] [--refresh]

Every pull is declared in `registry/sectors.yaml` — which cube, which slice, which
output file, and what `verify/` asserts about it. This file turns a declaration
into a payload and knows nothing about any one table.

Outputs (data/sectors/)
    national-monthly.json          real GDP, chained 2017, monthly         36100434
    national-constant.json         real GDP, 2017 constant prices          36100434
    provincial-annual.json         real GDP by province, annual            36100711
    national-annual-current.json   GDP at basic prices, current dollars    36100710
    capex-annual.json              capital expenditures, by province       34100035
    employment-monthly.json        employment (SEPH), unadjusted           14100201
    rates.json                     Bank of Canada policy rate
    _cubes.json                    sha256 of every cube zip

The taxonomy comes from registry/sectors.yaml; the LABELS come from the cube
itself, in both languages, because the industry column embeds its own code
("Manufacturing [31-33]"). Carrying our own labels would let the UI drift from
the source, which the project's governing rule forbids.

WHAT THE NEWER CUBES NEED THAT THE FIRST THREE DID NOT (BACKLOG B2)

The backlog called these "registry entries, not new code". Reading the cubes
before writing the entries showed otherwise:

  SEPH (14100201) is 986 MB of English CSV and 1,075 MB of French — 5.3 million
  rows. Parsed whole, as `read_cube` does, that is several gigabytes to keep one
  row in sixty. It is streamed (`stream: true`), and the French file is read only
  until every wanted label has been seen.

  SEPH publishes three sectors under combined codes — Utilities [22,221] — which
  `code_aliases` maps onto the two-digit key. It does NOT cover agriculture: its
  "Forestry, logging and support [11N]" is forestry alone, and joining it to
  NAICS 11 would divide agriculture-plus-forestry GDP by forestry jobs. So 11 is
  declared absent, with the reason, and `verify/` gates that it stays absent.

  SEPH is unadjusted for seasonality and GDP is seasonally adjusted at annual
  rates. Comparing a month of one with a month of the other measures the season.
  The measure is named `employment_nsa` so nothing can mistake it.

  Capital expenditures (34100035) carry no column saying which years are actual.
  The cube's own note does: the most recent two are preliminary actuals and
  intentions. The payload labels every period (`period_basis`) and cites the
  note; the stage stops if the note stops saying so. An intention on the same
  line as spending is a plan presented as a measurement.

  Suppression and quality codes (x, .., A–F) share the STATUS column. Where a pull
  keeps them, the payload carries them beside the values: a figure graded E is
  published "use with caution", and dropping the grade publishes it without one.

  33100225, declared in sources.yaml as revenue by industry, is NOT pulled: it is
  a balance-sheet table for non-financial corporations whose industry groups do
  not join the 20-sector key. BACKLOG B2a.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from atlas.core import registry as R
from atlas.core.jsonio import write_if_changed
from atlas.core.schema import Provenance, Series, Text, to_jsonable
from atlas.net import Fetcher
from atlas.sources import statcan

log = logging.getLogger("02_sectors")

#: Province and territory names as the cubes spell them, to our codes.
GEO_CODES = {
    "Newfoundland and Labrador": "NL", "Prince Edward Island": "PE",
    "Nova Scotia": "NS", "New Brunswick": "NB", "Quebec": "QC",
    "Ontario": "ON", "Manitoba": "MB", "Saskatchewan": "SK",
    "Alberta": "AB", "British Columbia": "BC", "Yukon": "YT",
    "Northwest Territories": "NT", "Nunavut": "NU", "Canada": "CA",
}

BOC_VALET = "https://www.bankofcanada.ca/valet/observations"

#: pid -> sha256 of the downloaded cube zip, filled by pull_cube().
#:
#: The hash is of the SOURCE PAYLOAD, not of our derived output. That is what
#: makes it a real change signal: StatCan revises cubes, and a new zip with the
#: same release stamp is a thing that happens. 99_bundle.py reads this so the
#: SourceRef it publishes carries a hash instead of an empty string.
CUBE_HASHES: dict[str, str] = {}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_taxonomy() -> tuple[dict, set[str]]:
    """The sector registry, plus the flat allowlist of codes to keep."""
    with (R.REGISTRY_DIR / "sectors.yaml").open(encoding="utf-8") as fh:
        tax = yaml.safe_load(fh)

    codes = {tax["aggregates"]["total"], *tax["aggregates"]["partition"]}
    codes |= {s["code"] for s in tax["sectors"]}

    # Sanity: the partition must actually partition. 5 goods + 15 services = 20.
    parents = {s["parent"] for s in tax["sectors"]}
    if not parents <= set(tax["aggregates"]["partition"]):
        raise ValueError(f"sectors.yaml: sector parents {parents} are not partition members")
    return tax, codes


def _sha256(path: Path) -> str:
    """Chunked, because the SEPH zips are 129 MB and 141 MB."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _previous_release(out_dir: Path, name: str) -> str:
    """
    The release stamp already committed for this output, if any.

    `statcan.release_time()` returns "" when getCubeMetadata is unreachable —
    which is right for a single run, but writing that "" into the committed file
    REPLACES a known-good vintage with nothing. A transient timeout would then
    silently degrade the data and, worse, look like a real change in the diff.
    So an empty fetch falls back to what is already on disk. Only a successful
    fetch may move the stamp.
    """
    path = out_dir / name
    if not path.exists():
        return ""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    for s in doc.get("series", []):
        if s.get("release_time"):
            return s["release_time"]
    return ""


def _previous_hashes(out_dir: Path) -> dict[str, str]:
    """
    The cube hashes already recorded.

    `--pull` runs a subset. Writing only that subset's hashes would erase every
    other cube's change signal from `_cubes.json`, and show up as a diff that has
    nothing to do with what the run touched.
    """
    try:
        doc = json.loads((out_dir / "_cubes.json").read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in doc.get("cubes", {}).items()}
    except (OSError, json.JSONDecodeError):
        return {}


def pull_cube(fetch: Fetcher, key: str, pull: dict, codes: set[str], raw_dir: Path,
              fallback_release: str = "") -> tuple[list[Series], dict]:
    """One declared pull, in both languages, as the series and the payload that holds them."""
    pid = pull["pid"]
    aliases = {str(k): str(v) for k, v in (pull.get("code_aliases") or {}).items()}
    keep = codes | {str(c) for c in pull.get("extra_codes", [])}
    log.info("%s: cube %s (%s, %s) → %s", key, pid, pull["frequency"], pull["measure"], pull["output"])

    zip_en = statcan.download_cube(fetch, pid, "eng", raw_dir)
    zip_fr = statcan.download_cube(fetch, pid, "fra", raw_dir)
    CUBE_HASHES[pid] = _sha256(zip_en)
    meta_en, meta_fr = statcan.cube_metadata(zip_en, pid), statcan.cube_metadata(zip_fr, pid)

    rows_en: Iterable[list[str]]
    rows_fr: Iterable[list[str]]
    if pull.get("stream"):
        stream_en, stream_fr = statcan.iter_cube(zip_en, pid), statcan.iter_cube(zip_fr, pid)
        header_en, rows_en = next(stream_en), stream_en
        header_fr, rows_fr = next(stream_fr), stream_fr
    else:
        header_en, rows_en = statcan.read_cube(zip_en, pid)
        header_fr, rows_fr = statcan.read_cube(zip_fr, pid)

    status: dict[str, tuple[str, ...]] = {}
    series = statcan.build_series(
        header_en, rows_en,
        pid=pid,
        measure=pull["measure"],
        frequency=pull["frequency"],
        filters=pull.get("filters", {}),
        keep_codes=keep,
        geo_codes=GEO_CODES,
        release=statcan.release_time(fetch, pid) or fallback_release,
        code_aliases=aliases,
        status_out=status if pull.get("keep_status") else None,
    )

    # French labels AFTER the English build, so the French file is read only
    # until the codes the build actually kept have all been seen — for SEPH that
    # is a few thousand rows of a five-million-row file.
    labels_fr = statcan.french_labels(header_fr, rows_fr, code_aliases=aliases,
                                      want={s.code for s in series})
    series = [replace(s, label=Text(en=s.label.en, fr=labels_fr.get(s.code, ""))) for s in series]
    unlabelled = sorted({s.code for s in series if not s.label.fr})
    if unlabelled:
        log.warning("%s: no French label for %s", key, unlabelled)

    payload: dict = {
        "generated_at": _now(),
        "count": len(series),
        # The cube's own title, reproduced in both languages, so a file names
        # what it is without anyone looking the product id up.
        "title": {"en": meta_en["title"], "fr": meta_fr["title"]},
        "series": to_jsonable(series),
    }
    if pull.get("keep_status"):
        payload["status"] = dict(sorted(status.items()))
    if pull.get("keep_status") or pull.get("period_basis"):
        payload["notes"] = {"en": meta_en["notes"], "fr": meta_fr["notes"]}
    if pull.get("period_basis"):
        spec = pull["period_basis"]
        periods = sorted({p for s in series for p in s.periods})
        basis, note_id = statcan.latest_periods_basis(
            periods, meta_en["notes"], contains=spec["note_contains"], labels=spec["latest"])
        payload["period_basis"] = basis
        payload["period_basis_note_id"] = note_id
        # Which label each period gets is OUR reading of the cube's note.
        payload["period_basis_provenance"] = Provenance.DERIVED.value

    log.info("  → %d series", len(series))
    return series, payload


def check_partition(series: list[Series], tax: dict) -> None:
    """
    Log T002 + T003 against T001 at the latest period all three publish.

    Aligned BY PERIOD, not by index — the same defect `verify/run.py` had, where
    one series a month longer than the others pairs every comparison with the
    wrong month. `verify/` gates the identity; this is the stage's own early look.
    """
    by_code = {s.code: s for s in series if s.geo == "CA"}
    total, goods, services = (by_code.get(tax["aggregates"]["total"]),
                              *(by_code.get(c) for c in tax["aggregates"]["partition"]))
    if not (total and goods and services):
        log.warning("partition check skipped: missing one of T001/T002/T003")
        return

    tp, gp, sp = (dict(zip(x.periods, x.values)) for x in (total, goods, services))
    for period in sorted(set(tp) & set(gp) & set(sp), reverse=True):
        t, g, s = tp[period], gp[period], sp[period]
        if None not in (t, g, s) and t:
            drift = (g + s - t) / t * 100
            log.info("partition %s: goods+services vs all-industries = %+.4f%%", period, drift)
            if abs(drift) > 1.0:
                log.warning("partition drift exceeds 1%% — check the price basis")
            return


def pull_policy_rate(fetch: Fetcher) -> dict:
    """
    Bank of Canada target for the overnight rate.

    Not a StatCan series and not a sector, so it is stored separately rather
    than forced into the sector schema. It exists here because the KPI row needs
    it and because the sibling repo's country record asks for it by name.

    No open licence: the Bank grants permission requiring attribution and that
    changes be indicated. See registry/sources.yaml.
    """
    src = R.source("boc_valet")
    sid = src["series"]["policy_rate"]
    body = fetch.json(f"{BOC_VALET}/{sid}/json?recent=1")
    obs = body.get("observations", [])
    detail = body.get("seriesDetail", {}).get(sid, {})
    if not obs:
        log.warning("Bank of Canada returned no observations for %s", sid)
        return {}
    return {
        "series": sid,
        "label": detail.get("label", ""),
        "description": detail.get("description", ""),
        "period": obs[-1]["d"],
        "value": float(obs[-1][sid]["v"]),
        "unit": "percent",
        "provenance": Provenance.OFFICIAL_DATASET.value,
        "source_url": f"{BOC_VALET}/{sid}/json",
        "licence": "boc-terms",
        "attribution": R.sources()["licences"]["boc-terms"]["attribution"],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pull", action="append", metavar="KEY",
                    help="run only this pull from sectors.yaml; repeatable")
    ap.add_argument("--skip-provincial", action="store_true",
                    help="skip pulls declared `scope: provincial`")
    ap.add_argument("--refresh", action="store_true", help="bypass the HTTP cache")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    tax, codes = _load_taxonomy()
    pulls: dict = tax["pulls"]
    unknown = sorted(set(args.pull or ()) - set(pulls))
    if unknown:
        ap.error(f"no pull named {unknown}; sectors.yaml declares {sorted(pulls)}")
    log.info("Stage 02 — %d sector codes in the allowlist, %d pulls declared", len(codes), len(pulls))

    fetch = Fetcher(cache_dir=R.DATA_DIR / "raw" / "cache", use_cache=not args.refresh)
    raw_dir = R.DATA_DIR / "raw" / "statcan"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_dir = R.DATA_DIR / "sectors"
    out_dir.mkdir(parents=True, exist_ok=True)
    hashes = _previous_hashes(out_dir)

    for key, pull in pulls.items():
        if args.pull and key not in args.pull:
            continue
        if args.skip_provincial and pull.get("scope") == "provincial":
            log.info("%s: skipped (--skip-provincial)", key)
            continue
        series, payload = pull_cube(fetch, key, pull, codes, raw_dir,
                                    _previous_release(out_dir, pull["output"]))
        if pull.get("partition_check"):
            check_partition(series, tax)
        changed = write_if_changed(out_dir / pull["output"], payload)
        size = (out_dir / pull["output"]).stat().st_size
        log.info("%-30s %3d series  %7.0f KB  %s",
                 pull["output"], len(series), size / 1000, "updated" if changed else "unchanged")

    hashes.update(CUBE_HASHES)
    write_if_changed(out_dir / "_cubes.json", {
        "generated_at": _now(),
        "note": "sha256 of each downloaded StatCan cube zip; the change signal "
                "for figures published in the bundle.",
        "cubes": dict(sorted(hashes.items())),
    })

    # The policy rate is part of a full run, not of a targeted `--pull`.
    if not args.pull:
        rate = pull_policy_rate(fetch)
        if rate:
            write_if_changed(out_dir / "rates.json", {"generated_at": _now(), "policy_rate": rate})
            log.info("policy rate %s = %.2f%%", rate["period"], rate["value"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
