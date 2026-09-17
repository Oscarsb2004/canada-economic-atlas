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

import re
from typing import Any

from atlas.core.schema import Text
from atlas.shells.acquire import commons_media, document_text

SECTIONS = {"motto": {"en": "Motto", "fr": "Devise"}, "flag": {"en": "Flag", "fr": "Drapeau"}}
#: Rendering width of the committed PNGs. Some source SVGs are over 1.5 MB.
IMAGE_WIDTH = 240

_SECTION = re.compile(r'<h2 id="a\d+">(.*?)</h2>(.*?)(?=<h2)', re.S)


class SymbolsError(ValueError):
    """A page or a Commons record is not shaped as expected."""





def _sections(page: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for heading, body in _SECTION.findall(page):
        title = document_text.strip_tags(heading)
        if title in out:
            raise SymbolsError(f"the page has two sections headed {title!r}")
        out[title] = document_text.strip_tags(body)
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
    """One Commons request for every file; see `commons_media.query_url`."""
    return commons_media.query_url(api, titles, IMAGE_WIDTH, error=SymbolsError)


def commons_records(response: dict[str, Any], titles: list[str]) -> dict[str, dict[str, Any]]:
    """Each requested file's record; see `commons_media.records`."""
    return commons_media.records(response, titles, error=SymbolsError)
