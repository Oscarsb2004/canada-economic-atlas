"""
Stage 02 — the baseline economy: GDP by sector, national and provincial.

    python pipeline/02_sectors.py [--skip-provincial] [--refresh]

Reads Statistics Canada via bulk cube download (see atlas.sources.statcan for
why bulk rather than vectors), plus the Bank of Canada policy rate.

Outputs
    data/sectors/national-monthly.json     23 series, 1997-01 →
    data/sectors/national-constant.json    additive price basis, same shape
    data/sectors/provincial-annual.json    13 geographies × 23 series
    data/sectors/rates.json                Bank of Canada policy rate

The taxonomy comes from registry/sectors.yaml; the LABELS come from the cube
itself, in both languages, because the industry column embeds its own code
("Manufacturing [31-33]"). Carrying our own labels would let the UI drift from
the source, which the project's governing rule forbids.

Sizing note: the monthly cube is 6.8 MB zipped and holds 249 industry members
across two price bases. We keep 23 series on one basis, which is why the output
is roughly 200 KB rather than tens of megabytes — the filtering is the point.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from atlas.core import registry as R
from atlas.core.jsonio import write_if_changed
from atlas.core.schema import Provenance, Series, Text, to_jsonable
from atlas.net import Fetcher
from atlas.sources import statcan

log = logging.getLogger("02_sectors")

#: Province and territory names as the cube spells them, to our codes. The cube
#: has no "Canada" member for 36100711 — it is provinces and territories only,
#: and the national total comes from the monthly cube.
GEO_CODES = {
    "Newfoundland and Labrador": "NL", "Prince Edward Island": "PE",
    "Nova Scotia": "NS", "New Brunswick": "NB", "Quebec": "QC",
    "Ontario": "ON", "Manitoba": "MB", "Saskatchewan": "SK",
    "Alberta": "AB", "British Columbia": "BC", "Yukon": "YT",
    "Northwest Territories": "NT", "Nunavut": "NU", "Canada": "CA",
}

BOC_VALET = "https://www.bankofcanada.ca/valet/observations"


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





#: pid -> sha256 of the downloaded cube zip, filled by pull_cube().
#:
#: The hash is of the SOURCE PAYLOAD, not of our derived output. That is what
#: makes it a real change signal: StatCan revises cubes, and a new zip with the
#: same release stamp is a thing that happens. 04_bundle.py reads this so the
#: SourceRef it publishes carries a hash instead of an empty string -- the
#: sibling repo flagged the blank field as unusable for change detection, which
#: was fair.
CUBE_HASHES: dict[str, str] = {}


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


def pull_cube(fetch: Fetcher, pull: dict, codes: set[str], raw_dir: Path,
              fallback_release: str = "") -> list[Series]:
    """One configured pull from `sectors.yaml`, in both languages."""
    pid = pull["pid"]
    log.info("cube %s (%s, %s)", pid, pull["frequency"], pull["measure"])

    zip_en = statcan.download_cube(fetch, pid, "eng", raw_dir)
    CUBE_HASHES[pid] = hashlib.sha256(zip_en.read_bytes()).hexdigest()
    header_en, rows_en = statcan.read_cube(zip_en, pid)

    zip_fr = statcan.download_cube(fetch, pid, "fra", raw_dir)
    header_fr, rows_fr = statcan.read_cube(zip_fr, pid)
    labels_fr = statcan.french_labels(header_fr, rows_fr)

    series = statcan.build_series(
        header_en, rows_en,
        pid=pid,
        measure=pull["measure"],
        frequency=pull["frequency"],
        filters=pull.get("filters", {}),
        keep_codes=codes,
        labels_fr=labels_fr,
        geo_codes=GEO_CODES,
        release=statcan.release_time(fetch, pid) or fallback_release,
    )
    log.info("  → %d series, %d rows scanned", len(series), len(rows_en))
    return series


def check_partition(series: list[Series], tax: dict) -> None:
    """
    Verify T002 + T003 == T001 on the latest shared period.

    This identity is the whole reason the composition chart can use two series
    instead of twenty, so it is asserted rather than assumed. Chained dollars
    are NOT additive by construction, so a gap of a few tenths of a percent is
    expected and only a large divergence is reported.
    """
    by_code = {s.code: s for s in series if s.geo == "CA"}
    total, goods, services = (by_code.get(tax["aggregates"]["total"]),
                              *(by_code.get(c) for c in tax["aggregates"]["partition"]))
    if not (total and goods and services):
        log.warning("partition check skipped: missing one of T001/T002/T003")
        return

    for i in range(len(total.periods) - 1, -1, -1):
        t, g, s = total.values[i], goods.values[i], services.values[i]
        if None not in (t, g, s):
            drift = (g + s - t) / t * 100
            note = "chained dollars are non-additive; small drift is expected"
            log.info("partition %s: goods+services vs all-industries = %+.3f%% (%s)",
                     total.periods[i], drift, note)
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
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-provincial", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="bypass the HTTP cache")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    tax, codes = _load_taxonomy()
    log.info("Stage 02 — %d sector codes in the allowlist", len(codes))

    fetch = Fetcher(cache_dir=R.DATA_DIR / "raw" / "cache", use_cache=not args.refresh)
    raw_dir = R.DATA_DIR / "raw" / "statcan"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_dir = R.DATA_DIR / "sectors"

    pulls = tax["pulls"]
    written = []

    national = pull_cube(fetch, pulls["national_monthly"], codes, raw_dir,
                         _previous_release(out_dir, "national-monthly.json"))
    check_partition(national, tax)
    written.append(("national-monthly.json", national))

    constant = pull_cube(fetch, pulls["national_monthly_constant"], codes, raw_dir,
                         _previous_release(out_dir, "national-constant.json"))
    check_partition(constant, tax)
    written.append(("national-constant.json", constant))

    if not args.skip_provincial:
        provincial = pull_cube(fetch, pulls["provincial_annual"], codes, raw_dir,
                               _previous_release(out_dir, "provincial-annual.json"))
        written.append(("provincial-annual.json", provincial))

    for name, series in written:
        changed = write_if_changed(out_dir / name, {
            "generated_at": _now(),
            "count": len(series),
            "series": to_jsonable(series),
        })
        size = (out_dir / name).stat().st_size
        log.info("%-26s %3d series  %6.0f KB  %s",
                 name, len(series), size / 1000, "updated" if changed else "unchanged")

    write_if_changed(out_dir / "_cubes.json", {
        "generated_at": _now(),
        "note": "sha256 of each downloaded StatCan cube zip; the change signal "
                "for figures published in the bundle.",
        "cubes": CUBE_HASHES,
    })

    rate = pull_policy_rate(fetch)
    if rate:
        write_if_changed(out_dir / "rates.json", {"generated_at": _now(), "policy_rate": rate})
        log.info("policy rate %s = %.2f%%", rate["period"], rate["value"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
