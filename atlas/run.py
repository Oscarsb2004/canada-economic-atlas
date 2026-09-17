"""
atlas.run — make datasets from their cards (docs/REBUILD.md §3).

    python -m atlas.run economy                        every card in a group, in order
    python -m atlas.run --dataset gdp-national-monthly one card (repeatable)
    python -m atlas.run --list                         every card, by group
    python -m atlas.run economy --refresh              bypass the HTTP cache and re-download

WHAT THE RUNNER OWNS

A card in registry/datasets/ names its builder (`atlas/datasets/…`). The runner
calls it, then does the three things no builder does:

  writes the published files, each only when its content changed, so a re-run
  against unchanged sources leaves a zero-line diff (CLAUDE.md §6);
  writes each frame and its manifest under build/frames/, after checking the
  rows against the frame's own profile;
  writes a receipt under build/receipts/: the named values the run produced
  and the hash of every file it published.

A builder that decides not to produce its dataset raises `Skipped`, and its
committed files stay as they are. Anything else it raises stops the run, as a
failing stage always has.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import logging
import sys
from pathlib import Path

from atlas.core import clock
from atlas.core import frames
from atlas.core import registry as R
from atlas.core.jsonio import write_if_changed
from atlas.datasets import Context, Skipped
from atlas.shells.acquire.fetcher import Fetcher

log = logging.getLogger("atlas.run")

BUILD_DIR = R.ROOT / "build"


def builder_of(card: dict):
    module, _, function = card["builder"].partition(":")
    return getattr(importlib.import_module(module), function)


def run_card(ctx: Context, dataset: str, card: dict) -> dict:
    """Build one dataset, write what it made, and return its receipt."""
    log.info("── %s — %s", dataset, card["title"])
    try:
        built = builder_of(card)(ctx, dataset=dataset, **card.get("params", {}))
    except Skipped as exc:
        log.warning("%s skipped: %s", dataset, exc)
        return {"dataset": dataset, "skipped": str(exc)}

    declared = {R.ROOT / p for p in card["outputs"]}
    written = {}
    for path, payload in built.outputs:
        if Path(path) not in declared:
            raise RuntimeError(f"{dataset}: wrote {path}, which its card does not declare as an output")
        changed = write_if_changed(path, payload)
        rel = Path(path).relative_to(R.ROOT).as_posix()
        written[rel] = {
            "changed": changed,
            "bytes": Path(path).stat().st_size,
            "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        }
        log.info("%-45s %s", rel, "updated" if changed else "unchanged")

    for frame in built.frames:
        body, _ = frames.write(frame, BUILD_DIR / "frames")
        log.info("frame %s: %d rows (%s)", body.relative_to(R.ROOT).as_posix(), len(frame.rows), frame.profile)

    receipt = {"dataset": dataset, "outputs": written, "values": built.receipt,
               "frames": {f.name: len(f.rows) for f in built.frames}}
    path = BUILD_DIR / "receipts" / f"{dataset}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**receipt, "at": clock.now_iso()}, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                    encoding="utf-8", newline="\n")
    return receipt


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Make datasets from their cards in registry/datasets/.")
    ap.add_argument("group", nargs="?", help="run every card in this group, in order")
    ap.add_argument("--dataset", action="append", metavar="ID", help="run only this card; repeatable")
    ap.add_argument("--list", action="store_true", help="list every card by group and stop")
    ap.add_argument("--refresh", action="store_true", help="bypass the HTTP cache and re-download")
    ap.add_argument("--set", action="append", default=[], metavar="NAME=VALUE", dest="options",
                    help="an option for the builders, such as --set limit=2 (a smoke test) or --set images=false")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    cards = R.datasets()
    if args.list:
        for group, members in R.dataset_groups().items():
            print(group)
            for dataset in members:
                print(f"  {dataset:34s} {cards[dataset]['title']}")
        return 0

    if args.dataset:
        unknown = sorted(set(args.dataset) - set(cards))
        if unknown:
            ap.error(f"no dataset card named {unknown}")
        selected = [d for group in R.dataset_groups().values() for d in group if d in args.dataset]
    elif args.group:
        groups = R.dataset_groups()
        if args.group not in groups:
            ap.error(f"no group {args.group!r}; groups are {sorted(groups)}")
        selected = groups[args.group]
    else:
        ap.error("name a group or --dataset (or --list)")

    options = {}
    for pair in args.options:
        name, _, value = pair.partition("=")
        options[name.strip()] = value.strip()
    ctx = Context(fetch=Fetcher(cache_dir=R.DATA_DIR / "raw" / "cache", use_cache=not args.refresh),
                  refresh=args.refresh, options=options)
    for dataset in selected:
        run_card(ctx, dataset, cards[dataset])
    log.info("%s", ctx.fetch.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
