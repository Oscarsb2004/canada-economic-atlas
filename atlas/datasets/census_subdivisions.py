"""
atlas.datasets.census_subdivisions — every census subdivision in Canada, as a `Municipality` record.

    python -m atlas.run municipalities

(Was pipeline/05_municipalities.py until step S4 of docs/REBUILD.md; the code is
carried unchanged, and the runner writes the output.)

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

import logging
from collections import Counter

from atlas.core import clock
from atlas.core import frames
from atlas.core import registry as R
from atlas.core.records import municipality_records
from atlas.core.schema import Provenance, SourceRef, to_jsonable
from atlas.datasets import Built, Context
from atlas.readers import census

log = logging.getLogger(__name__)

SOURCE_KEY = "statcan_municipal_population"
OUTPUT = R.DATA_DIR / "geography" / "municipalities.json"

#: Language suffix -> the source card field carrying that file's URL.
FILES = (("eng", "csv"), ("fra", "csv_fr"))


def build(ctx: Context, *, dataset: str) -> Built:
    """Every census subdivision, as the payload, a places frame and an observations frame."""
    src = R.source(SOURCE_KEY)

    # The parser's DGUID prefixes are vintage-specific ("2021A0005…"). A registry
    # pointed at a 2026 table with a 2021 parser would match no rows; saying so
    # here beats a "no Canada row" error three functions down.
    if str(src.get("census_vintage")) != census.CENSUS_VINTAGE:
        raise SystemExit(
            f"its source card declares census_vintage {src.get('census_vintage')!r}; "
            f"atlas/readers/census.py parses {census.CENSUS_VINTAGE!r}. A new census "
            f"is a deliberate change to both."
        )

    fetch = ctx.fetch
    raw = R.DATA_DIR / "raw" / "statcan"
    zips = {lang: fetch.download(src[key], raw / f"{census.PID}-{lang}.zip", force=ctx.refresh)
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
            f"table {census.PID}: counts differ from the source card's `expected`: {moved}. "
            f"If StatCan revised the table, update the registry in the same change."
        )

    retrieved = clock.now_iso()
    sources = [
        SourceRef(url=src[key], retrieved_at=retrieved, provenance=Provenance.OFFICIAL_DATASET,
                  licence=src.get("licence", ""), content_sha256=census.content_hash(zips[lang]))
        for lang, key in FILES
    ]
    payload = {
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
    }

    ms = counts.municipalities
    log.info("%d census subdivisions in %d census divisions · %d with no published "
             "population · %d with a population of zero",
             len(ms), len(counts.census_division_names),
             sum(m.population_2021 is None for m in ms),
             sum(m.population_2021 == 0 for m in ms))
    log.info("most common legal types: %s", ", ".join(
        f"{t} {n}" for t, n in Counter(m.csd_type.en for m in ms).most_common(6)))

    places, observations = municipality_records(ms)
    published = ("data/geography/municipalities.json",)
    place_frame = frames.Frame(dataset=dataset, name="places", profile="places", record_type="place",
                               keys=frames.PLACE_KEYS, columns=frames.PLACE_COLUMNS,
                               rows=[p.row() for p in places], published=published)
    obs_frame = frames.Frame(dataset=dataset, name="observations", profile="panel", record_type="observation",
                             keys=frames.OBSERVATION_KEYS, columns=frames.OBSERVATION_COLUMNS,
                             rows=[o.row() for o in observations], published=published,
                             notes={"table": census.PID, "census_vintage": census.CENSUS_VINTAGE})
    return Built(outputs=[(OUTPUT, payload)], frames=[place_frame, obs_frame],
                 receipt={"census_subdivisions": len(ms), "census_divisions": len(counts.census_division_names),
                          "provinces_and_territories": len(counts.province_totals)})
