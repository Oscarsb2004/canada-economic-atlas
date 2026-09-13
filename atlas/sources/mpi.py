"""
atlas.sources.mpi — Natural Resources Canada's Major Projects Inventory, read
from its open map service for two things: whether a project is under
construction (BACKLOG C1), and its capital cost (C2).

WHY THE MAP SERVICE AND NOT THE WORKBOOKS

Until 2026-09-13 this read NRCan's XLSX workbooks. Their own "About + Caveats"
sheet says they are "not authorized or approved for publication at this time",
although open.canada.ca lists them under the Open Government Licence – Canada.
The same record lists this ArcGIS service, in English and French, which carries
no such sentence and publishes the same cost for every project the two share —
all 9 of the atlas's joined projects the service lists, checked 2026-09-13. The
owner chose the source with no doubt attached. What that gives up: no prior-year
cost or status, a status that is only "Planned" or "Under Construction", and the
Deep Geological Repository, which the service does not list.

COSTS, AND THE LIMIT THEY CARRY

A cost is NRCan's figure for one project, in millions of dollars. Only the MPO
projects with a declared join have one, so no cost is ever summed across
projects (C3): a total over the joined ones would read as the portfolio's.

NUMBERS ARE PUBLISHED AS TEXT

`capital_cost` is a string, formatted per language: "20,900.00" in English and
"20 900,00" — no-break spaces, decimal comma — in French. Each is parsed by its
own language's pattern and the two must be the same number, or the project is
refused. Anything else in the field is refused rather than guessed at.

BOTH LANGUAGES, JOINED ON ID

The French layer carries French status words ("En construction") under the
same field names. It is joined on Project ID, and the two layers must list
exactly the same IDs. Names, proponents and points come from the English layer.

WHY THE JOIN TO AN MPO PROJECT IS DECLARED AND THEN CHECKED

Matching on names is how this project got six of eighteen projects the first
time, and names do not agree even where the project is the same: the inventory
calls McIlvenna Bay's proponent Foran Mining Corp. and the MPO page names
Eldorado Gold. So `registry/mpo_naics.yaml` names the inventory Project ID for
each MPO project, and `check_join` holds that declaration to geography — the
inventory's point must lie within `join_max_km` of a site the MPO publishes.
Where the inventory publishes no point, the entry must say
`accept_without_coordinates`, so an unchecked join is a visible decision rather
than a quiet pass.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from atlas.core.schema import Text

#: Mean Earth radius used for every distance this project states. `verify/`
#: re-declares it rather than importing it.
EARTH_RADIUS_KM = 6371.0

#: The layer's maxRecordCount, read 2026-09-13. The inventory has 295 projects,
#: so one page holds it today; paging is kept so growth cannot truncate it.
PAGE_SIZE = 1000

#: The attributes read, by the layer's field names — the same in both languages.
FIELDS = {"id": "id", "name": "project_name", "proponent": "company", "province": "province",
          "status": "status", "cost": "capital_cost"}

_COST = {
    "en": (re.compile(r"\d{1,3}(?:,\d{3})*(?:\.\d+)?"), lambda s: s.replace(",", "")),
    "fr": (re.compile(r"\d{1,3}(?: \d{3})*(?:,\d+)?"), lambda s: s.replace(" ", "").replace(",", ".")),
}


class InventoryError(ValueError):
    """The inventory is not shaped as expected, or a declared join fails its check."""


@dataclass(frozen=True, slots=True)
class InventoryRow:
    project_id: str
    name: str
    proponent: str
    province: str
    status: Text                                 # verbatim in each language
    cost: float | None                           # millions of dollars; both languages agree
    points: tuple[tuple[float, float], ...]      # [lon, lat], GeoJSON order


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two [lon, lat] points (haversine)."""
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


# ── Fetching ───────────────────────────────────────────────────────────────────

def query_url(layer: str, offset: int, page_size: int = PAGE_SIZE) -> str:
    """
    One page of the layer: every field, points in degrees, in a stable order.

    `orderByFields` is required, not decorative — ESRI promises no page order
    without it, and an unstable order would break the zero-line re-run.
    """
    return layer.rstrip("/") + "/query?" + urlencode({
        "where": "1=1", "outFields": "*", "returnGeometry": "true", "outSR": "4326",
        "orderByFields": "OBJECTID ASC", "resultOffset": offset, "resultRecordCount": page_size,
        "f": "json",
    })


def fetch_layer(get: Callable[[str], bytes], layer: str) -> tuple[list[dict[str, Any]], bytes]:
    """Every feature of a layer, and the raw bodies (for the content hash), page by page."""
    features: list[dict[str, Any]] = []
    raw = b""
    offset = 0
    while True:
        body = get(query_url(layer, offset))
        raw += body
        try:
            page = json.loads(body)
        except json.JSONDecodeError as exc:
            raise InventoryError(f"{layer}: page at {offset} is not JSON: {body[:120]!r}") from exc
        if "error" in page:
            raise InventoryError(f"{layer}: the service returned an error: {page['error']}")
        got = page.get("features") or []
        features.extend(got)
        if page.get("exceededTransferLimit"):
            if not got:
                raise InventoryError(f"{layer}: says more pages exist but returned none at {offset}")
        elif len(got) < PAGE_SIZE:
            return features, raw
        offset += len(got)


def caveat(record: dict[str, Any]) -> Text:
    """
    NRCan's disclaimer, verbatim, from the open.canada.ca record's description.

    It is the last paragraph of the description in each language, and opens
    with "DISCLAIMER" / "CLAUSE DE NON-RESPONSABILITÉ". Read rather than copied
    into the registry, so it cannot drift from what the record says.
    """
    notes = (record.get("result") or {}).get("notes_translated") or {}
    found = {}
    for lang, opening in (("en", "DISCLAIMER"), ("fr", "CLAUSE DE NON-RESPONSABILITÉ")):
        paragraphs = [p.strip() for p in str(notes.get(lang) or "").split("\n\n")]
        hits = [p for p in paragraphs if p.startswith(opening)]
        if len(hits) != 1:
            raise InventoryError(f"the dataset record's {lang} description has {len(hits)} paragraphs "
                                 f"opening {opening!r}; expected one")
        found[lang] = hits[0]
    return Text(**found)


# ── Parsing ────────────────────────────────────────────────────────────────────

def _cost(value: object, lang: str, where: str) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise InventoryError(f"{where}: {value!r} is not text, as the service publishes costs")
    pattern, normalise = _COST[lang]
    s = value.strip().replace(" ", " ").replace(" ", " ")
    if not pattern.fullmatch(s):
        raise InventoryError(f"{where}: {value!r} is not a cost as the {lang} service writes one")
    return float(normalise(s))


def _by_id(features: list[dict[str, Any]], lang: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for f in features:
        a = f.get("attributes") or {}
        missing = [k for k in FIELDS.values() if k not in a]
        if missing:
            raise InventoryError(f"{lang}: a feature has no {missing} attribute")
        pid = a["id"]
        # IDs are published as text with leading zeros ("0329"). A number here
        # would mean the field type changed and "0329" became 329.
        if not isinstance(pid, str) or not pid.strip():
            raise InventoryError(f"{lang}: Project ID {pid!r} is not text")
        pid = pid.strip()
        if pid in out:
            raise InventoryError(f"{lang}: duplicate Project ID {pid!r}")
        out[pid] = f
    return out


def read(features_en: list[dict[str, Any]], features_fr: list[dict[str, Any]]) -> dict[str, InventoryRow]:
    """Every project in the inventory, keyed by Project ID, in both languages."""
    en = _by_id(features_en, "en")
    fr = _by_id(features_fr, "fr")
    if set(en) != set(fr):
        raise InventoryError(
            f"the English and French layers list different projects: {sorted(set(en) ^ set(fr))[:10]}"
        )

    out: dict[str, InventoryRow] = {}
    for pid, f in en.items():
        a, b = f["attributes"], fr[pid]["attributes"]
        cost_en = _cost(a["capital_cost"], "en", f"{pid} capital_cost")
        cost_fr = _cost(b["capital_cost"], "fr", f"{pid} capital_cost")
        if cost_en != cost_fr:
            raise InventoryError(f"{pid}: the English layer publishes {a['capital_cost']!r} and the "
                                 f"French layer {b['capital_cost']!r}")
        g = f.get("geometry") or {}
        x, y = g.get("x"), g.get("y")
        points: tuple[tuple[float, float], ...] = ()
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            if not (-180 <= x <= 180 and -90 <= y <= 90):
                raise InventoryError(f"{pid}: point ({x}, {y}) is not in degrees — was outSR=4326 dropped?")
            points = ((float(x), float(y)),)
        out[pid] = InventoryRow(
            project_id=pid,
            name=str(a["project_name"] or "").strip(),
            proponent=str(a["company"] or "").strip(),
            province=str(a["province"] or "").strip(),
            status=Text(en=str(a["status"] or "").strip(), fr=str(b["status"] or "").strip()),
            cost=cost_en,
            points=points,
        )
    return out


def check_join(row: InventoryRow, anchors: list[tuple[float, float]], *,
               max_km: float, accept_without_coordinates: bool, slug: str,
               accept_km: float | None = None) -> float | None:
    """
    The distance that justifies a declared join, or None where none can be measured.

    Raises when the nearest inventory point is further than `max_km` from every
    MPO anchor, and when the inventory publishes no point and the registry did
    not say so. `accept_km` is a declared, per-entry waiver of `max_km`; a waiver
    the distance does not need is refused too, so none outlives its reason.
    """
    if not row.points:
        if not accept_without_coordinates:
            raise InventoryError(
                f"{slug} -> inventory {row.project_id}: the inventory publishes no coordinate, "
                f"so the join cannot be checked. Declare accept_without_coordinates if it stands."
            )
        return None
    if not anchors:
        raise InventoryError(f"{slug}: the MPO project has no anchor to measure the join against")
    nearest = min(distance_km(p, a) for p in row.points for a in anchors)
    if accept_km is not None:
        if nearest <= max_km:
            raise InventoryError(
                f"{slug} -> inventory {row.project_id}: declares a distance waiver, but the nearest "
                f"point is {nearest:.2f} km, within the {max_km} km limit. Remove the waiver."
            )
        max_km = accept_km
    if nearest > max_km:
        raise InventoryError(
            f"{slug} -> inventory {row.project_id} ({row.name!r}): nearest point is "
            f"{nearest:.2f} km from the MPO site, over the {max_km} km limit"
        )
    return round(nearest, 2)
