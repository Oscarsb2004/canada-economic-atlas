"""
atlas.datasets.business_locations — business locations with employees, by sector and size.

    python -m atlas.run business-counts

(Was pipeline/03_business_counts.py until step S4 of docs/REBUILD.md; the code is
carried unchanged, and the runner writes the output.)

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
`atlas/readers/business_counts.py` picks the newest one by its exact title.
"""

from __future__ import annotations

import hashlib
import logging
import re

import yaml

from atlas.core import clock
from atlas.core import frames
from atlas.core import registry as R
from atlas.core.records import Observation
from atlas.core.schema import Provenance, SourceRef
from atlas.datasets import Built, Context, statcan_sectors
from atlas.shells.acquire import statcan_table
from atlas.readers import business_counts as bc
from atlas.readers import statcan

log = logging.getLogger(__name__)

OUTPUT = R.DATA_DIR / "sectors" / "business-counts.json"

#: StatCan's notes carry links as HTML. The markup is removed; no word is changed.
_TAG = re.compile(r"<[^>]+>")


def build(ctx: Context, *, dataset: str) -> Built:
    """The newest Canadian Business Counts table, as its payload and a cross-section frame."""
    src = R.source("statcan_business_counts")
    fetch = ctx.fetch
    table = bc.latest_table(statcan_table.cube_list(fetch))
    pid = str(table["productId"])
    log.info("latest table: %s — %s", pid, table["cubeTitleEn"])

    live = statcan_table.release_time(fetch, pid)
    raw = R.DATA_DIR / "raw" / "statcan"
    zip_en, release = statcan_table.download_cube(fetch, pid, "eng", raw, live_release=live, refresh=ctx.refresh)
    zip_fr, release_fr = statcan_table.download_cube(fetch, pid, "fra", raw, live_release=live, refresh=ctx.refresh)
    if not release or release != release_fr:
        raise SystemExit(f"table {pid}: the English and French zips are not of one dated release "
                         f"({release!r} / {release_fr!r}); run with --refresh")

    header_en, rows_en = statcan.read_cube(zip_en, pid)
    header_fr, rows_fr = statcan.read_cube(zip_fr, pid)
    meta_en, meta_fr = statcan.cube_metadata(zip_en, pid), statcan.cube_metadata(zip_fr, pid)

    sectors = [s["code"] for s in yaml.safe_load((R.REGISTRY_DIR / "sectors.yaml").read_text(encoding="utf-8"))["sectors"]]
    geo_codes = statcan_sectors.GEO_CODES
    doc = bc.build(header_en, rows_en, header_fr, rows_fr, sector_codes=sectors, geo_codes=geo_codes)

    note_ids = sorted(set(meta_en["notes"]) | set(meta_fr["notes"]), key=int)
    payload = {
        "generated_at": clock.now_iso(),
        "table": pid,
        "title": {"en": meta_en["title"], "fr": meta_fr["title"]},
        "release_time": release,
        "licence": src["licence"],
        "source": SourceRef(url=f"{statcan_table.WDS}/getFullTableDownloadCSV/{pid}/en", retrieved_at=clock.now_iso(),
                            provenance=Provenance.OFFICIAL_DATASET, licence=src["licence"],
                            content_sha256=hashlib.sha256(zip_en.read_bytes()).hexdigest()).to_dict(),
        "notes": [{"id": i, "text": {"en": _TAG.sub("", meta_en["notes"].get(i, "")).strip(),
                                     "fr": _TAG.sub("", meta_fr["notes"].get(i, "")).strip()}}
                  for i in note_ids],
        **doc,
    }

    total = doc["counts"]["CA"]["total"][0]
    log.info("%s: %d geographies × %d industries × %d size ranges · Canada, all industries: %d locations",
             meta_en["title"], len(doc["geographies"]), len(doc["industries"]), len(doc["size_ranges"]), total)

    sizes = [s["en"] for s in doc["size_ranges"]]
    rows = []
    for geo, by_industry in doc["counts"].items():
        for industry, values in by_industry.items():
            for size, value in zip(sizes, values):
                rows.append(Observation(
                    entity=geo, category=industry, period=doc["reference_period"], measure="business_locations",
                    value=value, unit="count", slice="" if size == sizes[0] else size,
                    release=release, source_table=pid, provenance=Provenance.OFFICIAL_DATASET.value,
                ).row())
    frame = frames.Frame(
        dataset=dataset, name="observations", profile="cross-section", record_type="observation",
        keys=frames.OBSERVATION_KEYS, columns=frames.OBSERVATION_COLUMNS, rows=rows,
        published=("data/sectors/business-counts.json",), checks=("absent_cells",),
        notes={"table": pid, "absent_cells": doc["absent_cells"]},
    )
    return Built(outputs=[(OUTPUT, payload)], frames=[frame],
                 receipt={"table": pid, "release": release, "cells": len(rows), "absent_cells": doc["absent_cells"]})
