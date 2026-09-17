"""
atlas.core.clock — the one place the pipeline asks what time it is.

Nine stages each carried their own copy of `_now()`. One definition means one
format for every timestamp the project writes, and one place the golden-master
harness (verify/golden.py) has to freeze for two runs to be compared byte for
byte.
"""

from __future__ import annotations

from datetime import datetime, timezone


def now() -> datetime:
    """The current moment, in UTC."""
    return datetime.now(timezone.utc)


def now_iso() -> str:
    """The current moment as the pipeline writes it: ISO 8601, UTC, second precision."""
    return now().strftime("%Y-%m-%dT%H:%M:%SZ")
