"""
atlas.sources.business_counts — Statistics Canada's Canadian Business Counts,
with employees.

WHY THIS AND NOT A LIST OF COMPANIES

It replaces a panel that named the largest listed companies in each sector from
BlackRock's fund holdings, whose terms forbid public reuse (CLAUDE.md §9).
Statistics Canada publishes counts, not names, under its open licence: how many
business locations with employees each industry has, in each province and
territory, by employment-size range.

WHAT THE TABLE COUNTS — its own notes, carried in the payload

Locations, not firms: StatCan's note 1 says a retailer with ten stores and a
head office is counted eleven times. Note 4 says the size ranges must not be
used to calculate a total number of employees. Both notes, and the rest, travel
with the figures in both languages.

A NEW TABLE EVERY SIX MONTHS

Each reference period is published as its own table — 33101174 for June 2026,
33101095 for December 2025 — so a product ID written into the registry would go
stale without a sound. `latest_table` picks the most recently released table
whose title is exactly "Canadian Business Counts, with employees, <Month>
<Year>", which leaves out the same series' "without employees" tables and its
census-metropolitan-area tables.

ROWS THAT ARE NOT PUBLISHED

The file publishes no explicit zero anywhere: of 85,793 rows on 2026-09-12, not
one VALUE was 0. Instead a size range with no locations has no row at all — 260
of the 2,772 cells this atlas reads, most of them in the territories. Every one
of them is a size range, never a total, and in every one the ranges that ARE
published already add up to the published total. So each absent cell is carried
as null, and `build` checks the formula that makes it a zero —
total − sum of the published ranges = 0 — and stops if it does not hold. The
panel shows such a cell as zero and says why.

MEASURED 2026-09-12 on 33101174, with absent cells as zero: in every cell the
size ranges sum to the total, the provinces and territories sum to Canada, and
the twenty sectors plus "Unclassified" sum to all industries. `verify/` gates
all three with no tolerance.
"""

from __future__ import annotations

import re
from typing import Any

TITLE = re.compile(
    r"^Canadian Business Counts, with employees, "
    r"(January|February|March|April|May|June|July|August|September|October|November|December) \d{4}$"
)

#: Column names as each language's CSV publishes them. `coordinate` is the cell's
#: member-ID path, the same in both files, so the languages are joined on it and
#: never on row position.
COLUMNS = {
    "en": {"period": "REF_DATE", "geo": "GEO", "size": "Employment size",
           "naics": "North American Industry Classification System (NAICS)",
           "coordinate": "COORDINATE", "value": "VALUE"},
    "fr": {"period": "PÉRIODE DE RÉFÉRENCE", "geo": "GÉO", "size": "Tranches d'effectif",
           "naics": "Système de classification des industries de l'Amérique du Nord (SCIAN)",
           "coordinate": "COORDONNÉES", "value": "VALEUR"},
}

#: The codes StatCan gives the two aggregates inside its NAICS dimension.
AGGREGATES = {"1": "total", "2": "unclassified"}

_BRACKET = re.compile(r"^(?P<label>.*?)\s*\[(?P<code>[^\]]+)\]$")


class BusinessCountsError(ValueError):
    """The table is not shaped as expected."""


def latest_table(cubes: list[dict[str, Any]]) -> dict[str, Any]:
    """The newest "Canadian Business Counts, with employees, <Month Year>" table."""
    hits = [c for c in cubes if TITLE.match((c.get("cubeTitleEn") or "").strip())]
    if not hits:
        raise BusinessCountsError("no 'Canadian Business Counts, with employees' table in the WDS cube list")
    return max(hits, key=lambda c: c.get("releaseTime") or "")


def _split(member: str) -> tuple[str, str]:
    m = _BRACKET.match(member.strip())
    if not m:
        raise BusinessCountsError(f"NAICS member {member!r} carries no bracketed code")
    return m.group("label"), m.group("code")


def _index(header: list[str], lang: str) -> dict[str, int]:
    cols = COLUMNS[lang]
    missing = [c for c in cols.values() if c not in header]
    if missing:
        raise BusinessCountsError(f"{lang} CSV: columns {missing} are not in the header")
    return {key: header.index(col) for key, col in cols.items()}


def build(header_en: list[str], rows_en: list[list[str]], header_fr: list[str], rows_fr: list[list[str]],
          *, sector_codes: list[str], geo_codes: dict[str, str]) -> dict[str, Any]:
    """
    Counts for the twenty sectors, all industries and "Unclassified", for every
    geography and size range, with each language's labels.

    `geo_codes` maps StatCan's English geography names to this project's codes.
    A missing geography, sector or total raises. A missing size range is null,
    and only when its published total leaves nothing for it (module docstring).
    """
    ie, ifr = _index(header_en, "en"), _index(header_fr, "fr")
    french = {r[ifr["coordinate"]]: r for r in rows_fr if len(r) > ifr["value"]}
    keep = set(sector_codes) | set(AGGREGATES)

    periods: set[str] = set()
    sizes: list[str] = []
    size_fr: dict[str, str] = {}
    geos: list[str] = []
    geo_fr: dict[str, str] = {}
    labels: dict[str, dict[str, str]] = {}
    cells: dict[tuple[str, str, str], int] = {}

    for r in rows_en:
        if len(r) <= ie["value"]:
            continue
        label_en, code = _split(r[ie["naics"]])
        if code not in keep:
            continue
        coord = r[ie["coordinate"]]
        f = french.get(coord)
        if f is None:
            raise BusinessCountsError(f"cell {coord} is in the English table and not the French one")
        label_fr, code_fr = _split(f[ifr["naics"]])
        if code_fr != code:
            raise BusinessCountsError(f"cell {coord}: English code {code!r}, French code {code_fr!r}")
        geo = r[ie["geo"]]
        if geo not in geo_codes:
            raise BusinessCountsError(f"geography {geo!r} has no code")
        size = r[ie["size"]]
        if size not in size_fr:
            sizes.append(size)
            size_fr[size] = f[ifr["size"]]
        if geo not in geo_fr:
            geos.append(geo)
            geo_fr[geo] = f[ifr["geo"]]
        key = AGGREGATES.get(code, code)
        labels.setdefault(key, {"en": label_en, "fr": label_fr})
        value = r[ie["value"]].strip()
        if not value:
            raise BusinessCountsError(f"cell {coord} ({geo}, {size}, {code}) has no value")
        cells[(geo_codes[geo], size, key)] = int(float(value))
        periods.add(r[ie["period"]])

    if len(periods) != 1:
        raise BusinessCountsError(f"expected one reference period, found {sorted(periods)}")
    industries = ["total"] + list(sector_codes) + ["unclassified"]
    missing = [k for k in industries if k not in labels]
    if missing:
        raise BusinessCountsError(f"industries missing from the table: {missing}")

    counts: dict[str, dict[str, list[int | None]]] = {}
    absent = 0
    for geo in geos:
        code = geo_codes[geo]
        counts[code] = {}
        for key in industries:
            if (code, sizes[0], key) not in cells:
                raise BusinessCountsError(f"no total for {geo}, {key}: a total is never left unpublished")
            row: list[int | None] = [cells.get((code, size, key)) for size in sizes]
            gaps = row.count(None)
            if gaps:
                implied = row[0] - sum(v for v in row[1:] if v is not None)
                if implied != 0:
                    raise BusinessCountsError(
                        f"{geo}, {key}: {gaps} size range(s) unpublished, and the total less the published "
                        f"ranges is {implied}, not 0 — the absent rows cannot be read as zero"
                    )
                absent += gaps
            counts[code][key] = row

    return {
        "reference_period": periods.pop(),
        "size_ranges": [{"en": s, "fr": size_fr[s]} for s in sizes],
        "geographies": [{"code": geo_codes[g], "name": {"en": g, "fr": geo_fr[g]}} for g in geos],
        "industries": [{"code": k, "label": labels[k]} for k in industries],
        #: Size-range cells with no published row, each shown by its total to be 0.
        "absent_cells": absent,
        "counts": counts,
    }
