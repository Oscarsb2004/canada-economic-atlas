#!/usr/bin/env python3
"""
Stage 03 — business locations with employees, by sector and size.

    python pipeline/03_business_counts.py [--refresh]

Output
    data/sectors/business-counts.json

WHAT THIS IS FOR

The sector panel's view of who makes up each industry. Until 2026-09-12 this
stage published the largest listed companies from BlackRock's fund holdings;
those terms forbid public reuse, so that stage was removed (CLAUDE.md §9) and
this one reproduces Statistics Canada's Canadian Business Counts instead — how
many locations with employees each of the twenty sectors has, in Canada and
each province and territory, in StatCan's own employment-size ranges.

The table is found, not declared: each half-year is a new product ID, and
`atlas/sources/business_counts.py` picks the newest one by its exact title.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml

from atlas.core import registry as R
from atlas.core.jsonio import write_if_changed
from atlas.core.schema import Provenance, SourceRef
from atlas.net import Fetcher
from atlas.sources import business_counts as bc
from atlas.sources import statcan

log = logging.getLogger("03_business_counts")

OUTPUT = R.DATA_DIR / "sectors" / "business-counts.json"

#: StatCan's notes carry links as HTML. The markup is removed; no word is changed.
_TAG = re.compile(r"<[^>]+>")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-download the table")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    src = R.source("statcan_business_counts")
    fetch = Fetcher(cache_dir=R.DATA_DIR / "raw" / "cache", use_cache=not args.refresh)
    table = bc.latest_table(fetch.json(f"{statcan.WDS}/getAllCubesListLite"))
    pid = str(table["productId"])
    log.info("latest table: %s — %s", pid, table["cubeTitleEn"])

    live = statcan.release_time(fetch, pid)
    raw = R.DATA_DIR / "raw" / "statcan"
    zip_en, release = statcan.download_cube(fetch, pid, "eng", raw, live_release=live, refresh=args.refresh)
    zip_fr, release_fr = statcan.download_cube(fetch, pid, "fra", raw, live_release=live, refresh=args.refresh)
    if not release or release != release_fr:
        raise SystemExit(f"table {pid}: the English and French zips are not of one dated release "
                         f"({release!r} / {release_fr!r}); run with --refresh")

    header_en, rows_en = statcan.read_cube(zip_en, pid)
    header_fr, rows_fr = statcan.read_cube(zip_fr, pid)
    meta_en, meta_fr = statcan.cube_metadata(zip_en, pid), statcan.cube_metadata(zip_fr, pid)

    sectors = [s["code"] for s in yaml.safe_load((R.REGISTRY_DIR / "sectors.yaml").read_text(encoding="utf-8"))["sectors"]]
    geo_codes = importlib.import_module("02_sectors").GEO_CODES
    doc = bc.build(header_en, rows_en, header_fr, rows_fr, sector_codes=sectors, geo_codes=geo_codes)

    note_ids = sorted(set(meta_en["notes"]) | set(meta_fr["notes"]), key=int)
    changed = write_if_changed(OUTPUT, {
        "generated_at": _now(),
        "table": pid,
        "title": {"en": meta_en["title"], "fr": meta_fr["title"]},
        "release_time": release,
        "licence": src["licence"],
        "source": SourceRef(url=f"{statcan.WDS}/getFullTableDownloadCSV/{pid}/en", retrieved_at=_now(),
                            provenance=Provenance.OFFICIAL_DATASET, licence=src["licence"],
                            content_sha256=hashlib.sha256(zip_en.read_bytes()).hexdigest()).to_dict(),
        "notes": [{"id": i, "text": {"en": _TAG.sub("", meta_en["notes"].get(i, "")).strip(),
                                     "fr": _TAG.sub("", meta_fr["notes"].get(i, "")).strip()}}
                  for i in note_ids],
        **doc,
    })

    total = doc["counts"]["CA"]["total"][0]
    log.info("%s: %d geographies × %d industries × %d size ranges · Canada, all industries: %d locations",
             meta_en["title"], len(doc["geographies"]), len(doc["industries"]), len(doc["size_ranges"]), total)
    log.info("business-counts.json %s", "updated" if changed else "unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
