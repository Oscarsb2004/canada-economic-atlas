"""
Tests written to explain the failure they prevent.

Every case here corresponds to something that actually went wrong while
building this pipeline, or to a source quirk that fails SILENTLY — which is the
dangerous kind, because the output looks plausible and nothing raises.
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest
import yaml

from atlas.core import registry as R
from atlas.core.schema import (
    Geometry, GeometryKind, Provenance, Series, SourceRef, Text, to_jsonable,
)
from atlas.sources import companies as C
from atlas.sources import mpo
from atlas.sources import statcan

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


INDEX_PAGE = """
<html><body>
  <header><a href="/en/privy-council/major-projects-office/projects/national/header-junk.html">nav</a></header>
  <main property="mainContentOfPage">
    <a href="/en/privy-council/major-projects-office/projects/national/alpha.html">Alpha</a>
    <a href="/en/privy-council/major-projects-office/projects/national/beta.html">Beta</a>
    <a href="/en/privy-council/major-projects-office/projects/national/alpha.html">Alpha again</a>
    <a href="/en/privy-council/major-projects-office/projects/map.html">Map</a>
    <a href="https://example.org/elsewhere.html">Off site</a>
  </main>
  <footer><a href="/en/privy-council/major-projects-office/projects/national/footer-junk.html">f</a></footer>
</body></html>
"""


def test_index_slugs_reads_only_the_main_content():
    """
    The coverage oracle must count projects, not navigation.

    canada.ca's header, footer and breadcrumb all link into this section. A
    document-wide scan inflates the count with pages that are not projects,
    which is worse than undercounting: it reports coverage that was never
    checked. Deduplicated and sorted so two runs over an unchanged page compare
    equal regardless of DOM order.
    """
    assert mpo.index_slugs(INDEX_PAGE, "/projects/national/") == ["alpha", "beta"]


def test_index_slugs_ignores_pages_outside_the_detail_path():
    """`projects/map.html` sits in the section and is not a project."""
    got = mpo.index_slugs(INDEX_PAGE, "/projects/national/")
    assert "map" not in got and "elsewhere" not in got


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


def test_corridor_anchor_walks_the_route_rather_than_averaging_ends():
    """
    With two endpoints the two agree, which is exactly why averaging looks
    correct today and is wrong on the first route that arrives with a third
    vertex. An L-shaped route's halfway point is along the path, not at the
    centre of its bounding box.
    """
    bent = Geometry(kind=GeometryKind.CORRIDOR,
                    coordinates=((0.0, 0.0), (0.0, 10.0), (10.0, 10.0)))
    lon, lat = bent.anchor
    # Halfway along a 10-then-10 path is the corner region, near (0, 10) —
    # NOT the endpoint average of (5, 5).
    assert lat > 9.0 and lon < 1.0


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


def test_vector_batch_cap_is_the_undocumented_300():
    """
    getDataFromVectorsAndLatestNPeriods accepts 300 vectors and returns HTTP 416
    at 400. It is documented nowhere. Bulk CSV avoids the path entirely, but the
    incremental refresh still uses it.
    """
    assert statcan.VECTOR_BATCH_MAX == 300


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
    for s in R.strategies():
        assert all(isinstance(p, str) for p in s.provinces), s.slug
    critical = R.strategy("critical-minerals")
    assert critical is not None and "ON" in critical.provinces


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


# ── The independence rule, enforced ────────────────────────────────────────────

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
