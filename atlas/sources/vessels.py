"""
atlas.sources.vessels — Transport Canada's Canadian Register of Large Vessels.

WHY THIS EXISTS (BACKLOG S1)

A ship's flag is its state of registry, so "which vessels are Canadian" is a
question for the register, not for the radio. Live positions will come from a
non-government AIS feed (docs/AIS.md); the identity those positions are joined
to comes from here, under the Open Government Licence.

The register publishes no MMSI and no call sign. Its IMO number is the only
field AIS also carries, which is why stage 07 commits the entries that have one
and publishes the counts of the whole register beside them.

WHAT THE FILES ARE LIKE — measured 2026-09-12

- 26,907 entries in each language, in the same order: every row's Official
  Number agrees by position. The header is on the second row of the English
  sheet and the first row of the French one, so it is found by name.
- The Official Number is NOT unique. 843892 and 849528 each appear twice, with
  different tonnage. Both rows are reproduced, and a vessel's identity here is
  its Official Number together with its row in the published register — which
  is also why English and French are paired by position, with the Official
  Number checked on every row, rather than joined on the number alone.
- Words are published per language ("FISHING" / "PECHE", "NOT IN CANADA" /
  "PAS AU CANADA") and are carried as pairs. Every other field must be the same
  in both files, and `read` stops where one is not.
- Year of Build is published as a number: 188700, 2026, 0. It is reproduced as
  published. No year is read out of it: the data dictionary calls it "the period
  the hull was built" and does not say how that period is encoded.
- The French file has a registration-expiry column the English file lacks. It
  was empty in every row, and is not carried.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import openpyxl

from atlas.core.schema import Text, Vessel

#: Column names as each language's file publishes them.
COLUMNS: dict[str, dict[str, str]] = {
    "en": {
        "official_number": "Official Number", "name": "Vessel Name", "imo": "IMO Vessel Number",
        "hull_number": "Hull Number", "year_of_build": "Year of Build",
        "year_of_latest_rebuild": "Year of Latest Rebuild", "port_of_registry": "Port of Registry",
        "registration_date": "Certificate Issuing date or Registration date",
        "descriptor": "Vessel Descriptor", "gross_tonnage": "Gross Tonnage", "net_tonnage": "Net Tonnage",
        "construction_type": "Construction Type", "construction_material": "Construction Material",
        "length_m": "Length", "breadth_m": "Breadth", "depth_m": "Depth", "engine_type": "Engine Type",
        "engines": "Number of Engines", "propulsion_type": "Propulsion Type", "speed_knots": "Speed (Knots)",
        "propulsion_method": "Propulsion Method", "propulsion_power": "Engine Propulsion Power",
    },
    "fr": {
        "official_number": "Numéro Matricule", "name": "Nom du bâtiment", "imo": "Numéro OMI",
        "hull_number": "Numéro de la Coque", "year_of_build": "Année de Construction",
        "year_of_latest_rebuild": "Année de reconstruction", "port_of_registry": "Port d'immatriculation",
        "registration_date": "Date d'immatriculation",
        "descriptor": "Descripteur", "gross_tonnage": "Jauge brute", "net_tonnage": "Jauge nette",
        "construction_type": "Type de construction", "construction_material": "Matériaux de construction",
        "length_m": "Longueur", "breadth_m": "Largeur", "depth_m": "Creux", "engine_type": "Type du moteur",
        "engines": "Nombre de moteurs", "propulsion_type": "Type de propulsion", "speed_knots": "Vitesse (noeuds)",
        "propulsion_method": "Méthode de propulsion", "propulsion_power": "Puissance de propulsion",
    },
}

#: Fields each language words for itself. Everything else must match.
WORD_FIELDS = ("port_of_registry", "descriptor", "construction_type", "construction_material",
               "engine_type", "propulsion_type", "propulsion_method")
SAME_FIELDS = tuple(k for k in COLUMNS["en"] if k not in WORD_FIELDS)


class VesselRegisterError(ValueError):
    """The register files are not shaped as expected, or the two languages disagree."""


def imo_check_digit_valid(imo: str) -> bool:
    """
    The IMO ship identification number's own check: seven digits, the last equal
    to the final digit of the sum of the first six multiplied by 7, 6, 5, 4, 3
    and 2. A stated formula over the published number, so the result is DERIVED.
    """
    if not re.fullmatch(r"\d{7}", imo):
        return False
    d = [int(c) for c in imo]
    return sum(d[i] * (7 - i) for i in range(6)) % 10 == d[6]


def _clean(v: Any) -> Any:
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def _words(v: Any) -> str:
    v = _clean(v)
    return "" if v is None else str(v)


def _sheet(path: Path, lang: str) -> list[dict[str, Any]]:
    cols = COLUMNS[lang]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        rows = wb.worksheets[0].iter_rows(values_only=True)
        header = None
        for raw in rows:
            cells = [str(c).strip() if c is not None else "" for c in raw]
            if cols["official_number"] in cells:
                header = cells
                break
        if header is None:
            raise VesselRegisterError(f"{path.name}: no header row naming {cols['official_number']!r}")
        missing = [c for c in cols.values() if c not in header]
        if missing:
            raise VesselRegisterError(f"{path.name}: columns {missing} are not in the header")
        idx = {key: header.index(col) for key, col in cols.items()}
        out = []
        for raw in rows:
            if not raw or all(_clean(c) is None for c in raw):
                continue
            out.append({key: (raw[i] if i < len(raw) else None) for key, i in idx.items()})
        return out
    finally:
        wb.close()


def _iso_date(v: Any, where: str) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        if (v.hour, v.minute, v.second, v.microsecond) != (0, 0, 0, 0):
            raise VesselRegisterError(f"{where}: registration date {v!r} carries a time of day")
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    raise VesselRegisterError(f"{where}: registration date {v!r} is not a date")


def read(path_en: Path, path_fr: Path) -> list[Vessel]:
    """Every entry in the register, both languages paired by row and checked."""
    en = _sheet(path_en, "en")
    fr = _sheet(path_fr, "fr")
    if len(en) != len(fr):
        raise VesselRegisterError(f"the English file has {len(en)} entries and the French file {len(fr)}")

    out: list[Vessel] = []
    disagree: list[tuple[Any, str, Any, Any]] = []
    for row, (e, f) in enumerate(zip(en, fr), start=1):
        number = _clean(e["official_number"])
        if number != _clean(f["official_number"]):
            raise VesselRegisterError(
                f"row {row}: official number {number!r} in English, {_clean(f['official_number'])!r} in "
                f"French. The files are no longer in the same order, and pairing by position would give "
                f"one vessel another's French words."
            )
        if not isinstance(number, int):
            raise VesselRegisterError(f"row {row}: official number {number!r} is not a whole number")
        for key in SAME_FIELDS:
            if _clean(e[key]) != _clean(f[key]):
                disagree.append((number, key, e[key], f[key]))

        imo = _words(e["imo"])
        out.append(Vessel(
            official_number=number,
            register_row=row,
            name=_words(e["name"]),
            imo=imo,
            imo_check_digit_valid=imo_check_digit_valid(imo) if imo else False,
            hull_number=_words(e["hull_number"]),
            year_of_build=_clean(e["year_of_build"]),
            year_of_latest_rebuild=_clean(e["year_of_latest_rebuild"]),
            port_of_registry=Text(en=_words(e["port_of_registry"]), fr=_words(f["port_of_registry"])),
            registration_date=_iso_date(_clean(e["registration_date"]), f"row {row}"),
            descriptor=Text(en=_words(e["descriptor"]), fr=_words(f["descriptor"])),
            gross_tonnage=_clean(e["gross_tonnage"]),
            net_tonnage=_clean(e["net_tonnage"]),
            construction_type=Text(en=_words(e["construction_type"]), fr=_words(f["construction_type"])),
            construction_material=Text(en=_words(e["construction_material"]), fr=_words(f["construction_material"])),
            length_m=_clean(e["length_m"]),
            breadth_m=_clean(e["breadth_m"]),
            depth_m=_clean(e["depth_m"]),
            engine_type=Text(en=_words(e["engine_type"]), fr=_words(f["engine_type"])),
            engines=_clean(e["engines"]),
            propulsion_type=Text(en=_words(e["propulsion_type"]), fr=_words(f["propulsion_type"])),
            speed_knots=_clean(e["speed_knots"]),
            propulsion_method=Text(en=_words(e["propulsion_method"]), fr=_words(f["propulsion_method"])),
            propulsion_power=_clean(e["propulsion_power"]),
        ))
    if disagree:
        raise VesselRegisterError(
            f"{len(disagree)} values differ between the English and French registers "
            f"(official number, field, English, French): {disagree[:6]}"
        )
    return out
