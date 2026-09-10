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

import json
import math

import pytest
import yaml

from verify import checks
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

    The expected value is now stated. The earlier version compared against
    `distance((5, 5), exterior-only square) + 200` — but (5, 5) is INSIDE that
    square, so the right-hand side was the constant 200 dressed up as a second
    measurement. It happened to separate the rim (~111 km) from the exterior
    (~553 km), and it read as a comparison it was not.
    """
    d = distance_to_geometry_km((5, 5), SQUARE_WITH_HOLE)
    one_degree_of_longitude_at_5n = math.radians(1) * 6371 * math.cos(math.radians(5))
    assert d == pytest.approx(one_degree_of_longitude_at_5n, rel=0.01)


# ── Check kinds ────────────────────────────────────────────────────────────────

CTX = {"name": "probe", "dataset": {"id_field": "id"}, "regions": {}}


def test_zero_is_present_and_blank_is_not():
    """
    `fields_present` tested truthiness, so 0 read as missing. The municipalities
    dataset has 268 subdivisions with a population of exactly zero, and a
    presence gate on that field would have failed all 268 while every one was
    right. Presence asks whether a value was published, not what it is.
    """
    spec = {"fields": ["population", "flag", "name.en"]}
    ok, _, detail = checks.check_fields_present(
        [{"id": "a", "population": 0, "flag": False, "name": {"en": "Nowhere"}}], spec, CTX)
    assert ok, detail

    missing = [
        {"id": "none", "population": None, "flag": True, "name": {"en": "x"}},
        {"id": "blank", "population": 1, "flag": True, "name": {"en": "  "}},
        {"id": "absent", "flag": True, "name": {"en": "x"}},
    ]
    ok, _, detail = checks.check_fields_present(missing, spec, CTX)
    assert not ok
    assert all(f"'{i}." in detail for i in ("none", "blank", "absent"))


def test_unique_ids_names_duplicates_and_records_with_no_id():
    """
    A record with no id is not a duplicate, so it used to pass. With two of
    them the check sorted None against strings, raised TypeError, and reported
    that the check had crashed rather than which records were wrong.
    """
    records = [{"id": "a"}, {"id": "a"}, {"id": "b"}, {}, {"id": None}]
    ok, _, detail = checks.check_unique_ids(records, {}, CTX)
    assert not ok
    assert "duplicated: ['a']" in detail
    assert "2 records have no id" in detail

    ok, _, _ = checks.check_unique_ids([{"id": "a"}, {"id": "b"}], {}, CTX)
    assert ok


SUM_SPEC = {"group_field": "province", "value_field": "pop",
            "totals_path": "province_totals", "tolerance": 0}
TOWNS = [
    {"id": "a", "province": "NL", "pop": 10},
    {"id": "b", "province": "NL", "pop": 20},
    {"id": "c", "province": "NL", "pop": None},   # not published: skipped
    {"id": "d", "province": "PE", "pop": 0},      # published as zero: counted
    {"id": "e", "province": "PE", "pop": 5},
]


def _totals(totals: dict) -> dict:
    return {**CTX, "document": {"province_totals": totals}}


def test_components_sum_to_the_published_totals():
    """
    The identity that holds exactly on the 2021 census table: every province's
    published population is the sum of its subdivisions. An unpublished value
    is skipped rather than crashing the sum or failing the check.
    """
    ok, label, detail = checks.check_sums_to_published_totals(
        TOWNS, SUM_SPEC, _totals({"NL": {"pop": 30}, "PE": {"pop": 5}}))
    assert ok, detail
    assert "all 2 province groups" in label


def test_a_misfiled_record_fails_the_sum_though_the_count_is_right():
    """
    Moving one subdivision to the wrong province changes no record count and no
    field — it changes two provincial sums. That is the failure this check
    exists for, and `record_count` cannot see it.
    """
    misfiled = [dict(t, province="PE") if t["id"] == "b" else t for t in TOWNS]
    ok, _, detail = checks.check_sums_to_published_totals(
        misfiled, SUM_SPEC, _totals({"NL": {"pop": 30}, "PE": {"pop": 5}}))
    assert not ok
    assert "NL: components sum to 10 against a published 30" in detail
    assert "PE: components sum to 25 against a published 5" in detail


def test_a_group_on_one_side_only_fails_the_sum():
    """
    A province with records and no published total, or a total with no
    records, is a join that went wrong. Comparing only the groups both sides
    share would pass it.
    """
    ok, _, detail = checks.check_sums_to_published_totals(
        TOWNS + [{"id": "x", "province": "XX", "pop": 1}], SUM_SPEC,
        _totals({"NL": {"pop": 30}, "PE": {"pop": 5}, "NU": {"pop": 9}}))
    assert not ok
    assert "XX: records with no published total" in detail
    assert "NU: a published total with no records" in detail


# ── The runner ─────────────────────────────────────────────────────────────────

class _Report:
    """Stands in for `verify.run.Report`, recording what the runner decided."""

    def __init__(self):
        self.gates: list[tuple[bool, str, str]] = []
        self.notes: list[str] = []

    def gate(self, ok, label, detail=""):
        self.gates.append((ok, label, detail))

    def note(self, label):
        self.notes.append(label)


def _run(root, monkeypatch, document, **dataset_extra):
    """Run the declared-check runner against a one-dataset registry under `root`."""
    registry = root / "registry"
    registry.mkdir(parents=True)
    dataset = {"path": "probe.json", "records": "items", "id_field": "id",
               "checks": [{"kind": "unique_ids", "severity": "gate"}], **dataset_extra}
    (registry / "checks.yaml").write_text(
        yaml.safe_dump({"datasets": {"probe": dataset}}), encoding="utf-8")
    (root / "probe.json").write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(checks, "ROOT", root)
    monkeypatch.setattr(checks, "REGISTRY", registry)
    report = _Report()
    checks.run_declared_checks(report)
    return report


def test_a_renamed_records_key_fails_instead_of_passing_every_check(tmp_path, monkeypatch):
    """
    The runner read records with `.get(key, [])`. A stage that renamed its array
    — `items` to `itmes` — produced zero records, and every check asking "is
    anything wrong with these" passed on the empty list. Verify reported green
    over a file it had not read.
    """
    report = _run(tmp_path, monkeypatch, {"itmes": [{"id": "a"}]})
    assert [ok for ok, _, _ in report.gates] == [False]
    _, label, detail = report.gates[0]
    assert "'items'" in label and "missing" in detail and "itmes" in detail


def test_an_empty_dataset_fails_unless_declared_legitimate(tmp_path, monkeypatch):
    """An empty array is the same vacuous pass, so it needs saying out loud."""
    report = _run(tmp_path / "strict", monkeypatch, {"items": []})
    assert [ok for ok, _, _ in report.gates] == [False]

    allowed = _run(tmp_path / "allowed", monkeypatch, {"items": []}, allow_empty=True)
    assert [ok for ok, _, _ in allowed.gates] == [True]


def test_every_declared_check_is_implemented_and_every_reference_resolves():
    """
    Three registry typos that used to surface only when the whole verifier ran
    against real data: a misspelt kind; an `expect_from` path that resolves to
    nothing, which makes record_count compare against None; and a bare `ON` in
    an `allowed` list, which YAML reads as True.
    """
    doc = yaml.safe_load((checks.REGISTRY / "checks.yaml").read_text(encoding="utf-8"))
    for name, dataset in doc["datasets"].items():
        for spec in dataset.get("checks", []):
            assert spec["kind"] in checks.KINDS, f"{name}: unknown kind {spec['kind']!r}"
            if "expect_from" in spec:
                want = checks.resolve_registry(spec["expect_from"])
                assert isinstance(want, int) and want > 0, f"{name}: {spec['expect_from']} -> {want!r}"
            assert all(isinstance(a, str) for a in spec.get("allowed", [])), (
                f"{name}: {spec['kind']} has a non-string in `allowed` — quote it")
