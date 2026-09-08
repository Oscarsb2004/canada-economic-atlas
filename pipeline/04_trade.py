#!/usr/bin/env python3
"""
Stage 04 — Transport Canada's national trade corridors.

    python pipeline/04_trade.py [--refresh]

Outputs
    data/events/trade-corridors/corridors.json    current state
    data/history/<corridor>/<retrieved_at>.json   append-only, on change only

WHAT THIS ANSWERS THAT NOTHING ELSE DOES

The map could draw trade infrastructure but could not say what any of it was
FOR. Transport Canada's annual report names five corridors, describes each one,
and lists the ports, railways, highways and border crossings that constitute it
— so "explain what a trade corridor is" becomes reproduction rather than this
project inventing an explanation, which is the only way it is allowed to answer.

FIVE CORRIDORS. Pacific, Prairie, Central, Atlantic and NORTHERN. Summaries of
that page routinely list four, and an early draft of this pipeline was written
against four before the live page was read. The omission would have been
invisible: four corridors still sum to something and still draw something, and
the Northern Corridor — where most of the Major Projects Office portfolio
actually sits — would simply not have existed. `events.yaml` asserts the count.

THE CORRIDORS ARE NOT A PARTITION. The Northern Corridor is defined by latitude,
"regions north of 55 degrees", while the other four are described by province.
Northern British Columbia is in both Pacific and Northern. That overlap is
Transport Canada's framing and is carried into the payload rather than resolved
away — see `overlaps_provinces` and `unmapped_note`.

WHAT IS REPRODUCED AND WHAT IS OURS

Reproduced: every corridor's name, description paragraph, and mode-by-mode
infrastructure list, in both languages.

Ours, and marked `DERIVED`: which provinces we read each corridor as covering,
and where the named ports and border crossings actually are. Transport Canada
names those facilities and publishes no geometry for any of them, so their
coordinates carry `coordinate_provenance=DERIVED` explicitly — without it the
schema would infer a single point to be the publisher's own, and label our
placements `official_dataset`.

NOT HERE AT ALL: the statistics. TC's paragraph says $249 billion, 158 million
tonnes, 55% crude by pipeline. Those stay in the paragraph (CLAUDE.md §1). The
corridor's prose carries the numbers Transport Canada published; the charts
carry the numbers StatCan published; nothing crosses.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas.core import registry as R
from atlas.core.jsonio import write_if_changed
from atlas.core.schema import (
    CorridorMode, CorridorNode, CorridorNodeKind, Geometry, GeometryKind,
    Provenance, SourceRef, Text, TradeCorridor, to_jsonable,
)
from atlas.net import Fetcher
from atlas.sources import tc_corridors as tc

log = logging.getLogger("04_trade")

EVENT_SLUG = "trade-corridors"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pair(en: str, fr: str) -> Text:
    return Text(en=en, fr=fr)


# ── Build ──────────────────────────────────────────────────────────────────────

def _modes(en: tc.ParsedCorridor, fr: tc.ParsedCorridor) -> tuple[CorridorMode, ...]:
    """
    Pair the infrastructure lists EN-to-FR, positionally, per mode.

    Both pages publish the same four modes in the same order, so position is a
    valid key at the mode level. It is NOT automatically valid for the bullets
    inside a mode: the Northern Corridor publishes 13 items in English and 12 in
    French. Where the counts disagree the bullets are carried unpaired — each
    language keeping its own complete list — for exactly the reason the MPO
    benefits are: pairing bullet 3 to bullet 4 would present one government
    sentence as the translation of another and look entirely correct, while
    dropping the French side would delete a published sentence outright.
    """
    out: list[CorridorMode] = []
    fr_modes = {i: m for i, m in enumerate(fr.modes)}
    for i, m in enumerate(en.modes):
        f = fr_modes.get(i)
        label = _pair(m.label, f.label if f else "")
        if f is not None and len(m.items) == len(f.items):
            items = tuple(_pair(a, b) for a, b in zip(m.items, f.items))
        else:
            if f is not None:
                log.warning("%s: EN has %d items, FR has %d — carrying both unpaired",
                            m.label, len(m.items), len(f.items))
            items = (tuple(Text(en=a, fr="") for a in m.items)
                     + tuple(Text(en="", fr=b) for b in (f.items if f else ())))
        out.append(CorridorMode(label=label, items=items))
    return tuple(out)


def _nodes(spec: R.Corridor) -> tuple[CorridorNode, ...]:
    """
    The corridor's ports and crossings, as anchored POINT geometries.

    `coordinate_provenance=DERIVED` is the load-bearing argument here. Transport
    Canada names these facilities in its infrastructure list and publishes no
    coordinates, so every one of these positions is ours. Leaving it unset makes
    `Geometry.anchor_provenance` infer `official_dataset` from the fact that a
    single point looks like a published one.
    """
    catalogue = R.corridor_nodes()
    out: list[CorridorNode] = []
    for nid in spec.node_ids:
        n = catalogue[nid]
        out.append(CorridorNode(
            node_id=n.node_id,
            kind=CorridorNodeKind(n.kind),
            name=_pair(n.name_en, n.name_fr),
            geometry=Geometry(
                kind=GeometryKind.POINT,
                coordinates=(n.coord,),
                location_verbatim=spec.location_verbatim_en,
                approximate=True,
                coordinate_provenance=Provenance.DERIVED,
            ),
        ))
    return tuple(out)


def build(fetch: Fetcher) -> tuple[list[TradeCorridor], list[dict]]:
    src = R.corridor_source()
    specs = R.corridors()

    pages = {}
    for lang in ("en", "fr"):
        summaries = [getattr(s, f"summary_{lang}") for s in specs]
        pages[lang] = tc.parse_page(fetch.text(src[f"page_{lang}"]), summaries)

    retrieved = _now()
    out: list[TradeCorridor] = []
    history: list[dict] = []

    for spec in specs:
        en = pages["en"][spec.summary_en]
        fr = pages["fr"][spec.summary_fr]
        log.info("· %s", spec.corridor_id)

        sources = tuple(
            SourceRef(url=src[f"page_{lang}"], retrieved_at=retrieved,
                      provenance=Provenance.PAGE_VERBATIM, licence="ogl-canada-2.0",
                      content_sha256=SourceRef.hash_content(page.verbatim_blob()))
            for lang, page in (("en", en), ("fr", fr))
        )

        corridor = TradeCorridor(
            corridor_id=spec.corridor_id,
            event_slug=EVENT_SLUG,
            name=_pair(en.summary, fr.summary),
            description=_pair(en.description, fr.description),
            location_verbatim=_pair(spec.location_verbatim_en, spec.location_verbatim_fr),
            provinces=spec.provinces,
            modes=_modes(en, fr),
            nodes=_nodes(spec),
            overlaps_provinces=spec.overlaps_provinces,
            unmapped_note=_pair(spec.unmapped_note_en, spec.unmapped_note_fr),
            sources=sources,
        )
        out.append(corridor)
        history.append({
            "slug": spec.corridor_id,
            "retrieved_at": retrieved,
            "content_sha256": SourceRef.hash_content(
                en.verbatim_blob() + "\x1e" + fr.verbatim_blob()),
            "corridor": to_jsonable(corridor),
        })
    return out, history


def _write_history(slug: str, payload: dict, digest: str) -> bool:
    """Append a history entry only when the content hash has moved."""
    hist_dir = R.DATA_DIR / "history" / slug
    if hist_dir.exists():
        prior = sorted(hist_dir.glob("*.json"))
        if prior:
            import json
            last = json.loads(prior[-1].read_text(encoding="utf-8"))
            if last.get("content_sha256") == digest:
                return False
    hist_dir.mkdir(parents=True, exist_ok=True)
    stamp = payload["retrieved_at"].replace(":", "").replace("-", "")
    import json
    (hist_dir / f"{stamp}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="bypass the HTTP cache")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    fetch = Fetcher(R.DATA_DIR / "raw" / "cache", use_cache=not args.refresh)
    corridors, history = build(fetch)

    added = sum(_write_history(h["slug"], h, h["content_sha256"]) for h in history)
    out = R.DATA_DIR / "events" / EVENT_SLUG / "corridors.json"
    changed = write_if_changed(out, {
        "event": EVENT_SLUG,
        "generated_at": _now(),
        "corridors": [to_jsonable(c) for c in corridors],
    })

    nodes = sum(len(c.nodes) for c in corridors)
    log.info("%d corridors, %d nodes · corridors.json %s · %d history entries added",
             len(corridors), nodes, "updated" if changed else "unchanged", added)
    log.info("%s", fetch.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
