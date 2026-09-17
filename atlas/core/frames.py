"""
atlas.core.frames — the envelope every dataset is also written in (docs/REBUILD.md §2.2).

A frame is a body plus a manifest. The body is one JSON object per line. The
manifest says which profile the frame follows, which columns it has, and what
ROLE each column plays — entity, time, measure, category, slice, status, label,
source reference — so a program that has never seen the dataset can still
render it, and so a frame can be checked against its profile rather than
trusted.

Frames are written under build/frames/ and never committed. The published files
the web app reads are unchanged; a frame is a second, general description of
the same records, and the shape the atlas would bring to Athena Data. (Athena's
own design stores bodies as Parquet; JSON lines keep this project free of a new
dependency, and moving between the two changes the bytes, not the contract.)
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Every role a column may play.
ROLES = frozenset({"entity", "time", "measure", "category", "slice", "status", "label", "source_ref", "attribute"})

#: The roles each profile requires.
PROFILES = {
    "panel": frozenset({"entity", "time", "measure"}),
    "cross-section": frozenset({"entity", "measure"}),
    "places": frozenset({"entity", "label"}),
    "passages": frozenset({"entity", "label", "source_ref"}),
}


class FrameError(ValueError):
    """A frame does not meet its own manifest."""


@dataclass(frozen=True, slots=True)
class Column:
    name: str
    type: str       # "string" | "number" | "integer"
    role: str
    unit: str = ""


#: The columns of an observation frame, in `records.Observation` order.
OBSERVATION_COLUMNS = (
    Column("entity", "string", "entity"),
    Column("category", "string", "category"),
    Column("period", "string", "time"),
    Column("measure", "string", "attribute"),
    Column("value", "number", "measure"),
    Column("unit", "string", "attribute"),
    Column("scalar", "string", "attribute"),
    Column("slice", "string", "slice"),
    Column("status", "string", "status"),
    Column("release", "string", "source_ref"),
    Column("source_table", "string", "source_ref"),
    Column("provenance", "string", "status"),
)
OBSERVATION_KEYS = ("entity", "category", "period", "measure", "slice")

PLACE_COLUMNS = (
    Column("key", "string", "entity"),
    Column("kind", "string", "attribute"),
    Column("name_en", "string", "label"),
    Column("name_fr", "string", "label"),
    Column("parent", "string", "attribute"),
    Column("vintage", "string", "time"),
    Column("type_code", "string", "category"),
    Column("type_en", "string", "label"),
    Column("type_fr", "string", "label"),
    Column("source_table", "string", "source_ref"),
)
PLACE_KEYS = ("key",)

PASSAGE_COLUMNS = (
    Column("entity", "string", "entity"),
    Column("kind", "string", "category"),
    Column("text_en", "string", "label"),
    Column("text_fr", "string", "label"),
    Column("source_url", "string", "source_ref"),
    Column("locator", "string", "source_ref"),
    Column("content_sha256", "string", "source_ref"),
    Column("provenance", "string", "status"),
)
PASSAGE_KEYS = ("entity", "kind", "locator", "text_en")

PASSAGE_COLUMNS = (
    Column("entity", "string", "entity"),
    Column("kind", "string", "category"),
    Column("text_en", "string", "label"),
    Column("text_fr", "string", "label"),
    Column("source_url", "string", "source_ref"),
    Column("locator", "string", "source_ref"),
    Column("content_sha256", "string", "source_ref"),
    Column("provenance", "string", "status"),
)
PASSAGE_KEYS = ("entity", "kind", "locator", "text_en")

_TYPES = {"string": (str,), "number": (int, float), "integer": (int,)}


@dataclass(slots=True)
class Frame:
    dataset: str
    name: str
    profile: str
    record_type: str
    keys: tuple[str, ...]
    columns: tuple[Column, ...]
    rows: list[dict[str, Any]]
    published: tuple[str, ...] = ()
    checks: tuple[str, ...] = ()
    notes: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """Raise unless the rows meet the manifest: roles, columns, types, and unique keys."""
        if self.profile not in PROFILES:
            raise FrameError(f"{self.dataset}/{self.name}: unknown profile {self.profile!r}")
        roles = {c.role for c in self.columns}
        unknown = roles - ROLES
        if unknown:
            raise FrameError(f"{self.dataset}/{self.name}: unknown roles {sorted(unknown)}")
        missing = PROFILES[self.profile] - roles
        if missing:
            raise FrameError(f"{self.dataset}/{self.name}: profile {self.profile} needs roles {sorted(missing)}")
        names = [c.name for c in self.columns]
        if not set(self.keys) <= set(names):
            raise FrameError(f"{self.dataset}/{self.name}: keys {self.keys} are not all columns")
        seen: set[tuple] = set()
        for i, row in enumerate(self.rows):
            if list(row) != names:
                raise FrameError(f"{self.dataset}/{self.name}: row {i} has columns {list(row)}, not {names}")
            for c in self.columns:
                v = row[c.name]
                if v is not None and (not isinstance(v, _TYPES[c.type]) or isinstance(v, bool)):
                    raise FrameError(f"{self.dataset}/{self.name}: row {i} {c.name}={v!r} is not {c.type}")
            key = tuple(row[k] for k in self.keys)
            if key in seen:
                raise FrameError(f"{self.dataset}/{self.name}: duplicate key {key}")
            seen.add(key)

    def manifest(self) -> dict[str, Any]:
        entity = next(c.name for c in self.columns if c.role == "entity")
        time = next((c.name for c in self.columns if c.role == "time"), None)
        releases = sorted({r["release"] for r in self.rows if r.get("release")})
        provenance = Counter(r.get("provenance", "") for r in self.rows if r.get("provenance"))
        return {
            "schema": "atlas.frame/v1",
            "dataset": self.dataset,
            "name": self.name,
            "profile": self.profile,
            "record_type": self.record_type,
            "keys": list(self.keys),
            "columns": [{"name": c.name, "type": c.type, "role": c.role, "unit": c.unit} for c in self.columns],
            "rows": len(self.rows),
            "coverage": {
                "entities": len({r[entity] for r in self.rows}),
                "periods": sorted({r[time] for r in self.rows}) if time else [],
                "missing_values": sum(1 for r in self.rows for c in self.columns if c.role == "measure" and r[c.name] is None),
            },
            "releases": releases,
            "provenance": dict(sorted(provenance.items())),
            "published": list(self.published),
            "checks": list(self.checks),
            "notes": self.notes,
        }


def write(frame: Frame, root: Path) -> tuple[Path, Path]:
    """Validate, then write `<root>/<dataset>/<name>.jsonl` and its `.manifest.json`, deterministically."""
    frame.validate()
    folder = Path(root) / frame.dataset
    folder.mkdir(parents=True, exist_ok=True)
    body = folder / f"{frame.name}.jsonl"
    rows = sorted(frame.rows, key=lambda r: tuple("" if r[k] is None else str(r[k]) for k in frame.keys))
    with body.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n")
    manifest = folder / f"{frame.name}.manifest.json"
    manifest.write_text(json.dumps(frame.manifest(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8", newline="\n")
    return body, manifest
