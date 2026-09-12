#!/usr/bin/env python3
"""
Stage 06 — each Major Projects Office project, placed in the NAICS industries it
would operate in, and in construction while it is being built.

    python pipeline/06_industries.py [--refresh]

Output
    data/events/major-projects-office/industries.json

WHAT THIS IS FOR

The join between the two halves of the atlas (BACKLOG C1, and the ground C4
stands on): "what is being built in this sector, and how big is that sector"
needs a project and a GDP series to share a code. MPO publishes its own five
sectors; Statistics Canada publishes NAICS. Nobody publishes the bridge.

WHAT WAS DECIDED, AND WHY IT IS NOT MPO'S SECTORS

On 2026-09-12 the choice was option B with C (docs/ROADMAP.md §A3): each project
in the industry its finished asset would operate in, and also in construction
while a published status says it is under construction. Mapping MPO's sectors
wholesale was rejected because it is wrong at that grain: StatCan's own 562210
lists "radioactive waste disposal and treatment", so the Deep Geological
Repository belongs in 56 while MPO files it under Electricity.

WHAT MAKES IT CHECKABLE

Every placement in `registry/mpo_naics.yaml` quotes the project page's words for
the asset and Statistics Canada's words for the code, in both languages. This
stage downloads both classification files and refuses any quote that is not in
them, and refuses any asset quote that is not on the page. Construction status
is NRCan's Major Projects Inventory, joined by declared ID and checked by
distance (`atlas/sources/mpi.py`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas import industries
from atlas.core import registry as R
from atlas.core.jsonio import write_if_changed
from atlas.core.schema import Provenance, SourceRef, to_jsonable
from atlas.net import Fetcher
from atlas.sources import mpi, naics

log = logging.getLogger("06_industries")

PROJECTS = R.DATA_DIR / "events" / "major-projects-office" / "projects.json"
OUTPUT = R.DATA_DIR / "events" / "major-projects-office" / "industries.json"
NAICS_FILES = ("structure_en", "structure_fr", "elements_en", "elements_fr")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-download the classification and inventory")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    reg = R.project_naics()
    nsrc = R.source(reg["classification_source"])
    isrc = R.source(reg["inventory_source"])
    fetch = Fetcher(cache_dir=R.DATA_DIR / "raw" / "cache", use_cache=not args.refresh)
    retrieved = _now()

    # Strict UTF-8: a replacement character inside a quoted French example would
    # make an honest quote fail to match, and the error would blame the registry.
    raw = {key: fetch.bytes(nsrc[key], force=args.refresh) for key in NAICS_FILES}
    classification = naics.read(*(raw[key].decode("utf-8") for key in NAICS_FILES))
    log.info("NAICS Canada 2022: %d classes", len(classification.classes))

    xlsx = {lang: fetch.download(isrc[key], R.DATA_DIR / "raw" / "nrcan" / Path(isrc[key]).name,
                                 force=args.refresh)
            for lang, key in (("en", "xlsx"), ("fr", "xlsx_fr"))}
    inventory = mpi.read(xlsx["en"], xlsx["fr"], sheet_en=isrc["sheet"], sheet_fr=isrc["sheet_fr"],
                         status_field=isrc["status_field"],
                         prior_status_field=isrc["prior_status_field"])
    log.info("Major Projects Inventory: %d projects", len(inventory))

    projects = json.loads(PROJECTS.read_text(encoding="utf-8"))["projects"]
    records = industries.build(projects, reg, classification, inventory,
                               status_field=isrc["status_field"])

    changed = write_if_changed(OUTPUT, {
        "generated_at": retrieved,
        "method": {
            "en": "Each project is placed in the NAICS Canada 2022 industry its finished asset would "
                  "operate in, quoting the project page for the asset and Statistics Canada for the "
                  "industry. It is also counted in Construction (23) while NRCan's Major Projects "
                  "Inventory gives its status as under construction. The placement is this atlas's "
                  "reading, not a classification published by either government body.",
            "fr": "Chaque projet est classé dans l'industrie du SCIAN Canada 2022 où son ouvrage "
                  "achevé serait exploité, en citant la page du projet pour l'ouvrage et Statistique "
                  "Canada pour l'industrie. Il est aussi compté dans la construction (23) tant que "
                  "l'Inventaire des grands projets de RNCan indique qu'il est en construction. Ce "
                  "classement est une lecture de cet atlas, et non une classification publiée par "
                  "l'un ou l'autre de ces organismes.",
        },
        "classification": {
            "title": nsrc["title"],
            "dataset_record": nsrc.get("dataset_record", ""),
            "sources": to_jsonable([
                SourceRef(url=nsrc[key], retrieved_at=retrieved, provenance=Provenance.OFFICIAL_DATASET,
                          licence=nsrc["licence"], content_sha256=hashlib.sha256(raw[key]).hexdigest())
                for key in NAICS_FILES
            ]),
        },
        "inventory": {
            "title": isrc["title"],
            "status_field": isrc["status_field"],
            "join_max_km": reg["join_max_km"],
            "sources": to_jsonable([
                SourceRef(url=isrc[key], retrieved_at=retrieved, provenance=Provenance.OFFICIAL_DATASET,
                          licence=isrc["licence"],
                          content_sha256=hashlib.sha256(xlsx[lang].read_bytes()).hexdigest())
                for lang, key in (("en", "xlsx"), ("fr", "xlsx_fr"))
            ]),
        },
        "projects": to_jsonable(records),
    })

    by_sector = Counter(a.sector for r in records for a in r.operating)
    basis = Counter(r.construction.basis for r in records)
    log.info("operating placements by sector: %s",
             ", ".join(f"{k}={v}" for k, v in sorted(by_sector.items())))
    log.info("construction basis: %s", ", ".join(f"{k}={v}" for k, v in sorted(basis.items())))
    log.info("listed in construction: %s", [r.slug for r in records if r.construction.listed])
    log.info("industries.json %s", "updated" if changed else "unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
