"""
atlas.core.registry — load the YAML registries, and refuse to load them wrong.

Validation happens at load time, not at use time. A missing province code or a
strategy slug with no matching feature should stop the pipeline where the
mistake is, not surface three stages later as an empty region on a map.

The registries are the project's configuration surface. Code is Python; what
the project covers — which events, which sectors, which geography — is YAML,
hand-editable and reviewable in a diff.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

#: Repository root, resolved from this file rather than the working directory,
#: so a stage behaves the same however it was invoked.
ROOT = Path(__file__).resolve().parents[2]
REGISTRY_DIR = ROOT / "registry"
DATA_DIR = ROOT / "data"
WEB_PUBLIC_DIR = ROOT / "web" / "public"
WEB_DATA_DIR = ROOT / "web" / "public" / "data"
WEB_MEDIA_DIR = ROOT / "web" / "public" / "media"

#: The 13 provinces and territories. Any code outside this set is a typo.
PROVINCE_CODES = frozenset(
    {"NL", "NS", "PE", "NB", "QC", "ON", "MB", "SK", "AB", "BC", "YT", "NT", "NU"}
)


class RegistryError(ValueError):
    """A registry file is malformed or internally inconsistent."""


def _load(name: str) -> dict[str, Any]:
    path = REGISTRY_DIR / name
    if not path.exists():
        raise RegistryError(f"missing registry file: {path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise RegistryError(f"{name}: expected a mapping at the top level")
    return data


# ── Sources ────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def sources() -> dict[str, Any]:
    """Every external endpoint, with its licence."""
    data = _load("sources.yaml")
    licences = data.get("licences", {})
    srcs = data.get("sources", {})
    for key, src in srcs.items():
        lic = src.get("licence")
        if lic and lic not in licences:
            raise RegistryError(
                f"sources.yaml: source {key!r} claims licence {lic!r}, "
                f"which is not defined under `licences`"
            )
    return data


def source(key: str) -> dict[str, Any]:
    """One source entry by key."""
    srcs = sources()["sources"]
    if key not in srcs:
        raise RegistryError(f"no source named {key!r} in sources.yaml")
    return srcs[key]


# ── Events ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Event:
    slug: str
    kind: str
    title_en: str
    title_fr: str
    date: str
    source_module: str
    licence: str
    expected: dict[str, int]
    disclaimer_en: str
    disclaimer_fr: str
    sectors: tuple[str, ...]

    @property
    def has_projects(self) -> bool:
        return self.kind == "policy_with_projects"


@lru_cache(maxsize=1)
def events() -> tuple[Event, ...]:
    """The curated events, validated."""
    raw = _load("events.yaml").get("events", [])
    known_sources = set(sources()["sources"])
    out: list[Event] = []
    seen: set[str] = set()

    for e in raw:
        slug = e.get("slug")
        if not slug:
            raise RegistryError("events.yaml: an entry has no slug")
        if slug in seen:
            raise RegistryError(f"events.yaml: duplicate slug {slug!r}")
        seen.add(slug)

        # `reference_document` describes a network that already exists; the two
        # `policy` kinds announce things that will be built. Same loader, same
        # verbatim rules, different relationship to time.
        if e.get("kind") not in {"policy", "policy_with_projects", "reference_document"}:
            raise RegistryError(f"events.yaml: {slug!r} has unknown kind {e.get('kind')!r}")

        for s in e.get("sources", []):
            if s not in known_sources:
                raise RegistryError(f"events.yaml: {slug!r} references unknown source {s!r}")

        title = e.get("title", {})
        disc = e.get("disclaimer", {})
        out.append(Event(
            slug=slug,
            kind=e["kind"],
            title_en=title.get("en", ""),
            title_fr=title.get("fr", ""),
            date=str(e.get("date", "")),
            source_module=e.get("source_module", ""),
            licence=e.get("licence", ""),
            expected=dict(e.get("expected", {})),
            disclaimer_en=disc.get("en", ""),
            disclaimer_fr=disc.get("fr", ""),
            sectors=tuple(e.get("sectors", ())),
        ))
    return tuple(out)


def event(slug: str) -> Event:
    for e in events():
        if e.slug == slug:
            return e
    raise RegistryError(f"no event named {slug!r} in events.yaml")


# ── Strategies ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Strategy:
    slug: str
    location_verbatim: str
    provinces: tuple[str, ...]
    precision: str
    render: str
    #: The French page's terminal slug, when it is NOT the same as `slug`.
    #: Eight of the nine strategies use one slug in both languages; the ninth
    #: translates it ("critical-minerals" -> "mineraux-critiques"), so a join on
    #: slug equality alone drops its French silently.
    slug_fr: str = ""

    @property
    def fr_key(self) -> str:
        """The slug the French service will publish for this strategy."""
        return self.slug_fr or self.slug

    @property
    def draws_region(self) -> bool:
        """
        Whether this strategy may be drawn as a province fill.

        `render: list_only` opts out. The Toronto-Quebec rail corridor uses it:
        filling Ontario and Quebec entirely would claim a footprint orders of
        magnitude larger than the real one.
        """
        return self.render != "list_only" and bool(self.provinces)


@lru_cache(maxsize=1)
def strategies() -> tuple[Strategy, ...]:
    """The hand-mapped transformative strategies, validated."""
    raw = _load("strategies.yaml").get("strategies", [])
    out: list[Strategy] = []
    seen: set[str] = set()

    for s in raw:
        slug = s.get("slug")
        if not slug:
            raise RegistryError("strategies.yaml: an entry has no slug")
        if slug in seen:
            raise RegistryError(f"strategies.yaml: duplicate slug {slug!r}")
        seen.add(slug)

        if not s.get("location_verbatim"):
            raise RegistryError(
                f"strategies.yaml: {slug!r} has no location_verbatim. "
                f"The government's own wording is what the UI shows; our province "
                f"mapping is only a reading of it and cannot stand alone."
            )

        provinces = tuple(s.get("provinces", ()))

        # The Norway problem, and it really bites here. YAML 1.1 coerces the
        # bare tokens ON, NO, YES, OFF, TRUE, FALSE to booleans — so an
        # unquoted `[ON, QC]` loads as `[True, "QC"]` and Ontario silently
        # disappears from every strategy that includes it. The codes are quoted
        # in the YAML; this check is what makes a future unquoted edit fail
        # loudly instead of dropping a province.
        non_str = [p for p in provinces if not isinstance(p, str)]
        if non_str:
            raise RegistryError(
                f"strategies.yaml: {slug!r} has non-string province codes {non_str!r}. "
                f"YAML coerced a bare token to a boolean — quote the codes: "
                f'provinces: ["ON", "QC"]'
            )

        bad = set(provinces) - PROVINCE_CODES
        if bad:
            raise RegistryError(f"strategies.yaml: {slug!r} has unknown codes {sorted(bad)}")

        out.append(Strategy(
            slug=slug,
            location_verbatim=s["location_verbatim"],
            provinces=provinces,
            precision=s.get("precision", "provincial"),
            render=s.get("render", "region"),
            slug_fr=str(s.get("slug_fr", "") or ""),
        ))
    return tuple(out)


def strategy(slug: str) -> Strategy | None:
    return next((s for s in strategies() if s.slug == slug), None)


# ── Project industries ─────────────────────────────────────────────────────────

#: Re-declared from atlas.sources.naics so this module imports nothing from the
#: package; `tests/` asserts the two sets are equal.
PROJECT_EVIDENCE_KINDS = frozenset(
    {"definition", "illustrative_example", "all_examples", "inclusion", "exclusion"}
)


@lru_cache(maxsize=1)
def project_naics() -> dict[str, Any]:
    """
    `mpo_naics.yaml`, validated for shape.

    Whether each quote is really on its project page and really in Statistics
    Canada's files is checked against those sources by stage 06, not here — this
    only refuses a file that could not be checked at all.
    """
    name = "mpo_naics.yaml"
    data = _load(name)
    for key in ("version", "classification_source", "inventory_source", "join_max_km",
                "construction", "projects"):
        if key not in data:
            raise RegistryError(f"{name}: `{key}` is required")
    source(data["classification_source"])
    source(data["inventory_source"])
    if not isinstance(data["join_max_km"], (int, float)) or data["join_max_km"] <= 0:
        raise RegistryError(f"{name}: join_max_km must be a positive number")

    def code(value: Any, where: str) -> None:
        # YAML reads a bare 212233 as an integer, and a bare 23 the same way.
        if not isinstance(value, str) or not value:
            raise RegistryError(f"{name}: {where} code {value!r} must be a quoted string")

    def pair(value: Any, where: str, *, required: bool = True) -> None:
        if value is None and not required:
            return
        if not (isinstance(value, dict) and isinstance(value.get("en"), str) and value["en"].strip()
                and isinstance(value.get("fr"), str) and value["fr"].strip()):
            raise RegistryError(f"{name}: {where} needs non-empty `en` AND `fr`")

    def evidence(value: Any, where: str) -> None:
        if not isinstance(value, dict) or value.get("kind") not in PROJECT_EVIDENCE_KINDS:
            raise RegistryError(f"{name}: {where} needs a kind in {sorted(PROJECT_EVIDENCE_KINDS)}")
        code(value.get("code"), where)
        pair(value, where)

    cons = data["construction"]
    code(cons.get("sector"), "construction.sector")
    pair(cons.get("listed_when_status"), "construction.listed_when_status")
    evidence(cons.get("evidence"), "construction.evidence")

    projects = data["projects"]
    if not isinstance(projects, dict) or not projects:
        raise RegistryError(f"{name}: `projects` must map each slug to its entry")
    for slug, entry in projects.items():
        ops = (entry or {}).get("operating")
        if not isinstance(ops, list) or not ops:
            raise RegistryError(f"{name}: {slug} has no operating industry")
        for i, op in enumerate(ops):
            where = f"{slug}.operating[{i}]"
            code(op.get("code"), where)
            pair(op.get("asset"), f"{where}.asset")
            pair(op.get("note"), f"{where}.note", required=False)
            if not isinstance(op.get("evidence"), list) or not op["evidence"]:
                raise RegistryError(f"{name}: {where} quotes no evidence")
            for j, ev in enumerate(op["evidence"]):
                evidence(ev, f"{where}.evidence[{j}]")
        if "inventory" not in entry:
            raise RegistryError(
                f"{name}: {slug} must declare `inventory` — an ID, or null. An absent key "
                f"and a project the inventory does not list would otherwise look the same."
            )
        inv = entry["inventory"]
        if inv is not None:
            if not isinstance(inv, dict):
                raise RegistryError(f"{name}: {slug}.inventory must be null or a mapping with `id`")
            code(inv.get("id"), f"{slug}.inventory")
            waiver = inv.get("accept_distance_km")
            if waiver is not None:
                if not isinstance(waiver, (int, float)) or waiver <= data["join_max_km"]:
                    raise RegistryError(
                        f"{name}: {slug}.inventory.accept_distance_km must be a number above "
                        f"join_max_km — a waiver below the limit is not a waiver"
                    )
                if not entry.get("inventory_note"):
                    raise RegistryError(
                        f"{name}: {slug} waives the join distance and must say so on screen "
                        f"in an `inventory_note`"
                    )
        pair(entry.get("inventory_note"), f"{slug}.inventory_note", required=False)
    return data


# ── Trade corridors ────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class CorridorNode:
    """A port or border crossing named in a corridor's infrastructure list."""

    node_id: str
    kind: str                                # "port" | "border_crossing"
    name_en: str
    name_fr: str
    coord: tuple[float, float]               # [lon, lat], GeoJSON order


@dataclass(frozen=True, slots=True)
class Corridor:
    """
    One of Transport Canada's national trade corridors, as we join it.

    The name, description and infrastructure lists are NOT here — they are
    scraped verbatim by `atlas/sources/tc_corridors.py`. This carries only the
    joins, and every field on it is `Provenance.DERIVED`.
    """

    corridor_id: str
    summary_en: str                          # the join key into the scraped page
    summary_fr: str
    provinces: tuple[str, ...]
    location_verbatim_en: str
    location_verbatim_fr: str
    ports: tuple[str, ...]
    crossings: tuple[str, ...]
    overlaps_provinces: bool = False
    unmapped_note_en: str = ""
    unmapped_note_fr: str = ""

    @property
    def node_ids(self) -> tuple[str, ...]:
        return self.ports + self.crossings


@lru_cache(maxsize=1)
def corridor_nodes() -> dict[str, CorridorNode]:
    """Every port and border crossing, id-keyed, validated."""
    data = _load("corridors.yaml")
    out: dict[str, CorridorNode] = {}
    for key, kind in (("ports", "port"), ("crossings", "border_crossing")):
        for raw in data.get(key, []):
            nid = raw.get("id")
            if not nid:
                raise RegistryError(f"corridors.yaml: a {kind} has no id")
            if nid in out:
                raise RegistryError(f"corridors.yaml: duplicate node id {nid!r}")
            coord = raw.get("coord")
            if not (isinstance(coord, list) and len(coord) == 2):
                raise RegistryError(f"corridors.yaml: {nid!r} has no [lon, lat] coord")
            lon, lat = float(coord[0]), float(coord[1])
            # A sign-flipped or transposed coordinate is the error a human eye
            # does not catch on a globe, and every node here is Canadian.
            if not (-142.0 <= lon <= -52.0 and 41.0 <= lat <= 84.0):
                raise RegistryError(
                    f"corridors.yaml: {nid!r} at [{lon}, {lat}] is outside Canada. "
                    f"Coordinates are [lon, lat] in GeoJSON order, not [lat, lon]."
                )
            name = raw.get("name", {})
            out[nid] = CorridorNode(node_id=nid, kind=kind,
                                    name_en=name.get("en", ""), name_fr=name.get("fr", ""),
                                    coord=(lon, lat))
    return out


@lru_cache(maxsize=1)
def corridors() -> tuple[Corridor, ...]:
    """
    The trade corridors, validated.

    NOT validated as a partition of the provinces, deliberately. The Northern
    Corridor is defined by latitude — "regions north of 55 degrees" — so it
    overlaps the four described by province, and northern British Columbia is
    legitimately in both Pacific and Northern. A mutual-exclusivity check would
    reject Transport Canada's own framing as though it were our bug. What IS
    checked is that a corridor claiming overlap says so explicitly, so the
    overlap is a declaration rather than an oversight.
    """
    data = _load("corridors.yaml")
    nodes = corridor_nodes()
    out: list[Corridor] = []
    seen: set[str] = set()

    for c in data.get("corridors", []):
        cid = c.get("id")
        if not cid:
            raise RegistryError("corridors.yaml: a corridor has no id")
        if cid in seen:
            raise RegistryError(f"corridors.yaml: duplicate corridor id {cid!r}")
        seen.add(cid)

        summary = c.get("summary", {})
        if not summary.get("en") or not summary.get("fr"):
            raise RegistryError(
                f"corridors.yaml: {cid!r} needs `summary` in BOTH languages. It is the "
                f"join key into the scraped page, and a missing French summary yields a "
                f"corridor with no French content while the English side looks perfect."
            )

        loc = c.get("location_verbatim", {})
        if not loc.get("en"):
            raise RegistryError(
                f"corridors.yaml: {cid!r} has no location_verbatim. The province "
                f"mapping is OUR reading of Transport Canada's prose and cannot "
                f"stand without the words it was read from."
            )

        provinces = tuple(c.get("provinces", ()))
        # The Norway problem. YAML 1.1 coerces bare ON/NO/YES/OFF to booleans, so
        # an unquoted [ON, QC] loads as [True, "QC"] and Ontario disappears from
        # the Central Corridor, taking 70% of Canadian manufacturing GDP with it.
        non_str = [p for p in provinces if not isinstance(p, str)]
        if non_str:
            raise RegistryError(
                f"corridors.yaml: {cid!r} has non-string province codes {non_str!r}. "
                f'YAML coerced a bare token to a boolean — quote them: ["ON", "QC"]'
            )
        bad = set(provinces) - PROVINCE_CODES
        if bad:
            raise RegistryError(f"corridors.yaml: {cid!r} has unknown codes {sorted(bad)}")

        unknown = [n for n in tuple(c.get("ports", ())) + tuple(c.get("crossings", ()))
                   if n not in nodes]
        if unknown:
            raise RegistryError(
                f"corridors.yaml: {cid!r} references unknown nodes {unknown}. "
                f"Known ids: {sorted(nodes)}"
            )

        note = c.get("unmapped_note", {})
        if c.get("overlaps_provinces") and not note.get("en"):
            raise RegistryError(
                f"corridors.yaml: {cid!r} declares overlaps_provinces but carries no "
                f"unmapped_note. An overlap the reader is never shown reads as a "
                f"complete mapping."
            )

        out.append(Corridor(
            corridor_id=cid,
            summary_en=summary["en"], summary_fr=summary["fr"],
            provinces=provinces,
            location_verbatim_en=loc.get("en", ""), location_verbatim_fr=loc.get("fr", ""),
            ports=tuple(c.get("ports", ())), crossings=tuple(c.get("crossings", ())),
            overlaps_provinces=bool(c.get("overlaps_provinces", False)),
            unmapped_note_en=(note.get("en") or "").strip(),
            unmapped_note_fr=(note.get("fr") or "").strip(),
        ))

    # Every province and territory must be reachable from some corridor. Overlap
    # is allowed; a GAP is not — a province in no corridor would be absent from
    # every corridor view with nothing saying so.
    covered = {p for c in out for p in c.provinces}
    gap = PROVINCE_CODES - covered
    if gap:
        raise RegistryError(
            f"corridors.yaml: {sorted(gap)} belong to no corridor. Every province and "
            f"territory must be reachable from one; overlap is fine, a gap is not."
        )
    return tuple(out)


def corridor_source() -> dict[str, Any]:
    """The declared source pages. The FR URL is declared, never derived."""
    src = _load("corridors.yaml").get("source", {})
    for key in ("page_en", "page_fr"):
        if not src.get(key):
            raise RegistryError(f"corridors.yaml: source.{key} is required")
    return src
