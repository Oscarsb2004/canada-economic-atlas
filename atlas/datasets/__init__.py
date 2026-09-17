"""
atlas.datasets — the code each dataset card names (docs/REBUILD.md §3).

A card in registry/datasets/ says which builder makes a dataset: a function
here, `module:function`. A builder reads through the acquire shells, shapes
records, runs its checks, and RETURNS what it made. It never writes: the runner
(`atlas/run.py`) writes the published files, only when their content changed,
and the frames and receipts beside them. One writer is what makes "a re-run
leaves a zero-line diff" a property of the project rather than of each stage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from atlas.core.frames import Frame
from atlas.shells.acquire.fetcher import Fetcher


class Skipped(RuntimeError):
    """The builder decided not to produce this dataset this run; its committed output stays as it is."""


@dataclass(slots=True)
class Context:
    """What every builder in one run shares."""

    fetch: Fetcher
    refresh: bool = False
    #: Whatever `--set name=value` passed in: development aids, never anything
    #: a published figure depends on.
    options: dict[str, str] = field(default_factory=dict)
    #: Values one card leaves for a later card in the same run (the cube hashes).
    state: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Built:
    """What a builder made: published files, in their existing layouts, and frames describing them."""

    outputs: list[tuple[Path, dict[str, Any]]] = field(default_factory=list)
    #: (source, destination) pairs copied byte for byte rather than re-serialised,
    #: so a file that is already correct cannot change by being written again.
    copies: list[tuple[Path, Path]] = field(default_factory=list)
    frames: list[Frame] = field(default_factory=list)
    #: Named values for the receipt: what a reviewer checks the run by.
    receipt: dict[str, Any] = field(default_factory=dict)
