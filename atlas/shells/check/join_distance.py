"""
atlas.shells.check.join_distance — hold a declared join to geography.

(Taken from atlas/readers/mpi.py in step S3 of docs/REBUILD.md; unchanged in
behaviour. Card: registry/shells/join_distance.yaml.)

Two records are joined by an ID someone declared, never by name, because names
disagree even when the thing is the same. The declaration is then checked
against where the two records say they are: the nearest pair of points must be
within a limit, unless a waiver is declared — and a waiver the distance does
not need is refused too, so none outlives its reason.
"""

from __future__ import annotations

from atlas.shells.transform.geo_distance import great_circle_km


class JoinError(ValueError):
    """A declared join does not hold against geography."""


def nearest_km(points: list[tuple[float, float]] | tuple[tuple[float, float], ...],
               anchors: list[tuple[float, float]], *, max_km: float, accept_without_coordinates: bool,
               left: str, right: str, right_name: str, accept_km: float | None = None,
               error: type[Exception] = JoinError) -> float | None:
    """
    The distance that justifies the join, rounded to 10 m, or None where none can be measured.

    `left` names the record the join starts from, `right` the record it points
    at, and `right_name` that record's own name, for the messages.
    """
    if not points:
        if not accept_without_coordinates:
            raise error(
                f"{left} -> {right}: the inventory publishes no coordinate, "
                f"so the join cannot be checked. Declare accept_without_coordinates if it stands."
            )
        return None
    if not anchors:
        raise error(f"{left}: the MPO project has no anchor to measure the join against")
    nearest = min(great_circle_km(p, a) for p in points for a in anchors)
    if accept_km is not None:
        if nearest <= max_km:
            raise error(
                f"{left} -> {right}: declares a distance waiver, but the nearest "
                f"point is {nearest:.2f} km, within the {max_km} km limit. Remove the waiver."
            )
        max_km = accept_km
    if nearest > max_km:
        raise error(
            f"{left} -> {right} ({right_name!r}): nearest point is "
            f"{nearest:.2f} km from the MPO site, over the {max_km} km limit"
        )
    return round(nearest, 2)
