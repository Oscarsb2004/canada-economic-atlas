#!/usr/bin/env python3
"""
Stage 07 — Canadian-registered vessels that carry an IMO number.

    python pipeline/07_vessels.py [--refresh]

Output
    data/vessels/large-vessel-register.json

WHAT THIS IS FOR

BACKLOG S1, the identity half of the live vessel layer (docs/AIS.md). A flag is
a state of registry, so "is this ship Canadian" is answered by Transport
Canada's register rather than by the radio. Positions come later, from a feed
chosen in S0, and are never committed.

WHY ONLY THE ENTRIES WITH AN IMO NUMBER

The register publishes no MMSI and no call sign; the IMO number is the only
field an AIS message shares with it. An entry without one can never be matched
to a position, so committing it would carry the whole register for no join. The
register's own totals are published beside the records, so what was left out is
stated, and the full files remain re-fetchable input under data/raw/.

NOT BUNDLED

The app gets what the vessel layer needs when S3 builds it.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas.core import registry as R
from atlas.core.jsonio import write_if_changed
from atlas.core.schema import Provenance, SourceRef, to_jsonable
from atlas.net import Fetcher
from atlas.sources import vessels

log = logging.getLogger("07_vessels")

SOURCE_KEY = "tc_large_vessel_register"
OUTPUT = R.DATA_DIR / "vessels" / "large-vessel-register.json"
FILES = (("en", "xlsx_en"), ("fr", "xlsx_fr"))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-download the register")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    src = R.source(SOURCE_KEY)
    fetch = Fetcher(cache_dir=R.DATA_DIR / "raw" / "cache", use_cache=not args.refresh)
    raw = R.DATA_DIR / "raw" / "transport-canada"
    paths = {lang: fetch.download(src[key], raw / Path(src[key]).name, force=args.refresh)
             for lang, key in FILES}

    entries = vessels.read(paths["en"], paths["fr"])
    kept = [v for v in entries if v.imo]
    twice = sorted(n for n, c in Counter(v.official_number for v in entries).items() if c > 1)
    counts = {
        "register_entries": len(entries),
        "entries_with_imo": len(kept),
        "imo_failing_check_digit": sum(not v.imo_check_digit_valid for v in kept),
        "official_numbers_listed_twice": twice,
    }

    retrieved = _now()
    changed = write_if_changed(OUTPUT, {
        "generated_at": retrieved,
        "title": src["title"],
        "dataset_record": src.get("dataset_record", ""),
        "sources": to_jsonable([
            SourceRef(url=src[key], retrieved_at=retrieved, provenance=Provenance.OFFICIAL_DATASET,
                      licence=src["licence"], content_sha256=hashlib.sha256(paths[lang].read_bytes()).hexdigest())
            for lang, key in FILES
        ]),
        "scope": {
            "en": "Entries in the Canadian Register of Large Vessels that carry an IMO number — the only "
                  "field the register shares with AIS. The register publishes no MMSI or call sign.",
            "fr": "Inscriptions du Registre canadien des grands bâtiments qui portent un numéro OMI, seul "
                  "champ que le registre partage avec l'AIS. Le registre ne publie ni ISMM ni indicatif d'appel.",
        },
        "counts": counts,
        "vessels": to_jsonable(kept),
    })

    log.info("register: %d entries, %d with an IMO number, %d of those fail the IMO check digit",
             counts["register_entries"], counts["entries_with_imo"], counts["imo_failing_check_digit"])
    log.info("official numbers listed twice: %s", twice)
    log.info("most common descriptors among IMO entries: %s", ", ".join(
        f"{d} {n}" for d, n in Counter(v.descriptor.en for v in kept).most_common(6)))
    log.info("large-vessel-register.json %s", "updated" if changed else "unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
