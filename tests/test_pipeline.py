"""
Tests written to explain the failure they prevent.

Every case here corresponds to something that actually went wrong while
building this pipeline, or to a source quirk that fails SILENTLY — which is the
dangerous kind, because the output looks plausible and nothing raises.
"""

from __future__ import annotations

import ast
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
