"""
atlas.readers.sector_shares — each province and territory's industries as
Statistics Canada's own percentage shares of its GDP (table 36-10-0400,
BACKLOG R2, formerly M2a).

NOTHING IS COMPUTED HERE

The shares are StatCan's: GDP at basic prices, current dollars, each industry's
percentage share of the jurisdiction's economy, 1997 on. The panel lists them
largest first for a year, which is a sort of published figures, not a ranking
of this project's making (CLAUDE.md §11).

WHAT IS KEPT

The twenty two-digit sectors, and "All industries [T001]" (100 by definition,
kept so a reader can see the base). The cube's other aggregates — goods,
services, industrial production, the energy and ICT sectors — overlap the
twenty and are left out, so no reader adds an overlapping share to a sector.

BOTH LANGUAGES, JOINED ON THE COORDINATE

The French cube is its own file with French headers, semicolon-separated (read
by `statcan.read_cube`). Rows are joined on StatCan's coordinate, and the two
must list the same coordinates and periods with the same value.
"""

from __future__ import annotations

from typing import Any

from atlas.core.schema import Text
from atlas.readers import statcan

COLUMNS = {
    "en": {"period": "REF_DATE", "dguid": "DGUID", "industry": "North American Industry Classification System (NAICS)",
           "coordinate": "COORDINATE", "value": "VALUE", "status": "STATUS", "symbol": "SYMBOL"},
    "fr": {"period": "PÉRIODE DE RÉFÉRENCE", "dguid": "DGUID",
           "industry": "Système de classification des industries de l'Amérique du Nord (SCIAN)",
           "coordinate": "COORDONNÉES", "value": "VALEUR"},
}
TOTAL = "T001"


class SectorSharesError(ValueError):
    """The cube is not shaped as expected, or its two languages disagree."""


def _index(header: list[str], lang: str) -> dict[str, int]:
    missing = [v for v in COLUMNS[lang].values() if v not in header]
    if missing:
        raise SectorSharesError(f"36-10-0400 ({lang}): columns {missing} are not in the header")
    return {k: header.index(v) for k, v in COLUMNS[lang].items()}


def build(header_en: list[str], rows_en: list[list[str]], header_fr: list[str], rows_fr: list[list[str]],
          *, pruid_to_code: dict[str, str], sector_codes: set[str]) -> dict[str, Any]:
    """
    {"periods": [...], "industries": {code: label}, "shares": {geo: {code: [value|None per period]}},
     "symbols": {geo: {code: {period: symbol}}}} — every value StatCan's.
    """
    ce, cf = _index(header_en, "en"), _index(header_fr, "fr")
    keep = sector_codes | {TOTAL}

    fr = {}
    for r in rows_fr:
        fr[(r[cf["coordinate"]], r[cf["period"]])] = (r[cf["industry"]], r[cf["value"]])
    if len(fr) != len(rows_fr):
        raise SectorSharesError("36-10-0400 (fr): a coordinate and period appear twice")

    periods: set[str] = set()
    labels: dict[str, Text] = {}
    cells: dict[str, dict[str, dict[str, float | None]]] = {}
    symbols: dict[str, dict[str, dict[str, str]]] = {}
    seen = 0
    for r in rows_en:
        key = (r[ce["coordinate"]], r[ce["period"]])
        if key not in fr:
            raise SectorSharesError(f"36-10-0400: coordinate {key} is in English only")
        label_en = r[ce["industry"]]
        code = statcan.code_of(label_en)
        if code not in keep:
            continue
        seen += 1
        label_fr, value_fr = fr[key]
        if statcan.code_of(label_fr) != code:
            raise SectorSharesError(f"36-10-0400: coordinate {key} is {label_en!r} in English, {label_fr!r} in French")
        geo = pruid_to_code.get(r[ce["dguid"]][-2:])
        if geo is None:
            raise SectorSharesError(f"36-10-0400: DGUID {r[ce['dguid']]!r} is not a province or territory")
        raw = r[ce["value"]].strip()
        if raw != value_fr.strip():
            raise SectorSharesError(f"36-10-0400: {key} is {raw!r} in English, {value_fr!r} in French")
        value = float(raw) if raw else None
        period = r[ce["period"]]
        periods.add(period)
        labels.setdefault(code, Text(en=statcan.label_of(label_en), fr=statcan.label_of(label_fr)))
        cells.setdefault(geo, {}).setdefault(code, {})[period] = value
        mark = (r[ce["symbol"]] or r[ce["status"]]).strip()
        if mark:
            symbols.setdefault(geo, {}).setdefault(code, {})[period] = mark

    if not seen:
        raise SectorSharesError("36-10-0400: no row for any declared sector")
    missing = keep - set(labels)
    if missing:
        raise SectorSharesError(f"36-10-0400: no rows for declared codes {sorted(missing)}")
    order = sorted(periods)
    return {
        "periods": order,
        "industries": {code: labels[code] for code in sorted(labels)},
        "shares": {geo: {code: [by.get(p) for p in order] for code, by in sorted(codes.items())}
                   for geo, codes in sorted(cells.items())},
        "symbols": symbols,
    }
