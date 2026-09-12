"""
atlas.core.schema — the canonical objects the whole project agrees through.

The governing principle, carried over from African-Stability-Index:

    The frontend and the backend are the same object.

A record carries BOTH its identity and its value. The web app renders what it is
given and never re-derives a label, a total, or a rank. `verify/contract.py`
enforces this across the bundle boundary.

Nothing here computes anything. These are transport and validation types only,
so the pipeline, the web app, and the independent verifier share exactly one
vocabulary.

Two rules are specific to this project and are the reason several fields exist
that would otherwise look redundant:

  1. Federal text is reproduced, never authored. Every string sourced from a
     government page travels with the `SourceRef` that produced it, so a reader
     can always get back to the page and check. Fields we compute are marked
     DERIVED and are visibly ours.

  2. Federal pages are edited in place. `SourceRef.content_sha256` is what makes
     an append-only history possible: stage 01 writes a new history entry only
     when the hash moves, so "what did the government say, and when did it
     change" stays answerable without storing a copy per run.

Design notes:
  - stdlib dataclasses, no pydantic, no new dependencies
  - every type round-trips through to_dict()/from_dict() for JSON transport
  - bilingual text is a `Text` pair rather than parallel `_en`/`_fr` fields, so
    a language can never be silently dropped by a partial write
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── Portable (Athena core) ─────────────────────────────────────────────────────
# Provenance, SourceRef, Geometry, to_jsonable and the Text pattern are shared
# with world-strategic-map. Changing their wire shape is a cross-repo break;
# bump meta.schema_version. Everything below the "Project-specific" banner is
# free to change without telling anyone.
#
# Two known Canada-shaped edges, for whoever extracts these into athena-core:
#   - Text(en, fr) is a two-language pair because bilingual EN/FR is a federal
#     requirement, not a general one. The general form is a language-keyed map
#     with the same .get(lang) fallback. Nothing may depend on Text having
#     exactly two fields.
#   - Geometry.provinces holds subdivision codes here; the general form is a
#     tuple of area codes, and the sibling puts ISO3 country codes in that slot.


# ── Vocabularies ───────────────────────────────────────────────────────────────

class Provenance(str, Enum):
    """
    How a value came to exist. Rendered in the UI, never hidden.

    The distinction that matters most here is OFFICIAL_DATASET vs PAGE_VERBATIM:
    the first is a machine-readable government dataset under a stated licence,
    the second is prose lifted from a web page. They have different reliability
    and different citation needs, and collapsing them would let a scraped
    sentence pass itself off as a published statistic.
    """

    OFFICIAL_DATASET = "official_dataset"   # NRCan ArcGIS, StatCan WDS, Bank of Canada
    PAGE_VERBATIM    = "page_verbatim"      # reproduced from a federal page as published
    NEWS_RELEASE     = "news_release"       # reproduced from a dated announcement
    MARKET_DATA      = "market_data"        # index constituents — never a GDP claim
    DERIVED          = "derived"            # computed by this pipeline
    ABSENT           = "absent"             # nothing available

    @property
    def is_reproduced(self) -> bool:
        """True when the text is the government's words, not ours."""
        return self in (Provenance.PAGE_VERBATIM, Provenance.NEWS_RELEASE)


class GeometryKind(str, Enum):
    """
    What a project's location actually is.

    POINT is a single site. CORRIDOR is a two-endpoint route — a highway, a
    pipeline — which must be drawn as a line, because dropping a pin at one end
    of the Mackenzie Valley Highway asserts a location the source does not.
    REGION is a strategy whose published location is prose ("All of Canada"),
    hand-mapped to provinces. ABSENT is stated rather than guessed.
    """

    POINT    = "point"
    CORRIDOR = "corridor"
    REGION   = "region"
    ABSENT   = "absent"


def _flat_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    """
    Rough planar distance between two [lon, lat] pairs, longitude scaled.

    Only ever used to find the halfway point along a route, where a constant
    factor cancels — but the latitude scaling does not cancel, because a degree
    of longitude is half as long at 60°N as at the equator and the Mackenzie
    Valley Highway runs from 63°N to 68°N. Without it the midpoint slides
    toward the eastern end.
    """
    lat = math.radians((a[1] + b[1]) / 2)
    return math.hypot((b[0] - a[0]) * math.cos(lat), b[1] - a[1])


# ── Primitives ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Text:
    """
    One string in both official languages.

    A pair rather than two loose fields: the scrapers fetch EN and FR from
    separate pages, and a pair makes a half-written record a type error at
    construction instead of an empty panel in the UI.
    """

    en: str
    fr: str = ""

    def get(self, lang: str) -> str:
        """The text in `lang`, falling back to English when FR is missing."""
        return self.fr if (lang == "fr" and self.fr) else self.en

    def to_dict(self) -> dict[str, str]:
        return {"en": self.en, "fr": self.fr}

    @classmethod
    def from_dict(cls, d: dict[str, str]) -> Text:
        return cls(en=d.get("en", ""), fr=d.get("fr", ""))


@dataclass(frozen=True, slots=True)
class SourceRef:
    """
    Where a value came from, precisely enough to check it.

    `content_sha256` hashes the normalised text rather than the raw HTML: AEM
    rewrites whitespace and reorders attributes between deploys, so hashing raw
    bytes would report a change on every crawl and the history would be noise.
    """

    url: str
    retrieved_at: str                    # ISO-8601 UTC, second precision
    provenance: Provenance
    licence: str = ""
    content_sha256: str = ""

    @staticmethod
    def hash_content(text: str) -> str:
        """The canonical content hash. Normalise before calling."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "retrieved_at": self.retrieved_at,
            "provenance": self.provenance.value,
            "licence": self.licence,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SourceRef:
        return cls(
            url=d["url"],
            retrieved_at=d["retrieved_at"],
            provenance=Provenance(d["provenance"]),
            licence=d.get("licence", ""),
            content_sha256=d.get("content_sha256", ""),
        )


@dataclass(frozen=True, slots=True)
class Geometry:
    """
    A project's location as the source published it.

    `coordinates` is a list of [lon, lat] pairs — GeoJSON order, not lat/lon —
    because that is what MapLibre consumes and converting once at the boundary
    beats converting at every call site. One pair is a POINT, two is a CORRIDOR.

    `approximate` carries the source's own disclaimer forward: the MPO map states
    that all locations are approximate and subject to final routing decisions,
    and that caveat belongs with the coordinates rather than in a footer nobody
    reads.
    """

    kind: GeometryKind
    coordinates: tuple[tuple[float, float], ...] = ()
    provinces: tuple[str, ...] = ()          # REGION only
    location_verbatim: str = ""              # the source's own words
    approximate: bool = True

    #: Who produced these coordinates, when it is not the obvious answer.
    #:
    #: Left None, a single point is assumed to be the publisher's own — true for
    #: the MPO, whose ArcGIS service publishes official coordinates. It is NOT
    #: true everywhere: Transport Canada NAMES the ports and border crossings on
    #: each trade corridor and publishes no geometry for any of them, so those
    #: coordinates are ours. Inferring provenance from geometry shape would have
    #: labelled our placements `official_dataset`, which is the precise failure
    #: this project exists to avoid.
    coordinate_provenance: Provenance | None = None

    @property
    def anchor(self) -> tuple[float, float] | None:
        """
        The ONE point that represents this geometry on a map.

        Every geometry that has coordinates has an anchor, and that totality is
        the point. The map used to render points and corridors through two
        separate filters — `kind === "point"` for markers, `kind === "corridor"`
        for lines — so a corridor got a dashed line and NO marker: no headpiece,
        no click target, no way to open the project. Four of eighteen projects
        were anonymous squiggles, and adding a third kind would have made it
        five. Rendering has to be a total function over geometry, and a total
        function needs somewhere to put the marker.

        For a POINT that is the government's own coordinate. For a CORRIDOR it
        is the halfway point ALONG the route, which is why this walks the
        segments rather than averaging the ends: averaging is the same answer
        for the two-endpoint routes published today and the wrong one the moment
        a route arrives with a third vertex.

        A REGION has no coordinates — the strategies' locations are prose — so
        it returns None and must be reached some other way. `verify/` gates
        that: a record with no anchor and no other affordance is a record the
        reader cannot get to.
        """
        pts = self.coordinates
        if not pts:
            return None
        if len(pts) == 1:
            return pts[0]

        spans = [_flat_distance(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
        half = sum(spans) / 2
        if half <= 0:
            return pts[0]
        for (a, b), span in zip(zip(pts, pts[1:]), spans):
            if span >= half:
                t = half / span
                return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            half -= span
        return pts[-1]

    @property
    def anchor_provenance(self) -> Provenance:
        """
        Whether the anchor is the source's coordinate or our arithmetic.

        A single point is the government's. A corridor midpoint is ours, and the
        UI must not render the two identically — the source published the ends
        of the Mackenzie Valley Highway, not its middle.
        """
        if not self.coordinates:
            return Provenance.ABSENT
        # An explicit declaration always wins over the shape-based guess.
        if self.coordinate_provenance is not None:
            return self.coordinate_provenance
        if self.kind is GeometryKind.POINT and len(self.coordinates) == 1:
            return Provenance.OFFICIAL_DATASET
        return Provenance.DERIVED

    @property
    def is_linear(self) -> bool:
        """Whether this draws as a line in addition to its marker."""
        return len(self.coordinates) > 1

    def to_dict(self) -> dict[str, Any]:
        anchor = self.anchor
        return {
            "kind": self.kind.value,
            "coordinates": [list(c) for c in self.coordinates],
            "provinces": list(self.provinces),
            "location_verbatim": self.location_verbatim,
            "approximate": self.approximate,
            # Published rather than re-derived in the browser. The app never
            # recomputes what the pipeline can state (CLAUDE.md §2), and an
            # anchor computed in two languages is an anchor that can disagree
            # with itself.
            "anchor": list(anchor) if anchor else None,
            "anchor_provenance": self.anchor_provenance.value,
            "is_linear": self.is_linear,
            # The DECLARATION, kept distinct from the computed value above.
            # `anchor_provenance` is an output the frontend reads; this is the
            # optional input that overrides it. Reading the computed value back
            # as a declaration would make a round trip lossy in the other
            # direction — every inferred value would come back explicit.
            "coordinate_provenance": (self.coordinate_provenance.value
                                      if self.coordinate_provenance else None),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Geometry:
        return cls(
            kind=GeometryKind(d["kind"]),
            coordinates=tuple((float(c[0]), float(c[1])) for c in d.get("coordinates", [])),
            provinces=tuple(d.get("provinces", ())),
            location_verbatim=d.get("location_verbatim", ""),
            approximate=d.get("approximate", True),
            coordinate_provenance=(Provenance(d["coordinate_provenance"])
                                   if d.get("coordinate_provenance") else None),
        )


# ── Project-specific ───────────────────────────────────────────────────────────
# Everything below is this repo's own vocabulary. Change freely.


# ── Event records ──────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class QuickFact:
    """
    One labelled bullet from a project page's "Quick facts" block.

    The label varies per project — "Global leadership", "Economic impact", "Job
    creation" — so it is data, not an enum. The dollar figures and job counts
    live inside `body` as prose and are deliberately NOT parsed into numbers:
    turning "Will attract $5 billion in investment" into `{"capex": 5e9}` would
    be us making a claim the page does not make in that form.
    """

    label: Text
    body: Text


@dataclass(frozen=True, slots=True)
class Update:
    """
    One entry from a project page's "Latest updates" block.

    `date` is ISO 8601 at the precision the entry publishes — "2026-05-19",
    "2026-07" for "In July 2026", "2022" for "In 2022" — or "" when the entry
    opens with no date. Reduced precision still sorts correctly against full
    dates; a month is never widened to a day, and an undated entry is never given
    a neighbour's date.

    This field's comment used to say "ISO-8601 where parseable, else verbatim"
    while stage 01 stored the verbatim text unparsed. Nothing read it, so nothing
    noticed, until the portfolio timeline needed to sort by it.

    `date_verbatim` and `date_verbatim_fr` are each page's own wording of the
    date, so the French interface shows "19 mai, 2026" as the French page wrote
    it rather than an English date inside a French sentence.
    """

    date: str
    date_verbatim: str
    body: Text
    date_verbatim_fr: str = ""


@dataclass(frozen=True, slots=True)
class Site:
    """
    One mapped location belonging to a project.

    Most projects have exactly one. The North Coast Transmission Line has three
    — the dataset publishes "North Coast Transmission Line (Phase 1/2/3)" as
    three separately named point features that all link to one page.

    They are kept as three sites, and rendered as three pins, rather than being
    joined into a polyline. The three points do progress north-west along the
    line's general path, so a route could be drawn — but the source published
    discrete points with discrete names, not a route geometry, and connecting
    them would assert a corridor alignment the government did not state.
    """

    name: Text
    geometry: Geometry


@dataclass(frozen=True, slots=True)
class MediaRef:
    """
    One image, at the sizes the app actually uses.

    The federal heroes are full-resolution (~2 MB), which is neither committable
    nor loadable in a map pin, so stage 01 derives both variants and the record
    points at the derivatives. `source_url` keeps the original re-fetchable.
    """

    source_url: str
    thumb: str = ""                          # 96px circular — the map-pin headpiece
    web: str = ""                            # ~1400px — the project viewer
    role: str = "hero"                       # hero | extra
    alt: Text = field(default_factory=lambda: Text(en=""))


@dataclass(frozen=True, slots=True)
class Project:
    """
    One project referred to the Major Projects Office.

    Every text field is the government's wording. `sector` is theirs too (Mining,
    Energy, Electricity, Transport, Industrial, Infrastructure) and is distinct
    from the NAICS sector taxonomy in `registry/sectors.yaml` — the two are not
    the same vocabulary and are deliberately not joined.

    The identity key is `slug`, taken from the canonical page URL, because that
    is what the ArcGIS dataset and the scraped page agree on. Note the dataset
    publishes 20 features for 18 projects: the slug is unique per project but
    NOT per feature, so features are grouped into `sites` on the page link.
    """

    slug: str
    event_slug: str
    name: Text
    proponent: Text
    sector: str
    status: Text
    description: Text
    sites: tuple[Site, ...] = ()
    quick_facts: tuple[QuickFact, ...] = ()
    #: The page's own "Benefits" bullets, one entry per <li>, verbatim. Kept as
    #: a list rather than a paragraph because the list is the government's
    #: structure; see `atlas.sources.mpo._benefits`.
    benefits: tuple[Text, ...] = ()
    updates: tuple[Update, ...] = ()
    media: tuple[MediaRef, ...] = ()
    page_url: Text = field(default_factory=lambda: Text(en=""))
    sources: tuple[SourceRef, ...] = ()

    @property
    def hero(self) -> MediaRef | None:
        """The rendering that fronts this project's map pin, if there is one."""
        return next((m for m in self.media if m.role == "hero"), None)


# ── Sector series ──────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Series:
    """
    One economic time series, carrying its own identity.

    `code` is the StatCan classification code parsed out of the industry label —
    `Manufacturing [31-33]` yields `31-33` — and is the join key across GDP,
    employment and revenue tables. `label` is the government's own wording, so
    the UI never invents a sector name.

    `release_time` and `retrieved_at` are both present because GDP is revised:
    two runs a month apart legitimately disagree about a recent month, and
    without the vintage stamped that reads as a bug rather than a revision.
    """

    code: str                                # NAICS 2-digit or StatCan T-code
    label: Text
    geo: str                                 # "CA" or a province/territory code
    measure: str                             # gdp_chained | gdp_current | employment | revenue | capex
    unit: str
    scalar: str                              # units | thousands | millions
    frequency: str                           # monthly | quarterly | annual
    periods: tuple[str, ...] = ()            # ISO dates, ascending
    values: tuple[float | None, ...] = ()    # None where the source is blank
    source_table: str = ""                   # StatCan 8-digit productId
    release_time: str = ""                   # the source's own release stamp
    provenance: Provenance = Provenance.OFFICIAL_DATASET

    def __post_init__(self) -> None:
        if len(self.periods) != len(self.values):
            raise ValueError(
                f"series {self.geo}/{self.code}/{self.measure}: "
                f"{len(self.periods)} periods but {len(self.values)} values"
            )


# ── Companies ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Company:
    """
    One index constituent.

    Deliberately NOT called a "top GDP contributor". Index weight is not output,
    and company revenue is gross output while GDP is value added — summing
    revenues within a sector overshoots that sector's GDP by roughly two to
    three times. `weight_pct` is also a *capped* index weight, so it understates
    the largest holdings. The UI labels this panel as market data throughout.
    """

    ticker: str
    name: str
    gics_sector: str
    naics_codes: tuple[str, ...] = ()        # via registry/gics_naics.yaml; lossy by nature
    weight_pct: float | None = None
    shares: float | None = None
    price: float | None = None
    currency: str = "CAD"
    provenance: Provenance = Provenance.MARKET_DATA


# ── Trade corridors ────────────────────────────────────────────────────────────

class CorridorNodeKind(str, Enum):
    """
    What a corridor node is.

    An open enum, so CLAUDE.md §2b applies in full: anything that renders these
    decides exhaustively, never by a pair of filters. `Globe.tsx` gets a typed
    layer table keyed on this rather than one `filter` per kind, because a third
    kind added to a filter pair renders nothing and raises nothing.
    """

    PORT            = "port"
    BORDER_CROSSING = "border_crossing"


@dataclass(frozen=True, slots=True)
class CorridorMode:
    """
    One transport mode inside a corridor's infrastructure list, verbatim.

    Transport Canada publishes each corridor's infrastructure as Marine / Rail /
    Road / Air with a bulleted list under each. Both the label and the bullets
    are the government's wording — this is where "what IS this corridor" is
    actually answered, and it is reproduced rather than summarised.

    `items` is a list of `Text` rather than one blob for the same reason the MPO
    benefits are: the list is the source's own structure, and flattening it runs
    four modes into a paragraph the page never published.
    """

    label: Text
    items: tuple[Text, ...] = ()


@dataclass(frozen=True, slots=True)
class CorridorNode:
    """A port or border crossing on a corridor. Always a POINT, so always anchored."""

    node_id: str
    kind: CorridorNodeKind
    name: Text
    geometry: Geometry


@dataclass(frozen=True, slots=True)
class TradeCorridor:
    """
    One of Transport Canada's national trade corridors.

    THERE ARE FIVE — Pacific, Prairie, Central, Atlantic and Northern — and they
    are NOT a partition of the provinces. The Northern Corridor is defined by
    latitude ("regions north of 55 degrees"), so it overlaps the four described
    by province. `overlaps_provinces` and `unmapped_note` carry that fact into
    the payload, because a corridor whose provincial coverage is partial and
    silent reads as complete.

    `description` and `modes` are Transport Canada's wording. `provinces`,
    `location_verbatim` and the node lists are OUR reading of it, which is why
    `provenance` defaults to DERIVED: the corridor's own words are reproduced,
    the joins around them are inference and must render differently.

    The statistics in TC's paragraph — $249 billion, 158 million tonnes, 55%
    crude by pipeline — are deliberately NOT fields. They stay in the paragraph
    (CLAUDE.md §1). The corridor's prose carries the numbers Transport Canada
    published; the charts carry the numbers StatCan published; nothing crosses.
    """

    corridor_id: str
    event_slug: str
    name: Text
    description: Text
    location_verbatim: Text
    provinces: tuple[str, ...]
    modes: tuple[CorridorMode, ...] = ()
    nodes: tuple[CorridorNode, ...] = ()
    overlaps_provinces: bool = False
    unmapped_note: Text = field(default_factory=lambda: Text(en=""))
    sources: tuple[SourceRef, ...] = ()
    provenance: Provenance = Provenance.DERIVED

    @property
    def ports(self) -> tuple[CorridorNode, ...]:
        return tuple(n for n in self.nodes if n.kind is CorridorNodeKind.PORT)

    @property
    def crossings(self) -> tuple[CorridorNode, ...]:
        return tuple(n for n in self.nodes if n.kind is CorridorNodeKind.BORDER_CROSSING)


# ── Geography: municipalities ──────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Municipality:
    """
    One census subdivision — the unit Statistics Canada publishes municipal
    figures for, and the identity later civic, fiscal and demographic data
    joins to.

    NOT A `City`. "City" is a legal status each province defines for itself.
    Halifax (439,819) is a Regional municipality, Oakville a Town, Saanich a
    District municipality; Greenwood, BC is a City of 702. A class keyed on that
    status would drop Halifax and keep Greenwood. So every subdivision is a
    record, `csd_type` carries the legal type as published, and "cities" is a
    filter a view applies.

    NOT ALWAYS A GOVERNMENT. 992 subdivisions are Indian reserves and others are
    unorganized territory: no council, no municipal budget. Where a local
    government exists it may be one tier of two. Fiscal records therefore attach
    to a separate local-government entity mapped onto subdivisions, never to
    this record — see docs/CIVIC-FISCAL.md.

    `csd_type` IS VERBATIM IN BOTH LANGUAGES, AND NOT ALWAYS TRANSLATED. The
    French file publishes "Town" for Ontario towns and "Réserve indienne" for
    reserves; the English file publishes "Ville" and "Municipalité" for Quebec.
    Where StatCan leaves a legal type in the language of the statute that
    created it, this record does too.

    Identity is `csd_uid` WITH `census_vintage`. Codes change between censuses
    when municipalities amalgamate or dissolve, and StatCan's 2018–2020 municipal
    finance tables use 2016 codes, so a bare seven-digit code is ambiguous
    across datasets. `geo_key` is the unambiguous form.

    Every measure is optional and None means NOT PUBLISHED — 63 incompletely
    enumerated reserves, and ranks where none applies. Zero is a published
    value: 268 subdivisions have no usual residents. `symbols` keeps StatCan's
    flag for every measure that has one — ".." not available, "..." not
    applicable, "r" revised, "E" use with caution — so the reason for a None
    and the quality of a value both survive. (A dict on a frozen dataclass:
    the record is comparable but not hashable, and nothing needs to hash it.)

    The percentage changes, density and ranks are StatCan's figures, not ours,
    so `provenance` is OFFICIAL_DATASET. SourceRefs live once on the payload
    rather than 5,161 times on the records.

    Not in the web bundle, so it has no mirror in `bundle.ts` yet (BACKLOG M11).
    """

    csd_uid: str                          # PR(2) CD(2) CSD(3), e.g. "1001186"
    dguid: str                            # "2021A0005" + csd_uid
    name: Text
    province: str                         # two-letter code, read from the uid
    census_division_uid: str              # csd_uid[:4]
    census_division_name: Text
    csd_type_abbr: str                    # "T", "IRI", ...
    csd_type: Text
    population_2021: int | None = None
    # The 2016 counts do NOT sum to the published 2016 province totals
    # (measured: NL, QC, ON differ). Never aggregate them upward.
    population_2016: int | None = None
    population_change_pct: float | None = None
    private_dwellings_2021: int | None = None
    private_dwellings_2016: int | None = None
    private_dwellings_change_pct: float | None = None
    occupied_dwellings_2021: int | None = None
    occupied_dwellings_2016: int | None = None
    occupied_dwellings_change_pct: float | None = None
    land_area_km2: float | None = None
    density_per_km2: float | None = None
    rank_national: int | None = None
    rank_provincial: int | None = None
    symbols: dict[str, str] = field(default_factory=dict)   # measure -> "..", "...", "r", "E", "r,E"
    census_vintage: str = "2021"
    source_table: str = ""
    provenance: Provenance = Provenance.OFFICIAL_DATASET

    @property
    def geo_key(self) -> str:
        """`csd:2021:1001186` — the code qualified by the census that issued it."""
        return f"csd:{self.census_vintage}:{self.csd_uid}"


# ── Transport ──────────────────────────────────────────────────────────────────

def to_jsonable(obj: Any) -> Any:
    """
    Recursively convert schema objects to JSON-safe primitives.

    Dataclasses that define their own `to_dict` are asked first — `Text`,
    `SourceRef` and `Geometry` have shapes the web app reads directly, and their
    own methods are the single definition of those shapes.

    Note this walks `__dataclass_fields__` with `getattr` rather than calling
    `dataclasses.asdict`. `asdict` recurses eagerly and would convert a nested
    `Text` to a plain dict before this function ever saw it, silently bypassing
    `Text.to_dict()` — so the one place the wire format is defined would stop
    being the place it is produced.
    """
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return obj.to_dict()
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(o) for o in obj]
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if hasattr(obj, "__dataclass_fields__"):
        return {f: to_jsonable(getattr(obj, f)) for f in obj.__dataclass_fields__}
    return obj
