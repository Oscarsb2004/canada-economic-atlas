"""
Stage 01 — Major Projects Office: projects, strategies, verbatim text, images.

    python pipeline/01_projects.py [--limit N] [--no-images] [--refresh]

Joins two sources on the canonical page URL:

    NRCan ArcGIS  →  official WGS84 coordinates, sector, status, proponent
    canada.ca     →  the description, Quick facts, Latest updates, the rendering

Outputs
    data/events/major-projects-office/projects.json    current state
    data/events/major-projects-office/strategies.json  current state
    data/history/<slug>/<retrieved_at>.json            append-only, on change only
    web/public/media/{thumb,web}/                      derived renderings

Two structural facts drive most of the code below, and both were established by
reading the live sources rather than assumed:

  The ArcGIS layer publishes 20 point features for 18 projects. The North Coast
  Transmission Line ships three separately named phase points that all link to
  one page, so features are grouped on `Link` and become `Site`s of one project.

  Federal pages are edited in place — Crawford gained a March 2026 update long
  after its November 2025 referral, and `Date modified` moves with no
  announcement. So writes to `data/history/` are append-only and conditional on
  the content hash changing. A run that finds nothing new writes nothing.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas import media
from atlas.core import registry as R
from atlas.core.jsonio import write_if_changed
from atlas.core.schema import (
    Geometry, GeometryKind, MediaRef, Project, Provenance,
    QuickFact, Site, SourceRef, Text, Update, to_jsonable,
)
from atlas.net import Fetcher
from atlas.sources import mpo

log = logging.getLogger("01_projects")

EVENT_SLUG = "major-projects-office"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _geometry_for(coords: list, location: str) -> Geometry:
    """
    Classify a feature's geometry by how many points the source published.

    One point is a site. Two points are the endpoints of a route — a highway, a
    pipeline — and must be drawn as a line, because dropping a pin at one end of
    the Mackenzie Valley Highway asserts a location the source does not give.
    """
    pts = tuple((float(c[0]), float(c[1])) for c in coords)
    kind = {0: GeometryKind.ABSENT, 1: GeometryKind.POINT}.get(len(pts), GeometryKind.CORRIDOR)
    return Geometry(kind=kind, coordinates=pts, location_verbatim=location, approximate=True)


def _pair(en: str, fr: str) -> Text:
    return Text(en=en or "", fr=fr or "")


def _fetch_features(fetch: Fetcher, lang: str) -> dict[str, list[dict]]:
    """
    ArcGIS project features, grouped by project slug.

    Grouped by slug rather than by link because the French service is a separate
    dataset with French field names whose `Lien` points at the French page — so
    the two languages share no URL. The terminal slug is identical in both
    (`crawford.html` either way), which makes it the only usable join key.
    """
    data = fetch.json(mpo.projects_query_url(lang))
    grouped: dict[str, list[dict]] = defaultdict(list)
    for feat in data.get("features", []):
        link = mpo.attr(feat["properties"], "link", lang)
        grouped[mpo.slug_from_url(link)].append(feat)
    return grouped


def _fetch_strategy_attrs(fetch: Fetcher, lang: str) -> dict[str, dict]:
    """
    Strategy attributes, keyed by slug.

    Geometry is requested off deliberately: this layer's polygons come back
    empty under `f=geojson`, while the attributes are fine under `f=json`. Their
    locations are prose, hand-mapped in registry/strategies.yaml.
    """
    data = fetch.json(mpo.strategies_query_url(lang))
    return {
        mpo.slug_from_url(mpo.attr(f["attributes"], "link", lang)): f["attributes"]
        for f in data.get("features", [])
    }


def _quick_facts(en: mpo.ParsedPage, fr: mpo.ParsedPage) -> tuple[QuickFact, ...]:
    """
    Pair EN and FR bullets positionally.

    Positional pairing is safe only because the counts are asserted equal by the
    caller — the pages are generated from one source and list facts in the same
    order. When the counts disagree the caller drops the FR side rather than
    pairing a French label to an unrelated English one.
    """
    if len(en.quick_facts) != len(fr.quick_facts):
        return tuple(QuickFact(label=_pair(f.label, ""), body=_pair(f.body, ""))
                     for f in en.quick_facts)
    return tuple(
        QuickFact(label=_pair(e.label, f.label), body=_pair(e.body, f.body))
        for e, f in zip(en.quick_facts, fr.quick_facts)
    )


def _benefits(en: mpo.ParsedPage, fr: mpo.ParsedPage) -> tuple[Text, ...]:
    """
    Pair the Benefits bullets EN-to-FR, positionally, like the quick facts.

    Same safety argument as `_quick_facts`: both language pages are generated
    from one source and list the bullets in the same order, so position is a
    valid key — but only while the counts agree. When they do not, pairing
    bullet 3 to bullet 4 would put a French sentence under an unrelated English
    one and still look entirely right, so nothing is paired.

    Where this differs from `_quick_facts` is what happens to the unmatched
    side. A quick fact that loses its French label is still shown; a benefit
    that loses its French bullet would DISAPPEAR, because the bullet is the
    whole record. The French Taltson page really does publish a fifth benefit
    the English page omits (on integrating the grids north and south of Great
    Slave Lake), and dropping the FR side would delete published federal text
    from the app entirely — the one thing this pipeline exists not to do.

    So on a mismatch both lists are carried whole and unpaired: English bullets
    with an empty `fr`, then French bullets with an empty `en`. Each language
    then renders its own source list, complete, and no sentence is presented as
    the translation of another. `ProjectViewer` does that selection.
    """
    if len(en.benefits) == len(fr.benefits):
        return tuple(_pair(e, f) for e, f in zip(en.benefits, fr.benefits))
    return (tuple(Text(en=b, fr="") for b in en.benefits)
            + tuple(Text(en="", fr=b) for b in fr.benefits))


def _updates(en: mpo.ParsedPage, fr: mpo.ParsedPage) -> tuple[Update, ...]:
    if len(en.updates) != len(fr.updates):
        return tuple(Update(date=u.date_verbatim, date_verbatim=u.date_verbatim,
                            body=_pair(u.body, "")) for u in en.updates)
    return tuple(
        Update(date=e.date_verbatim, date_verbatim=e.date_verbatim, body=_pair(e.body, f.body))
        for e, f in zip(en.updates, fr.updates)
    )


def _images(fetch: Fetcher, page: mpo.ParsedPage, slug: str, do_images: bool) -> tuple[MediaRef, ...]:
    """
    Download the hero and derive the two committed sizes.

    The hero is a `data-bgimg` attribute, never an <img>, and the path is always
    read from the page: three project folders do not match their slug and one
    official filename contains a typo, so any constructed path 404s on those.
    """
    if not page.hero_path:
        log.warning("%s: no hero image on the page", slug)
        return ()

    url = mpo.CANADA_CA + page.hero_path
    if not do_images:
        return (MediaRef(source_url=url, role="hero", alt=_pair(page.title, "")),)

    raw = R.DATA_DIR / "raw" / "media" / f"{slug}{Path(page.hero_path).suffix}"
    fetch.download(url, raw)
    thumb, web = media.derive(raw, R.WEB_PUBLIC_DIR, slug, "hero")
    return (MediaRef(source_url=url, thumb=thumb, web=web, role="hero",
                     alt=_pair(page.title, "")),)





def _write_history(slug: str, payload: dict, digest: str) -> bool:
    """
    Append a history entry, but only when the content hash has moved.

    Returns True when something was written. The guard is what keeps the history
    directory a record of editorial change rather than a log of crawl times.
    """
    hist_dir = R.DATA_DIR / "history" / slug
    hist_dir.mkdir(parents=True, exist_ok=True)

    previous = sorted(hist_dir.glob("*.json"))
    if previous:
        last = json.loads(previous[-1].read_text(encoding="utf-8"))
        if last.get("content_sha256") == digest:
            return False

    stamp = payload["retrieved_at"].replace(":", "").replace("-", "")
    (hist_dir / f"{stamp}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return True


# ── Build ──────────────────────────────────────────────────────────────────────

def _coverage_manifest(fetch: Fetcher, arcgis_slugs: list[str]) -> dict:
    """
    What each source says exists, side by side, as a committed record.

    Three lists per kind: what the website's index page links to, what the
    ArcGIS service publishes, and the difference. The difference is the whole
    point — `only_on_site` is a project with a page and no map presence, and
    nothing in this pipeline would otherwise notice it.

    A failed index fetch records `null` rather than an empty list, because an
    empty list would read as "the site lists nothing" and silently pass a
    coverage check that never ran.
    """
    src = R.source("mpo_pages")
    declared: dict[str, str] = src.get("record_groups", {})

    try:
        crawl = mpo.crawl_section(fetch, src["section_en"])
    except Exception as exc:                              # noqa: BLE001
        log.warning("section crawl failed, coverage not checked this run: %s", exc)
        return {kind: {"site_index": None, "reason": str(exc)[:200]}
                for kind in set(declared.values())}

    log.info("crawled %d pages under %s", crawl["pages_crawled"], src["section_en"])
    for link in crawl["broken_links"]:
        log.warning("broken link on the source: %s (%s)", link["path"], link["error"][:80])

    out: dict[str, dict] = {}
    for group, kind in declared.items():
        listed = crawl["groups"].get(group)
        if listed is None:
            log.error("declared record group %r found no pages — the site was "
                      "restructured, or the path in sources.yaml is stale", group)
            out[kind] = {"site_index": None, "reason": f"group {group!r} not found by the crawl"}
            continue

        entry: dict = {"site_index": listed, "site_index_group": group}
        if kind == "projects":
            entry["arcgis"] = arcgis_slugs
            entry["only_on_site"] = sorted(set(listed) - set(arcgis_slugs))
            entry["only_in_arcgis"] = sorted(set(arcgis_slugs) - set(listed))
            if entry["only_on_site"]:
                log.warning("listed on canada.ca but ABSENT from the map service: %s",
                            entry["only_on_site"])
            if entry["only_in_arcgis"]:
                log.warning("in the map service but not listed on canada.ca: %s",
                            entry["only_in_arcgis"])
        out[kind] = entry

    # Groups the crawl found that nothing claims. A single sibling is usually a
    # sub-page of a record — Pathways Plus has a memorandum of understanding
    # under it — so the signal is a group with SEVERAL members, which is what a
    # new category of referred item looks like on its first day.
    out["_discovered"] = {
        "pages_crawled": crawl["pages_crawled"],
        "groups": {g: len(v) for g, v in crawl["groups"].items()},
        "undeclared_groups": {
            g: v for g, v in crawl["groups"].items() if g not in declared
        },
        "broken_links": crawl["broken_links"],
    }
    return out


def build_project(fetch: Fetcher, slug: str, feats_en: list[dict],
                  feats_fr: list[dict], do_images: bool) -> tuple[Project, bool]:
    """One project, from its ArcGIS features plus its EN and FR pages."""
    log.info("· %s", slug)
    url_en = mpo.attr(feats_en[0]["properties"], "link", "en")

    page_en = mpo.parse_page(fetch.text(url_en), url_en, lang="en")
    url_fr = page_en.alternate_lang_url
    page_fr = (mpo.parse_page(fetch.text(url_fr), url_fr, lang="fr")
               if url_fr else mpo.ParsedPage(url="", title=""))

    if url_fr and len(page_en.quick_facts) != len(page_fr.quick_facts):
        log.warning("%s: EN has %d quick facts, FR has %d — dropping the FR side",
                    slug, len(page_en.quick_facts), len(page_fr.quick_facts))
    if url_fr and len(page_en.benefits) != len(page_fr.benefits):
        log.warning("%s: EN has %d benefits, FR has %d — carrying both lists "
                    "unpaired so neither loses a bullet",
                    slug, len(page_en.benefits), len(page_fr.benefits))

    props_en = feats_en[0]["properties"]
    props_fr = feats_fr[0]["properties"] if feats_fr else {}

    sites = tuple(
        Site(name=_pair(mpo.attr(f["properties"], "name", "en"),
                        (mpo.attr(feats_fr[i]["properties"], "name", "fr")
                         if i < len(feats_fr) else "")),
             geometry=_geometry_for(f["geometry"]["coordinates"],
                                    mpo.attr(f["properties"], "location", "en")))
        for i, f in enumerate(feats_en)
    )

    retrieved = _now()
    sources = (
        SourceRef(url=mpo.projects_query_url("en"), retrieved_at=retrieved,
                  provenance=Provenance.OFFICIAL_DATASET, licence="ogl-canada-2.0"),
        SourceRef(url=url_en, retrieved_at=retrieved, provenance=Provenance.PAGE_VERBATIM,
                  licence="ogl-canada-2.0",
                  content_sha256=SourceRef.hash_content(page_en.verbatim_blob())),
    )

    project = Project(
        slug=slug,
        event_slug=EVENT_SLUG,
        name=_pair(page_en.title or mpo.attr(props_en, "name", "en"),
                   page_fr.title or mpo.attr(props_fr, "name", "fr")),
        proponent=_pair(page_en.proponent or mpo.attr(props_en, "proponent", "en"),
                        page_fr.proponent or mpo.attr(props_fr, "proponent", "fr")),
        sector=mpo.attr(props_en, "sector", "en") or page_en.sector,
        status=_pair(mpo.attr(props_en, "status", "en"), mpo.attr(props_fr, "status", "fr")),
        description=_pair(page_en.description, page_fr.description),
        sites=sites,
        quick_facts=_quick_facts(page_en, page_fr),
        benefits=_benefits(page_en, page_fr),
        updates=_updates(page_en, page_fr),
        media=_images(fetch, page_en, slug, do_images),
        page_url=_pair(url_en, url_fr),
        sources=sources,
    )

    digest = SourceRef.hash_content(page_en.verbatim_blob() + "\x1e" + page_fr.verbatim_blob())
    changed = _write_history(slug, {
        "slug": slug,
        "retrieved_at": retrieved,
        "content_sha256": digest,
        "date_modified_en": page_en.date_modified,
        "project": to_jsonable(project),
    }, digest)

    return project, changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0, help="only build N projects (smoke test)")
    ap.add_argument("--no-images", action="store_true", help="skip image download and derivation")
    ap.add_argument("--refresh", action="store_true", help="bypass the HTTP cache")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    event = R.event(EVENT_SLUG)
    fetch = Fetcher(cache_dir=R.DATA_DIR / "raw" / "cache", use_cache=not args.refresh)

    log.info("Stage 01 — %s", event.title_en)

    feats_en = _fetch_features(fetch, "en")
    feats_fr = _fetch_features(fetch, "fr")
    n_features = sum(len(v) for v in feats_en.values())

    # The registry states what the source should contain. A silent change in
    # either number would alter what the map shows without anyone noticing.
    expected = event.expected
    if n_features != expected.get("features") or len(feats_en) != expected.get("projects"):
        log.warning("source shape changed: %d features / %d projects, registry expects %s",
                    n_features, len(feats_en), expected)

    log.info("%d features → %d projects", n_features, len(feats_en))

    # Coverage, against the website's own listing rather than against a number
    # we wrote down. Everything above reads the ArcGIS service; the site is a
    # separate publication with its own cadence, so a project that has a page
    # but has not yet reached the map service is invisible to every check that
    # only counts features. The manifest is committed so `verify/` can compare
    # offline, which is the point — a coverage claim that needs the network is
    # a coverage claim nobody runs.
    manifest = _coverage_manifest(fetch, sorted(feats_en))

    slugs = sorted(feats_en)
    if args.limit:
        slugs = slugs[: args.limit]

    projects, changed = [], 0
    for slug in slugs:
        try:
            project, did_change = build_project(
                fetch, slug, feats_en[slug], feats_fr.get(slug, []), not args.no_images
            )
            projects.append(project)
            changed += did_change
        except Exception as exc:                       # noqa: BLE001 — one bad page must not
            log.error("%s FAILED: %s", slug, exc)      # abandon the other 17

    # Strategies: attributes only, joined to the hand-made province mapping.
    strategies = []
    attrs_fr = _fetch_strategy_attrs(fetch, "fr")
    attrs_en = _fetch_strategy_attrs(fetch, "en")

    # The French service keys on the FRENCH page slug, which is usually — but
    # not always — the same string. `critical-minerals` is published as
    # `mineraux-critiques`, so a join on slug equality alone drops its French
    # and nothing says so. The registry declares the exception; this asserts
    # that the declaration is complete, because an unmatched French feature is
    # the signature of the next one.
    fr_keys = {(R.strategy(s).fr_key if R.strategy(s) else s): s for s in attrs_en}
    unmatched = sorted(set(attrs_fr) - set(fr_keys))
    if unmatched:
        log.error("French strategy features match no English slug: %s. Add `slug_fr:` "
                  "to registry/strategies.yaml for each, or the French is dropped "
                  "silently.", unmatched)

    for slug, attrs in sorted(attrs_en.items()):
        mapped = R.strategy(slug)
        fr = attrs_fr.get(mapped.fr_key if mapped else slug, {})
        strategies.append({
            "slug": slug,
            "name": {"en": mpo.attr(attrs, "name", "en"), "fr": mpo.attr(fr, "name", "fr")},
            "sector": mpo.attr(attrs, "sector", "en"),
            "location_verbatim": {"en": mpo.attr(attrs, "location", "en"),
                                  "fr": mpo.attr(fr, "location", "fr")},
            "description": {"en": mpo.attr(attrs, "description", "en"),
                            "fr": mpo.attr(fr, "description", "fr")},
            "page_url": {"en": mpo.attr(attrs, "link", "en"),
                         "fr": mpo.attr(fr, "link", "fr")},
            # Our reading of the prose, marked as ours.
            "provinces": list(mapped.provinces) if mapped else [],
            "draws_region": bool(mapped and mapped.draws_region),
            "provenance": Provenance.DERIVED.value if mapped else Provenance.ABSENT.value,
        })
        if not mapped:
            log.warning("strategy %s has no entry in registry/strategies.yaml", slug)

    out_dir = R.DATA_DIR / "events" / EVENT_SLUG
    out_dir.mkdir(parents=True, exist_ok=True)

    wrote_p = write_if_changed(out_dir / "projects.json", {
        "event": EVENT_SLUG, "generated_at": _now(), "projects": to_jsonable(projects)})
    wrote_s = write_if_changed(out_dir / "strategies.json", {
        "event": EVENT_SLUG, "generated_at": _now(), "strategies": strategies})
    write_if_changed(out_dir / "coverage.json", {
        "event": EVENT_SLUG, "generated_at": _now(), "sources": manifest})

    corridors = sum(1 for p in projects for s in p.sites if s.geometry.kind is GeometryKind.CORRIDOR)
    log.info("%d projects (%d corridor sites), %d strategies", len(projects), corridors, len(strategies))
    log.info("projects.json %s · strategies.json %s · %d history entries added",
             "updated" if wrote_p else "unchanged",
             "updated" if wrote_s else "unchanged", changed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
