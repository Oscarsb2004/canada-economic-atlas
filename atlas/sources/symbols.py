"""
atlas.sources.symbols — who each province and territory is on paper: its motto
and the description of its flag, in Canadian Heritage's words, and its flag and
coat of arms as images from Wikimedia Commons (BACKLOG R0).

THE WORDS

Canadian Heritage publishes one page per jurisdiction in each language. Its
sections carry stable ids and headings — "Motto" / "Devise", "Flag" /
"Drapeau" — and are read by heading, never by position, so a page that gains a
section cannot shift a motto into the flag's place. Text is reproduced verbatim,
markup removed. A jurisdiction whose pages have no motto section publishes none;
the two languages must agree on that.

THE IMAGES

Chosen 2026-09-13 on the owner's decision: the flag and coat of arms come from
Wikimedia Commons rather than each government. Commons records a licence per
file, and they differ — the flags are public domain, the arms drawings range from
public domain and CC0 to CC BY-SA, which requires crediting the artist. So each
file's licence, artist and Commons restriction notices ("insignia": the use of
official insignia may be restricted by law regardless of copyright) are read
from the Commons API and published beside the image, never assumed.
"""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urlencode

from atlas.core.schema import Text

SECTIONS = {"motto": {"en": "Motto", "fr": "Devise"}, "flag": {"en": "Flag", "fr": "Drapeau"}}
#: Rendering width of the committed PNGs. Some source SVGs are over 1.5 MB.
IMAGE_WIDTH = 240

_SECTION = re.compile(r'<h2 id="a\d+">(.*?)</h2>(.*?)(?=<h2)', re.S)
_TAG = re.compile(r"<[^>]+>")


class SymbolsError(ValueError):
    """A page or a Commons record is not shaped as expected."""


def _clean(fragment: str) -> str:
    return " ".join(html.unescape(_TAG.sub(" ", fragment)).split())


def _sections(page: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for heading, body in _SECTION.findall(page):
        title = _clean(heading)
        if title in out:
            raise SymbolsError(f"the page has two sections headed {title!r}")
        out[title] = _clean(body)
    return out


def read_pages(page_en: str, page_fr: str, *, where: str) -> dict[str, Any]:
    """{"motto": Text | None, "flag": Text, "modified": Text} from one jurisdiction's two pages."""
    en, fr = _sections(page_en), _sections(page_fr)
    out: dict[str, Any] = {}
    for key, heads in SECTIONS.items():
        te, tf = en.get(heads["en"]), fr.get(heads["fr"])
        if (te is None) != (tf is None):
            raise SymbolsError(f"{where}: the {key} section is in one language only")
        if key == "flag" and te is None:
            raise SymbolsError(f"{where}: no flag section")
        if te is not None and not (te and tf):
            raise SymbolsError(f"{where}: the {key} section is empty")
        out[key] = Text(en=te, fr=tf) if te is not None else None
    # No "date modified" is read: the pages carry none in their markup (checked
    # 2026-09-13), and the content hash on each page's SourceRef says when the
    # words last changed.
    return out


def commons_query_url(api: str, titles: list[str]) -> str:
    """One Commons request for every file: URLs, a PNG rendering, and the licence metadata."""
    if len(titles) > 50:
        raise SymbolsError("the Commons API takes at most 50 titles a request")
    return api + "?" + urlencode({
        "action": "query", "format": "json", "titles": "|".join(titles), "prop": "imageinfo",
        "iiprop": "url|sha1|extmetadata", "iiurlwidth": IMAGE_WIDTH,
        "iiextmetadatafilter": "LicenseShortName|LicenseUrl|Artist|Restrictions|Credit",
    })


def commons_records(response: dict[str, Any], titles: list[str]) -> dict[str, dict[str, Any]]:
    """Each requested file's record, keyed by its title as the registry writes it."""
    query = response.get("query") or {}
    # Commons normalises underscores and case; map its titles back to ours.
    back = {n["to"]: n["from"] for n in query.get("normalized", [])}
    out: dict[str, dict[str, Any]] = {}
    for page in (query.get("pages") or {}).values():
        title = back.get(page.get("title"), page.get("title"))
        if "missing" in page or not page.get("imageinfo"):
            raise SymbolsError(f"Commons has no file {title!r}")
        info = page["imageinfo"][0]
        meta = {k: _clean(str((info.get("extmetadata") or {}).get(k, {}).get("value", "")))
                for k in ("LicenseShortName", "LicenseUrl", "Artist", "Restrictions", "Credit")}
        if not meta["LicenseShortName"]:
            raise SymbolsError(f"Commons states no licence for {title!r}")
        if not info.get("thumburl"):
            raise SymbolsError(f"Commons offers no rendering of {title!r}")
        out[title] = {
            "title": title,
            "page_url": info.get("descriptionurl", ""),
            "file_url": info.get("url", ""),
            "rendering_url": info["thumburl"],
            "source_sha1": info.get("sha1", ""),
            "licence": meta["LicenseShortName"],
            "licence_url": meta["LicenseUrl"],
            "artist": meta["Artist"],
            "credit": meta["Credit"],
            "restrictions": [r for r in meta["Restrictions"].split("|") if r],
        }
    missing = set(titles) - set(out)
    if missing:
        raise SymbolsError(f"Commons returned no record for {sorted(missing)}")
    return out
