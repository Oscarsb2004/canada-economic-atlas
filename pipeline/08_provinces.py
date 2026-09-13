#!/usr/bin/env python3
"""
Stage 08 — each province and territory in depth (BACKLOG Stage R).

    python pipeline/08_provinces.py [--refresh]

Outputs
    data/provinces/provinces.json
    web/public/media/provinces/<code>-flag.png, <code>-arms.png

WHAT THIS IS FOR

The province page: who the jurisdiction is, what its economy is made of, and
how its finances have gone. Four publishers, each read by its own module:

    Finance Canada   Fiscal Reference Tables — revenues, expenditures, deficit
                     or surplus, net debt, every fiscal year the table carries
                     (atlas/sources/fiscal_tables.py)
    StatCan          36-10-0400 — each industry's percentage share of the
                     jurisdiction's GDP, 1997 on (atlas/sources/sector_shares.py)
    Canadian Heritage   the motto and the flag's description, verbatim
    Wikimedia Commons   the flag and coat of arms, with each file's own licence
                     (atlas/sources/symbols.py)

Not yet here: the licence plate slogan (R1) and each province's budget text
(R5) — both need their sources read first.

Nothing here is computed except a 240-pixel rendering of each image, which
Commons itself produces.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from atlas.core import registry as R
from atlas.core.jsonio import write_if_changed
from atlas.core.schema import Provenance, SourceRef, Text, to_jsonable
from atlas.net import Fetcher, FetchError
from atlas.sources import census, fiscal_tables, sector_shares, statcan, symbols

log = logging.getLogger("08_provinces")

OUTPUT = R.DATA_DIR / "provinces" / "provinces.json"
IMAGES = R.WEB_MEDIA_DIR / "provinces"
REGISTRY = Path(__file__).resolve().parents[1] / "registry"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="re-download every source")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    reg = yaml.safe_load((REGISTRY / "provinces.yaml").read_text(encoding="utf-8"))
    provinces = reg["provinces"]
    if set(provinces) != set(R.PROVINCE_CODES):
        raise SystemExit(f"provinces.yaml lists {sorted(provinces)}, not the thirteen {sorted(R.PROVINCE_CODES)}")
    pruid_to_code = {str(p["pruid"]): code for code, p in provinces.items()}
    if pruid_to_code != {k: v for k, v in census.PRUID_TO_CODE.items() if v in provinces}:
        raise SystemExit("provinces.yaml PRUIDs disagree with atlas/sources/census.py")

    fetch = Fetcher(cache_dir=R.DATA_DIR / "raw" / "cache", use_cache=not args.refresh)
    retrieved = _now()
    sources: list[SourceRef] = []

    # ── Fiscal Reference Tables ──────────────────────────────────────────────
    fsrc = R.source(reg["fiscal_source"])

    def get(url: str) -> bytes | None:
        try:
            return fetch.bytes(url, force=args.refresh)
        except FetchError:
            return None

    year, books = fiscal_tables.latest_edition(get, fsrc["xlsx"], datetime.now(timezone.utc).year + 1,
                                               int(fsrc["oldest_edition"]))
    log.info("Fiscal Reference Tables: %d edition", year)
    for lang in ("en", "fr"):
        sources.append(SourceRef(url=fsrc["xlsx"][lang].format(year=year, yy=f"{year % 100:02d}"),
                                 retrieved_at=retrieved, provenance=Provenance.OFFICIAL_DATASET,
                                 licence=fsrc["licence"], content_sha256=_sha(books[lang])))
    fiscal = {}
    for code, p in provinces.items():
        t = fiscal_tables.read(books["en"], books["fr"], int(p["fiscal_table"]))
        fiscal[code] = t
        if t.year_label_mismatches:
            log.warning("%s: the French workbook labels rows differently: %s", code, t.year_label_mismatches)

    # ── GDP shares by industry ───────────────────────────────────────────────
    ssrc = R.source(reg["shares_source"])
    pid = str(ssrc["pid"])
    live = statcan.release_time(fetch, pid)
    raw = R.DATA_DIR / "raw" / "statcan"
    zip_en, release = statcan.download_cube(fetch, pid, "eng", raw, live_release=live, refresh=args.refresh)
    zip_fr, release_fr = statcan.download_cube(fetch, pid, "fra", raw, live_release=live, refresh=args.refresh)
    if not release or release != release_fr:
        raise SystemExit(f"table {pid}: the English and French zips are not of one dated release "
                         f"({release!r} / {release_fr!r}); run with --refresh")
    sectors = {str(s["code"]) for s in yaml.safe_load((REGISTRY / "sectors.yaml").read_text(encoding="utf-8"))["sectors"]}
    header_en, rows_en = statcan.read_cube(zip_en, pid)
    header_fr, rows_fr = statcan.read_cube(zip_fr, pid)
    shares = sector_shares.build(header_en, rows_en, header_fr, rows_fr,
                                 pruid_to_code=pruid_to_code, sector_codes=sectors)
    meta_en, meta_fr = statcan.cube_metadata(zip_en, pid), statcan.cube_metadata(zip_fr, pid)
    for z in (zip_en, zip_fr):
        sources.append(SourceRef(url=f"https://www150.statcan.gc.ca/n1/tbl/csv/{z.name}", retrieved_at=retrieved,
                                 provenance=Provenance.OFFICIAL_DATASET, licence=ssrc["licence"],
                                 content_sha256=_sha(z.read_bytes())))
    log.info("36-10-0400: %d industries, %s to %s, release %s",
             len(shares["industries"]), shares["periods"][0], shares["periods"][-1], release)

    # ── Canadian Heritage ────────────────────────────────────────────────────
    hsrc = R.source(reg["symbols_source"])
    words = {}
    for code, p in provinces.items():
        urls = {lang: hsrc["page"][lang].format(slug=p["heritage"][lang]) for lang in ("en", "fr")}
        pages = {lang: fetch.text(urls[lang]) for lang in ("en", "fr")}
        words[code] = {**symbols.read_pages(pages["en"], pages["fr"], where=code), "pages": urls}
        for lang in ("en", "fr"):
            sources.append(SourceRef(url=urls[lang], retrieved_at=retrieved, provenance=Provenance.PAGE_VERBATIM,
                                     licence=hsrc["licence"], content_sha256=_sha(pages[lang].encode("utf-8"))))

    # ── Wikimedia Commons ────────────────────────────────────────────────────
    csrc = R.source(reg["images_source"])
    titles = [p[kind] for p in provinces.values() for kind in ("flag", "arms")]
    records = symbols.commons_records(json.loads(fetch.bytes(symbols.commons_query_url(csrc["api"], titles),
                                                             force=args.refresh)), titles)
    IMAGES.mkdir(parents=True, exist_ok=True)
    images: dict[str, dict[str, dict]] = {}
    for code, p in provinces.items():
        for kind in ("flag", "arms"):
            rec = records[p[kind]]
            body = fetch.bytes(rec["rendering_url"], force=args.refresh)
            if not body.startswith(b"\x89PNG"):
                raise SystemExit(f"{code} {kind}: the Commons rendering is not a PNG")
            path = IMAGES / f"{code.lower()}-{kind}.png"
            if not path.exists() or path.read_bytes() != body:
                path.write_bytes(body)
            images.setdefault(code, {})[kind] = {
                **{k: rec[k] for k in ("title", "page_url", "file_url", "licence", "licence_url", "artist",
                                       "credit", "restrictions", "source_sha1")},
                "src": f"/media/provinces/{path.name}",
                "rendering_sha256": _sha(body),
                "provenance": Provenance.THIRD_PARTY.value,
            }

    # ── Output ───────────────────────────────────────────────────────────────
    doc = {
        "generated_at": retrieved,
        "fiscal": {
            "title": fsrc["title"],
            "edition": year,
            "edition_page": fsrc["edition_page"].format(year=year),
            "unit": to_jsonable(next(iter(fiscal.values())).unit),
        },
        "sector_shares": {
            "title": Text(en=meta_en["title"], fr=meta_fr["title"]),
            "table": pid,
            "release": release,
            "periods": shares["periods"],
            "industries": shares["industries"],
        },
        "provinces": {
            code: {
                "name": fiscal[code].name,
                "motto": words[code]["motto"],
                "flag_description": words[code]["flag"],
                "heritage_pages": words[code]["pages"],
                "flag": images[code]["flag"],
                "arms": images[code]["arms"],
                "fiscal": {
                    "table": fiscal[code].table,
                    "years": list(fiscal[code].years),
                    "columns": [{"label": c.label, "values": list(c.values)} for c in fiscal[code].columns],
                    "notes": {"en": list(fiscal[code].notes_en), "fr": list(fiscal[code].notes_fr)},
                    "year_label_mismatches": [list(m) for m in fiscal[code].year_label_mismatches],
                },
                "sector_shares": shares["shares"][code],
                "sector_share_symbols": shares["symbols"].get(code, {}),
            }
            for code in sorted(provinces)
        },
        "sources": sources,
    }
    changed = write_if_changed(OUTPUT, to_jsonable(doc))
    log.info("provinces.json %s: %d jurisdictions, %d images",
             "updated" if changed else "unchanged", len(doc["provinces"]), sum(len(v) for v in images.values()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
