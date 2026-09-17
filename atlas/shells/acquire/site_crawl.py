"""
atlas.shells.acquire.site_crawl — every page under one section of a website, grouped by path.

(Moved from atlas/readers/mpo.py in step S2 of docs/REBUILD.md; unchanged in
behaviour. Card: registry/shells/site_crawl.yaml.)
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

SAFE_SLUG = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

#: The ways canada.ca links to its own pages absolutely.


def _section_href(href: str, site: str, section_path: str) -> str:
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
    host = site.split("://", 1)[-1]
    for prefix in (site, "http://" + host, "//" + host):
        if href.startswith(prefix):
            href = href[len(prefix):]
            break
    if not (href.startswith("/") and href.endswith(".html")):
        return ""
    if href == section_path + ".html" or href.startswith(section_path + "/"):
        return href
    return ""


def crawl_section(fetch, site: str, section_path: str, *, max_pages: int = 300) -> dict:
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
            html = fetch.text(site + path)
        except Exception as exc:                          # noqa: BLE001
            broken.append({"path": path, "error": str(exc)[:160]})
            continue

        rel = path[len(section_path):].strip("/")[: -len(".html")]
        parent, _, slug = rel.rpartition("/")
        if parent and SAFE_SLUG.match(slug):
            groups.setdefault(parent, set()).add(slug)

        soup = BeautifulSoup(html, "lxml")
        main = soup.select_one("main[property=mainContentOfPage]") or soup.select_one("main")
        if main is None:
            continue
        for a in main.find_all("a", href=True):
            href = _section_href(a["href"], site, section_path)
            if href and href not in seen:
                queue.append(href)

    return {
        "pages_crawled": len(seen),
        "groups": {k: sorted(v) for k, v in sorted(groups.items())},
        "broken_links": broken,
    }
