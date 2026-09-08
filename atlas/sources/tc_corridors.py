"""
atlas.sources.tc_corridors — Transport Canada's national trade corridors.

Transport Canada's annual report defines the corridors Canadian trade actually
moves through, and defines them with names, descriptions and the specific ports,
railways, highways and border crossings that constitute each one. That makes
"explain what a trade corridor is" a matter of REPRODUCTION rather than
authorship, which is the only way this project is allowed to answer it.

THERE ARE FIVE CORRIDORS, NOT FOUR

Pacific, Prairie, Central, Atlantic — and **Northern**. Summaries of this page
routinely list four, and an early draft of this module was written against four
before the live page was read. Missing one would have been invisible: the four
would have summed to something, the map would have drawn something, and the
Northern Corridor — which is where most of the Major Projects Office portfolio
actually sits — would simply not have existed. The count is asserted in
`registry/events.yaml` and gated by `verify/`.

THE NORTHERN CORRIDOR IS DEFINED BY LATITUDE, NOT BY PROVINCE

Its own description says "regions north of 55 degrees". The other four are
described by province. So the corridors are **not a partition of the provinces**
and must never be validated as one: northern British Columbia is in both the
Pacific and the Northern corridor, and that is Transport Canada's framing, not
an error in ours. Only the three territories map cleanly, and
`registry/corridors.yaml` records the verbatim definition beside the mapping so
the reading can be checked against the words it came from.

PAGE STRUCTURE, established by reading the live markup rather than assumed

    main[property=mainContentOfPage]
      details                       ← one per section; 8 in total, 5 are corridors
        summary                     ← the corridor's name, and the join key
        p                           ← the description paragraph
        div.well.well-sm            ← the infrastructure box
          h4                        "<Name> Corridor Infrastructure"
          p / ul  x4                Marine / Rail / Road / Air
        h4 + p ...                  ← longer prose per mode, not extracted

The `<details>` accordion is what makes this parseable: each corridor's content
is bounded by its own element rather than running from one heading to the next.
Both language pages carry the same eight blocks in the same order.

FRENCH IS READ, NEVER GUESSED

`STATUS.md` records an entire lost afternoon to guessed French headings on
canada.ca ("Faits saillants", not "Faits en bref"), which yields zero content
silently while every other field looks fine. So the French summary text and the
French mode labels are declared in `registry/corridors.yaml`, read off the live
page, and the FR URL is declared rather than derived — it is
`role-reseau-transport-canadien`, which no rule would produce from
`role-canada-s-transportation-network`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

log = logging.getLogger(__name__)

#: Collapses the whitespace the CMS leaves in its output. Same narrow rule as
#: `mpo.normalise`: punctuation spacing is restricted to marks neither language
#: puts a space before, because French requires one before `: ; ! ? %`.
_WS = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.)\]])")

#: Footnote markers the CMS appends inside sentences ("Class I rail network
#: Footnote 6 ,"). They are navigation, not text, and leaving them in puts a
#: word the government did not write inside a quoted sentence.
_FOOTNOTE = re.compile(r"\s*Footnote\s+\d+\s*", re.I)
_FOOTNOTE_FR = re.compile(r"\s*Note de bas de page\s+\d+\s*", re.I)


def normalise(text: str) -> str:
    """Collapse CMS whitespace and drop footnote markers, changing nothing else."""
    out = _WS.sub(" ", text or "").strip()
    out = _FOOTNOTE.sub(" ", out)
    out = _FOOTNOTE_FR.sub(" ", out)
    out = _WS.sub(" ", out).strip()
    return _SPACE_BEFORE_PUNCT.sub(r"\1", out)


@dataclass(slots=True)
class ParsedMode:
    """One transport mode inside a corridor's infrastructure box."""

    label: str                       # "Rail" / "Transport ferroviaire", verbatim
    items: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParsedCorridor:
    """One corridor, in one language, as published."""

    summary: str                     # the <summary> text — the join key
    description: str
    modes: list[ParsedMode] = field(default_factory=list)

    def verbatim_blob(self) -> str:
        """Every reproduced string, joined, for content hashing."""
        parts = [self.summary, self.description]
        for m in self.modes:
            parts.append(m.label)
            parts.extend(m.items)
        return "\x1e".join(parts)


def _modes(well: Tag | None) -> list[ParsedMode]:
    """
    The infrastructure box, as mode -> items.

    Markup is a flat run of `<p>Rail</p><ul><li>…</li></ul>` pairs inside one
    div, so the `<p>` is a label and the `<ul>` that follows it belongs to it.
    Reading the `<ul>`s alone would lose which mode each belongs to, and reading
    the box's text would run four modes into one paragraph.
    """
    if well is None:
        return []
    out: list[ParsedMode] = []
    for p in well.find_all("p"):
        label = normalise(p.get_text(" "))
        if not label:
            continue
        mode = ParsedMode(label=label)
        nxt = p.find_next_sibling()
        if nxt is not None and nxt.name == "ul":
            mode.items = [normalise(li.get_text(" ")) for li in nxt.find_all("li")]
            mode.items = [i for i in mode.items if i]
        out.append(mode)
    return out


def parse_page(html: str, summaries: list[str]) -> dict[str, ParsedCorridor]:
    """
    Every corridor on the page, keyed by its `<summary>` text.

    `summaries` is the declared list of corridor names for this language, from
    the registry. Matching against a declared list rather than a pattern like
    "anything ending in Corridor" is deliberate: the page also carries
    "Supporting the Economy" and "Infrastructure That Supports Trade and
    Mobility Corridors" as `<details>` blocks, and the second of those has the
    same four-mode infrastructure box as a real corridor. A structural heuristic
    would have picked it up as a sixth corridor.
    """
    soup = BeautifulSoup(html, "lxml")
    main = soup.select_one("main[property=mainContentOfPage]") or soup.select_one("main")
    if main is None:
        raise ValueError("Transport Canada page: no <main> content element")

    wanted = {s: None for s in summaries}
    for det in main.find_all("details"):
        summ = det.find("summary")
        if summ is None:
            continue
        name = normalise(summ.get_text(" "))
        if name not in wanted:
            continue
        para = det.find("p")
        wanted[name] = ParsedCorridor(
            summary=name,
            description=normalise(para.get_text(" ")) if para else "",
            modes=_modes(det.select_one("div.well")),
        )

    missing = [s for s, v in wanted.items() if v is None]
    if missing:
        raise ValueError(
            f"Transport Canada page: no <details> block found for {missing}. "
            f"The page was restructured, or the declared summary text in "
            f"registry/corridors.yaml no longer matches it verbatim."
        )
    return {k: v for k, v in wanted.items() if v is not None}
