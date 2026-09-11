"""
atlas.sources.census — Statistics Canada census geography and population counts.

    Table 98-10-0002 — Population and dwelling counts: Canada, provinces and
    territories, census divisions and census subdivisions (municipalities).

WHY THE RECORD IS A MUNICIPALITY, NOT A CITY

"City" is a legal status, and it means different things in different provinces.
On the 2021 table only 165 of Canada's 5,161 census subdivisions are typed City
(229 more are Ville). Halifax (439,819) is a Regional municipality; Oakville
(213,759) and Richmond Hill (202,022) are Towns; the district municipality of
Langley (132,603; the City of Langley, 28,963, is a separate subdivision) and
Saanich (117,735) are District municipalities. Greenwood, BC is a City of 702 people and
L'Île-Dorval a Ville of 30. A class keyed on legal status would drop Halifax and
keep L'Île-Dorval. So every census subdivision is a record, its legal type is a
FIELD, and "city" is a filter a view applies — never an identity the data asserts.

A CENSUS SUBDIVISION IS NOT ALWAYS A GOVERNMENT

992 of the 5,161 are Indian reserves, and others are unorganized territory or
regional-district electoral areas: statistical units with no municipal council
and no municipal budget. Where a local government does exist it may be one tier
of two. This module models the geography, not the government — fiscal records
attach elsewhere. See docs/CIVIC-FISCAL.md.

THE TRAPS, ALL MEASURED ON THE 2021 TABLE

  The French file is SEMICOLON-delimited, as the French GDP cube is.
  `statcan.read_cube` detects the delimiter; nothing here assumes one. French
  decimals are still written with a point.

  Value columns are selected by the member number the table appends to each
  header — "Population, 2021 [1]" — because the English and French headers share
  nothing else. Selecting by English header text would return no French values
  and raise nothing. Each value column is followed by its Symbols column, and
  that pairing is checked rather than assumed.

  An unpublished value is a BLANK cell with its reason in the Symbols column:
  ".." not available (63 incompletely enumerated reserves), "..." not
  applicable (a percentage change from a population of zero; a rank for Canada).
  Both become None, never 0 — and 0 is a real value: 268 subdivisions have no
  usual residents. The reason is kept per record in `symbols`, so "not
  available" and "not applicable" stay distinguishable.

  Published values carry flags too: "r" revised (the 2016 counts of 604
  subdivisions, seven of them flagged "r,E") and "E" use with caution. They are kept in `symbols` as well.
  Reading the value and dropping its flag would present a revised or low-quality
  figure with full authority.

  Metadata attributes are read by their NUMERIC key (5 = type abbreviation,
  10 = province code, 15 = type description, 16 = DGUID), which is identical in
  both languages, rather than by attribute name. The type description is
  StatCan's own wording per language and is not always translated: the French
  file says "Town" for Ontario towns and the English file says "Ville" for
  Quebec ones. Both are reproduced as published.

  The province comes from the identifier, not from the row's position: a CSDUID
  is PR(2) CD(2) CSD(3), so 1001186 is census division 1001 in province 10. The
  metadata's own province attribute is checked against it.

  The English and French files agree on every geography, every value and every
  flag. That makes them a free second read of the table, and `build` raises on
  any disagreement.

  The 2021 subdivision counts sum EXACTLY to their province — population,
  private dwellings and occupied dwellings, all thirteen. The 2016 counts do
  NOT (NL, QC and ON differ). `verify/` gates the 2021 identities at zero
  tolerance and deliberately declares none for 2016.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from atlas.core.schema import Municipality, SourceRef, Text
from atlas.sources import statcan

PID = "98100002"
CENSUS_VINTAGE = "2021"

#: DGUID prefixes for this vintage: "2021A" and a four-digit geographic level.
LEVEL_COUNTRY = f"{CENSUS_VINTAGE}A0000"
LEVEL_PROVINCE = f"{CENSUS_VINTAGE}A0002"
LEVEL_CENSUS_DIVISION = f"{CENSUS_VINTAGE}A0003"
LEVEL_CENSUS_SUBDIVISION = f"{CENSUS_VINTAGE}A0005"

#: Member geo-attribute keys in the metadata file. Numbered, so one reader serves
#: both languages.
ATTR_TYPE_ABBR = 5
ATTR_PR_CODE = 10
ATTR_TYPE_DESC = 15
ATTR_DGUID = 16

#: StatCan's two-digit province identifier to the two-letter code used everywhere
#: else in this project.
PRUID_TO_CODE = {
    "10": "NL", "11": "PE", "12": "NS", "13": "NB", "24": "QC", "35": "ON",
    "46": "MB", "47": "SK", "48": "AB", "59": "BC", "60": "YT", "61": "NT", "62": "NU",
}

#: The table's value dimension: member number -> (Municipality field, type).
#: Field names match `Municipality` exactly, so a record is built by keyword.
MEASURES: dict[int, tuple[str, type]] = {
    1: ("population_2021", int),
    2: ("population_2016", int),
    3: ("population_change_pct", float),
    4: ("private_dwellings_2021", int),
    5: ("private_dwellings_2016", int),
    6: ("private_dwellings_change_pct", float),
    7: ("occupied_dwellings_2021", int),
    8: ("occupied_dwellings_2016", int),
    9: ("occupied_dwellings_change_pct", float),
    10: ("land_area_km2", float),
    11: ("density_per_km2", float),
    12: ("rank_national", int),
    13: ("rank_provincial", int),
}

#: StatCan's symbol legend. A symbol not listed here RAISES: a new flag is a new
#: meaning, and dropping it would present a qualified figure as an unqualified one.
SYMBOLS = {
    "..": "not available for a specific reference period",
    "...": "not applicable",
    "x": "suppressed to meet the confidentiality requirements of the Statistics Act",
    "E": "use with caution",
    "F": "too unreliable to be published",
    "r": "revised",
    "p": "preliminary",
}

#: The symbols that explain a BLANK cell. A blank flagged only "r" or "E" would
#: be a value qualified and then not published, which is not a reason.
BLANK_REASONS = frozenset({"..", "...", "x", "F"})

#: Markers a value cell itself may carry (other StatCan tables put them there).
#: Deliberately does NOT include "0".
UNAVAILABLE = frozenset({"..", "...", "x", "X", "F"})

_MEMBER_NUMBER = re.compile(r"\[(\d+)\]\s*$")

Values = dict[str, int | float | None]


# ── Reading ────────────────────────────────────────────────────────────────────

def number(raw: str | None, kind: type, symbol: str = "") -> int | float | None:
    """
    One published value, or None where the table says why nothing is published.

    `symbol` is the Symbols cell beside the value and may hold several flags
    ("r,E"). Three things RAISE rather than become None: a symbol not in the
    legend, a blank cell with no reason beside it, and a cell that is neither a
    number nor a marker. Each is the table changing shape, and a quiet None would
    read as "not published" when it means something nobody has looked at.
    """
    value = (raw or "").strip()
    flags = [f for f in (symbol or "").replace(" ", "").split(",") if f]
    unknown = [f for f in flags if f not in SYMBOLS]
    if unknown:
        raise ValueError(f"census value {raw!r} carries unknown symbol(s) {unknown}; "
                         f"the legend is {sorted(SYMBOLS)}")
    if value in UNAVAILABLE:
        return None
    if not value:
        if any(f in BLANK_REASONS for f in flags):
            return None
        raise ValueError(f"census value is blank with no published reason (symbol "
                         f"{symbol!r}); expected one of {sorted(BLANK_REASONS)}")
    try:
        return int(value) if kind is int else float(value)
    except ValueError as exc:
        raise ValueError(
            f"census value {raw!r} is neither a number nor a published "
            f"not-available marker {sorted(UNAVAILABLE)}"
        ) from exc


def measure_columns(header: list[str]) -> dict[int, int]:
    """
    Member number -> value column index, for all thirteen measures, or raise.

    Each value column's flags are read from the column after it, so that
    position is checked, not assumed: a header where the next column is another
    measure would otherwise read one value's number as another's symbol.
    """
    found: dict[int, int] = {}
    for index, column in enumerate(header):
        match = _MEMBER_NUMBER.search(column)
        if match and int(match.group(1)) in MEASURES:
            found[int(match.group(1))] = index
    missing = sorted(set(MEASURES) - set(found))
    if missing:
        raise ValueError(
            f"table {PID}: no value column for members {missing}. The table's "
            f"shape changed; header was {header}"
        )
    unpaired = sorted(n for n, i in found.items()
                      if i + 1 >= len(header) or _MEMBER_NUMBER.search(header[i + 1]))
    if unpaired:
        raise ValueError(f"table {PID}: no symbol column after members {unpaired}; "
                         f"header was {header}")
    return found


@dataclass(frozen=True, slots=True)
class _Row:
    name: str
    values: Values
    symbols: dict[str, str]


def read_values(zip_path: Path) -> dict[str, _Row]:
    """Every geography in one language's data file, keyed by DGUID."""
    header, rows = statcan.read_cube(zip_path, PID)
    if "DGUID" not in header:
        raise ValueError(f"{zip_path.name}: no DGUID column in {header}")
    dguid = header.index("DGUID")
    # The name column sits immediately before DGUID in both languages ("GEO" /
    # "GÉO"); position is used because the header text is translated.
    name = dguid - 1
    columns = measure_columns(header)
    width = max(columns.values()) + 1          # the last symbol column

    out: dict[str, _Row] = {}
    for row in rows:
        # Blank lines and the footnote block at the end of the file carry no
        # DGUID. A row that DOES carry one and is short is truncated data, and
        # skipping it would silently drop a geography.
        if len(row) <= dguid or not row[dguid].startswith(f"{CENSUS_VINTAGE}A"):
            continue
        if len(row) <= width:
            raise ValueError(f"{zip_path.name}: the row for {row[dguid]} has {len(row)} "
                             f"cells, expected {width + 1}")
        values: Values = {}
        symbols: dict[str, str] = {}
        for n, i in columns.items():
            field, kind = MEASURES[n]
            flag = row[i + 1].strip()
            try:
                values[field] = number(row[i], kind, flag)
            except ValueError as exc:
                raise ValueError(f"{zip_path.name}: {row[dguid]} {field}: {exc}") from exc
            if flag:
                symbols[field] = flag
        out[row[dguid]] = _Row(name=row[name].strip(), values=values, symbols=symbols)
    return out


def read_attributes(zip_path: Path) -> dict[str, dict[int, str]]:
    """
    Member geo attributes from the metadata file, keyed by DGUID.

    Attribute rows are `dimension, member id, attribute key, name, label, label,
    value`. Joining on the DGUID attribute rather than on member id means the
    data file and the metadata file never have to agree on position.
    """
    header, rows = statcan.read_cube(zip_path, PID, member=f"{PID}_MetaData.csv")
    by_member: dict[str, dict[int, str]] = {}
    for row in (header, *rows):
        if len(row) >= 7 and row[0] == "1" and row[1].isdigit() and row[2].isdigit():
            by_member.setdefault(row[1], {})[int(row[2])] = row[6].strip()

    out = {attrs[ATTR_DGUID]: attrs for attrs in by_member.values() if attrs.get(ATTR_DGUID)}
    if not out:
        raise ValueError(f"{zip_path.name}: metadata carries no member attributes keyed by DGUID")
    return out


def content_hash(zip_path: Path) -> str:
    """
    Hash of the data file's TEXT, not of the zip.

    Statistics Canada rebuilds its archives on release; hashing the container
    would report a change whenever the zip was re-packed around identical data.
    """
    with zipfile.ZipFile(zip_path) as z:
        text = z.read(f"{PID}.csv").decode("utf-8-sig")
    return SourceRef.hash_content(text)


# ── Building ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class CensusCounts:
    """Everything one build of table 98-10-0002 yields."""

    municipalities: tuple[Municipality, ...]
    canada_total: Values
    province_totals: dict[str, Values]
    province_names: dict[str, Text]
    census_division_names: dict[str, Text]


def build(en_zip: Path, fr_zip: Path) -> CensusCounts:
    """
    Every census subdivision as a `Municipality`, plus the published totals above it.

    Validation is collected and raised once, so a broken release names every
    subdivision it broke rather than the first.
    """
    en, fr = read_values(en_zip), read_values(fr_zip)
    if set(en) != set(fr):
        only_en = sorted(set(en) - set(fr))[:5]
        only_fr = sorted(set(fr) - set(en))[:5]
        raise ValueError(
            f"table {PID}: the English and French files describe different "
            f"geographies (only in English: {only_en}; only in French: {only_fr})"
        )
    # Same geographies is not enough. The two files are two renderings of one
    # table, and on the 2021 release they agree on every value and flag — so a
    # disagreement means one download is not the table the other is.
    differ = sorted(d for d in en
                    if (en[d].values, en[d].symbols) != (fr[d].values, fr[d].symbols))
    if differ:
        raise ValueError(
            f"table {PID}: the English and French files publish different values "
            f"for {len(differ)} geographies, e.g. {differ[:5]}"
        )
    attributes_en, attributes_fr = read_attributes(en_zip), read_attributes(fr_zip)

    canada: Values | None = None
    province_totals: dict[str, Values] = {}
    province_names: dict[str, Text] = {}
    divisions: dict[str, Text] = {}

    for dguid, row in en.items():
        if dguid.startswith(LEVEL_COUNTRY):
            canada = row.values
        elif dguid.startswith(LEVEL_PROVINCE):
            code = PRUID_TO_CODE.get(dguid[len(LEVEL_PROVINCE):])
            if code is None:
                raise ValueError(f"table {PID}: unknown province DGUID {dguid}")
            province_totals[code] = row.values
            province_names[code] = Text(en=row.name, fr=fr[dguid].name)
        elif dguid.startswith(LEVEL_CENSUS_DIVISION):
            divisions[dguid[len(LEVEL_CENSUS_DIVISION):]] = Text(en=row.name, fr=fr[dguid].name)

    if canada is None:
        raise ValueError(f"table {PID}: no Canada row")

    municipalities: list[Municipality] = []
    problems: list[str] = []
    for dguid in sorted(d for d in en if d.startswith(LEVEL_CENSUS_SUBDIVISION)):
        uid = dguid[len(LEVEL_CENSUS_SUBDIVISION):]
        province = PRUID_TO_CODE.get(uid[:2])
        division = uid[:4]
        attrs_en = attributes_en.get(dguid, {})
        attrs_fr = attributes_fr.get(dguid, {})

        if len(uid) != 7 or province is None:
            problems.append(f"{uid}: not a seven-digit CSDUID in a known province")
            continue
        if attrs_en.get(ATTR_PR_CODE) and attrs_en[ATTR_PR_CODE] != uid[:2]:
            problems.append(f"{uid}: metadata says province {attrs_en[ATTR_PR_CODE]}, "
                            f"the identifier says {uid[:2]}")
        if division not in divisions:
            problems.append(f"{uid}: census division {division} is not in the table")
        if not attrs_en.get(ATTR_TYPE_ABBR):
            problems.append(f"{uid}: no municipal type in the metadata")
        if not attrs_fr.get(ATTR_TYPE_DESC):
            problems.append(f"{uid}: no municipal type in the French metadata")

        municipalities.append(Municipality(
            csd_uid=uid,
            dguid=dguid,
            name=Text(en=en[dguid].name, fr=fr[dguid].name),
            province=province,
            census_division_uid=division,
            census_division_name=divisions.get(division, Text(en="")),
            csd_type_abbr=attrs_en.get(ATTR_TYPE_ABBR, ""),
            csd_type=Text(en=attrs_en.get(ATTR_TYPE_DESC, ""), fr=attrs_fr.get(ATTR_TYPE_DESC, "")),
            symbols=dict(en[dguid].symbols),
            census_vintage=CENSUS_VINTAGE,
            source_table=PID,
            **en[dguid].values,
        ))

    if problems:
        raise ValueError(
            f"table {PID}: {len(problems)} census subdivisions failed validation, "
            f"e.g. {problems[:5]}"
        )
    return CensusCounts(
        municipalities=tuple(municipalities),
        canada_total=canada,
        province_totals=dict(sorted(province_totals.items())),
        province_names=dict(sorted(province_names.items())),
        census_division_names=dict(sorted(divisions.items())),
    )
