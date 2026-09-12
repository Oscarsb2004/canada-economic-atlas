"""
atlas.sources.naics — NAICS Canada 2022 Version 1.0, read from Statistics
Canada's own classification files.

WHY THE CLASSIFICATION IS READ RATHER THAN TYPED

`registry/mpo_naics.yaml` places each Major Projects Office project in the NAICS
industry its finished asset would operate in. CLAUDE.md §11 admits a mapping of
our own only as a DECLARED crosswalk, so that file is the declaration, and it is
written to be checked rather than trusted: every placement quotes
Statistics Canada's own wording — part of a class definition, or a whole
example, inclusion or exclusion — and `evidence()` refuses it unless the quoted
words are in StatCan's file under that code, in both languages. A paraphrase, a
typo, or a code that does not carry the quoted words stops the stage.

THE FRENCH FILE IS NOT IN THE ENGLISH FILE'S ORDER

The two element files publish the same number of elements for every one of the
1,071 codes that have any (measured 2026-09-12), which makes pairing by position
look safe. It is not. Each file is sorted by its own language's wording, so the
sixth English illustrative example of 488310, "waterfront terminal operation",
sits beside the French "voie maritime, exploitation de" — the seaway. Pairing by
position would attach a French quote to the wrong English one on nearly every
code, and both halves would look perfectly correct. Each language's quote is
declared in the registry and found in its own file.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from atlas.core.schema import NaicsEvidence, Text

#: Evidence kinds, and the element type label each language's file publishes.
#: `definition` is the other kind: a substring of the class definition.
ELEMENT_LABELS: dict[str, dict[str, str]] = {
    "illustrative_example": {"en": "Illustrative example(s)", "fr": "Exemple(s) illustratif(s)"},
    "all_examples":         {"en": "All examples",            "fr": "Tous les exemples"},
    "inclusion":            {"en": "Inclusion(s)",            "fr": "Inclusion(s)"},
    "exclusion":            {"en": "Exclusion(s)",            "fr": "Exclusion(s)"},
}
EVIDENCE_KINDS = frozenset(ELEMENT_LABELS) | {"definition"}

#: Header names as published. The French structure file writes "Parent " with a
#: trailing space, so headers are stripped before they are looked up.
STRUCTURE_COLUMNS = {
    "en": {"level": "Level", "code": "Code", "parent": "Parent",
           "title": "Class title", "definition": "Class definition"},
    "fr": {"level": "Niveau", "code": "Code", "parent": "Parent",
           "title": "Titres de classes", "definition": "Définitions de la classe"},
}
ELEMENT_COLUMNS = {
    "en": {"code": "Code", "kind": "Element Type Label", "text": "Element Description"},
    "fr": {"code": "Code", "kind": "Nom du type d'élément", "text": "Description d'élément"},
}


class NaicsError(ValueError):
    """A classification file is not shaped as expected, or a quote is not in it."""


@dataclass(frozen=True, slots=True)
class NaicsClass:
    code: str
    level: int                   # 1 sector … 5 Canadian industry
    parent: str                  # "" for a sector
    title: Text
    definition: Text


@dataclass(frozen=True, slots=True)
class Classification:
    classes: dict[str, NaicsClass]
    #: (lang, code, kind) -> every element description of that kind, as published.
    elements: dict[tuple[str, str, str], tuple[str, ...]]


def _records(text: str, columns: dict[str, str], name: str) -> list[dict[str, str]]:
    reader = csv.reader(io.StringIO(text.lstrip("﻿"), newline=""))
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration:
        raise NaicsError(f"{name}: empty file") from None
    missing = [c for c in columns.values() if c not in header]
    if missing:
        raise NaicsError(f"{name}: columns {missing} are not in the header {header}")
    idx = {key: header.index(col) for key, col in columns.items()}
    return [{key: row[i].strip() for key, i in idx.items()} for row in reader if row]


def read(structure_en: str, structure_fr: str, elements_en: str, elements_fr: str) -> Classification:
    """Both languages of both files, joined on code — never on position."""
    en = _records(structure_en, STRUCTURE_COLUMNS["en"], "structure (en)")
    fr = {r["code"]: r for r in _records(structure_fr, STRUCTURE_COLUMNS["fr"], "structure (fr)")}
    en_codes = {r["code"] for r in en}
    if en_codes != set(fr):
        raise NaicsError(
            f"structure files disagree on codes: {sorted(en_codes ^ set(fr))[:10]}"
        )

    classes: dict[str, NaicsClass] = {}
    for r in en:
        f = fr[r["code"]]
        classes[r["code"]] = NaicsClass(
            code=r["code"], level=int(r["level"]), parent=r["parent"],
            title=Text(en=r["title"], fr=f["title"]),
            definition=Text(en=r["definition"], fr=f["definition"]),
        )

    elements: dict[tuple[str, str, str], list[str]] = {}
    for lang, text in (("en", elements_en), ("fr", elements_fr)):
        kind_of = {labels[lang]: kind for kind, labels in ELEMENT_LABELS.items()}
        for r in _records(text, ELEMENT_COLUMNS[lang], f"elements ({lang})"):
            kind = kind_of.get(r["kind"])
            if kind is None:
                raise NaicsError(
                    f"elements ({lang}): unknown element type {r['kind']!r} on {r['code']}. "
                    f"A new type is a decision about whether it can be evidence."
                )
            elements.setdefault((lang, r["code"], kind), []).append(r["text"])

    return Classification(classes=classes, elements={k: tuple(v) for k, v in elements.items()})


def sector_of(c: Classification, code: str) -> str:
    """The level-1 sector a code sits in, by StatCan's own parent column."""
    seen: set[str] = set()
    at = code
    while True:
        cls = c.classes.get(at)
        if cls is None:
            raise NaicsError(f"{code}: {at!r} is not a NAICS Canada 2022 code")
        if cls.level == 1:
            return at
        if at in seen or not cls.parent:
            raise NaicsError(f"{code}: the parent chain breaks at {at!r}")
        seen.add(at)
        at = cls.parent


def evidence(c: Classification, code: str, kind: str, quote: Text) -> NaicsEvidence:
    """
    StatCan's words for `code`, confirmed present in both languages.

    A definition quote may be any part of the definition. An element quote must
    be a WHOLE element: a fragment of "hazardous or non hazardous waste material
    treatment and disposal sites" could be made to say something the element
    does not.
    """
    if kind not in EVIDENCE_KINDS:
        raise NaicsError(f"{code}: unknown evidence kind {kind!r}; known: {sorted(EVIDENCE_KINDS)}")
    cls = c.classes.get(code)
    if cls is None:
        raise NaicsError(f"{code!r} is not a NAICS Canada 2022 code")
    for lang in ("en", "fr"):
        q = getattr(quote, lang)
        if not q:
            raise NaicsError(f"{code} {kind}: no {lang} quote. Both languages are declared, never derived.")
        if kind == "definition":
            found = q in getattr(cls.definition, lang)
        else:
            found = q in c.elements.get((lang, code, kind), ())
        if not found:
            raise NaicsError(
                f"{code} {kind} ({lang}): {q!r} is not in Statistics Canada's text for this code"
            )
    return NaicsEvidence(kind=kind, code=code, text=quote)
