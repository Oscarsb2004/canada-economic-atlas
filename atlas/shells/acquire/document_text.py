"""
atlas.shells.acquire.document_text — the words of a PDF or an HTML page, normalised for quoting.

(Moved from atlas/readers/budget_text.py in step S2 of docs/REBUILD.md; unchanged
in behaviour. Card: registry/shells/document_text.yaml.)

Normalisation is what lets a quote typed from a document be found in the
extracted text: Unicode compatibility forms folded, pypdf's `/Tx_` ligature
escapes undone, curly apostrophes straightened, whitespace collapsed, and no
space before closing punctuation.
"""

from __future__ import annotations

import html
import io
import logging
import re
import unicodedata

import pypdf

_TAG = re.compile(r"<[^>]+>")


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


def strip_tags(fragment: str) -> str:
    """An HTML fragment's text: tags removed, entities decoded, whitespace collapsed."""
    return " ".join(html.unescape(_TAG.sub(" ", fragment)).split())
