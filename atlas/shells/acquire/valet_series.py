"""
atlas.shells.acquire.valet_series — a Bank of Canada Valet series.

(Taken from pipeline/02_sectors.py in step S2 of docs/REBUILD.md; unchanged in
behaviour. Card: registry/shells/valet_series.yaml.)

Keyless. The list of groups is at /valet/lists/groups/json; /valet/groups/json
is a 404. Shaping the answer into a payload stays with the stage that knows
what it is for.
"""

from __future__ import annotations

from typing import Any

from atlas.shells.acquire.fetcher import Fetcher


def series_url(base: str, series: str) -> str:
    """The series' observations, as the payload cites them."""
    return f"{base}/{series}/json"


def latest(fetch: Fetcher, base: str, series: str) -> dict[str, Any]:
    """The service's answer for the most recent observation of `series`."""
    return fetch.json(f"{series_url(base, series)}?recent=1")
