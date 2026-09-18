"""
atlas.datasets.province_profiles — each province and territory in depth (BACKLOG Stage R).

    python -m atlas.run provinces

(Was pipeline/08_provinces.py until step S5 of docs/REBUILD.md; the code is carried
unchanged, and the runner writes the output.)

Outputs
    data/provinces/provinces.json
    web/public/media/provinces/<code>-flag.png, <code>-arms.png

WHAT THIS IS FOR

The province page: who the jurisdiction is, what its economy is made of, and
how its finances have gone. Four publishers, each read by its own module:

    Finance Canada   Fiscal Reference Tables — revenues, expenditures, deficit
                     or surplus, net debt, every fiscal year the table carries
                     (atlas/readers/fiscal_tables.py)
    StatCan          36-10-0400 — each industry's percentage share of the
                     jurisdiction's GDP, 1997 on (atlas/readers/sector_shares.py)
    Canadian Heritage   the motto and the flag's description, verbatim
    Wikimedia Commons   the flag and coat of arms, with each file's own licence
                     (atlas/readers/symbols.py)

Also: short passages from each jurisdiction's latest budget on the risks to its
outlook, each checked against its document (atlas/readers/budget_text.py).

Nothing here is computed except a 240-pixel rendering of each image, which
Commons itself produces.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import yaml

from atlas.core import clock
from atlas.core import frames
from atlas.core import registry as R
from atlas.core.records import Observation, Passage
from atlas.core.schema import Provenance, SourceRef, Text, to_jsonable
from atlas.datasets import Built, Context
from atlas.shells.acquire import document_text, statcan_table
from atlas.shells.acquire.fetcher import FetchError
from atlas.readers import budget_text, census, fiscal_tables, sector_shares, statcan, symbols

log = logging.getLogger(__name__)

OUTPUT = R.DATA_DIR / "provinces" / "provinces.json"
IMAGES = R.WEB_MEDIA_DIR / "provinces"
REGISTRY = R.REGISTRY_DIR


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _page_sha(page: str) -> str:
    """The content hash of an HTML page: its visible text, never its bytes.

    Hashing the bytes made these hashes useless. canada.ca injects an Akamai
    telemetry script and budget.ontario.ca a bot-manager token, each different
    on every request, so all 26 symbols pages and Ontario's budget chapter
    hashed differently on every fetch while every word on them stayed the same
    (measured 2026-09-17: 27 of 27 raw hashes moved between two fetches, 0 of 27
    text hashes did). html_text drops <script> and <style>, which is where both
    tokens live. The Major Projects Office pages never had the problem because
    their hash was always taken over the extracted text (mpo.verbatim_blob).
    """
    return hashlib.sha256(document_text.html_text(page).encode("utf-8")).hexdigest()


def build(ctx: Context, *, dataset: str) -> Built:
    """Every province and territory: its finances, its economy, its words and its symbols."""
    reg = yaml.safe_load((REGISTRY / "provinces.yaml").read_text(encoding="utf-8"))
    provinces = reg["provinces"]
    if set(provinces) != set(R.PROVINCE_CODES):
        raise SystemExit(f"provinces.yaml lists {sorted(provinces)}, not the thirteen {sorted(R.PROVINCE_CODES)}")
    pruid_to_code = {str(p["pruid"]): code for code, p in provinces.items()}
    if pruid_to_code != {k: v for k, v in census.PRUID_TO_CODE.items() if v in provinces}:
        raise SystemExit("provinces.yaml PRUIDs disagree with atlas/readers/census.py")

    fetch = ctx.fetch
    retrieved = clock.now_iso()
    sources: list[SourceRef] = []

    # ── Fiscal Reference Tables ──────────────────────────────────────────────
    fsrc = R.source(reg["fiscal_source"])

    def get(url: str) -> bytes | None:
        try:
            return fetch.bytes(url, force=ctx.refresh)
        except FetchError:
            return None

    year_edition, books = fiscal_tables.latest_edition(get, fsrc["xlsx"], clock.now().year + 1,
                                               int(fsrc["oldest_edition"]))
    log.info("Fiscal Reference Tables: %d edition", year_edition)
    for lang in ("en", "fr"):
        sources.append(SourceRef(url=fsrc["xlsx"][lang].format(year=year_edition, yy=f"{year_edition % 100:02d}"),
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
    live = statcan_table.release_time(fetch, pid)
    raw = R.DATA_DIR / "raw" / "statcan"
    zip_en, release = statcan_table.download_cube(fetch, pid, "eng", raw, live_release=live, refresh=ctx.refresh)
    zip_fr, release_fr = statcan_table.download_cube(fetch, pid, "fra", raw, live_release=live, refresh=ctx.refresh)
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
                                     licence=hsrc["licence"], content_sha256=_page_sha(pages[lang])))

    # ── Wikimedia Commons ────────────────────────────────────────────────────
    csrc = R.source(reg["images_source"])
    titles = [p[kind] for p in provinces.values() for kind in ("flag", "arms")]
    records = symbols.commons_records(json.loads(fetch.bytes(symbols.commons_query_url(csrc["api"], titles),
                                                             force=ctx.refresh)), titles)
    IMAGES.mkdir(parents=True, exist_ok=True)
    images: dict[str, dict[str, dict]] = {}
    for code, p in provinces.items():
        for kind in ("flag", "arms"):
            rec = records[p[kind]]
            body = fetch.bytes(rec["rendering_url"], force=ctx.refresh)
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

    # ── Budget passages (R5) ─────────────────────────────────────────────────
    breg = yaml.safe_load((REGISTRY / "budgets.yaml").read_text(encoding="utf-8"))
    bsrc = R.source(breg["source"])
    if set(breg["budgets"]) != set(provinces):
        raise SystemExit(f"budgets.yaml lists {sorted(breg['budgets'])}, not the thirteen")
    budgets: dict[str, dict] = {}
    for code, b in breg["budgets"].items():
        quotes = b.get("quotes") or []
        if quotes:
            # Some government servers refuse this project's polite user agent
            # (yukon.ca answers 403) while serving the same file to a browser.
            # Then the document is read from a copy saved by hand under
            # data/raw/budgets/ — never committed — and still checked quote by quote.
            try:
                body = fetch.bytes(b["url"], force=ctx.refresh)
            except FetchError as exc:
                saved = [f for f in (R.DATA_DIR / "raw" / "budgets").glob(f"{code}.*")]
                if not saved:
                    raise SystemExit(f"{code}: {exc}. Download {b['url']} in a browser and save it as "
                                     f"data/raw/budgets/{code}.pdf (or .html), then re-run.") from exc
                body = saved[0].read_bytes()
                log.warning("%s: %s refused the download; checking the saved copy %s", code, b["url"], saved[0].name)
            if body.startswith(b"%PDF"):
                budget_text.check(quotes, pages=document_text.pdf_pages(body), text=None, where=code)
            else:
                budget_text.check(quotes, pages=None, text=document_text.html_text(body.decode("utf-8", "replace")),
                                  where=code)
            sources.append(SourceRef(url=b["url"], retrieved_at=retrieved, provenance=Provenance.PAGE_VERBATIM,
                                     licence=bsrc["licence"],
                                     content_sha256=_sha(body) if body.startswith(b"%PDF")
                                     else _page_sha(body.decode("utf-8", "replace"))))
        budgets[code] = {"title": b["title"], "url": b["url"],
                         "quotes": [{"page": q.get("page"), "kind": q["kind"], "text": q["text"]} for q in quotes],
                         "note": b.get("note")}
    log.info("budget passages: %d quotes checked across %d documents",
             sum(len(v["quotes"]) for v in budgets.values()), sum(1 for v in budgets.values() if v["quotes"]))

    # ── Output ───────────────────────────────────────────────────────────────
    doc = {
        "generated_at": retrieved,
        "fiscal": {
            "title": fsrc["title"],
            "edition": year_edition,
            "edition_page": fsrc["edition_page"].format(year=year_edition),
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
                "budget": budgets[code],
            }
            for code in sorted(provinces)
        },
        "sources": sources,
    }

    published = ("data/provinces/provinces.json",)
    observations = []
    for code, table in fiscal.items():
        unit = table.unit.en
        for column in table.columns:
            for year, value in zip(table.years, column.values):
                observations.append(Observation(
                    entity=code, category="", period=year, measure=column.label.en, value=value,
                    unit=unit, source_table=f"frt-{year_edition}", provenance=Provenance.OFFICIAL_DATASET.value,
                ).row())
    for code, by_sector in shares["shares"].items():
        marks = shares["symbols"].get(code, {})
        for sector, values in by_sector.items():
            for period, value in zip(shares["periods"], values):
                observations.append(Observation(
                    entity=code, category=sector, period=period, measure="gdp_share_percent", value=value,
                    unit="percent", status=marks.get(sector, {}).get(period, ""), release=release,
                    source_table=pid, provenance=Provenance.OFFICIAL_DATASET.value,
                ).row())

    passages = []
    for code in sorted(provinces):
        for quote in budgets[code]["quotes"]:
            passages.append(Passage(
                entity=code, kind=f"budget_{quote['kind']}", text_en=quote["text"], text_fr="",
                source_url=budgets[code]["url"], locator="" if quote["page"] is None else f"page {quote['page']}",
                provenance=Provenance.PAGE_VERBATIM.value,
            ).row())
        for kind, value in (("motto", words[code]["motto"]), ("flag_description", words[code]["flag"])):
            if value is not None:
                passages.append(Passage(
                    entity=code, kind=kind, text_en=value.en, text_fr=value.fr,
                    source_url=words[code]["pages"]["en"], provenance=Provenance.PAGE_VERBATIM.value,
                ).row())

    obs_frame = frames.Frame(dataset=dataset, name="observations", profile="panel", record_type="observation",
                             keys=frames.OBSERVATION_KEYS, columns=frames.OBSERVATION_COLUMNS, rows=observations,
                             published=published, checks=("paired_values",),
                             notes={"fiscal_edition": year_edition, "shares_table": pid})
    passage_frame = frames.Frame(dataset=dataset, name="passages", profile="passages", record_type="passage",
                                 keys=frames.PASSAGE_KEYS, columns=frames.PASSAGE_COLUMNS, rows=passages,
                                 published=published, checks=("verbatim_quotes",))
    return Built(outputs=[(OUTPUT, to_jsonable(doc))], frames=[obs_frame, passage_frame],
                 receipt={"jurisdictions": len(doc["provinces"]),
                          "fiscal_edition": year_edition,
                          "fiscal_cells": sum(len(c.values) for t in fiscal.values() for c in t.columns),
                          "share_cells": sum(len(v) for by in shares["shares"].values() for v in by.values()),
                          "quotes": sum(len(v["quotes"]) for v in budgets.values()),
                          "images": sum(len(v) for v in images.values())})
