"""
Tests written to explain the failure they prevent.

Every case here corresponds to something that actually went wrong while
building this pipeline, or to a source quirk that fails SILENTLY — which is the
dangerous kind, because the output looks plausible and nothing raises.
"""

from __future__ import annotations

import ast
import csv
import importlib
import io
import sys
import zipfile
from pathlib import Path

import pytest
import yaml

from atlas.core import registry as R
from atlas.core.schema import (
    Geometry, GeometryKind, Municipality, Provenance, Series, SourceRef, Text, to_jsonable,
)
from atlas.sources import census
from atlas.sources import companies as C
from atlas.sources import mpo
from atlas.sources import statcan
from atlas.sources import tc_corridors as tc

ROOT = Path(__file__).resolve().parents[1]


# ── The doubled markup ─────────────────────────────────────────────────────────

DOUBLED_PAGE = """
<main property="mainContentOfPage">
  <h1>Test Project</h1>
  <section class="container gc-features">
    <div class="col-md-4 visible-md visible-lg"><h2>Proponent</h2>Acme</div>
    <div class="col-md-4 visible-xs visible-sm"><h2>Proponent</h2>Acme</div>
  </section>
  <section class="container">
    <div class="col-md-7">
      <div class="mwsbodytext visible-md visible-lg"><h2>Description</h2><p>A unique sentence.</p></div>
      <div class="mwsbodytext visible-xs visible-sm"><h2>Description</h2><p>A unique sentence.</p></div>
    </div>
    <div class="col-md-5">
      <div class="mwsbodytext"><h2>Quick facts</h2>
        <ul><li><strong>Economic impact: </strong>Will attract $5 billion.</li></ul>
      </div>
    </div>
  </section>
  <section class="container">
    <h3 class="h4">Benefits</h3>
    <ul class="lst-spcd">
      <li>First benefit.</li>
      <li>Second <abbr title="Small Modular Reactor">SMR</abbr> benefit.</li>
    </ul>
  </section>
</main>
"""


def test_desktop_mobile_twins_are_deduped():
    """
    canada.ca emits the feature cards and the whole Description TWICE — once in
    a `visible-md visible-lg` wrapper and once in `visible-xs visible-sm`. A
    naive get_text() returns every one of those fields twice, concatenated, and
    raises nothing.
    """
    page = mpo.parse_page(DOUBLED_PAGE, "http://x/test.html", lang="en")
    assert page.description.count("A unique sentence.") == 1
    assert page.proponent == "Acme"


def test_quick_facts_are_not_deduped_away():
    """
    The converse trap. Quick facts, Benefits and Latest updates are NOT doubled,
    so deduplicating by repeated text — rather than structurally — would delete
    real content instead of copies.
    """
    page = mpo.parse_page(DOUBLED_PAGE, "http://x/test.html", lang="en")
    assert len(page.quick_facts) == 1
    assert page.quick_facts[0].label == "Economic impact"
    # The dollar figure stays in its sentence. Parsing it into a number would be
    # this project making a claim in a form the source never used.
    assert "$5 billion" in page.quick_facts[0].body


def test_benefits_are_bullets_not_one_flattened_paragraph():
    """
    Benefits is published as a <ul>, and the list is the government's own
    structure. An earlier version read the block with get_text(" "), which ran
    every bullet into one paragraph AND left the heading word "Benefits" glued
    to the front of the first sentence — so the viewer would have shown prose
    the page never published as prose.

    The <abbr> is flattened to its visible text: the title attribute is a
    tooltip the template renders, not a sentence the government wrote.
    """
    page = mpo.parse_page(DOUBLED_PAGE, "http://x/test.html", lang="en")
    assert page.benefits == ["First benefit.", "Second SMR benefit."]
    assert not any(b.startswith("Benefits") for b in page.benefits)


def test_splitting_benefits_did_not_move_the_content_hash():
    """
    `verbatim_blob` decides whether a `data/history/` entry is appended, so it
    must flip when the GOVERNMENT changes the page and at no other time. Reading
    Benefits as a list instead of a string is a change in how we read, not in
    what was said, and hashing the new shape would have appended a spurious
    "content changed" entry to all 18 project histories on a day nothing
    changed. The blob therefore keeps hashing the flattened block.
    """
    page = mpo.parse_page(DOUBLED_PAGE, "http://x/test.html", lang="en")
    assert page.benefits_block_text == "Benefits First benefit. Second SMR benefit."
    assert page.benefits_block_text in page.verbatim_blob()


def test_benefits_falls_back_when_the_list_markup_goes_away():
    """
    A template that swaps the <ul> for paragraphs should degrade to one bullet,
    not to nothing — an empty Benefits list is indistinguishable from a page
    that has none, and the verify gate would then read as a data problem rather
    than a parser problem.
    """
    head, _, _ = DOUBLED_PAGE.partition('<ul class="lst-spcd">')
    html = head + "<p>A single paragraph of benefit.</p></section></main>"
    page = mpo.parse_page(html, "http://x/test.html", lang="en")
    assert page.benefits == ["A single paragraph of benefit."]


def test_mismatched_benefit_counts_lose_no_bullet():
    """
    The French Taltson page publishes five benefits where the English page
    publishes four. Positional pairing is unsafe there — an inserted bullet
    would put every later French sentence under an unrelated English one — but
    dropping the French side, which is what `_quick_facts` does, would delete a
    published federal sentence from the app in every language.

    Both lists are therefore carried whole and unpaired, and each language
    renders its own.
    """
    sys.path.insert(0, str(ROOT / "pipeline"))
    stage = importlib.import_module("01_projects")

    en = mpo.ParsedPage(url="", title="", benefits=["One.", "Two."])
    fr = mpo.ParsedPage(url="", title="", benefits=["Un.", "Deux.", "Trois."])
    out = stage._benefits(en, fr)

    assert [b.en for b in out if b.en] == ["One.", "Two."]
    assert [b.fr for b in out if b.fr] == ["Un.", "Deux.", "Trois."]
    # Nothing claims to be a translation of anything.
    assert not any(b.en and b.fr for b in out)


# ── Section crawl ──────────────────────────────────────────────────────────────

SECTION = "/en/privy-council/major-projects-office"


def _page(*links: str, header: tuple[str, ...] = ()) -> str:
    nav = "".join(f'<a href="{h}">nav</a>' for h in header)
    body = "".join(f'<a href="{h}">link</a>' for h in links)
    return (f"<html><body><header>{nav}</header>"
            f'<main property="mainContentOfPage">{body}</main></body></html>')


class _FakeFetch:
    """Serves canned pages by URL, raises for anything else, records every request."""

    def __init__(self, pages: dict[str, str]):
        self.pages = pages
        self.requested: list[str] = []

    def text(self, url: str) -> str:
        self.requested.append(url)
        if url not in self.pages:
            raise RuntimeError(f"HTTP 404 for {url}")
        return self.pages[url]


def test_crawl_follows_absolute_links_and_stays_inside_the_section():
    """
    The coverage crawl decides which page groups exist under the MPO section,
    and `source_section_shape` reports any group nobody declared. Its link
    filter was `href.startswith(section_path)`, wrong both ways:

    - an ABSOLUTE link (`https://www.canada.ca/en/…`) never starts with a path,
      so `beta` below — linked absolutely, with a query and a fragment — was
      never crawled and its project never counted;
    - a sibling section that merely shares the prefix
      (`…/major-projects-office-archive/`) WAS crawled, and would have been
      reported as an undeclared group inside the MPO section.

    Header links are ignored (only `<main>` is read), a broken link is recorded
    rather than raised, and nothing is requested twice.
    """
    site = mpo.CANADA_CA
    pages = {
        site + SECTION + ".html": _page(
            SECTION + "/projects/national.html",
            SECTION + "/missing.html",
            header=(SECTION + "/projects/national/header-junk.html",),
        ),
        site + SECTION + "/projects/national.html": _page(
            SECTION + "/projects/national/alpha.html",
            site + SECTION + "/projects/national/beta.html?utm_source=x#top",
            SECTION + "-archive/old.html",
            "https://example.org/elsewhere.html",
            SECTION + "/projects/national/alpha.html",
        ),
        site + SECTION + "/projects/national/alpha.html": _page(),
        site + SECTION + "/projects/national/beta.html": _page(SECTION + ".html"),
    }
    fetch = _FakeFetch(pages)
    out = mpo.crawl_section(fetch, SECTION)

    assert out["groups"] == {"projects": ["national"], "projects/national": ["alpha", "beta"]}
    assert [b["path"] for b in out["broken_links"]] == [SECTION + "/missing.html"]
    assert out["pages_crawled"] == 5
    assert len(fetch.requested) == len(set(fetch.requested)) == 5
    assert not any("header-junk" in u or "-archive" in u or "example.org" in u
                   for u in fetch.requested)


def test_crawl_is_bounded_by_max_pages():
    """
    `max_pages` is a stop, not a target. A template change that links an
    endless chain must end the crawl rather than walk canada.ca one request a
    second.
    """
    class Endless(_FakeFetch):
        def text(self, url: str) -> str:
            self.requested.append(url)
            return _page(f"{SECTION}/deep/p{len(self.requested)}.html")

    fetch = Endless({})
    out = mpo.crawl_section(fetch, SECTION, max_pages=3)
    assert out["pages_crawled"] == 3
    assert len(fetch.requested) == 3


def test_strategy_french_slug_is_declared_not_assumed():
    """
    Eight of the nine strategies share a terminal slug across languages and the
    ninth translates it, so a join on slug equality alone silently dropped
    `critical-minerals`'s French name from the first run onward. The exception
    is declared in the registry; this is what stops it being re-assumed.
    """
    cm = R.strategy("critical-minerals")
    assert cm is not None
    assert cm.fr_key == "mineraux-critiques"
    # Every other strategy still keys on its own slug.
    others = [s for s in R.strategies() if s.slug != "critical-minerals"]
    assert others and all(s.fr_key == s.slug for s in others)


def test_every_geometry_with_coordinates_has_an_anchor():
    """
    The map used to build markers from a `kind == "point"` filter and lines from
    a `kind == "corridor"` filter, so a corridor got a dashed line and NO
    marker: nothing to click, no headpiece, no way into the project. Four of
    eighteen projects were unreachable while every count and field check passed.

    An anchor on every coordinate-bearing geometry is what makes the render a
    total function instead of two filters that can both miss.
    """
    point = Geometry(kind=GeometryKind.POINT, coordinates=((-73.29, 45.82),))
    corridor = Geometry(kind=GeometryKind.CORRIDOR,
                        coordinates=((-133.73, 68.36), (-123.48, 63.23)))
    assert point.anchor == (-73.29, 45.82)
    assert corridor.anchor is not None
    assert corridor.is_linear and not point.is_linear


def test_a_corridor_anchor_is_marked_as_ours():
    """
    The source published the ENDS of the Mackenzie Valley Highway, never its
    middle. A midpoint is arithmetic, and rendering it with the same authority
    as a published coordinate would be this project making a claim in a form the
    source never used.
    """
    corridor = Geometry(kind=GeometryKind.CORRIDOR,
                        coordinates=((-133.73, 68.36), (-123.48, 63.23)))
    point = Geometry(kind=GeometryKind.POINT, coordinates=((-73.29, 45.82),))
    assert corridor.anchor_provenance is Provenance.DERIVED
    assert point.anchor_provenance is Provenance.OFFICIAL_DATASET


def test_a_region_has_no_anchor_and_says_so():
    """
    The strategies' locations are prose — "All of Canada" — with no coordinates
    at all. That must be stated, not faked with a centroid nobody published.
    """
    region = Geometry(kind=GeometryKind.REGION, provinces=("ON", "QC"))
    assert region.anchor is None
    assert region.anchor_provenance is Provenance.ABSENT


def test_a_placed_point_says_the_placement_is_ours():
    """
    A single point LOOKS published, so `anchor_provenance` infers
    OFFICIAL_DATASET for one. Transport Canada names its corridor ports and
    publishes no coordinates, so stage 04 places them itself and must be able
    to say so. The override has to survive the JSON round trip too, because the
    web app reads the dict, not the dataclass.
    """
    placed = Geometry(kind=GeometryKind.POINT, coordinates=((-63.57, 44.65),),
                      coordinate_provenance=Provenance.DERIVED)
    assert placed.anchor_provenance is Provenance.DERIVED
    again = Geometry.from_dict(placed.to_dict())
    assert again == placed and again.anchor_provenance is Provenance.DERIVED


def test_corridor_anchor_walks_the_route_rather_than_averaging_ends():
    """
    With two endpoints the two agree, which is exactly why averaging looks
    correct today and is wrong on the first route that arrives with a third
    vertex. An L-shaped route's halfway point is along the path, not at the
    centre of its bounding box.
    """
    # Lopsided on purpose: 1 unit north, then 10 east. Halfway along the route
    # is 5.5 units in, at (4.5, 1.0). Every shortcut lands elsewhere — the
    # endpoint average and the bounding-box centre are (5.0, 0.5), the middle
    # vertex is (0.0, 1.0). The previous route had two EQUAL legs, so halfway
    # along it WAS the middle vertex, and an implementation that just picked
    # the middle coordinate passed.
    bent = Geometry(kind=GeometryKind.CORRIDOR,
                    coordinates=((0.0, 0.0), (0.0, 1.0), (10.0, 1.0)))
    lon, lat = bent.anchor
    assert lon == pytest.approx(4.5, abs=0.05)
    assert lat == pytest.approx(1.0, abs=0.05)


def test_hero_image_is_read_from_data_bgimg_not_constructed():
    """
    The hero is a `data-bgimg` attribute on a div, not an <img>. Three project
    folders do not match their page slug (`nouveau-monde` -> `nouveau/`,
    `wind-west` -> `atlantic-energy/`, `vancouver` -> `port-van/`) and one
    official filename contains a typo, so any path built from the slug 404s.
    """
    html = (
        '<main property="mainContentOfPage"><h1>T</h1>'
        '<div class="bg-cover" data-bgimg="/content/dam/pco-bcp/mpo-bgp/projects/indiv/'
        'nouveau/MPO_NouveauMondeGraphite_Large.png"></div></main>'
    )
    page = mpo.parse_page(html, "http://x/nouveau-monde.html", lang="en")
    assert page.hero_path.endswith("MPO_NouveauMondeGraphite_Large.png")
    assert "/nouveau/" in page.hero_path
    assert "nouveau-monde" not in page.hero_path


# ── French, which fails silently in both directions ────────────────────────────

def test_french_headings_are_present_and_not_guessed():
    """
    The FR pages say "Faits saillants" and "Dernière mise à jour" (singular),
    not the plausible "Faits en bref" / "Dernières mises à jour". A wrong
    heading does not raise — it yields zero facts while every other field looks
    correct.
    """
    assert mpo.HEADINGS["fr"]["quick_facts"] == "Faits saillants"
    assert mpo.HEADINGS["fr"]["updates"] == "Dernière mise à jour"
    assert set(mpo.HEADINGS["en"]) == set(mpo.HEADINGS["fr"])


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Our own extraction artefact: a " " separator before punctuation that
        # followed an inline tag. Removing it restores the page's wording.
        ("On November 13, 2025 , the project", "On November 13, 2025, the project"),
        ("word ( inner ) end", "word (inner) end"),
        # French REQUIRES a space before these. Stripping it would rewrite
        # correct French and call the result verbatim.
        ("émissions 90 % inférieures", "émissions 90 % inférieures"),
        ("Longévité : le site", "Longévité : le site"),
        ("Vraiment ? Oui !", "Vraiment ? Oui !"),
    ],
)
def test_normalise_respects_french_typography(raw, expected):
    assert mpo.normalise(raw) == expected


# ── ArcGIS field vocabulary ────────────────────────────────────────────────────

def test_french_arcgis_uses_french_field_names():
    """
    The FR service is not the EN one with translated values: the FIELD NAMES are
    French and `Lien` points at the French page, so the two share no URL. They
    join on the terminal slug, which is identical in both languages.
    """
    fr = {"Nom": "Projet", "Lien": "https://x/fr/.../crawford.html", "Etat": "Renvoyé"}
    en = {"Name": "Project", "Link": "https://x/en/.../crawford.html", "Status": "Referred"}
    assert mpo.attr(fr, "name", "fr") == "Projet"
    assert mpo.attr(en, "name", "en") == "Project"
    assert mpo.slug_from_url(mpo.attr(fr, "link", "fr")) == mpo.slug_from_url(
        mpo.attr(en, "link", "en")
    )


# ── Geometry classification ────────────────────────────────────────────────────

def test_corridor_and_point_round_trip():
    """
    Two published endpoints are a route, not a pin. Dropping a marker at one end
    of the Mackenzie Valley Highway asserts a location the source does not give.
    """
    corridor = Geometry(
        kind=GeometryKind.CORRIDOR,
        coordinates=((-133.73, 68.359), (-123.479, 63.232)),
        location_verbatim="Wrigley to Inuvik",
    )
    assert Geometry.from_dict(corridor.to_dict()) == corridor
    assert len(corridor.coordinates) == 2

    point = Geometry(kind=GeometryKind.POINT, coordinates=((-81.37, 48.84),))
    assert Geometry.from_dict(point.to_dict()) == point


def test_series_rejects_ragged_periods():
    """A series whose periods and values drift apart is silently wrong."""
    with pytest.raises(ValueError):
        Series(
            code="T001", label=Text(en="All"), geo="CA", measure="gdp_chained",
            unit="Dollars", scalar="millions", frequency="monthly",
            periods=("2026-01", "2026-02"), values=(1.0,),
        )


def test_sourceref_survives_json():
    ref = SourceRef(
        url="https://x", retrieved_at="2026-09-04T00:00:00Z",
        provenance=Provenance.PAGE_VERBATIM, licence="ogl-canada-2.0",
        content_sha256=SourceRef.hash_content("hello"),
    )
    assert to_jsonable(ref)["provenance"] == "page_verbatim"
    assert SourceRef.from_dict(ref.to_dict()) == ref
    assert Provenance.PAGE_VERBATIM.is_reproduced


# ── StatCan quirks ─────────────────────────────────────────────────────────────

def test_industry_code_is_parsed_from_the_label():
    """The cube embeds its own join key: "Manufacturing [31-33]"."""
    assert statcan.code_of("Manufacturing [31-33]") == "31-33"
    assert statcan.label_of("Manufacturing [31-33]") == "Manufacturing"
    assert statcan.code_of("Goods-producing industries [T002]") == "T002"
    # No bracket means no code — that is how provincial-only members are told
    # apart from real NAICS sectors without a second lookup.
    assert statcan.code_of("Some heading with no code") == ""


def test_number_parsing_handles_thousands_separators():
    """
    The XIC holdings file writes "3,047.11". A bare float() raises on roughly
    every large row, which is how a naive reader ends up with only the small
    constituents.
    """
    assert C._num("3,047.11") == pytest.approx(3047.11)
    assert C._num("-") is None
    assert C._num("") is None


def test_holdings_preamble_and_junk_rows():
    """Cash, derivatives and stale zero-priced equities are not companies."""
    csv = (
        '﻿Fund Holdings as of,"Sep 2, 2026"\n'
        " \n"
        "Ticker,Name,Sector,Asset Class,Market Value,Weight (%),Shares,Price,Currency\n"
        '"RY","ROYAL BANK","Financials","Equity","1,000.00","7.82","9,285","287.89","CAD"\n'
        '"MLPFT","CASH COLLATERAL","Cash and/or Derivatives","Cash Collateral","1.00","0.01","1","1.00","CAD"\n'
        '"2299955D","STALE CO","Information Technology","Equity","0.61","0.00","60,915","0.00","CAD"\n'
    )
    as_of, rows = C.parse_holdings(csv)
    assert as_of == "Sep 2, 2026"
    assert len(rows) == 3

    crosswalk = {e["gics"]: e for e in yaml.safe_load(
        (ROOT / "registry" / "gics_naics.yaml").read_text(encoding="utf-8"))["map"]}
    kept = C.to_companies(rows, crosswalk)
    assert [c.ticker for c in kept] == ["RY"]
    assert kept[0].provenance is Provenance.MARKET_DATA


# ── Registry integrity ─────────────────────────────────────────────────────────

def test_yaml_does_not_coerce_ontario_to_a_boolean():
    """
    YAML 1.1 reads bare `ON` as True (and `NO` as False, `NA` as nan). An
    unquoted `provinces: [ON, QC]` silently drops Ontario from every strategy
    that includes it, with no error and a plausible-looking result.
    """
    critical = R.strategy("critical-minerals")
    assert critical is not None and "ON" in critical.provinces


def test_an_unquoted_on_in_strategies_yaml_is_refused(monkeypatch):
    """
    The test above only proves today's file is quoted. The loop it used to carry
    — "every loaded province code is a string" — could never fail, because the
    loader raises on a non-string code before any caller sees one. What protects
    the next edit is that guard, so feed it the trap.
    """
    doc = yaml.safe_load(
        "strategies: [{slug: probe, location_verbatim: somewhere, provinces: [ON, QC]}]")
    # The precondition, asserted: if PyYAML ever stopped coercing, this test
    # should say so rather than pass for a reason nobody intended.
    assert doc["strategies"][0]["provinces"][0] is True

    real = R._load
    monkeypatch.setattr(R, "_load", lambda name: doc if name == "strategies.yaml" else real(name))
    R.strategies.cache_clear()
    try:
        with pytest.raises(R.RegistryError, match="boolean"):
            R.strategies()
    finally:
        monkeypatch.undo()
        R.strategies.cache_clear()


def test_sector_partition_actually_partitions():
    tax = yaml.safe_load((ROOT / "registry" / "sectors.yaml").read_text(encoding="utf-8"))
    parents = {s["parent"] for s in tax["sectors"]}
    assert parents == set(tax["aggregates"]["partition"])
    assert len(tax["sectors"]) == 20
    # Cross-cuts OVERLAP and must never be summed with the partition.
    assert set(tax["cross_cuts"]).isdisjoint(tax["aggregates"]["partition"])


def test_every_source_declares_a_defined_licence():
    src = R.sources()
    for key, entry in src["sources"].items():
        lic = entry.get("licence")
        assert lic in src["licences"], f"{key} claims undefined licence {lic!r}"


def test_alto_is_not_drawn_as_a_region():
    """
    The Toronto-Quebec corridor is a rail line. Filling Ontario and Quebec
    entirely would claim a footprint orders of magnitude larger than the real
    one, so it is listed and not drawn.
    """
    alto = R.strategy("alto")
    assert alto is not None and alto.draws_region is False


# ── Trade corridors ────────────────────────────────────────────────────────────

def _corridor_doc(*, central_provinces: str = '["ON", "QC"]', central_ports: str = "[toronto]",
                  atlantic_provinces: str = '["NB", "NS", "PE", "NL"]',
                  northern_note: bool = True) -> str:
    """A minimal corridors.yaml covering all 13 codes, with one knob per failure."""
    note = ('\n    unmapped_note: { en: "Defined by latitude.", fr: "Défini par la latitude." }'
            if northern_note else "")
    return f"""
ports:
  - {{ id: toronto, name: {{ en: Toronto, fr: Toronto }}, coord: [-79.36, 43.64] }}
crossings: []
corridors:
  - {{ id: west, summary: {{ en: W, fr: O }}, location_verbatim: {{ en: west }}, provinces: ["BC", "AB", "SK", "MB"] }}
  - {{ id: central, summary: {{ en: C, fr: C }}, location_verbatim: {{ en: centre }}, provinces: {central_provinces}, ports: {central_ports} }}
  - {{ id: atlantic, summary: {{ en: A, fr: A }}, location_verbatim: {{ en: east }}, provinces: {atlantic_provinces} }}
  - id: northern
    summary: {{ en: N, fr: N }}
    location_verbatim: {{ en: north }}
    provinces: ["YT", "NT", "NU"]
    overlaps_provinces: true{note}
"""


@pytest.fixture
def load_corridors(monkeypatch):
    """Run the corridor loaders against a YAML string instead of the registry file."""
    real = R._load

    def load(text: str):
        doc = yaml.safe_load(text)
        monkeypatch.setattr(R, "_load", lambda name: doc if name == "corridors.yaml" else real(name))
        R.corridor_nodes.cache_clear()
        R.corridors.cache_clear()
        return R.corridors()

    yield load
    R.corridor_nodes.cache_clear()
    R.corridors.cache_clear()


def test_the_corridor_fixture_loads(load_corridors):
    """The control: the minimal document is valid, so each failure below is its knob."""
    got = {c.corridor_id: c for c in load_corridors(_corridor_doc())}
    assert set(got) == {"west", "central", "atlantic", "northern"}
    assert got["central"].provinces == ("ON", "QC")
    assert got["northern"].overlaps_provinces and got["northern"].unmapped_note_en


@pytest.mark.parametrize("knob,message", [
    ({"central_provinces": "[ON, QC]"}, "boolean"),
    ({"central_ports": "[toronto, atlantis]"}, "unknown nodes"),
    ({"northern_note": False}, "unmapped_note"),
    ({"atlantic_provinces": '["NB", "NS", "PE"]'}, "belong to no corridor"),
])
def test_corridor_registry_refuses_each_silent_failure(load_corridors, knob, message):
    """
    Four edits to corridors.yaml that would each load, draw, and be wrong:

    - `[ON, QC]` unquoted loads as `[True, "QC"]`; Ontario leaves the Central
      Corridor and nothing on the map says so.
    - A node id with a typo is a port that is listed and never placed.
    - `overlaps_provinces` without a note is an overlap the reader never sees,
      so a latitude-defined corridor reads as exactly three territories.
    - A province in no corridor vanishes from every corridor view. Overlap is
      Transport Canada's framing; a GAP would be ours.
    """
    with pytest.raises(R.RegistryError, match=message):
        load_corridors(_corridor_doc(**knob))


CORRIDOR_PAGE = """
<main property="mainContentOfPage">
  <details><summary>Supporting the Economy</summary><p>Not a corridor.</p></details>
  <details>
    <summary>Infrastructure That Supports Trade and Mobility Corridors</summary>
    <p>Looks exactly like a corridor.</p>
    <div class="well well-sm"><h4>Infrastructure</h4><p>Rail</p><ul><li>Not ours.</li></ul></div>
  </details>
  <details>
    <summary>Atlantic
      Corridor</summary>
    <p>It links the ports of Halifax Footnote 3 , Saint John and St. John's.</p>
    <div class="well well-sm">
      <h4>Atlantic Corridor Infrastructure</h4>
      <p>Rail</p><ul><li>CN main line</li><li>CPKC</li></ul>
      <p>Road</p><ul><li>Highway 104</li></ul>
    </div>
  </details>
</main>
"""


def test_corridors_are_matched_by_declared_name_not_by_shape():
    """
    Transport Canada's page has eight `<details>` blocks and five corridors. One
    of the other three — "Infrastructure That Supports Trade and Mobility
    Corridors" — carries the same infrastructure box a corridor does, so any
    structural rule finds a sixth corridor. Only declared summaries are read.

    Also pinned: the CMS's footnote marker is navigation, not the government's
    sentence, and each `<ul>` belongs to the `<p>` label before it rather than
    being read as one run of bullets.
    """
    got = tc.parse_page(CORRIDOR_PAGE, ["Atlantic Corridor"])
    assert list(got) == ["Atlantic Corridor"]
    atlantic = got["Atlantic Corridor"]
    assert atlantic.description == "It links the ports of Halifax, Saint John and St. John's."
    assert [(m.label, m.items) for m in atlantic.modes] == [
        ("Rail", ["CN main line", "CPKC"]),
        ("Road", ["Highway 104"]),
    ]


def test_a_declared_corridor_missing_from_the_page_raises():
    """
    Five declared and four found is the failure this event was nearly built
    with. It must stop the stage, not ship four corridors.
    """
    with pytest.raises(ValueError, match="Northern Corridor"):
        tc.parse_page(CORRIDOR_PAGE, ["Atlantic Corridor", "Northern Corridor"])


def test_unequal_corridor_lists_are_carried_unpaired_in_both_directions():
    """
    The Northern Corridor publishes 13 infrastructure items in English and 12 in
    French, so positional pairing would present one sentence as the translation
    of another. Where counts differ, each language keeps its whole list.

    One level up had the same hole and no guard: `_modes` walked the English
    modes only, so a mode the French page published and the English page did
    not was dropped silently. It is now carried French-only.
    """
    sys.path.insert(0, str(ROOT / "pipeline"))
    stage = importlib.import_module("04_trade")

    en = tc.ParsedCorridor(summary="N", description="", modes=[
        tc.ParsedMode("Rail", ["One", "Two"]),
        tc.ParsedMode("Road", ["Alaska Highway"]),
    ])
    fr = tc.ParsedCorridor(summary="N", description="", modes=[
        tc.ParsedMode("Transport ferroviaire", ["Un", "Deux", "Trois"]),
        tc.ParsedMode("Routes", ["Route de l'Alaska"]),
        tc.ParsedMode("Transport aérien", ["Aéroport d'Iqaluit"]),
    ])
    rail, road, air = stage._modes(en, fr)

    assert rail.label == Text(en="Rail", fr="Transport ferroviaire")
    assert [i.en for i in rail.items if i.en] == ["One", "Two"]
    assert [i.fr for i in rail.items if i.fr] == ["Un", "Deux", "Trois"]
    assert not any(i.en and i.fr for i in rail.items)

    # Equal counts still pair.
    assert road.items == (Text(en="Alaska Highway", fr="Route de l'Alaska"),)

    # The French-only mode survives, and claims no English.
    assert air.label == Text(en="", fr="Transport aérien")
    assert air.items == (Text(en="", fr="Aéroport d'Iqaluit"),)


# ── The independence rule, enforced ────────────────────────────────────────────

def test_the_bundle_is_the_last_stage():
    """
    `run.py` executes stages in SORTED KEY ORDER, so the number is the run order.

    The bundle reads what every other stage wrote. A stage numbered above it
    would have its output bundled a run late — the first run ships nothing, the
    second ships the first run's data — which is silent and reads as a caching
    bug rather than an ordering one. Numbering the bundle 99 leaves room for
    every future stage in between, and this test is what keeps that a rule
    rather than a comment somebody edits past.
    """
    sys.path.insert(0, str(ROOT))
    run = importlib.import_module("run")

    assert sorted(run.STAGES)[-1] == "99", (
        f"the bundle must sort last; stages are {sorted(run.STAGES)}"
    )
    assert "bundle" in run.STAGES["99"]
    for num, path in run.STAGES.items():
        assert (ROOT / path).exists(), f"stage {num} names a missing script: {path}"


def test_verify_does_not_import_atlas():
    """
    Verification that imports the code it checks inherits that code's bugs.
    African-Stability-Index states this rule and then broke it, so here it is
    enforced mechanically rather than by good intentions.
    """
    offenders = []
    for path in (ROOT / "verify").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders += [f"{path.name}: {a.name}" for a in node.names
                              if a.name.split(".")[0] == "atlas"]
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[0] == "atlas":
                    offenders.append(f"{path.name}: from {node.module}")
    assert not offenders, offenders


# ── Regressions from the 2026-09-05 code review ────────────────────────────────

def test_write_if_changed_ignores_only_volatile_keys():
    """
    F11. Four stages each carried a private copy of this helper and they had
    already drifted on WHICH keys count as volatile. One implementation now, and
    the rule is: a run that changes only timestamps must not rewrite the file.
    """
    from atlas.core.jsonio import VOLATILE_KEYS, write_if_changed

    assert VOLATILE_KEYS == {"generated_at", "retrieved_at"}

    import tempfile
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "out.json"
        base = {"generated_at": "A", "series": [{"retrieved_at": "A", "v": 1}]}

        assert write_if_changed(path, base) is True, "first write must happen"
        moved = {"generated_at": "B", "series": [{"retrieved_at": "B", "v": 1}]}
        assert write_if_changed(path, moved) is False, "timestamps alone must not rewrite"
        real = {"generated_at": "B", "series": [{"retrieved_at": "B", "v": 2}]}
        assert write_if_changed(path, real) is True, "a real change must rewrite"


def test_write_if_changed_does_not_rewrite_a_payload_holding_tuples():
    """
    B2. A tuple serialises as a JSON array and reads back as a list, and
    `("E", "x") != ["E", "x"]` in Python. `write_if_changed` compared the file as
    read against the payload as built, so any payload carrying a tuple was
    unequal to its own file on every run and was rewritten with a new
    `generated_at` — capex-annual.json and employment-monthly.json changed on a
    re-run of unchanged sources, breaking the zero-line-diff rule (CLAUDE.md §6).
    """
    import tempfile

    from atlas.core.jsonio import write_if_changed

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "out.json"
        assert write_if_changed(path, {"generated_at": "A", "status": {"CA/23": ("E", "x")}}) is True
        assert write_if_changed(path, {"generated_at": "B", "status": {"CA/23": ("E", "x")}}) is False,             "an unchanged payload holding a tuple must not rewrite"
        assert write_if_changed(path, {"generated_at": "B", "status": {"CA/23": ("E", "F")}}) is True


def test_cube_filter_mismatch_raises_instead_of_yielding_nothing():
    """
    F13. A renamed StatCan column used to reject every row and return an empty
    list, which surfaced three stages later as "the registry is missing sectors"
    — pointing the reader at the wrong file entirely.
    """
    header = ["REF_DATE", "GEO", "North American Industry Classification System (NAICS)",
              "UOM", "SCALAR_ID", "SCALAR_FACTOR", "VALUE"]
    rows = [["2026-01", "Canada", "All industries [T001]", "Dollars", "6", "millions", "100"]]

    # A column that no longer exists.
    with pytest.raises(ValueError, match="not in the CSV header"):
        statcan.build_series(header, rows, pid="36100434", measure="gdp", frequency="monthly",
                             filters={"Prices": "Chained (2017) dollars"}, keep_codes={"T001"})

    # The column exists but its value was renamed.
    with pytest.raises(ValueError, match="no rows matched"):
        statcan.build_series(header, rows, pid="36100434", measure="gdp", frequency="monthly",
                             filters={"GEO": "Atlantis"}, keep_codes={"T001"})


def test_cache_entries_expire():
    """
    F4. An immortal cache silently disables change detection: data/history/ only
    appends when a page's content hash moves, and a permanently cached page's
    hash never moves. Entries must age out.
    """
    import os
    import tempfile
    import time as _time

    from atlas.net import CACHE_TTL_SECONDS, Fetcher

    assert CACHE_TTL_SECONDS == 24 * 60 * 60

    with tempfile.TemporaryDirectory() as d:
        f = Fetcher(cache_dir=Path(d), cache_ttl=100)
        url = "https://example.invalid/thing"
        f._cache_write(url, b"body")

        assert f._cache_read(url) == b"body", "a fresh entry is served"

        # Backdate the entry past its TTL.
        path = f._cache_path(url)
        old = _time.time() - 200
        os.utime(path, (old, old))
        assert f._cache_read(url) is None, "a stale entry must read as a miss"
        assert f.expired == 1


# ── Census subdivisions ────────────────────────────────────────────────────────

def _census_header(geo: str, measure: str, symbols: str) -> list[str]:
    header = ["REF_DATE", geo, "DGUID", "Coordinate"]
    for n in range(1, 14):
        header += [f"{measure} {n} [{n}]", symbols]
    return header


#: Table 98-10-0002 in miniature. Each row: English name, French name, DGUID,
#: (type abbreviation, English type, French type) for subdivisions, then the 13
#: value cells and the 13 symbol cells, exactly as the table lays them out.
_CENSUS_ROWS = [
    ("Canada", "Canada", "2021A000011124", None,
     ["250", "260", "-3.8", "120", "118", "1.7", "100", "98", "2.0", "1000.50", "0.3", "", ""],
     [""] * 11 + ["...", "..."]),
    ("Newfoundland and Labrador", "Terre-Neuve-et-Labrador", "2021A000210", None,
     ["250", "260", "-3.8", "120", "118", "1.7", "100", "98", "2.0", "1000.50", "0.3", "", ""],
     [""] * 11 + ["...", "..."]),
    ("Division No.  1", "Division No.  1", "2021A00031001", None,
     ["250", "260", "-3.8", "120", "118", "1.7", "100", "98", "2.0", "1000.50", "0.3", "27", "1"],
     [""] * 13),
    # A town whose 2016 count StatCan has revised.
    ("Admirals Beach", "Admirals Beach", "2021A00051001186", ("T", "Town", "Town"),
     ["97", "135", "-28.1", "76", "80", "-5.0", "48", "62", "-22.6", "24.20", "4.0", "4267", "325"],
     ["", "r"] + [""] * 11),
    # Nobody lives here: zero is published, and a change from zero is not applicable.
    ("Probe Unorganized", "Probe Unorganized", "2021A00051001201", ("NO", "Unorganized", "Non organisé"),
     ["0", "0", "", "3", "2", "50.0", "0", "0", "", "400.00", "0.0", "5000", "400"],
     ["", "", "..."] + [""] * 5 + ["..."] + [""] * 4),
    # An incompletely enumerated reserve: 2021 not available, 2016 and area published.
    ("Probe Reserve", "Probe Reserve", "2021A00051001999", ("IRI", "Indian reserve", "Réserve indienne"),
     ["", "40", "", "", "12", "", "", "10", "", "1.50", "", "", ""],
     ["..", "", "..", "..", "", "..", "..", "", "..", "", "..", "..", ".."]),
]


def _census_zip(tmp_path, lang, *, drop="", population_of_beach="", pr_code_of_beach=""):
    """One language's zip: English comma-separated, French semicolon-separated."""
    sep = "," if lang == "en" else ";"
    geo, symbols, measure = (
        ("GEO", "Symbols", "Population and dwelling counts (13): Measure") if lang == "en"
        else ("GÉO", "Symboles", "Chiffres de population et des logements (13) : Mesure"))
    data, meta = io.StringIO(), io.StringIO()
    rows, attrs = csv.writer(data, delimiter=sep), csv.writer(meta, delimiter=sep)
    rows.writerow(_census_header(geo, measure, symbols))
    attrs.writerow(["Cube Title", "Product Id", "CANSIM Id", "URL"])

    for member, (en_name, fr_name, dguid, kind, values, syms) in enumerate(_CENSUS_ROWS, start=1):
        if dguid == drop:
            continue
        beach = dguid.endswith("1001186")
        values = list(values)
        if beach and population_of_beach:
            values[0] = population_of_beach
        cells = ["2021", en_name if lang == "en" else fr_name, dguid, str(member)]
        for value, symbol in zip(values, syms):
            cells += [value, symbol]
        rows.writerow(cells)

        # A member row — which the attribute reader must skip — then attributes.
        attrs.writerow(["1", en_name, f"[{dguid[9:]}]", str(member), ""])
        found = {16: dguid}
        if kind:
            found[5] = kind[0]
            found[10] = pr_code_of_beach if (beach and pr_code_of_beach) else dguid[9:11]
            found[15] = kind[1] if lang == "en" else kind[2]
        for key, value in found.items():
            attrs.writerow(["1", str(member), str(key), "ATTR", "label", "label", value])

    path = tmp_path / f"98100002-{lang}-{drop}{population_of_beach}{pr_code_of_beach}.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("98100002.csv", "\ufeff" + data.getvalue())
        z.writestr("98100002_MetaData.csv", "\ufeff" + meta.getvalue())
    return path


def test_census_values_keep_not_available_apart_from_zero():
    """
    The table writes an unpublished value as a BLANK cell with its reason in the
    Symbols column beside it: ".." not available (63 incompletely enumerated
    reserves), "..." not applicable (a percentage change from zero). Zero is a
    value — 268 subdivisions have no usual residents.

    Three things raise instead of becoming a quiet None: a blank with no reason,
    a symbol not in StatCan's legend, and a cell that is not a number. Each is
    the table changing shape.
    """
    assert census.number("0", int) == 0
    assert census.number("-28.1", float) == pytest.approx(-28.1)
    assert census.number("", int, "..") is None
    assert census.number("", float, "...") is None
    assert census.number("135", int, "r") == 135          # revised is still a value
    assert census.number("7", int, "r,E") == 7            # flags combine
    with pytest.raises(ValueError, match="no published reason"):
        census.number("", int, "")
    with pytest.raises(ValueError, match="unknown symbol"):
        census.number("5", int, "Z")
    with pytest.raises(ValueError, match="neither a number"):
        census.number("n/a", int)


def test_census_columns_are_found_by_member_number_not_header_text():
    """
    The English and French headers share nothing but the member number StatCan
    appends — "Land area in square kilometres, 2021 [10]" is "Superficie des
    terres en kilomètres carrés, 2021 [10]". Selecting by English text would
    return no French values and raise nothing.

    Each value's flags are read from the next column, so a header where that
    column is missing must raise rather than read one value as another's symbol.
    """
    en = _census_header("GEO", "Population and dwelling counts (13): Measure", "Symbols")
    fr = _census_header("GÉO", "Chiffres de population et des logements (13) : Mesure", "Symboles")
    want = {n: 2 + 2 * n for n in range(1, 14)}
    assert census.measure_columns(en) == census.measure_columns(fr) == want

    with pytest.raises(ValueError, match=r"no value column for members \[13\]"):
        census.measure_columns(en[:-2])
    with pytest.raises(ValueError, match="no symbol column"):
        census.measure_columns([c for c in en if c != "Symbols"])


def test_census_build_reads_every_subdivision_in_both_languages(tmp_path):
    """
    The whole path from two zips to records: the province and division read
    from the identifier, the legal type from each language's metadata as
    published (the French file says "Town" for this town, and "Réserve
    indienne" for the reserve), None and zero kept apart, and every flag kept
    beside the value it qualifies.
    """
    counts = census.build(_census_zip(tmp_path, "en"), _census_zip(tmp_path, "fr"))
    by = {m.csd_uid: m for m in counts.municipalities}
    assert list(by) == ["1001186", "1001201", "1001999"]
    assert all(isinstance(m, Municipality) for m in by.values())

    beach = by["1001186"]
    assert beach.province == "NL" and beach.census_division_uid == "1001"
    assert beach.census_division_name == Text(en="Division No.  1", fr="Division No.  1")
    assert beach.csd_type_abbr == "T" and beach.csd_type == Text(en="Town", fr="Town")
    assert beach.population_2021 == 97
    assert beach.population_change_pct == pytest.approx(-28.1)
    assert beach.symbols == {"population_2016": "r"}
    assert beach.geo_key == "csd:2021:1001186"

    empty = by["1001201"]
    assert empty.population_2021 == 0 and empty.population_change_pct is None
    assert empty.symbols == {"population_change_pct": "...", "occupied_dwellings_change_pct": "..."}

    reserve = by["1001999"]
    assert reserve.csd_type == Text(en="Indian reserve", fr="Réserve indienne")
    assert reserve.population_2021 is None and reserve.population_2016 == 40
    assert reserve.symbols["population_2021"] == ".."
    assert to_jsonable(reserve)["population_2021"] is None      # null in JSON, never 0

    assert counts.province_names == {
        "NL": Text(en="Newfoundland and Labrador", fr="Terre-Neuve-et-Labrador")}
    assert counts.census_division_names == {"1001": Text(en="Division No.  1", fr="Division No.  1")}
    assert counts.canada_total["rank_national"] is None


def test_census_english_and_french_must_describe_the_same_table(tmp_path):
    """
    The French file is the only source of French names, and a free second read
    of every value. A geography in one file and not the other, or a value that
    differs between them, means one download is not the table the other is.
    """
    en = _census_zip(tmp_path, "en")
    with pytest.raises(ValueError, match="different geographies"):
        census.build(en, _census_zip(tmp_path, "fr", drop="2021A00051001999"))
    with pytest.raises(ValueError, match="different values"):
        census.build(en, _census_zip(tmp_path, "fr", population_of_beach="98"))


def test_census_province_is_checked_against_the_metadata(tmp_path):
    """
    A CSDUID starts with its province: 1001186 is in province 10. The metadata
    states the province too, and the two disagreeing means a join is wrong
    somewhere — so it is collected and raised, naming the subdivision.
    """
    with pytest.raises(ValueError, match="1001186: metadata says province 11"):
        census.build(_census_zip(tmp_path, "en", pr_code_of_beach="11"),
                     _census_zip(tmp_path, "fr"))


# ── B2: the newer StatCan cubes ────────────────────────────────────────────────

SEPH_HEADER = ["REF_DATE", "GEO", "DGUID", "Type of employee",
               "North American Industry Classification System (NAICS)", "UOM", "UOM_ID",
               "SCALAR_FACTOR", "SCALAR_ID", "VECTOR", "COORDINATE", "VALUE", "STATUS",
               "SYMBOL", "TERMINATED", "DECIMALS"]


def _seph_row(period, member, value, status="A", geo="Canada", employee="All employees"):
    return [period, geo, "", employee, member, "Persons", "249", "units", "0",
            "v1", "1.1", value, status, "", "", "0"]


def _cube_zip(path, pid, rows, *, sep=",", metadata=None):
    buf = io.StringIO()
    csv.writer(buf, delimiter=sep).writerows(rows)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"{pid}.csv", "\ufeff" + buf.getvalue())
        if metadata is not None:
            meta = io.StringIO()
            csv.writer(meta, delimiter=sep).writerows(metadata)
            z.writestr(f"{pid}_MetaData.csv", "\ufeff" + meta.getvalue())
    return path


def _seph_series(rows, **extra):
    return statcan.build_series(
        SEPH_HEADER, rows, pid="14100201", measure="employment_nsa", frequency="monthly",
        filters={"Type of employee": "All employees"}, geo_codes={"Canada": "CA"}, **extra)


def test_iter_cube_streams_exactly_what_read_cube_loads(tmp_path):
    """
    SEPH is 986 MB of English CSV and 1,075 MB of French; `read_cube` parses a
    file whole, which for SEPH is several gigabytes of Python strings. The
    streaming reader must yield the same header and rows — including from a
    semicolon-separated French file — or switching readers changes the data.
    """
    rows = [SEPH_HEADER,
            _seph_row("2026-05", "Services publics [22,221]", "117000"),
            _seph_row("2026-06", "Construction [23]", "1200000", status="")]
    path = _cube_zip(tmp_path / "fr.zip", "14100201", rows, sep=";")
    header, loaded = statcan.read_cube(path, "14100201")
    stream = statcan.iter_cube(path, "14100201")
    assert next(stream) == header == SEPH_HEADER
    assert list(stream) == loaded


def test_combined_codes_join_the_key_and_never_merge_two_members():
    """
    SEPH publishes Utilities as [22,221]; `code_aliases` maps it to 22 so the
    series joins GDP. An alias that lands two DIFFERENT published members on
    one code would interleave their months into one series, every period twice
    — so that raises rather than merging.
    """
    rows = [_seph_row("2026-05", "Utilities [22,221]", "117000"),
            _seph_row("2026-06", "Utilities [22,221]", "118000")]
    out = _seph_series(rows, keep_codes={"22"}, code_aliases={"22,221": "22"})
    assert [(x.code, x.periods, x.values) for x in out] == [("22", ("2026-05", "2026-06"), (117000.0, 118000.0))]

    clash = rows + [_seph_row("2026-06", "Utilities [22]", "1")]
    with pytest.raises(ValueError, match="both map to code 22"):
        _seph_series(clash, keep_codes={"22"}, code_aliases={"22,221": "22"})


def test_quality_and_suppression_codes_travel_with_the_values():
    """
    STATUS holds both suppression ("x") and quality grades (A–F; E is "use with
    caution"). A suppressed cell is a None, never a zero, and the grade stays
    beside the value it qualifies.
    """
    status: dict = {}
    rows = [_seph_row("2026-05", "Construction [23]", "1200000", status="E"),
            _seph_row("2026-06", "Construction [23]", "", status="x"),
            _seph_row("2026-06", "Manufacturing [31-33]", "1700000", status="")]
    out = _seph_series(rows, keep_codes={"23", "31-33"}, status_out=status)
    assert {x.code: x.values for x in out} == {"23": (1200000.0, None), "31-33": (1700000.0,)}
    # A series with no status at all adds nothing to the map.
    assert status == {"CA/23": ("E", "x")}


def test_seph_forestry_is_never_joined_to_agriculture():
    """
    SEPH excludes agriculture: its [11N] is "Forestry, logging and support",
    forestry alone. Mapping it to NAICS 11 would divide agriculture-plus-forestry
    GDP by forestry jobs and report a productivity figure several times too
    high, with nothing on screen to suggest it. The registry must declare 11
    absent for SEPH, with a reason, and must never alias 11N.
    """
    tax = yaml.safe_load((ROOT / "registry" / "sectors.yaml").read_text(encoding="utf-8"))
    seph = tax["pulls"]["employment_monthly"]
    assert seph["measure"] == "employment_nsa", "SEPH is unadjusted; the measure name must say so"
    assert "11" in (seph.get("absent_codes") or {}) and seph["absent_codes"]["11"].strip()
    assert "11N" not in (seph.get("code_aliases") or {})


def test_french_labels_stop_reading_once_every_wanted_label_is_found():
    """
    Industry members repeat for every period, so all of SEPH's appear in the
    first few thousand of its five million French rows. Reading past the last
    wanted label would re-read 1 GB to learn nothing.
    """
    header = ["PÉRIODE DE RÉFÉRENCE", "GÉO",
              "Système de classification des industries de l'Amérique du Nord (SCIAN)", "VALEUR"]

    def rows():
        yield ["2026-05", "Canada", "Services publics [22,221]", "1"]
        yield ["2026-05", "Canada", "Construction [23]", "1"]
        raise AssertionError("read past the last wanted label")

    got = statcan.french_labels(header, rows(), code_aliases={"22,221": "22"}, want={"22", "23"})
    assert got == {"22": "Services publics", "23": "Construction"}


def test_cube_metadata_reads_the_title_and_numbered_notes(tmp_path):
    """The cube's own words about itself — title and notes — read from its metadata file."""
    note = "Most recent 2 years of data are preliminary actuals and intentions and do not have the repairs expenditures."
    metadata = [
        ["Cube Title", "Product Id", "CANSIM Id"],
        ["Capital and repair expenditures, non-residential tangible assets, by industry and geography", "34100035", ""],
        [],
        ["Note ID", "Note"],
        ["1", "From reference year 2013, this table replaces an archived table."],
        ["4", note],
        [],
        ["Correction ID", "Correction Date"],
    ]
    path = _cube_zip(tmp_path / "capex.zip", "34100035", [["REF_DATE"]], metadata=metadata)
    meta = statcan.cube_metadata(path, "34100035")
    assert meta["title"].startswith("Capital and repair expenditures")
    assert meta["notes"] == {"1": "From reference year 2013, this table replaces an archived table.", "4": note}


def test_capex_intentions_are_labelled_and_the_rule_needs_its_note():
    """
    34-10-0035 has no column separating spending from intentions; its note says
    the most recent two years are preliminary actuals and intentions. Plotting
    2026 intentions as spending would put a plan on the same line as a
    measurement. The labels follow the note — and if the note is gone, the rule
    stops rather than labelling years by a statement the publisher withdrew.
    """
    notes = {"4": "Most recent 2 years of data are preliminary actuals and intentions and do not have the repairs expenditures."}
    basis, note_id = statcan.latest_periods_basis(
        ["2023", "2024", "2025", "2026"], notes,
        contains="Most recent 2 years", labels=["preliminary_actual", "intentions"])
    assert basis == {"2023": "actual", "2024": "actual", "2025": "preliminary_actual", "2026": "intentions"}
    assert note_id == "4"

    with pytest.raises(ValueError, match="Most recent 2 years"):
        statcan.latest_periods_basis(["2025", "2026"], {"4": "Something else entirely."},
                                     contains="Most recent 2 years", labels=["preliminary_actual", "intentions"])


# ── B2a: gross output, from a cube that is not NAICS ───────────────────────────

IOIC_HEADER = ["REF_DATE", "GEO", "DGUID", "Industry", "UOM", "UOM_ID", "SCALAR_FACTOR",
               "SCALAR_ID", "VECTOR", "COORDINATE", "VALUE", "STATUS", "SYMBOL",
               "TERMINATED", "DECIMALS"]
EDUCATION = {"61": ["BS610", "NP61000", "GS610"]}


def _ioic_row(period, member, value, status=""):
    return [period, "Canada", "", member, "Dollars", "81", "millions", "6",
            "v1", "1.1", value, status, "", "", "0"]


def _ioic_series(rows, crosswalk=EDUCATION, **extra):
    labels = {"T001": Text(en="Total industries", fr="Ensemble des industries"),
              "61": Text(en="Educational services", fr="Services d'enseignement"),
              "62": Text(en="Health care and social assistance", fr="Soins de santé et assistance sociale")}
    return statcan.build_crosswalk_series(
        IOIC_HEADER, rows, pid="36100488", measure="gross_output", frequency="annual",
        column="Industry", crosswalk=crosswalk, total_member="Total industries",
        total_code="T001", labels=labels, geo_codes={"Canada": "CA"}, **extra)


def test_a_non_naics_cube_is_summed_into_sectors_and_says_the_sum_is_ours():
    """
    36-10-0488 is classified by IOIC and split by institutional sector, so no
    member is NAICS 61: education is business + non-profit + government
    members. The sum is this project's and must be labelled DERIVED; the cube's
    own total is reproduced and must not be.
    """
    rows = [_ioic_row("2022", "Total industries", "1000"),
            _ioic_row("2022", "Educational services [BS610]", "10"),
            _ioic_row("2022", "Educational services [NP61000]", "6"),
            _ioic_row("2022", "Government education services [GS610]", "145"),
            _ioic_row("2022", "Hospitals [GS622000]", "99")]
    out = {x.code: x for x in _ioic_series(rows)}
    assert set(out) == {"T001", "61"}
    assert out["61"].values == (161.0,) and out["61"].provenance is Provenance.DERIVED
    assert out["T001"].values == (1000.0,) and out["T001"].provenance is Provenance.OFFICIAL_DATASET
    assert out["61"].scalar == "millions" and out["61"].label.fr == "Services d'enseignement"


def test_a_sector_with_a_blank_member_is_blank_not_partial():
    """
    For 14 years a non-profit member of health care is not published. Summing
    the members that are would report most of the sector as all of it, and the
    chart would show a dip that is a publication gap.
    """
    status: dict = {}
    rows = [_ioic_row("2021", "Total industries", "1000"),
            _ioic_row("2021", "Educational services [BS610]", "10"),
            _ioic_row("2021", "Educational services [NP61000]", "6"),
            _ioic_row("2021", "Government education services [GS610]", "145"),
            _ioic_row("2022", "Total industries", "1100"),
            _ioic_row("2022", "Educational services [BS610]", "11"),
            _ioic_row("2022", "Educational services [NP61000]", "", status=".."),
            _ioic_row("2022", "Government education services [GS610]", "150")]
    out = {x.code: x for x in _ioic_series(rows, status_out=status)}
    assert out["61"].periods == ("2021", "2022")
    assert out["61"].values == (161.0, None)
    assert status == {"CA/61": ("", "..")}


def test_a_member_summed_into_two_sectors_raises():
    """A member in two sectors is counted twice, and only the total would ever say so."""
    rows = [_ioic_row("2022", "Total industries", "1"), _ioic_row("2022", "Educational services [BS610]", "1")]
    with pytest.raises(ValueError, match="mapped to both"):
        _ioic_series(rows, crosswalk={"61": ["BS610"], "62": ["BS610"]})


def test_member_labels_find_the_uncoded_total_in_either_language():
    """
    The total is the cube's one member without a code, so its French wording is
    found rather than assumed. Two uncoded members make the total ambiguous.
    """
    header = ["PÉRIODE DE RÉFÉRENCE", "GÉO", "DGUID", "Industries", "VALEUR"]
    rows = [["2022", "Canada", "", "Ensemble des industries", "1"],
            ["2022", "Canada", "", "Services d'enseignement [BS610]", "1"]]
    got = statcan.member_labels(header, rows, column="Industries", codes={"T001", "BS610"}, total_code="T001")
    assert got == {"T001": "Ensemble des industries", "BS610": "Services d'enseignement"}
    with pytest.raises(ValueError, match="two members without a code"):
        statcan.member_labels(header, rows[:1] + [["2022", "Canada", "", "Autre total", "1"]],
                              column="Industries", codes={"T001", "BS610"}, total_code="T001")


def test_the_output_crosswalk_counts_every_member_once_and_guesses_nothing():
    """
    The registry's IOIC crosswalk must cover each of the twenty sectors, assign
    each member once, never list a parent aggregate beside its own children
    (BS5B0 or BS5A000 next to the finance members would count finance twice),
    and keep the one member with no NAICS code as `unallocated`.
    """
    tax = yaml.safe_load((ROOT / "registry" / "sectors.yaml").read_text(encoding="utf-8"))
    pull = tax["pulls"]["output_annual"]
    crosswalk = pull["crosswalk"]
    members = [m for ms in crosswalk.values() for m in ms]
    assert len(members) == len(set(members))
    assert set(crosswalk) - {"unallocated"} == {s["code"] for s in tax["sectors"]}
    assert crosswalk["unallocated"] == ["NP999999"]
    assert not {"BS5B0", "BS5A000", "NP000", "NPA0000"} & set(members)
    # It reads the GDP output for its sector names, so it must run after that pull.
    order = list(tax["pulls"])
    source = next(k for k, v in tax["pulls"].items() if v.get("output") == pull["labels_from"])
    assert order.index(source) < order.index("output_annual")


# ── Cube vintage ───────────────────────────────────────────────────────────────

class _FakeWDS:
    """
    Stands in for `Fetcher` at the two calls `download_cube` makes, keeping the
    real `download` rule — an existing file is skipped unless `force` — so a
    regression that stops forcing fails here instead of passing on a stub.
    """

    def __init__(self, files: dict[str, bytes]):
        self.files = files
        self.downloads: list[tuple[str, bool]] = []

    def json(self, url: str) -> dict:
        pid, lang = url.rstrip("/").split("/")[-2:]
        return {"status": "SUCCESS", "object": f"https://example.invalid/{pid}-{lang}.zip"}

    def download(self, url: str, dest: Path, *, force: bool = False) -> Path:
        self.downloads.append((url, force))
        if dest.exists() and not force:
            return dest
        dest.write_bytes(self.files[dest.name])
        return dest


def test_a_new_release_replaces_the_zip_and_a_failed_lookup_moves_nothing(tmp_path):
    """
    An existing zip was always skipped while the release stamp was fetched live,
    so the first run after a StatCan release wrote the NEW stamp over figures
    parsed from the OLD zip — and `--refresh` never reached the download. The
    file claimed a vintage it did not contain, and `verify/` could not see it.

    The zip must follow the release, and the stamp returned must be the one
    recorded for the zip on disk. When getCubeMetadata fails, the zip and its
    stamp both stay put: nothing may claim a release that was not observed.
    """
    old, new = "2026-07-29T08:30", "2026-08-28T08:30"
    dest = tmp_path / "36100434-eng.zip"
    dest.write_bytes(b"july zip")
    statcan.release_path(dest).write_text(old, encoding="utf-8")
    fetch = _FakeWDS({dest.name: b"august zip"})

    # The lookup fails: keep the zip and its recorded stamp, even under --refresh.
    for refresh in (False, True):
        got = statcan.download_cube(fetch, "36100434", "eng", tmp_path, live_release="", refresh=refresh)
        assert got == (dest, old)
    assert fetch.downloads == [] and dest.read_bytes() == b"july zip"
    assert statcan.recorded_release(dest) == old

    # The release has not moved: 141 MB is not re-fetched to learn nothing.
    assert statcan.download_cube(fetch, "36100434", "eng", tmp_path, live_release=old) == (dest, old)
    assert fetch.downloads == []

    # A newer release: the zip is replaced, and the stamp moves with it.
    assert statcan.download_cube(fetch, "36100434", "eng", tmp_path, live_release=new) == (dest, new)
    assert fetch.downloads == [("https://example.invalid/36100434-en.zip", True)]
    assert dest.read_bytes() == b"august zip" and statcan.recorded_release(dest) == new

    # --refresh reaches the download even when the release has not moved.
    statcan.download_cube(fetch, "36100434", "eng", tmp_path, live_release=new, refresh=True)
    assert fetch.downloads[-1] == ("https://example.invalid/36100434-en.zip", True)
    assert len(fetch.downloads) == 2


def test_a_zip_from_before_stamps_were_recorded_is_dated_by_when_it_was_written(tmp_path):
    """
    Zips downloaded before the sidecar existed have no recorded release.
    Re-fetching all of them once pulls SEPH's 270 MB for nothing; adopting the
    live stamp blindly is the original defect. A file written after the release
    was surely out holds that release. The stamp has no offset and is Ottawa
    time, so "surely" means reading it as UTC-5 — a zip written at 09:00 EDT on
    release day might be the old file, and is replaced.
    """
    import os
    from datetime import datetime, timezone

    release = "2026-08-28T08:30"
    dest = tmp_path / "36100434-eng.zip"
    fetch = _FakeWDS({dest.name: b"fresh"})

    def legacy_zip(written_utc: str) -> None:
        dest.write_bytes(b"legacy")
        t = datetime.fromisoformat(written_utc).replace(tzinfo=timezone.utc).timestamp()
        os.utime(dest, (t, t))

    legacy_zip("2026-09-03T21:18")
    assert statcan.download_cube(fetch, "36100434", "eng", tmp_path, live_release=release) == (dest, release)
    assert fetch.downloads == [] and dest.read_bytes() == b"legacy"
    assert statcan.recorded_release(dest) == release

    statcan.release_path(dest).unlink()
    legacy_zip("2026-08-28T13:00")
    assert statcan.download_cube(fetch, "36100434", "eng", tmp_path, live_release=release) == (dest, release)
    assert len(fetch.downloads) == 1 and dest.read_bytes() == b"fresh"


def test_the_published_stamp_is_the_parsed_zips_not_what_wds_says_at_run_time(tmp_path, monkeypatch):
    """
    The stage-level half of the vintage defect. Stage 02 stamped every series
    with getCubeMetadata's answer at run time, so the stamp described StatCan's
    latest release whatever zip was read. July's figures must carry July's stamp
    while the lookup is down, August's stamp must arrive only with August's
    month, and zips nobody can date must not be parsed at all.
    """
    sys.path.insert(0, str(ROOT / "pipeline"))
    stage = importlib.import_module("02_sectors")
    pid, july, august = "36100434", "2026-07-29T08:30", "2026-08-28T08:30"
    pull = {"pid": pid, "frequency": "monthly", "measure": "gdp_chained", "output": "national-monthly.json"}

    def cube(lang: str, periods: list[str]) -> bytes:
        en = lang == "eng"
        header = (["REF_DATE", "GEO", "North American Industry Classification System (NAICS)",
                   "UOM", "SCALAR_ID", "VALUE"] if en else
                  ["PÉRIODE DE RÉFÉRENCE", "GÉO",
                   "Système de classification des industries de l'Amérique du Nord (SCIAN)",
                   "UNITÉ DE MESURE", "IDENTIFICATEUR SCALAIRE", "VALEUR"])
        member = "All industries [T001]" if en else "Ensemble des industries [T001]"
        rows = [header] + [[p, "Canada", member, "Dollars", "6", "100"] for p in periods]
        path = _cube_zip(tmp_path / f"{lang}-{len(periods)}.zip", pid, rows, sep="," if en else ";",
                         metadata=[["Cube Title"], ["GDP" if en else "PIB"]])
        return path.read_bytes()

    raw = tmp_path / "raw"
    raw.mkdir()
    for lang in ("eng", "fra"):
        (raw / f"{pid}-{lang}.zip").write_bytes(cube(lang, ["2026-06"]))
        statcan.release_path(raw / f"{pid}-{lang}.zip").write_text(july, encoding="utf-8")
    fetch = _FakeWDS({f"{pid}-{lang}.zip": cube(lang, ["2026-06", "2026-07"]) for lang in ("eng", "fra")})

    def pull_with(live: str):
        monkeypatch.setattr(statcan, "release_time", lambda _fetch, _pid: live)
        (series,), _ = stage.pull_cube(fetch, "national_monthly", pull, {"T001"}, raw)
        return series

    s = pull_with("")
    assert (s.periods, s.release_time) == (("2026-06",), july)
    assert fetch.downloads == []

    # WDS says August but the July zip is kept. With today's `download_cube` a
    # live stamp always replaces the zip, so only this pins the payload to the
    # zip's stamp: a later "skip the 141 MB download" change must not publish
    # August's stamp over July's figures.
    real_download = statcan.download_cube
    monkeypatch.setattr(statcan, "download_cube",
                        lambda *a, **kw: real_download(*a, **{**kw, "live_release": ""}))
    s = pull_with(august)
    assert (s.periods, s.release_time) == (("2026-06",), july)
    monkeypatch.setattr(statcan, "download_cube", real_download)

    s = pull_with(august)
    assert (s.periods, s.release_time) == (("2026-06", "2026-07"), august)
    assert len(fetch.downloads) == 2

    for lang in ("eng", "fra"):
        statcan.release_path(raw / f"{pid}-{lang}.zip").unlink()
    with pytest.raises(stage.VintageUnknown, match="no recorded release"):
        pull_with("")


# ── B3: update dates ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("lang,body,written,iso", [
    ("en", "On August 15, 2026, the Tłı̨chǫ Government and the Yellowknives Dene First Nation",
     "August 15, 2026", "2026-08-15"),
    ("en", "On January 5,2026, the Montreal Port Authority obtained a permit", "January 5,2026", "2026-01-05"),
    ("en", "In July 2026, MPO began consultations with Indigenous groups", "July 2026", "2026-07"),
    ("en", "In 2022, the McIlvenna Bay Project underwent a process", "2022", "2022"),
    ("en", "The MPO is working with proponents to determine funding solutions", "", ""),
    ("fr", "Le 19 mai, 2026, le Gouvernement du Canada et Nouveau Monde Graphite", "19 mai, 2026", "2026-05-19"),
    ("fr", "Le 1er août 2026, le promoteur a déposé", "1er août 2026", "2026-08-01"),
    ("fr", "En juillet 2026, le Bureau des grands projets a entrepris", "juillet 2026", "2026-07"),
    ("fr", "Le BGP collabore avec les promoteurs", "", ""),
    ("en", "On February 30, 2026, nothing happened", "February 30, 2026", ""),
])
def test_update_dates_are_read_at_the_precision_published(lang, body, written, iso):
    """
    The portfolio timeline sorts by these. All but the `1er` and 30 February
    cases are copied from live project pages. The strict pattern this replaced
    missed "January 5,2026" and "19 mai, 2026" (the publisher's own separators)
    and had no form for "In July 2026" at all. A month-only entry must not become
    a day, an entry that names no date must not get one, and an impossible day is
    no date rather than a corrected one.
    """
    assert mpo.parse_update_date(body, lang) == (written, iso)


def _updates_page(lang, *bodies):
    parsed = []
    for body in bodies:
        written, iso = mpo.parse_update_date(body, lang)
        parsed.append(mpo.ParsedUpdate(date_verbatim=written, body=body, date_iso=iso))
    return mpo.ParsedPage(url=f"http://x/{lang}.html", title="", updates=parsed)


def test_updates_pair_by_position_and_take_the_date_from_either_page():
    """
    Where the English entry names no date and the French one does, the date is
    the French page's — it is the same entry, published in both languages. Each
    page's wording of the date is kept for its own language.
    """
    sys.path.insert(0, str(ROOT / "pipeline"))
    stage = importlib.import_module("01_projects")
    en = _updates_page("en", "The port obtained a permit that January.", "The MPO is working with proponents.")
    fr = _updates_page("fr", "Le 5 janvier 2026, le port a obtenu un permis.", "Le BGP collabore avec les promoteurs.")
    out = stage._updates(en, fr)
    assert [(u.date, u.date_verbatim, u.date_verbatim_fr) for u in out] == [
        ("2026-01-05", "", "5 janvier 2026"), ("", "", "")]
    assert all(u.body.en and u.body.fr for u in out)


def test_updates_that_do_not_line_up_are_carried_unpaired_never_dropped():
    """
    `_updates` used to keep only the English list whenever the counts differed,
    deleting every French entry — the deletion `_benefits` exists to prevent.
    Dates that disagree mean position pairs different entries, so that is
    treated the same way.
    """
    sys.path.insert(0, str(ROOT / "pipeline"))
    stage = importlib.import_module("01_projects")
    en = _updates_page("en", "On May 19, 2026, work began.")
    fr = _updates_page("fr", "Le 19 mai, 2026, les travaux ont commencé.",
                       "En juillet 2026, le BGP a entrepris des consultations.")
    out = stage._updates(en, fr)
    assert [u.body.en for u in out if u.body.en] == ["On May 19, 2026, work began."]
    assert [u.body.fr for u in out if u.body.fr] == ["Le 19 mai, 2026, les travaux ont commencé.",
                                                       "En juillet 2026, le BGP a entrepris des consultations."]
    assert not any(u.body.en and u.body.fr for u in out)
    assert [u.date for u in out] == ["2026-05-19", "2026-05-19", "2026-07"]

    same_count_different_days = stage._updates(_updates_page("en", "On May 19, 2026, work began."),
                                               _updates_page("fr", "Le 20 mai 2026, les travaux ont commencé."))
    assert len(same_count_different_days) == 2


def test_reading_more_dates_does_not_move_the_content_hash():
    """
    The content hash decides whether stage 01 appends a "content changed"
    history entry, so it may only move when the page's words move. It hashed
    `date_verbatim` — our reading of the page — and when the date parser learned
    "In July 2026" and "January 5,2026", seven projects gained history entries
    the government never caused. The hash reads the frozen pattern; the display
    reads the improved one.
    """
    from bs4 import BeautifulSoup

    block = BeautifulSoup(
        "<ul><li>In July 2026, MPO began consultations.</li>"
        "<li>On January 5,2026, the port obtained a permit.</li>"
        "<li>On May 19, 2026, work began.</li></ul>", "html.parser")
    updates = mpo._updates(block, "en")
    assert [u.date_verbatim for u in updates] == ["July 2026", "January 5,2026", "May 19, 2026"]
    assert [u.hashed_date for u in updates] == ["", "", "May 19, 2026"]
    page = mpo.ParsedPage(url="http://x/en.html", title="T", updates=updates)
    assert "\x1eJuly 2026\x1f" not in page.verbatim_blob()
    assert "\x1f\x1fIn July 2026, MPO began consultations." not in page.verbatim_blob()
    assert "\x1e\x1fIn July 2026, MPO began consultations." in page.verbatim_blob()
