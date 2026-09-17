"""
atlas.core.records — the record types every frame is made of (docs/REBUILD.md §2.1).

The published files keep the shapes the web app reads (`atlas.core.schema`).
Alongside them, each dataset is also described in these few general types, so
two datasets can be put side by side without knowing how either was published.
This module only defines the types and the conversions the datasets need; it
computes nothing.

    Observation   a published number about a place, in a period
    Place         an identity with a type, a parent and a boundary vintage
    Passage       words reproduced from a document, with where they were found
    Asset         a thing at a place: a project site, a port, a border crossing
    Event         something dated that happened to one of them
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from atlas.core.schema import Municipality, Series, Text


@dataclass(frozen=True, slots=True)
class Observation:
    """One published value. `value` is None where the publisher left the cell blank; blank is not zero."""

    entity: str             # the place: "CA", "ON", "csd:2021:1001101"
    category: str           # a classification code (NAICS, T-code), or ""
    period: str             # as published: "2026-06", "2025", "2021"
    measure: str            # what is measured: gdp_chained, population, ...
    value: float | int | None
    unit: str = ""
    scalar: str = ""
    slice: str = ""         # a further breakdown, such as a size range; "" is the whole
    status: str = ""        # the publisher's flag for this cell, verbatim
    release: str = ""       # the publisher's release stamp
    source_table: str = ""
    provenance: str = ""

    def row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Place:
    """A place as its publisher identifies it, at one boundary vintage."""

    key: str                # "csd:2021:1001101"
    kind: str               # "census_subdivision", "province"
    name: Text
    parent: str             # the key of the place it sits inside, or ""
    vintage: str
    type_code: str = ""     # the publisher's own legal or statistical type code
    type_name: Text | None = None
    source_table: str = ""

    def row(self) -> dict[str, Any]:
        return {
            "key": self.key, "kind": self.kind, "name_en": self.name.en, "name_fr": self.name.fr,
            "parent": self.parent, "vintage": self.vintage, "type_code": self.type_code,
            "type_en": self.type_name.en if self.type_name else "",
            "type_fr": self.type_name.fr if self.type_name else "",
            "source_table": self.source_table,
        }


@dataclass(frozen=True, slots=True)
class Passage:
    """Words as their publisher wrote them, and where to find them again."""

    entity: str             # what the passage is about: "ON"
    kind: str               # what it is: "budget_risk", "motto", "flag_description"
    text_en: str
    text_fr: str
    source_url: str
    locator: str = ""       # a page number, a heading — where in the document
    content_sha256: str = ""
    provenance: str = ""

    def row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Passage:
    """Words as their publisher wrote them, and where to find them again."""

    entity: str             # what the passage is about: "ON"
    kind: str               # what it is: "budget_risk", "motto", "flag_description"
    text_en: str
    text_fr: str
    source_url: str
    locator: str = ""       # a page number, a heading — where in the document
    content_sha256: str = ""
    provenance: str = ""

    def row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Asset:
    """A thing at a place. Coordinates are [lon, lat], and a derived one says so."""

    key: str
    kind: str                       # "project_site", "port", "border_crossing"
    name_en: str
    name_fr: str
    parent: str = ""                # the project or corridor it belongs to
    category: str = ""              # the publisher's own class: a sector, a mode
    lon: float | None = None
    lat: float | None = None
    geometry_kind: str = ""         # point | corridor | region | absent
    coordinate_provenance: str = ""
    status_en: str = ""
    status_fr: str = ""
    source_url: str = ""
    provenance: str = ""

    def row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Event:
    """Something dated, in the publisher's words, with the date exactly as published."""

    entity: str
    period: str                     # ISO, as precise as the source was
    category: str                   # "project_update"
    text_en: str
    text_fr: str
    date_verbatim: str = ""         # the publisher's own wording of the date
    source_url: str = ""
    provenance: str = ""

    def row(self) -> dict[str, Any]:
        return asdict(self)


def observations_from_series(series: Iterable[Series],
                             status: Mapping[str, tuple[str, ...]] | None = None) -> list[Observation]:
    """
    One observation per published period of each series.

    `status` is the payload's `{"geo/code": (flag per period, ...)}` block, where a
    pull keeps StatCan's STATUS column.
    """
    out: list[Observation] = []
    for s in series:
        flags = (status or {}).get(f"{s.geo}/{s.code}", ())
        for i, (period, value) in enumerate(zip(s.periods, s.values)):
            out.append(Observation(
                entity=s.geo, category=s.code, period=period, measure=s.measure, value=value,
                unit=s.unit, scalar=s.scalar, status=flags[i] if i < len(flags) else "",
                release=s.release_time, source_table=s.source_table, provenance=s.provenance.value,
            ))
    return out


#: Municipality fields that are published counts, with the census year each describes.
MUNICIPAL_COUNTS = (
    ("population", "2021", "population_2021"),
    ("population", "2016", "population_2016"),
    ("private_dwellings", "2021", "private_dwellings_2021"),
    ("private_dwellings", "2016", "private_dwellings_2016"),
    ("occupied_dwellings", "2021", "occupied_dwellings_2021"),
    ("occupied_dwellings", "2016", "occupied_dwellings_2016"),
    ("land_area_km2", "2021", "land_area_km2"),
)


def place_key(m: Municipality) -> str:
    return f"csd:{m.census_vintage}:{m.csd_uid}"


def municipality_records(ms: Iterable[Municipality]) -> tuple[list[Place], list[Observation]]:
    """Each census subdivision as a place, and its published counts as observations."""
    places: list[Place] = []
    obs: list[Observation] = []
    for m in ms:
        key = place_key(m)
        places.append(Place(key=key, kind="census_subdivision", name=m.name,
                            parent=f"cd:{m.census_vintage}:{m.census_division_uid}", vintage=m.census_vintage,
                            type_code=m.csd_type_abbr, type_name=m.csd_type, source_table=m.source_table))
        for measure, period, field_name in MUNICIPAL_COUNTS:
            obs.append(Observation(
                entity=key, category="", period=period, measure=measure, value=getattr(m, field_name),
                unit="km2" if measure == "land_area_km2" else "count", status=m.symbols.get(field_name, ""),
                source_table=m.source_table, provenance=m.provenance.value,
            ))
    return places, obs
