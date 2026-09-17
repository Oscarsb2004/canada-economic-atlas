"""
atlas.datasets.vessel_register — Canadian-registered vessels that carry an IMO number.

    python -m atlas.run vessels

(Was pipeline/07_vessels.py until step S7 of docs/REBUILD.md; the code is carried
unchanged, and the runner writes the output.)

Output
    data/vessels/large-vessel-register.json

WHAT THIS IS FOR

BACKLOG S1, the identity half of the live vessel layer (docs/AIS.md). A flag is
a state of registry, so "is this ship Canadian" is answered by Transport
Canada's register rather than by the radio. Positions come later, from a feed
chosen in S0, and are never committed.

WHY ONLY THE ENTRIES WITH AN IMO NUMBER

The register publishes no MMSI and no call sign; the IMO number is the only
field an AIS message shares with it. An entry without one can never be matched
to a position, so committing it would carry the whole register for no join. The
register's own totals are published beside the records, so what was left out is
stated, and the full files remain re-fetchable input under data/raw/.

NOT BUNDLED

The app gets what the vessel layer needs when S3 builds it.
"""

from __future__ import annotations

import hashlib
import logging
from collections import Counter
from pathlib import Path

from atlas.core import clock
from atlas.core import frames
from atlas.core import registry as R
from atlas.core.records import Observation
from atlas.core.schema import Provenance, SourceRef, to_jsonable
from atlas.datasets import Built, Context
from atlas.sources import vessels

log = logging.getLogger(__name__)

SOURCE_KEY = "tc_large_vessel_register"
OUTPUT = R.DATA_DIR / "vessels" / "large-vessel-register.json"
FILES = (("en", "xlsx_en"), ("fr", "xlsx_fr"))

#: The register's numeric fields, and the unit each is published in. Anything
#: the register leaves blank stays blank: a vessel with no published tonnage is
#: not a vessel of zero tonnes.
MEASURES = (
    ("gross_tonnage", "tons register"),
    ("net_tonnage", "tons register"),
    ("length_m", "metres"),
    ("breadth_m", "metres"),
    ("depth_m", "metres"),
    ("speed_knots", "knots"),
    ("propulsion_power", "kilowatts"),
    ("engines", "count"),
)


def build(ctx: Context, *, dataset: str) -> Built:
    """Every register entry carrying an IMO number, and the counts of the whole register."""
    src = R.source(SOURCE_KEY)
    fetch = ctx.fetch
    raw = R.DATA_DIR / "raw" / "transport-canada"
    paths = {lang: fetch.download(src[key], raw / Path(src[key]).name, force=ctx.refresh)
             for lang, key in FILES}

    entries = vessels.read(paths["en"], paths["fr"])
    kept = [v for v in entries if v.imo]
    twice = sorted(n for n, c in Counter(v.official_number for v in entries).items() if c > 1)
    counts = {
        "register_entries": len(entries),
        "entries_with_imo": len(kept),
        "imo_failing_check_digit": sum(not v.imo_check_digit_valid for v in kept),
        "official_numbers_listed_twice": twice,
    }

    retrieved = clock.now_iso()
    payload = {
        "generated_at": retrieved,
        "title": src["title"],
        "dataset_record": src.get("dataset_record", ""),
        "sources": to_jsonable([
            SourceRef(url=src[key], retrieved_at=retrieved, provenance=Provenance.OFFICIAL_DATASET,
                      licence=src["licence"], content_sha256=hashlib.sha256(paths[lang].read_bytes()).hexdigest())
            for lang, key in FILES
        ]),
        "scope": {
            "en": "Entries in the Canadian Register of Large Vessels that carry an IMO number — the only "
                  "field the register shares with AIS. The register publishes no MMSI or call sign.",
            "fr": "Inscriptions du Registre canadien des grands bâtiments qui portent un numéro OMI, seul "
                  "champ que le registre partage avec l'AIS. Le registre ne publie ni ISMM ni indicatif d'appel.",
        },
        "counts": counts,
        "vessels": to_jsonable(kept),
    }

    log.info("register: %d entries, %d with an IMO number, %d of those fail the IMO check digit",
             counts["register_entries"], counts["entries_with_imo"], counts["imo_failing_check_digit"])
    log.info("official numbers listed twice: %s", twice)

    rows = []
    for vessel in kept:
        for measure, unit in MEASURES:
            value = getattr(vessel, measure)
            rows.append(Observation(
                # The register lists two official numbers twice (843892 and 849528),
                # so identity here is the number AND the row it was published on.
                entity=f"{vessel.official_number}:{vessel.register_row}", category=vessel.imo,
                period="", measure=measure,
                value=value if isinstance(value, (int, float)) else None, unit=unit,
                status="" if isinstance(value, (int, float)) or value is None else str(value),
                source_table=str(src.get("dataset_record", "")), provenance=Provenance.OFFICIAL_DATASET.value,
            ).row())
    frame = frames.Frame(
        dataset=dataset, name="measurements", profile="cross-section", record_type="observation",
        keys=frames.OBSERVATION_KEYS, columns=frames.OBSERVATION_COLUMNS, rows=rows,
        published=("data/vessels/large-vessel-register.json",),
        notes={"register_entries": counts["register_entries"],
               "why_only_imo_entries": "IMO is the only field the register shares with AIS"},
    )
    return Built(outputs=[(OUTPUT, payload)], frames=[frame], receipt=counts)
