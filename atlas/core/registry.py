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

        if e.get("kind") not in {"policy", "policy_with_projects"}:
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
        ))
    return tuple(out)


def strategy(slug: str) -> Strategy | None:
    return next((s for s in strategies() if s.slug == slug), None)
