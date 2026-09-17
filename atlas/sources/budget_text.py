"""
atlas.sources.budget_text — short passages from each province and territory's
latest budget on the risks to its outlook, checked against the document itself
(BACKLOG R5).

The passages are chosen by hand in registry/budgets.yaml. This module is what
keeps that honest: a quote that is not on its stated page fails the build. Reading
the document's text is the `document_text` acquire shell.

Text extraction mangles PDFs in predictable ways, so both sides are normalised
the same way before comparing: Unicode compatibility forms (the "ﬀ" ligature),
pypdf's "/f_" glyph markers, curly apostrophes, runs of whitespace, and a space
before punctuation (Alberta's PDF extracts "per cent ." ). Nothing else is
forgiven: a word changed in the quote fails.
"""

from __future__ import annotations

import logging

from atlas.shells.acquire.document_text import normalise

log = logging.getLogger(__name__)


class BudgetTextError(ValueError):
    """A declared quote is not in its document where the registry says it is."""


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
