"""
atlas.shells.check.verbatim_quotes — every quote is in its document, where it says it is.

(Taken from `check` in atlas/sources/budget_text.py in step S3 of
docs/REBUILD.md; unchanged in behaviour. Card: registry/shells/verbatim_quotes.yaml.)

A quote carries a page number, or `page: null` for a document with no pages (an
HTML page). Both the quote and the document are normalised the same way
(`document_text.normalise`), so extraction artefacts are forgiven and nothing
else is: a changed word fails.
"""

from __future__ import annotations

from atlas.shells.acquire.document_text import normalise


class QuoteError(ValueError):
    """A declared quote is not in its document where its locator says."""


def check(quotes: list[dict], *, pages: list[str] | None, text: str | None, where: str,
          error: type[Exception] = QuoteError) -> None:
    """Raise unless every quote is on its page (paged documents) or in the text (unpaged ones)."""
    for q in quotes:
        want = normalise(q["text"])
        if q.get("page") is None:
            haystack = text or ""
        else:
            if pages is None or not 1 <= int(q["page"]) <= len(pages):
                raise error(f"{where}: page {q.get('page')} is not in the document")
            haystack = pages[int(q["page"]) - 1]
        if want not in haystack:
            raise error(f"{where}: quote not found on page {q.get('page')}: {q['text'][:80]!r}")
