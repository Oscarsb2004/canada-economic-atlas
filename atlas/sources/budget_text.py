"""
atlas.sources.budget_text — short passages from each province and territory's
latest budget on the risks to its outlook, checked against the document itself
(BACKLOG R5).

The passages are chosen by hand in registry/budgets.yaml. This module is what
keeps that honest: it reads the document's text — each PDF page, or the whole
HTML page — and a quote that is not on its stated page fails the build.

Text extraction mangles PDFs in predictable ways, so both sides are normalised
the same way before comparing: Unicode compatibility forms (the "ﬀ" ligature),
pypdf's "/f_" glyph markers, curly apostrophes, runs of whitespace, and a space
before punctuation (Alberta's PDF extracts "per cent ." ). Nothing else is
forgiven: a word changed in the quote fails.
"""

from __future__ import annotations

import html
import io
import logging
import re
import unicodedata

import pypdf

log = logging.getLogger(__name__)


class BudgetTextError(ValueError):
    """A declared quote is not in its document where the registry says it is."""


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"/([A-Za-z]{1,2})_", r"\1", text)
    text = text.replace("’", "'").replace("‘", "'")
    text = " ".join(text.split())
    return re.sub(r"\s+([.,;:)])", r"\1", text)


def pdf_pages(body: bytes) -> list[str]:
    """Normalised text of every page, in file order."""
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = pypdf.PdfReader(io.BytesIO(body))
    return [normalise(page.extract_text() or "") for page in reader.pages]


def html_text(page: str) -> str:
    """Normalised visible text of an HTML page."""
    page = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", page, flags=re.S | re.I)
    return normalise(html.unescape(re.sub(r"<[^>]+>", " ", page)))


def check(quotes: list[dict], *, pages: list[str] | None, text: str | None, where: str) -> None:
    """Raise unless every quote is on its page (PDF) or in the page text (HTML)."""
    for q in quotes:
        want = normalise(q["text"])
        if q.get("page") is None:
            haystack = text or ""
        else:
            if pages is None or not 1 <= int(q["page"]) <= len(pages):
                raise BudgetTextError(f"{where}: page {q.get('page')} is not in the document")
            haystack = pages[int(q["page"]) - 1]
        if want not in haystack:
            raise BudgetTextError(f"{where}: quote not found on page {q.get('page')}: {q['text'][:80]!r}")
