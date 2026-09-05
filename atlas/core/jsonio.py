"""
atlas.core.jsonio — write JSON only when the content actually changed.

Every pipeline stage needs the same thing: serialise a payload, but leave the
file alone if nothing meaningful moved, so that re-running a stage against
unchanged sources produces a zero-line git diff. That guarantee is the project's
acceptance test for every stage.

This lived as a near-identical private copy in all four stages, and the copies
had already drifted: stage 01 ignored both `generated_at` and `retrieved_at`
when comparing, while 02, 03 and 04 ignored only `generated_at`. The drift was
harmless in practice but it is exactly the kind of thing that makes a future
"why did this file rewrite?" unanswerable. One implementation, one rule.

THE RULE

`generated_at` and `retrieved_at` are excluded from the comparison. Both move on
every run regardless of content, so including them would rewrite the file every
time and defeat the whole mechanism. Excluding them also gives the stored
timestamps a better meaning: they record when the content was last seen to
CHANGE, not when the scraper last ran.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: Keys that move on every run no matter what the source said.
VOLATILE_KEYS = frozenset({"generated_at", "retrieved_at"})


def strip_volatile(obj: Any) -> Any:
    """A copy of `obj` with every volatile key removed, at any depth."""
    if isinstance(obj, dict):
        return {k: strip_volatile(v) for k, v in obj.items() if k not in VOLATILE_KEYS}
    if isinstance(obj, list):
        return [strip_volatile(v) for v in obj]
    return obj


def write_if_changed(path: Path, payload: dict) -> bool:
    """
    Write `payload` to `path` only if its non-volatile content differs.

    Returns True when the file was written. A malformed or unreadable existing
    file counts as "different" and is overwritten, because the alternative is
    refusing to repair a corrupt output.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            existing = None
        if existing is not None and strip_volatile(existing) == strip_volatile(payload):
            return False

    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return True
