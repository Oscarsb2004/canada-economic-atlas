"""
atlas.sources.mpo — the Major Projects Office.

Two sources, joined on the project's canonical page URL:

  1. NRCan's ArcGIS service, which publishes the referred projects as GeoJSON
     with official WGS84 coordinates under the Open Government Licence. This is
     the backbone. Coordinates are never geocoded or guessed — they are the
     government's own.

  2. The canada.ca project pages, which carry everything the dataset omits:
     the description, the "Quick facts" bullets, the "Latest updates" log, and
     the rendering that fronts the map pin.

Everything taken from (2) is reproduced verbatim. In particular the dollar
figures and job counts stay as prose: the pages say "Will attract $5 billion in
investment", and turning that into a number field would be this project making a
claim in a form the source never used.

Page structure, established by inspecting the live markup rather than assumed:

    main[property=mainContentOfPage]
      section.gc-features
        div.col-md-4 × 3        h2 label + value: Proponent / Sector / Location
      section.container
        div.col-md-7            h2 "Description"     ← DOUBLED
        div.col-md-5            h2 "Quick facts"     ← not doubled
                                h3 "Benefits"
      h2 "Latest updates"                            ← not doubled
      time[property=dateModified]

The doubling is the trap. canada.ca's AEM templates emit the Proponent/Sector/
Location cards and the whole Description block twice — once wrapped in
`visible-md visible-lg`, once in `visible-xs visible-sm` — so a naive
`get_text()` returns every one of those fields twice, concatenated. Quick facts,
Benefits and Latest updates are NOT doubled, so blanket deduplication of repeated
text would instead corrupt those. The fix is structural: drop the mobile twins
once, up front, and parse what remains.
"""

from __future__ import annotations

import re
from datetime import date
from dataclasses import dataclass, field
from typing import Iterable

from bs4 import BeautifulSoup, Tag

# ── Endpoints ──────────────────────────────────────────────────────────────────

ARCGIS_BASE = (
    "https://maps-cartes.services.geo.ca/server_serveur/rest/services/NRCan/"
    "projects_referred_to_mpo_{lang}/MapServer"
)

#: Layer 1 = the 20 referred project features. Layer 2 = the 9 transformative
#: strategies, whose polygons come back empty (see `strategy_attributes`).
LAYER_PROJECTS = 1
LAYER_STRATEGIES = 2

CANADA_CA = "https://www.canada.ca"

#: The mobile half of every doubled block. Removing these leaves exactly one
#: copy of each field; the desktop wrapper is kept because it is the one that
#: carries the full markup on every page inspected.
MOBILE_ONLY = ("visible-xs", "visible-sm")

#: Section headings, per language, EXACTLY as the live pages spell them.
#:
#: Every string here was read off a rendered page, never translated by us. The
#: first attempt guessed "Faits en bref" and "Dernières mises à jour"; the pages
#: actually say "Faits saillants" and "Dernière mise à jour" — singular — so the
#: French quick facts and updates parsed as empty while every other field looked
#: correct. That is the failure mode this table exists to prevent: a wrong
#: heading does not raise, it silently yields nothing.
#:
#: Adding a language means adding a row, having read the page first.
HEADINGS: dict[str, dict[str, str]] = {
    "en": {
        "proponent":   "Proponent",
        "sector":      "Sector",
        "location":    "Location",
        "description": "Description",
        "quick_facts": "Quick facts",
        "benefits":    "Benefits",
        "updates":     "Latest updates",
    },
    "fr": {
        "proponent":   "Promoteur",
        "sector":      "Secteur",
        "location":    "Emplacement",
        "description": "Description",
        "quick_facts": "Faits saillants",
        "benefits":    "Avantages",
        "updates":     "Dernière mise à jour",
    },
}

#: ArcGIS attribute names, per language. The French service is not the English
#: one with translated values — the FIELD NAMES are French too, and `Lien`
#: points at the French page rather than the English one.
#:
#: So the two services cannot be joined on the link. They are joined on the
#: terminal slug, which is identical in both languages (`crawford.html` in each).
FIELDS: dict[str, dict[str, str]] = {
    "en": {"name": "Name", "location": "Location", "proponent": "Proponent",
           "sector": "Sector", "status": "Status", "description": "Description",
           "link": "Link"},
    "fr": {"name": "Nom", "location": "Emplacement", "proponent": "Promoteur",
           "sector": "Secteur", "status": "Etat", "description": "Description",
           "link": "Lien"},
}


def attr(props: dict, key: str, lang: str) -> str:
    """Read a canonical field out of a language-specific ArcGIS attribute bag."""
    return (props.get(FIELDS[lang][key]) or "").strip()


_WS = re.compile(r"\s+")

#: Whitespace we introduced ourselves, not the source's. Extracting text with a
#: " " separator is needed so block elements don't run together ("theImpact"),
#: but it also inserts a space before punctuation that follows an inline tag —
#: `<a>November 13, 2025</a>, the project` comes out as "2025 , the project".
#: That space is an artefact of our extraction, so removing it restores the
#: page's own wording rather than editing it.
#:
#: The character set is deliberately narrow. French typography puts a space
#: BEFORE `: ; ! ?` and before `%` ("50 %"), and these pages are captured in
#: both languages — so a broader pattern would silently rewrite correct French
#: punctuation on every FR page and call the result verbatim. Only marks that
#: neither language spaces are listed here.
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.)\]])")
_SPACE_AFTER_OPEN = re.compile(r"([(\[])\s+")

#: The date a Latest-updates entry opens with, at the precision it publishes:
#: a day ("On May 19, 2026," / "Le 19 mai 2026,"), a month ("In July 2026," /
#: "En juillet 2026,") or a year ("In 2022," / "En 2022,").
#:
#: The separators are tolerant, and ONLY the separators. The source writes
#: "On January 5,2026," once and "Le 19 mai, 2026," once, and the strict pattern
#: this replaced read each as undated in one language and dated in the other.
#: What is matched is still the publisher's date — month name, day and year as
#: written. An entry that does not open with one gets no date, never one borrowed
#: from the entries around it; and a month is never widened to a day.
#:
#: The comment on the old pattern said the date was "kept verbatim as well as
#: parsed". It was never parsed: stage 01 copied the verbatim text into the ISO
#: field, and nothing read that field until the portfolio timeline (B3).
_MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
           "septembre", "octobre", "novembre", "décembre"],
}
_MONTH_EN = "|".join(_MONTHS["en"])
_MONTH_FR = "|".join(_MONTHS["fr"])
_UPDATE_DATE: dict[str, list[tuple[str, re.Pattern[str]]]] = {
    "en": [
        ("day", re.compile(
            rf"^On\s+(?P<text>(?P<month>{_MONTH_EN})\s+(?P<day>\d{{1,2}}),?\s*(?P<year>\d{{4}}))")),
        ("month", re.compile(rf"^In\s+(?P<text>(?P<month>{_MONTH_EN})\s+(?P<year>\d{{4}})),")),
        ("year", re.compile(r"^In\s+(?P<text>(?P<year>\d{4})),")),
    ],
    "fr": [
        ("day", re.compile(
            rf"^Le\s+(?P<text>(?P<day>\d{{1,2}})(?:er)?\s+(?P<month>{_MONTH_FR}),?\s*(?P<year>\d{{4}}))")),
        ("month", re.compile(rf"^En\s+(?P<text>(?P<month>{_MONTH_FR})\s+(?P<year>\d{{4}})),")),
        ("year", re.compile(r"^En\s+(?P<text>(?P<year>\d{4})),")),
    ],
}


#: FROZEN. The pattern `date_verbatim` was read with until 2026-09-11, kept for
#: one purpose: `ParsedPage.verbatim_blob` hashes the date it captures.
#:
#: The blob hashed `date_verbatim`, which is how WE read the page rather than
#: what the page says. When the patterns above learned "In July 2026" and
#: "January 5,2026", seven project hashes moved and stage 01 appended seven
#: "content changed" history entries on a day the government changed nothing.
#: The date's words are already inside the hashed body, so this capture adds no
#: detection; it exists so that every hash recorded before that day still
#: matches an unchanged page. It is the `benefits_block_text` decision again.
#: Never edit it — improve `_UPDATE_DATE` instead.
_HASHED_UPDATE_DATE = {
    "en": re.compile(
        r"^On\s+((?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+\d{1,2},\s+\d{4})",
    ),
    "fr": re.compile(
        r"^Le\s+(\d{1,2}(?:er)?\s+(?:janvier|février|mars|avril|mai|juin|juillet|"
        r"août|septembre|octobre|novembre|décembre)\s+\d{4})",
    ),
}


def parse_update_date(body: str, lang: str) -> tuple[str, str]:
    """
    The date an update entry opens with, as (words as written, ISO 8601), or ("", "").

    ISO at the precision published — "2026-05-19", "2026-07", "2022" — because a
    month-only entry given a day would carry a date the government never wrote.
    Reduced-precision ISO strings still sort correctly against full dates. A day
    that does not exist in its month yields no ISO date, never a corrected one.
    """
    if lang not in _UPDATE_DATE:
        raise ValueError(f"no update-date patterns for language {lang!r}")
    for precision, pattern in _UPDATE_DATE[lang]:
        m = pattern.match(body)
        if not m:
            continue
        text, year = m.group("text"), int(m.group("year"))
        if precision == "year":
            return text, f"{year:04d}"
        month = _MONTHS[lang].index(m.group("month")) + 1
        if precision == "month":
            return text, f"{year:04d}-{month:02d}"
        try:
            return text, date(year, month, int(m.group("day"))).isoformat()
        except ValueError:
            return text, ""
    return "", ""


def projects_query_url(lang: str = "en", layer: int = LAYER_PROJECTS) -> str:
    """The GeoJSON query that returns every feature of `layer`."""
    return (
        f"{ARCGIS_BASE.format(lang=lang)}/{layer}/query"
        "?where=1%3D1&outFields=*&returnGeometry=true&outSR=4326&f=geojson"
    )


def strategies_query_url(lang: str = "en") -> str:
    """
    Attributes-only query for the transformative strategies.

    `f=geojson` returns an empty collection for this layer — the polygons carry
    no geometry — so we ask for `f=json` with geometry off and take the
    attributes. Their locations are prose and are mapped to provinces by hand in
    `registry/strategies.yaml`.
    """
    return (
        f"{ARCGIS_BASE.format(lang=lang)}/{LAYER_STRATEGIES}/query"
        "?where=1%3D1&outFields=*&returnGeometry=false&f=json"
    )


# ── Parsed shapes ──────────────────────────────────────────────────────────────

@dataclass(slots=True)
class ParsedFact:
    label: str
    body: str


@dataclass(slots=True)
class ParsedUpdate:
    date_verbatim: str
    body: str
    date_iso: str = ""
    #: Hashed, never displayed — see `_HASHED_UPDATE_DATE`.
    hashed_date: str = ""


@dataclass(slots=True)
class ParsedPage:
    """One project page, in one language, as published."""

    url: str
    title: str
    proponent: str = ""
    sector: str = ""
    location: str = ""
    description: str = ""
    benefits: list[str] = field(default_factory=list)
    quick_facts: list[ParsedFact] = field(default_factory=list)
    updates: list[ParsedUpdate] = field(default_factory=list)
    hero_path: str = ""
    extra_paths: list[str] = field(default_factory=list)
    date_modified: str = ""
    alternate_lang_url: str = ""

    #: The Benefits block flattened exactly as it was read before `benefits`
    #: became a list. Hashed, never displayed — see `verbatim_blob`.
    benefits_block_text: str = ""

    def verbatim_blob(self) -> str:
        """
        Every reproduced string on the page, joined, for content hashing.

        Deliberately excludes `url` and image paths: a CDN path change is not a
        change in what the government said, and hashing it would produce history
        entries with no editorial difference.

        For the same reason it hashes `benefits_block_text` rather than the
        `benefits` list. Benefits used to be extracted as one flat string; it is
        now split per bullet. That is a change in how WE read the page, not in
        what the page says, so it must not move the hash — otherwise the next
        run appends a "content changed" entry to all 18 project histories on a
        day the government changed nothing. The blob only has to flip when the
        words flip, and either form does that equally well.
        """
        parts: list[str] = [
            self.title, self.proponent, self.sector, self.location,
            self.description, self.benefits_block_text, self.date_modified,
        ]
        parts += [f"{f.label}\x1f{f.body}" for f in self.quick_facts]
        parts += [f"{u.hashed_date}\x1f{u.body}" for u in self.updates]
        return "\x1e".join(parts)


# ── Parsing ────────────────────────────────────────────────────────────────────

def normalise(text: str) -> str:
    """
    Collapse the whitespace AEM leaves in its output, changing nothing else.

    Federal page source carries `\\r\\n` and doubled spaces inside sentences
    ("the project will  produce low-carbon nickel"). Those are artefacts of the
    editor, not the text, and leaving them in means the content hash flips on a
    reflow. HTML entities are already decoded by BeautifulSoup.

    The punctuation passes undo spacing this module introduced itself; see
    `_SPACE_BEFORE_PUNCT`. Nothing here alters a word, a number, or a mark the
    source actually published.
    """
    out = _WS.sub(" ", text).strip()
    out = _SPACE_BEFORE_PUNCT.sub(r"\1", out)
    return _SPACE_AFTER_OPEN.sub(r"\1", out)


def strip_mobile_twins(soup: BeautifulSoup) -> None:
    """
    Remove the mobile copy of every doubled block, in place.

    This is the single most important line in the module — see the module
    docstring. It runs once, before any field is read, so no downstream selector
    has to think about duplication.
    """
    for cls in MOBILE_ONLY:
        for el in soup.select(f".{cls}"):
            el.decompose()


def _heading_block(main: Tag, heading: str, tags: Iterable[str] = ("h2", "h3")) -> Tag | None:
    """The container div holding `heading` and the content beneath it."""
    for tag in tags:
        for hd in main.find_all(tag):
            if normalise(hd.get_text()) == heading:
                return hd.parent
    return None


def _feature_cards(main: Tag) -> dict[str, str]:
    """
    The Proponent / Sector / Location cards from the gc-features strip.

    Read by their own h2 label rather than by position, so a future page that
    adds or reorders a card does not silently shift Sector into Location.
    """
    out: dict[str, str] = {}
    for col in main.select("section.gc-features div[class*=col-md-4]"):
        hd = col.find(re.compile(r"^h[2-4]$"))
        if not hd:
            continue
        label = normalise(hd.get_text())
        hd.extract()
        out[label] = normalise(col.get_text(" "))
    return out


def _quick_facts(block: Tag | None) -> list[ParsedFact]:
    """
    The labelled bullets, split on their own `<strong>` label.

    Markup is `<li><strong>Label:</strong> body</li>`, with the colon and
    sometimes a trailing space inside the strong. The label set varies per
    project, so it is data rather than an enum.
    """
    if block is None:
        return []
    facts: list[ParsedFact] = []
    for li in block.select("ul li"):
        strong = li.find("strong")
        if strong:
            label = normalise(strong.get_text()).rstrip(":").strip()
            strong.extract()
            facts.append(ParsedFact(label=label, body=normalise(li.get_text(" "))))
        else:
            facts.append(ParsedFact(label="", body=normalise(li.get_text(" "))))
    return facts


def _benefits(block: Tag | None) -> list[str]:
    """
    The Benefits bullets, one string per `<li>`.

    The markup is `<h3>Benefits</h3><ul class="lst-spcd"><li>…</li></ul>` on all
    18 pages, in both languages. Flattening it with `get_text(" ")` — which is
    what this did before — runs the bullets into one paragraph and buries the
    heading word inside the result, so the reader sees prose the page never
    published as prose. The list IS the government's structure; keeping it is
    the same decision `_quick_facts` makes.

    The heading is dropped rather than carried, because the viewer supplies its
    own. `<abbr>` tags inside the bullets (the DGR pages use them heavily) are
    flattened to their visible text, not their title attribute — the title is
    markup the page renders as a tooltip, not a sentence it published.

    Falls back to the block's paragraphs if a future page drops the `<ul>`, so
    a template change degrades to one bullet instead of to nothing.
    """
    if block is None:
        return []

    items = [normalise(li.get_text(" ")) for li in block.select("ul li")]
    if items:
        return [i for i in items if i]

    for hd in block.find_all(re.compile(r"^h[2-4]$")):
        hd.extract()
    text = normalise(block.get_text(" "))
    return [text] if text else []


def _updates(block: Tag | None, lang: str = "en") -> list[ParsedUpdate]:
    """
    The Latest-updates log, newest first as published.

    Entries are prose with embedded links ("On March 3, 2026, the Impact
    Assessment Agency of Canada formally began the..."), and on some entries the
    date itself is inside the anchor. So the date is extracted where the leading
    phrase matches and left empty otherwise — never inferred from position.
    """
    if block is None:
        return []
    out: list[ParsedUpdate] = []
    for li in block.select("li"):
        body = normalise(li.get_text(" "))
        verbatim, iso = parse_update_date(body, lang)
        hashed = _HASHED_UPDATE_DATE.get(lang, _HASHED_UPDATE_DATE["en"]).match(body)
        out.append(ParsedUpdate(date_verbatim=verbatim, body=body, date_iso=iso,
                                hashed_date=hashed.group(1) if hashed else ""))
    return out


def _images(main: Tag) -> tuple[str, list[str]]:
    """
    The hero rendering and any secondary images.

    The hero is a `data-bgimg` attribute on a div, NOT an `<img>` tag, so
    `find_all('img')` misses it entirely. The attribute is always read rather
    than reconstructed from the page slug: three project folders do not match
    their slug, and one official filename contains a typo ("Altantic"), so any
    constructed path 404s on those.
    """
    hero = ""
    el = main.select_one("[data-bgimg]")
    if el:
        hero = el["data-bgimg"].strip()

    extras: list[str] = []
    for img in main.select('img[src*="/content/dam/"]'):
        src = img.get("src", "").strip()
        if src and src != hero:
            extras.append(src)
    return hero, extras


def parse_page(html: str, url: str, lang: str = "en") -> ParsedPage:
    """
    Parse one project page in one language.

    `lang` selects the heading table; it is not a translation switch. Passing
    the wrong one yields empty sections rather than an error, which is exactly
    why `pipeline/01_projects.py` asserts that EN and FR agree on section counts.
    """
    if lang not in HEADINGS:
        raise ValueError(f"no heading table for language {lang!r}; add one to HEADINGS")
    h = HEADINGS[lang]

    soup = BeautifulSoup(html, "lxml")
    strip_mobile_twins(soup)

    main = soup.select_one("main[property=mainContentOfPage]") or soup.select_one("main")
    if main is None:
        raise ValueError(f"{url}: no <main> content element")

    h1 = main.find("h1")
    cards = _feature_cards(main)

    desc_block = _heading_block(main, h["description"])
    description = ""
    if desc_block is not None:
        for hd in desc_block.find_all(re.compile(r"^h[2-4]$")):
            hd.extract()
        description = normalise(desc_block.get_text(" "))

    benefits_block = _heading_block(main, h["benefits"], tags=("h3", "h2"))
    if benefits_block is desc_block:
        benefits_block = None
    benefits = _benefits(benefits_block)
    benefits_flat = normalise(benefits_block.get_text(" ")) if benefits_block else ""

    hero, extras = _images(main)
    date_modified_el = soup.select_one("time[property=dateModified]")
    alt = soup.select_one("#wb-lng a[href], section#wb-lng a[href]")

    return ParsedPage(
        url=url,
        title=normalise(h1.get_text()) if h1 else "",
        proponent=cards.get(h["proponent"], ""),
        sector=cards.get(h["sector"], ""),
        location=cards.get(h["location"], ""),
        description=description,
        benefits=benefits,
        benefits_block_text=benefits_flat,
        quick_facts=_quick_facts(_heading_block(main, h["quick_facts"])),
        updates=_updates(_heading_block(main, h["updates"]), lang=lang),
        hero_path=hero,
        extra_paths=extras,
        date_modified=date_modified_el.get_text(strip=True) if date_modified_el else "",
        alternate_lang_url=(CANADA_CA + alt["href"]) if alt and alt["href"].startswith("/") else "",
    )


# ── Coverage ───────────────────────────────────────────────────────────────────

#: A project slug, which is also a filename and a URL path segment.
_SAFE_SLUG = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

#: The ways canada.ca links to its own pages absolutely.
_SITE_PREFIXES = (CANADA_CA, "http://www.canada.ca", "//www.canada.ca")


def _section_href(href: str, section_path: str) -> str:
    """
    A link as a crawlable path inside `section_path`, or "" if it is not one.

    The crawl used to test `href.startswith(section_path)`, which was wrong in
    both directions. An ABSOLUTE link — `https://www.canada.ca/en/…` — never
    starts with a path, so a page the CMS happened to link absolutely was never
    crawled and its group never reported. And a bare prefix admits a sibling
    section whose name merely begins the same way:
    `…/major-projects-office-archive/x.html` starts with
    `…/major-projects-office`. The section is its own page or a path that
    continues with "/", and nothing else.

    (This replaces `index_slugs`, which read one index page, was superseded by
    the crawl, and had no caller left but its own tests.)
    """
    href = href.split("#")[0].split("?")[0].strip()
    for prefix in _SITE_PREFIXES:
        if href.startswith(prefix):
            href = href[len(prefix):]
            break
    if not (href.startswith("/") and href.endswith(".html")):
        return ""
    if href == section_path + ".html" or href.startswith(section_path + "/"):
        return href
    return ""


def crawl_section(fetch, section_path: str, *, max_pages: int = 300) -> dict:
    """
    Walk a whole canada.ca section and report what is in it, grouped by path.

    WHY A CRAWL RATHER THAN A LIST OF INDEX PAGES

    Reading two named index pages answers "did we get every project the
    projects page lists". It cannot answer "did a THIRD kind of page appear",
    which is the question that actually matters — a coverage check built from
    hardcoded path markers is blind to precisely the category nobody thought
    of. Discovering the section's shape and reporting every group of sibling
    pages moves that from an assumption to an observation.

    Returns groups keyed by parent path — `projects/national` ->
    ["aesc", "contrecoeur", ...] — plus every link that failed, because a
    broken link on the source is a finding too: canada.ca links a "Projects
    designated under the Building Canada Act" page that 404s, and that is a
    category to watch for rather than one to ignore.

    Breadth-first and bounded. `max_pages` is a stop, not a target: a template
    change that starts linking outside the section should end the crawl, not
    walk canada.ca.
    """
    section_path = section_path.rstrip("/")
    seen: set[str] = set()
    queue: list[str] = [section_path + ".html"]
    groups: dict[str, set[str]] = {}
    broken: list[dict] = []

    while queue and len(seen) < max_pages:
        path = queue.pop(0)
        if path in seen:
            continue
        seen.add(path)

        try:
            html = fetch.text(CANADA_CA + path)
        except Exception as exc:                          # noqa: BLE001
            broken.append({"path": path, "error": str(exc)[:160]})
            continue

        rel = path[len(section_path):].strip("/")[: -len(".html")]
        parent, _, slug = rel.rpartition("/")
        if parent and _SAFE_SLUG.match(slug):
            groups.setdefault(parent, set()).add(slug)

        soup = BeautifulSoup(html, "lxml")
        main = soup.select_one("main[property=mainContentOfPage]") or soup.select_one("main")
        if main is None:
            continue
        for a in main.find_all("a", href=True):
            href = _section_href(a["href"], section_path)
            if href and href not in seen:
                queue.append(href)

    return {
        "pages_crawled": len(seen),
        "groups": {k: sorted(v) for k, v in sorted(groups.items())},
        "broken_links": broken,
    }


def slug_from_url(url: str) -> str:
    """
    `.../national/crawford.html` → `crawford`.

    The result is used to name files under `data/raw/media/` and to build the
    asset paths the web app requests, so it is validated rather than trusted.
    A path segment of `..` — from a URL ending `/../` — would otherwise write
    outside the media directory. The source is a federal site and this is not a
    live threat; it is three lines to make it impossible instead of unlikely.
    """
    slug = url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".html").strip().lower()
    if not _SAFE_SLUG.match(slug):
        raise ValueError(f"refusing unsafe slug {slug!r} from {url!r}")
    return slug
