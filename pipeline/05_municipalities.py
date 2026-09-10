#!/usr/bin/env python3
"""
Stage 05 — every census subdivision in Canada, as a `Municipality` record.

    python pipeline/05_municipalities.py [--refresh]

Outputs
    data/geography/municipalities.json    current state

WHAT THIS IS FOR

Infrastructure, not a view. Nothing in `web/` reads this file yet. It is the
identity spine that later civic, fiscal and demographic work joins to — a
municipal finance table, a census profile, a project placed in a municipality
by point-in-polygon. Building the spine first, and gating it, is what stops
each of those joins inventing its own idea of what a municipality is.
`docs/CIVIC-FISCAL.md` has the staged plan and what it deliberately does not
attempt; `docs/BACKLOG.md` Stage M is the queue.

WHY EVERY SUBDIVISION AND NOT "EVERY CITY"

"City" is a legal status each province defines for itself: Halifax is a
Regional municipality and Greenwood, BC is a City of 702. All 5,161 census
subdivisions are records, the legal type is a field, and "cities" is a filter a
view applies.

WHY BOTH LANGUAGES ARE DOWNLOADED

The French data file is the only place this table publishes French geographic
names ("Terre-Neuve-et-Labrador"). It is also a free cross-check: both files
must describe the same geographies with the same values, and `census.build`
raises if they do not.

NOT BUNDLED

The app gets a sliced, purpose-built payload when a view needs one (BACKLOG
M11), never this whole file.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas.core import registry as R
from atlas.core.jsonio import write_if_changed
from atlas.core.schema import Provenance, SourceRef, to_jsonable
from atlas.net import Fetcher
from atlas.sources import census

log = logging.getLogger("05_municipalities")

SOURCE_KEY = "statcan_municipal_population"
OUTPUT = R.DATA_DIR / "geography" / "municipalities.json"

#: Language suffix -> the sources.yaml key carrying that file's URL.
FILES = (("eng", "csv"), ("fra", "csv_fr"))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-download the table")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    src = R.source(SOURCE_KEY)

    # The parser's DGUID prefixes are vintage-specific ("2021A0005…"). A registry
    # pointed at a 2026 table with a 2021 parser would match no rows; saying so
    # here beats a "no Canada row" error three functions down.
    if str(src.get("census_vintage")) != census.CENSUS_VINTAGE:
        raise SystemExit(
            f"sources.yaml declares census_vintage {src.get('census_vintage')!r}; "
            f"atlas/sources/census.py parses {census.CENSUS_VINTAGE!r}. A new census "
            f"is a deliberate change to both."
        )

    fetch = Fetcher(cache_dir=R.DATA_DIR / "raw" / "cache", use_cache=not args.refresh)
    raw = R.DATA_DIR / "raw" / "statcan"
    zips = {lang: fetch.download(src[key], raw / f"{census.PID}-{lang}.zip", force=args.refresh)
            for lang, key in FILES}

    counts = census.build(zips["eng"], zips["fra"])

    # Stop BEFORE writing when the table's shape moved. verify/ gates the
    # subdivision count independently; this keeps a wrong file from being
    # written in the first place.
    expected = src.get("expected", {})
    got = {
        "census_subdivisions": len(counts.municipalities),
        "census_divisions": len(counts.census_division_names),
        "provinces_and_territories": len(counts.province_totals),
    }
    moved = {k: {"got": v, "declared": expected.get(k)} for k, v in got.items()
             if expected.get(k) != v}
    if moved:
        raise SystemExit(
            f"table {census.PID}: counts differ from sources.yaml `expected`: {moved}. "
            f"If StatCan revised the table, update the registry in the same change."
        )

    retrieved = _now()
    sources = [
        SourceRef(url=src[key], retrieved_at=retrieved, provenance=Provenance.OFFICIAL_DATASET,
                  licence=src.get("licence", ""), content_sha256=census.content_hash(zips[lang]))
        for lang, key in FILES
    ]
    changed = write_if_changed(OUTPUT, {
        "census_vintage": census.CENSUS_VINTAGE,
        "source_table": census.PID,
        "dataset_record": src.get("dataset_record", ""),
        "generated_at": retrieved,
        "sources": to_jsonable(sources),
        "canada_total": counts.canada_total,
        "province_totals": counts.province_totals,
        "province_names": to_jsonable(counts.province_names),
        "census_division_names": to_jsonable(counts.census_division_names),
        "municipalities": to_jsonable(counts.municipalities),
    })

    ms = counts.municipalities
    log.info("%d census subdivisions in %d census divisions · %d with no published "
             "population · %d with a population of zero",
             len(ms), len(counts.census_division_names),
             sum(m.population_2021 is None for m in ms),
             sum(m.population_2021 == 0 for m in ms))
    log.info("most common legal types: %s", ", ".join(
        f"{t} {n}" for t, n in Counter(m.csd_type.en for m in ms).most_common(6)))
    log.info("municipalities.json %s", "updated" if changed else "unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
