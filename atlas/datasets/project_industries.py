"""
atlas.datasets.project_industries — each Major Projects Office project, placed in the NAICS
industries it would operate in, and in construction while it is being built.

    python -m atlas.run industries

(Was pipeline/06_industries.py until step S6 of docs/REBUILD.md; the code is carried
unchanged, and the runner writes the output.)

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
distance (`atlas/readers/mpi.py`).
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter

from atlas.core import clock
from atlas.core import frames
from atlas.core import registry as R
from atlas.core.records import Observation, Passage
from atlas.core.schema import Provenance, SourceRef, Text, to_jsonable
from atlas.datasets import Built, Context
from atlas.shells.acquire.fetcher import Fetcher
from atlas.readers import industries_source as industries
from atlas.readers import mpi, naics

log = logging.getLogger(__name__)

OUTPUT = R.DATA_DIR / "events" / "major-projects-office" / "industries.json"
PROJECTS = R.DATA_DIR / "events" / "major-projects-office" / "projects.json"
NAICS_FILES = ("structure_en", "structure_fr", "elements_en", "elements_fr")


def build(ctx: Context, *, dataset: str) -> Built:
    """Each project placed in the industry its finished asset would operate in, with its evidence."""
    reg = R.project_naics()
    nsrc = R.source(reg["classification_source"])
    isrc = R.source(reg["inventory_source"])
    fetch = ctx.fetch
    retrieved = clock.now_iso()

    # Strict UTF-8: a replacement character inside a quoted French example would
    # make an honest quote fail to match, and the error would blame the registry.
    raw = {key: fetch.bytes(nsrc[key], force=ctx.refresh) for key in NAICS_FILES}
    classification = naics.read(*(raw[key].decode("utf-8") for key in NAICS_FILES))
    log.info("NAICS Canada 2022: %d classes", len(classification.classes))

    # NRCan's open map service, both languages, paged in a stable order; and the
    # dataset record, for the licence and the disclaimer shown beside costs.
    layers = {lang: mpi.fetch_layer(lambda url: fetch.bytes(url, force=ctx.refresh), isrc["service"][lang])
              for lang in ("en", "fr")}
    record_raw = fetch.bytes(isrc["record_api"], force=ctx.refresh)
    inventory = mpi.read(layers["en"][0], layers["fr"][0])
    disclaimer = mpi.caveat(json.loads(record_raw))
    log.info("Major Projects Inventory: %d projects", len(inventory))

    projects = json.loads(PROJECTS.read_text(encoding="utf-8"))["projects"]
    records = industries.build(projects, reg, classification, inventory,
                               status_field=Text(**isrc["fields"]["status"]),
                               cost_field=Text(**isrc["fields"]["cost"]))

    payload = {
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
            "dataset_record": isrc["dataset_record"],
            "status_field": isrc["fields"]["status"],
            # Costs are NRCan's figures for the joined projects only; no total is
            # written, because a sum over them would read as the portfolio's (C3).
            "cost_field": isrc["fields"]["cost"],
            "disclaimer": to_jsonable(disclaimer),
            "join_max_km": reg["join_max_km"],
            "sources": to_jsonable([
                SourceRef(url=isrc["service"][lang], retrieved_at=retrieved,
                          provenance=Provenance.OFFICIAL_DATASET, licence=isrc["licence"],
                          content_sha256=hashlib.sha256(layers[lang][1]).hexdigest())
                for lang in ("en", "fr")
            ] + [
                # Hashed over what is read from the record — its licence and its
                # description — not the whole body, whose metadata timestamps
                # would move the hash without the content the atlas uses moving.
                SourceRef(url=isrc["record_api"], retrieved_at=retrieved,
                          provenance=Provenance.OFFICIAL_DATASET, licence=isrc["licence"],
                          content_sha256=hashlib.sha256(json.dumps(
                              {k: json.loads(record_raw)["result"].get(k) for k in ("license_id", "notes_translated")},
                              sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest())
            ]),
        },
        "projects": to_jsonable(records),
    }

    by_sector = Counter(a.sector for r in records for a in r.operating)
    basis = Counter(r.construction.basis for r in records)
    log.info("operating placements by sector: %s", ", ".join(f"{k}={v}" for k, v in sorted(by_sector.items())))
    log.info("construction basis: %s", ", ".join(f"{k}={v}" for k, v in sorted(basis.items())))
    log.info("listed in construction: %s", [r.slug for r in records if r.construction.listed])

    costs, passages = [], []
    for record in records:
        status = record.construction.status
        if status is not None and status.cost_musd is not None:
            costs.append(Observation(
                entity=record.slug, category=record.operating[0].code, period="", measure="capital_cost",
                value=status.cost_musd, unit="millions of dollars", scalar="millions",
                source_table=status.inventory_id, provenance=Provenance.OFFICIAL_DATASET.value,
            ).row())
        for assignment in record.operating:
            passages.append(Passage(entity=record.slug, kind="asset", text_en=assignment.asset.en,
                                    text_fr=assignment.asset.fr, source_url="", locator=assignment.code,
                                    provenance=Provenance.PAGE_VERBATIM.value).row())
            for evidence in assignment.evidence:
                passages.append(Passage(entity=record.slug, kind=f"naics_{evidence.kind}",
                                        text_en=evidence.text.en, text_fr=evidence.text.fr,
                                        source_url=nsrc["dataset_record"], locator=evidence.code,
                                        provenance=Provenance.OFFICIAL_DATASET.value).row())

    published = ("data/events/major-projects-office/industries.json",)
    made = [
        frames.Frame(dataset=dataset, name="capital_costs", profile="cross-section", record_type="observation",
                     keys=frames.OBSERVATION_KEYS, columns=frames.OBSERVATION_COLUMNS, rows=costs,
                     published=published, checks=("join_distance",),
                     notes={"published_costs": len(costs), "projects": len(records),
                            "never_totalled": "a sum over the joined projects would read as the portfolio's"}),
        frames.Frame(dataset=dataset, name="evidence", profile="passages", record_type="passage",
                     keys=frames.PASSAGE_KEYS, columns=frames.PASSAGE_COLUMNS, rows=passages, published=published),
    ]
    return Built(outputs=[(OUTPUT, payload)], frames=made,
                 receipt={"projects": len(records), "published_costs": len(costs),
                          "listed_in_construction": sorted(r.slug for r in records if r.construction.listed),
                          "placements_by_sector": dict(sorted(by_sector.items()))})
