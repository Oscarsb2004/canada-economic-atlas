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
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "coordinates": [list(c) for c in self.coordinates],
            "provinces": list(self.provinces),
            "location_verbatim": self.location_verbatim,
            "approximate": self.approximate,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Geometry:
        return cls(
            kind=GeometryKind(d["kind"]),
            coordinates=tuple((float(c[0]), float(c[1])) for c in d.get("coordinates", [])),
            provinces=tuple(d.get("provinces", ())),
            location_verbatim=d.get("location_verbatim", ""),
            approximate=d.get("approximate", True),
        )


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
    """One dated entry from a project page's "Latest updates" block."""

    date: str                                # ISO-8601 where parseable, else verbatim
    date_verbatim: str
    body: Text


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
