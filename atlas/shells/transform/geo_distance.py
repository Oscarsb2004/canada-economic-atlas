"""
atlas.shells.transform.geo_distance — the distance between two [lon, lat] points.

(Moved from atlas/sources/mpi.py in step S3 of docs/REBUILD.md; unchanged in
behaviour. Card: registry/shells/geo_distance.yaml.)

Great-circle distance on a spherical Earth, which is what holding a join to
geography needs: tens of kilometres, not survey precision. The corridor
midpoint's planar measure stays with the record that uses it
(`atlas.core.schema.Geometry`), because core code does not depend on shells.
"""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0


def great_circle_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two [lon, lat] points (haversine)."""
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))
