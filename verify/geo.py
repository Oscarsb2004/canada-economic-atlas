"""
verify.geo — the geometry checks, written from scratch on purpose.

THIS MODULE MUST NOT IMPORT `atlas`. See `verify/run.py`.

The pipeline never computes geometry: coordinates arrive from the government's
own ArcGIS service and are stored unchanged. So there is no pipeline code here
to disagree with — what this module exists to catch is a coordinate that is
WRONG AT SOURCE, or one that our join attached to the wrong record.

WHY THE TOLERANCE IS NOT OPTIONAL

The committed boundaries are Statistics Canada's **cartographic** file, whose
own description is "major land mass, no coastal water". Marine infrastructure
is therefore outside every province by construction, not by error:

    Roberts Bank   a causeway terminal built out into the Strait of Georgia
    Contrecoeur    a container terminal on the St. Lawrence
    Grays Bay      a port, in a bay
    Ksi Lisims     a floating LNG facility

A containment check with no tolerance flags all four and reports a data problem
that does not exist — and a checker that cries wolf on four of nineteen points
is a checker nobody reads. The tolerance is declared per dataset in
`registry/checks.yaml`, so a future event whose sites are all inland can set it
to zero and get a stricter check without touching this file.

Distances use an equirectangular approximation with the latitude correction
applied at the point being measured. Over the tens of kilometres this is used
for, the error against a proper geodesic is metres — and the alternative,
carrying a projection library into a package whose whole purpose is to have no
shared machinery with the pipeline, costs more than it buys.
"""

from __future__ import annotations

import math

#: Mean Earth radius, km. WGS84's semi-major axis differs by ~0.3%, which is
#: three orders of magnitude below the tolerances this feeds.
EARTH_RADIUS_KM = 6371.0

Point = tuple[float, float]


def rings_of(geometry: dict) -> list[list[list[Point]]]:
    """Every polygon in a Polygon or MultiPolygon, as a list of ring lists."""
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if kind == "MultiPolygon":
        return coords
    if kind == "Polygon":
        return [coords]
    return []


def point_in_ring(pt: Point, ring: list[Point]) -> bool:
    """
    Ray casting, counting crossings of a horizontal ray to the east.

    Deliberately not a library call. A point exactly on an edge is undefined
    here and that is acceptable: nothing this checks sits on a boundary to
    within floating point, and pretending otherwise would add a tolerance
    argument to a predicate that should stay a predicate.
    """
    x, y = pt
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def point_in_geometry(pt: Point, geometry: dict) -> bool:
    """
    True when `pt` is inside the geometry, holes excluded.

    Ring 0 of each polygon is the exterior and the rest are holes — the GeoJSON
    rule. Honouring holes matters here: without it a point in a large inland
    lake reads as being on land, which is exactly the class of error this is
    meant to surface.
    """
    for polygon in rings_of(geometry):
        if not polygon:
            continue
        if point_in_ring(pt, polygon[0]) and not any(
            point_in_ring(pt, hole) for hole in polygon[1:]
        ):
            return True
    return False


def _segment_distance_km(pt: Point, a: Point, b: Point) -> float:
    """Shortest distance from `pt` to segment `a`-`b`, in km."""
    # Project to a local plane: degrees of longitude shrink with latitude, and
    # ignoring that overstates east-west distance by a factor of 2 at 60°N —
    # which is most of this country.
    lat_scale = math.cos(math.radians(pt[1]))
    deg_km = math.radians(1.0) * EARTH_RADIUS_KM

    px, py = pt[0] * lat_scale, pt[1]
    ax, ay = a[0] * lat_scale, a[1]
    bx, by = b[0] * lat_scale, b[1]

    dx, dy = bx - ax, by - ay
    if dx == 0.0 and dy == 0.0:
        t = 0.0
    else:
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy) * deg_km


def distance_to_geometry_km(pt: Point, geometry: dict) -> float:
    """
    Distance from `pt` to the nearest edge of `geometry`; 0.0 when inside.

    Every ring is walked, holes included: a point inside a hole is outside the
    polygon, and its distance to safety is the distance to the hole's edge.
    """
    if point_in_geometry(pt, geometry):
        return 0.0
    best = float("inf")
    for polygon in rings_of(geometry):
        for ring in polygon:
            for i in range(len(ring) - 1):
                best = min(best, _segment_distance_km(pt, ring[i], ring[i + 1]))
    return best


def containing_features(pt: Point, features: list[dict]) -> list[dict]:
    """Every feature whose geometry contains `pt`. Usually one; never assumed."""
    return [f for f in features if point_in_geometry(pt, f.get("geometry") or {})]
