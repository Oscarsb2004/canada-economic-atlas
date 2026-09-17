"""
Acquire shells (atlas/shells/acquire/, docs/REBUILD.md step S2).

A request is recorded by its exact URL, so the URL tests below pin strings the
golden master actually recorded from the legacy pipeline: a shell that builds a
different URL would fetch something the recording never saw.
"""

from __future__ import annotations

import json

import pytest

from atlas.shells.acquire import arcgis_layer, commons_media, document_text, statcan_table, valet_series, workbook_edition

MPO = "https://maps-cartes.services.geo.ca/server_serveur/rest/services/NRCan/projects_referred_to_mpo_en/MapServer"
MPI = "https://maps-cartes.services.geo.ca/server_serveur/rest/services/NRCan/major_projects_inventory_en/MapServer/0"


# ── arcgis_layer ─────────────────────────────────────────────────────────────

def test_the_two_query_forms_are_the_recorded_urls():
    """Both forms, verbatim from verify/golden/legacy-v1/inputs.json: `*` literal in one, escaped in the other."""
    assert arcgis_layer.geojson_query_url(MPO, 1) == (
        MPO + "/1/query?where=1%3D1&outFields=*&returnGeometry=true&outSR=4326&f=geojson")
    assert arcgis_layer.attributes_query_url(MPO, 2) == (
        MPO + "/2/query?where=1%3D1&outFields=*&returnGeometry=false&f=json")
    assert arcgis_layer.page_query_url(MPI, 0, 1000) == (
        MPI + "/query?where=1%3D1&outFields=%2A&returnGeometry=true&outSR=4326"
        "&orderByFields=OBJECTID+ASC&resultOffset=0&resultRecordCount=1000&f=json")


def _pages(*pages: dict):
    bodies = {arcgis_layer.page_query_url(MPI, offset, 2): json.dumps(page).encode()
              for offset, page in zip((0, 2, 4), pages)}
    asked: list[str] = []

    def get(url: str) -> bytes:
        asked.append(url)
        return bodies[url]

    return get, asked


def test_pages_are_read_until_a_short_page():
    get, asked = _pages({"features": [{"a": 1}, {"a": 2}]}, {"features": [{"a": 3}]})
    features, raw = arcgis_layer.fetch_pages(get, MPI, 2)
    assert [f["a"] for f in features] == [1, 2, 3]
    assert len(asked) == 2
    assert raw.count(b"features") == 2  # the hash covers every page, not the last one


def test_a_full_last_page_is_followed_by_one_more_request():
    """Exactly `page_size` features may not be the end; the empty page after it is."""
    get, asked = _pages({"features": [{"a": 1}, {"a": 2}]}, {"features": []})
    features, _ = arcgis_layer.fetch_pages(get, MPI, 2)
    assert len(features) == 2 and len(asked) == 2


def test_a_bad_page_raises_the_callers_error():
    """Negative control: a caller that passes its own error type gets that type, with the same message."""
    class InventoryLike(ValueError):
        pass

    get, _ = _pages({"error": {"code": 500}})
    with pytest.raises(InventoryLike, match="the service returned an error"):
        arcgis_layer.fetch_pages(get, MPI, 2, error=InventoryLike)
    get, _ = _pages({"features": [], "exceededTransferLimit": True})
    with pytest.raises(arcgis_layer.LayerError, match="returned none"):
        arcgis_layer.fetch_pages(get, MPI, 2)


# ── statcan_table and valet_series ───────────────────────────────────────────

class _Json:
    def __init__(self):
        self.asked: list[str] = []

    def json(self, url: str):
        self.asked.append(url)
        return {"url": url}


def test_the_cube_list_is_one_request_to_its_endpoint():
    fetch = _Json()
    statcan_table.cube_list(fetch)
    assert fetch.asked == ["https://www150.statcan.gc.ca/t1/wds/rest/getAllCubesListLite"]


def test_a_valet_series_is_asked_for_its_latest_observation():
    fetch = _Json()
    base = "https://www.bankofcanada.ca/valet/observations"
    valet_series.latest(fetch, base, "V39079")
    assert fetch.asked == [base + "/V39079/json?recent=1"]
    assert valet_series.series_url(base, "V39079") == base + "/V39079/json"


# ── document_text ────────────────────────────────────────────────────────────

def test_normalising_twice_changes_nothing():
    once = document_text.normalise("The /f_iscal  plan ’s tariﬀs , per cent .")
    assert once == "The fiscal plan 's tariffs, per cent."
    assert document_text.normalise(once) == once


def test_an_html_fragment_loses_its_tags_and_entities():
    assert document_text.strip_tags("<p>Ad&nbsp;mari <b>usque</b>\n ad mare</p>") == "Ad mari usque ad mare"


# ── workbook_edition and commons_media ───────────────────────────────────────

def test_no_edition_raises_the_default_error():
    template = {"en": "https://x/{year}-{yy}-en.xlsx", "fr": "https://x/{year}-{yy}-fr.xlsx"}
    with pytest.raises(workbook_edition.EditionError, match="between 2024 and 2025"):
        workbook_edition.latest(lambda url: None, template, 2025, 2024)


def test_more_than_fifty_titles_are_refused():
    with pytest.raises(commons_media.MediaError, match="at most 50"):
        commons_media.query_url("https://commons.test/api.php", [f"File:{i}.svg" for i in range(51)], 240)
