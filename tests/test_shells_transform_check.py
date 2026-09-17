"""
Transform and check shells (atlas/shells/transform/, atlas/shells/check/, docs/REBUILD.md step S3).

Each test names the failure the shell exists to prevent. Where a shell can
refuse, one test shows it raising the caller's own error type, because that is
how the readers kept their error types and messages through the move.
"""

from __future__ import annotations

import pytest
from PIL import Image

from atlas.shells.check import join_distance, paired_values, partition_drift, verbatim_quotes
from atlas.shells.transform import absent_cells, crosswalk_sum, geo_distance, image_derive


class CallerError(ValueError):
    pass


# ── transform ────────────────────────────────────────────────────────────────

def test_a_derived_image_is_byte_identical_on_a_second_run(tmp_path):
    """A re-run must leave a zero-line diff (CLAUDE.md §6), so derivation is deterministic."""
    src = tmp_path / "src.png"
    Image.new("RGB", (300, 200), (30, 90, 160)).save(src)
    first = image_derive.derive(src, tmp_path / "a", "probe")
    second = image_derive.derive(src, tmp_path / "b", "probe")
    assert first == second
    assert first == ("/media/thumb/probe-hero.png", "/media/web/probe-hero.jpg")
    for url in first:
        rel = url.lstrip("/")  # the web app requests them from the site root
        assert (tmp_path / "a" / rel).read_bytes() == (tmp_path / "b" / rel).read_bytes()


def test_a_degree_of_latitude_is_about_111_km():
    km = geo_distance.great_circle_km((-75.0, 45.0), (-75.0, 46.0))
    assert 111.0 < km < 111.4
    assert geo_distance.great_circle_km((-75.0, 45.0), (-75.0, 45.0)) == 0
    assert km == geo_distance.great_circle_km((-75.0, 46.0), (-75.0, 45.0))


def test_absent_parts_are_zero_only_when_the_total_proves_it():
    assert absent_cells.proven_zero([10, 4, 6, None], where="X") == 1
    assert absent_cells.proven_zero([10, 4, 6], where="X") == 0
    # Negative control: 3 businesses are unaccounted for, so the blank is not zero.
    with pytest.raises(CallerError, match="X: 1 size range"):
        absent_cells.proven_zero([10, 4, 3, None], where="X", error=CallerError)


def test_a_member_mapped_twice_is_refused():
    """Counted in two sectors, a member would inflate both and only the grand total would show it."""
    assert crosswalk_sum.owners({"61": ["BS610", "GS610"]}, where="cube 1") == {"BS610": "61", "GS610": "61"}
    with pytest.raises(ValueError, match="cube 1: member GS610 is mapped to both 61 and 62"):
        crosswalk_sum.owners({"61": ["BS610", "GS610"], "62": ["GS610"]}, where="cube 1")


def test_a_sum_with_a_missing_member_is_missing():
    """Summing the published members and skipping a blank one reports part of a sector as all of it."""
    assert crosswalk_sum.total([1.5, 2.5]) == 4.0
    assert crosswalk_sum.total([1.5, None]) is None


# ── check ────────────────────────────────────────────────────────────────────

def test_a_join_raises_the_callers_error():
    near = [(-73.0, 45.0)]
    assert join_distance.nearest_km(near, [(-73.1, 45.0)], max_km=25, accept_without_coordinates=False,
                                    left="x", right="inventory 1", right_name="Mine") < 25
    with pytest.raises(CallerError, match="x -> inventory 1 \\('Mine'\\): nearest point"):
        join_distance.nearest_km(near, [(-75.0, 45.0)], max_km=25, accept_without_coordinates=False,
                                 left="x", right="inventory 1", right_name="Mine", error=CallerError)
    assert join_distance.nearest_km([], [(-73.0, 45.0)], max_km=25, accept_without_coordinates=True,
                                    left="x", right="inventory 1", right_name="Mine") is None


def test_drift_is_read_at_the_latest_period_all_publish():
    """The newest total has no parts yet; aligning by position would compare it with last month's parts."""
    total = {"2026-04": 50.0, "2026-05": 100.0, "2026-06": 110.0}
    goods = {"2026-04": 20.0, "2026-05": 30.0}
    services = {"2026-04": 30.0, "2026-05": 70.5}
    period, drift = partition_drift.latest_drift(total, [goods, services])
    # Two periods are complete; the answer is the later one, not the first found.
    assert period == "2026-05" and drift == pytest.approx(0.5)
    assert partition_drift.latest_drift({"2026-05": None}, [{"2026-05": 1.0}]) is None


def test_a_quote_on_the_wrong_page_raises_the_callers_error():
    pages = ["Summary", "The main risks include tariffs."]
    quote = [{"page": 2, "kind": "risk", "text": "The main risks include tariffs."}]
    verbatim_quotes.check(quote, pages=pages, text=None, where="BC")
    with pytest.raises(CallerError, match="BC: quote not found on page 1"):
        verbatim_quotes.check([{**quote[0], "page": 1}], pages=pages, text=None, where="BC", error=CallerError)
    with pytest.raises(verbatim_quotes.QuoteError, match="page 3 is not in the document"):
        verbatim_quotes.check([{**quote[0], "page": 3}], pages=pages, text=None, where="BC")


def test_a_blank_against_a_figure_is_a_disagreement():
    """French unrounded against English rounded is agreement; a blank against a figure never is."""
    assert paired_values.first_disagreement([[1.0, 2.0]], [[1.4, 2.0]], 1.0) is None
    assert paired_values.first_disagreement([[1.0, None]], [[1.0, 0.0]], 1.0) == (0, 1, None, 0.0)
    assert paired_values.first_disagreement([[1.0], [5.0]], [[1.0], [7.5]], 1.0) == (1, 0, 5.0, 7.5)
