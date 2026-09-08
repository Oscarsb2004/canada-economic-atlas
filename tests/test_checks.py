"""
Tests for the declarative verification layer.

These exercise `verify/`, which must not import `atlas` — so they import
`verify` and never both. `test_pipeline.py::test_verify_does_not_import_atlas`
enforces that rule mechanically; these check that the machinery it protects
actually works.

The point of each test is the failure it prevents, which is stated in its
docstring rather than left to the reader.
"""

from __future__ import annotations

from verify.checks import resolve, resolve_one
from verify.geo import distance_to_geometry_km, point_in_geometry

# A unit square with a square hole in the middle.
SQUARE_WITH_HOLE = {
    "type": "Polygon",
    "coordinates": [
        [[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]],
        [[4, 4], [4, 6], [6, 6], [6, 4], [4, 4]],
    ],
}


# ── The path language ──────────────────────────────────────────────────────────

def test_path_fans_out_over_arrays():
    """
    `[]` means "every element". Without it the registry would have to declare
    one path per site, which defeats the point of describing a shape rather
    than an instance.
    """
    record = {"sites": [{"geometry": {"n": 1}}, {"geometry": {"n": 2}}]}
    assert resolve(record, "sites[].geometry.n") == [1, 2]


def test_path_selects_an_array_element_by_field():
    """
    `expect_from` addresses a value inside another registry file. Selecting by
    field rather than by index is what stops the reference breaking when
    somebody reorders the events list.
    """
    doc = {"events": [{"slug": "a", "expected": {"n": 1}},
                      {"slug": "b", "expected": {"n": 2}}]}
    assert resolve_one(doc, "events[slug=b].expected.n") == 2


def test_unresolvable_path_returns_empty_rather_than_raising():
    """
    This is what lets one registry describe datasets that are not shaped alike.
    A dataset declaring no `geometry_path` must SKIP the geometry checks; if an
    absent path raised, every check would have to be guarded at the call site
    and the strategies dataset — which genuinely has no geometry — could not be
    declared at all.
    """
    assert resolve({"a": 1}, "b.c.d") == []
    assert resolve({}, "") == []
    assert resolve_one({"a": 1}, "nope") is None


def test_path_does_not_fan_out_over_a_missing_array():
    """A `[]` on a key that is not a list yields nothing, not a crash."""
    assert resolve({"sites": {"geometry": 1}}, "sites[].geometry") == []


# ── Geometry ───────────────────────────────────────────────────────────────────

def test_point_in_polygon_respects_holes():
    """
    Ring 0 is the exterior and the rest are holes. Ignoring holes makes a point
    in a large inland lake read as being on land — exactly the class of bad
    coordinate the containment gate exists to surface.
    """
    assert point_in_geometry((1, 1), SQUARE_WITH_HOLE)
    assert not point_in_geometry((5, 5), SQUARE_WITH_HOLE)
    assert not point_in_geometry((20, 20), SQUARE_WITH_HOLE)


def test_distance_is_zero_inside_and_positive_outside():
    """The tolerance in checks.yaml is meaningless if this is not monotone."""
    assert distance_to_geometry_km((1, 1), SQUARE_WITH_HOLE) == 0.0
    near = distance_to_geometry_km((10.1, 5), SQUARE_WITH_HOLE)
    far = distance_to_geometry_km((12.0, 5), SQUARE_WITH_HOLE)
    assert 0 < near < far


def test_longitude_is_scaled_by_latitude():
    """
    A degree of longitude is ~111 km at the equator and ~55 km at 60°N. Most of
    this country is north of 55, so ignoring the correction would roughly
    double every east-west distance — and a 30 km tolerance measured with a
    2x error is not a 30 km tolerance.
    """
    box = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}
    equator = distance_to_geometry_km((2.0, 0.5), box)

    high = {"type": "Polygon",
            "coordinates": [[[0, 60], [0, 61], [1, 61], [1, 60], [0, 60]]]}
    northern = distance_to_geometry_km((2.0, 60.5), high)

    assert northern < equator * 0.6


def test_a_point_inside_a_hole_measures_to_the_hole_edge():
    """
    A point in a hole is outside the polygon, and its distance to safety is the
    distance to the hole's rim — not to the far exterior. Walking only exterior
    rings would report a large distance for a point one step inside a lake.
    """
    d = distance_to_geometry_km((5, 5), SQUARE_WITH_HOLE)
    assert 0 < d < distance_to_geometry_km((5, 5), {
        "type": "Polygon", "coordinates": [[[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]]][:1],
    }) + 200
