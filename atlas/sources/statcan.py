"""
atlas.sources.statcan — Statistics Canada Web Data Service.

Keyless, no registration, no cost, under the Statistics Canada Open Licence.

**Bulk download is the primary path.** `getFullTableDownloadCSV` returns an
entire cube as one zip — 6.8 MB for the monthly GDP cube — in a single request.
The obvious alternative, `getDataFromVectorsAndLatestNPeriods`, needs the vector
list up front, caps at 300 vectors per POST (undocumented; 400 returns HTTP 416),
and would be dozens of requests for the same data. Bulk is simpler, atomic, and
lighter on their servers.

Three traps, all confirmed against the live service:

  The `productId` is the 8-digit CUBE, not the 10-digit table view. Table
  36-10-0434-01 is `pid=3610043401` on the website but `36100434` in the API;
  views -01 through -06 are all the same cube.

  Table 36-10-0402 is dead — silently replaced by 36-10-0711, same title. Using
  the old number gets you data that stops in 2024.

  Chained dollars are not additive. The cube's own footnote says "aggregates are
  not always equal to the sum of their components", so any view where components
  must sum to their total has to read the constant-price series instead.

The industry column embeds its classification code — "Manufacturing [31-33]" —
so the join key across GDP, employment and revenue tables comes free, and the
label arrives from the source rather than being carried by us.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Iterator

from atlas.core.schema import Provenance, Series, Text
from atlas.net import Fetcher

log = logging.getLogger(__name__)

WDS = "https://www150.statcan.gc.ca/t1/wds/rest"

#: Undocumented cap on getDataFromVectorsAndLatestNPeriods POST bodies: 300
#: succeeds, 400 returns HTTP 416. NOTHING IN THIS REPO CALLS THAT ENDPOINT —
#: every stage reads bulk CSV — so this records a finding for the incremental
#: refresh BACKLOG E3 would add; it is not a live limit. An earlier comment said
#: "the incremental path hits this" when no incremental path existed, and a test
#: asserted the constant equalled the number it was defined as.
VECTOR_BATCH_MAX = 300

#: "Manufacturing [31-33]" -> "31-33". The bracketed code is the join key.
_CODE = re.compile(r"\[([^\]]+)\]\s*$")

#: SCALAR_ID -> human scalar, from the service's own code set.
SCALARS = {"0": "units", "3": "thousands", "6": "millions", "9": "billions"}


def code_of(label: str) -> str:
    """
    Extract the classification code a StatCan industry label carries.

    Returns "" when the label has no bracketed code, which is how the special
    aggregates and the odd provincial-only member are told apart from real
    NAICS sectors without a second lookup.
    """
    m = _CODE.search(label or "")
    return m.group(1) if m else ""


def label_of(label: str) -> str:
    """The industry label with its bracketed code removed."""
    return _CODE.sub("", label or "").strip()


# ── Bulk download ──────────────────────────────────────────────────────────────

def download_cube(fetch: Fetcher, pid: str, lang: str, dest_dir: Path) -> Path:
    """
    Fetch a whole cube as a zip and return the local path.

    `lang` is StatCan's own suffix vocabulary: "eng" or "fra".
    """
    api_lang = "en" if lang == "eng" else "fr"
    resp = fetch.json(f"{WDS}/getFullTableDownloadCSV/{pid}/{api_lang}")
    if resp.get("status") != "SUCCESS":
        raise RuntimeError(f"WDS refused cube {pid}: {resp}")

    dest = dest_dir / f"{pid}-{lang}.zip"
    fetch.download(resp["object"], dest)
    return dest


def read_cube(zip_path: Path, pid: str, member: str | None = None) -> tuple[list[str], list[list[str]]]:
    """
    Header and rows of a downloaded cube's data CSV — or, with `member`, of
    another file in the same archive. The census table's geographic
    attributes (legal type, province code) live only in `_MetaData.csv`.

    The delimiter is detected, not assumed. The English cube is comma-separated
    and the FRENCH CUBE IS SEMICOLON-SEPARATED — the European convention, since
    French uses the comma as a decimal mark. Parsing the French file with a
    comma yields exactly one enormous column per row, no error, and every French
    label silently comes back empty while the English side looks perfect.

    utf-8-sig strips the BOM these files carry; without it the first column name
    becomes "﻿REF_DATE" and every lookup misses.
    """
    with zipfile.ZipFile(zip_path) as z:
        # Read once into memory rather than seeking: a zip member stream is not
        # seekable, and these cubes are ~50 MB of text, which is fine.
        with z.open(member or f"{pid}.csv") as fh:
            body = io.TextIOWrapper(fh, encoding="utf-8-sig").read()

    first = body[: body.find("\n")]
    delimiter = ";" if first.count(";") > first.count(",") else ","

    reader = csv.reader(io.StringIO(body), delimiter=delimiter)
    header = next(reader)
    return header, list(reader)


def iter_cube(zip_path: Path, pid: str, member: str | None = None) -> Iterator[list[str]]:
    """
    A cube's rows one at a time, HEADER FIRST, without holding the file.

        rows = iter_cube(path, pid)
        header = next(rows)

    `read_cube` reads the whole CSV into memory, which is right for a 7 MB GDP
    cube and wrong for SEPH (14100201): 986 MB of English CSV and 1,075 MB of
    French, 5.3 million rows. Parsed into lists of strings that is several
    gigabytes, for a pull that keeps one row in sixty.

    Same delimiter detection as `read_cube` — the French file is semicolons —
    and `newline=""` so a quoted field containing a line break stays one field.
    """
    with zipfile.ZipFile(zip_path) as z, z.open(member or f"{pid}.csv") as fh:
        text = io.TextIOWrapper(fh, encoding="utf-8-sig", newline="")
        first = text.readline()
        delimiter = ";" if first.count(";") > first.count(",") else ","
        yield next(csv.reader([first], delimiter=delimiter))
        yield from csv.reader(text, delimiter=delimiter)


# ── Shaping ────────────────────────────────────────────────────────────────────

def build_series(
    header: list[str],
    rows: Iterable[list[str]],
    *,
    pid: str,
    measure: str,
    frequency: str,
    filters: dict[str, str],
    keep_codes: set[str],
    labels_fr: dict[str, str] | None = None,
    geo_codes: dict[str, str] | None = None,
    release: str = "",
    code_aliases: dict[str, str] | None = None,
    status_out: dict[str, tuple[str, ...]] | None = None,
) -> list[Series]:
    """
    Turn cube rows into `Series`, one per (geography, industry code).

    `keep_codes` is an allowlist, which is doing real work: the provincial cube
    carries members the monthly cube does not (4AA "Retail trade except
    cannabis", 51A, 53A). Summing without filtering double-counts them against
    the sectors they duplicate.

    Values are parsed as floats, with blanks preserved as None rather than
    dropped — a suppressed or not-yet-published period is not the same as a
    period that does not exist, and collapsing them would silently shorten a
    series. `Series.__post_init__` enforces that periods and values stay aligned.

    `code_aliases` maps a code as published onto the registry's key — SEPH
    publishes Utilities as [22,221]. An alias that lands two DIFFERENT published
    members on one key raises: their months would interleave into one series
    with every period twice, and nothing downstream could tell.

    `status_out`, when given, receives each series' STATUS column keyed
    "GEO/CODE", but only for series where some cell carries one. The column
    holds suppression ("x", "..") and quality grades (A–F, E = use with
    caution), and a value read without its grade is published with authority
    the source withheld.
    """
    idx = {name: i for i, name in enumerate(header)}
    naics_col = next(c for c in header if c.startswith("North American Industry"))

    # A filter naming a column the cube no longer has would reject every row and
    # yield an EMPTY series list — no exception, just nothing. That surfaces
    # three stages later as "the registry is missing sectors", which points the
    # reader at the wrong file. Fail here, naming the column.
    missing = [col for col in filters if col not in idx]
    if missing:
        raise ValueError(
            f"cube {pid}: filter columns {missing} are not in the CSV header. "
            f"StatCan changed the cube's shape; available columns are {header}"
        )

    def cell(row: list[str], col: str) -> str:
        return row[idx[col]].strip() if col in idx else ""

    aliases = code_aliases or {}
    width = len(header)
    grouped: dict[tuple[str, str], list[list[str]]] = defaultdict(list)
    member_of: dict[tuple[str, str], str] = {}
    for row in rows:
        # A short row is a blank line or a footnote, never data; indexing it
        # would raise IndexError far from the cause.
        if len(row) < width:
            continue
        if any(cell(row, col) != want for col, want in filters.items()):
            continue
        member = cell(row, naics_col)
        published = code_of(member)
        code = aliases.get(published, published)
        if code not in keep_codes:
            continue
        key = (cell(row, "GEO"), code)
        first = member_of.setdefault(key, member)
        if first != member:
            raise ValueError(
                f"cube {pid}: {first!r} and {member!r} both map to code {code} in "
                f"{key[0]}. An alias may rename a published code, never merge two."
            )
        grouped[key].append(row)

    # Same failure in the other direction: the columns exist but a filter VALUE
    # was renamed ("Chained (2017) dollars" -> something else), so nothing
    # matches. Also loud, also naming what was looked for.
    if not grouped:
        raise ValueError(
            f"cube {pid}: no rows matched {filters}. The columns exist, so a "
            f"filter value has changed — check the cube's member names."
        )

    out: list[Series] = []
    for (geo, code), group in grouped.items():
        group.sort(key=lambda r: cell(r, "REF_DATE"))
        raw_label = cell(group[0], naics_col)

        periods, values = [], []
        for row in group:
            periods.append(cell(row, "REF_DATE"))
            raw = cell(row, "VALUE")
            values.append(float(raw) if raw else None)

        geo_code = (geo_codes or {}).get(geo, geo)
        if status_out is not None:
            statuses = tuple(cell(row, "STATUS") for row in group)
            if any(statuses):
                status_out[f"{geo_code}/{code}"] = statuses

        out.append(Series(
            code=code,
            label=Text(en=label_of(raw_label),
                       fr=(labels_fr or {}).get(code, "")),
            geo=geo_code,
            measure=measure,
            unit=cell(group[0], "UOM"),
            scalar=SCALARS.get(cell(group[0], "SCALAR_ID"), cell(group[0], "SCALAR_FACTOR")),
            frequency=frequency,
            periods=tuple(periods),
            values=tuple(values),
            source_table=pid,
            release_time=release,
            provenance=Provenance.OFFICIAL_DATASET,
        ))
    return out


def french_labels(
    header: list[str],
    rows: Iterable[list[str]],
    *,
    code_aliases: dict[str, str] | None = None,
    want: set[str] | None = None,
) -> dict[str, str]:
    """
    Map classification code -> French industry label, from the -fra cube.

    `want`, when given, stops the read as soon as every wanted code has a label.
    Industry members repeat for every period, so for SEPH all of them appear in
    the first few thousand rows of a five-million-row file, and reading the rest
    would only re-read them. `code_aliases` must be the same map the English
    build used, or the French labels land on the published code, not the key.
    """
    # "Système de classification des industries de l'Amérique du Nord (SCIAN)"
    # in the French cube; "North American Industry Classification System (NAICS)"
    # in the English one.
    i = next(n for n, c in enumerate(header)
             if "SCIAN" in c or c.startswith("North American Industry"))
    aliases = code_aliases or {}
    out: dict[str, str] = {}
    for row in rows:
        if len(row) <= i:
            continue
        raw = row[i].strip()
        published = code_of(raw)
        code = aliases.get(published, published)
        if code and code not in out:
            out[code] = label_of(raw)
            if want and want <= out.keys():
                break
    return out


def cube_metadata(zip_path: Path, pid: str) -> dict:
    """
    The cube's own title and numbered notes, from `<pid>_MetaData.csv`, in the
    zip's language.

    The notes are where StatCan says the things no column does — that SEPH
    excludes agriculture, that the last two capex years are intentions — so a
    payload that reproduces them carries its own caveats rather than relying on
    someone reading the table page.
    """
    _, rows = read_cube(zip_path, pid, member=f"{pid}_MetaData.csv")
    title = rows[0][0].strip() if rows and rows[0] else ""
    notes: dict[str, str] = {}
    start = next((i for i, r in enumerate(rows)
                  if len(r) >= 2 and "note" in r[0].lower() and "note" in r[1].lower()), None)
    if start is not None:
        for r in rows[start + 1:]:
            if len(r) < 2 or not r[0].strip().isdigit():
                break
            notes[r[0].strip()] = r[1].strip()
    return {"title": title, "notes": notes}


def latest_periods_basis(
    periods: Iterable[str],
    notes: dict[str, str],
    *,
    contains: str,
    labels: list[str],
    earlier: str = "actual",
) -> tuple[dict[str, str], str]:
    """
    Which periods are measurements and which are not, when a cube says so only
    in a note. Returns (period -> basis, the note's id).

    Table 34-10-0035 has no column separating actual spending from preliminary
    actuals and intentions; its note says "Most recent 2 years of data are
    preliminary actuals and intentions". The latest `len(labels)` periods get
    `labels`, in order, and every earlier period gets `earlier`.

    The rule applies only while the cube still publishes the note: `contains`
    must appear in one, or this raises. A rule read out of a note must stop the
    moment the note changes, not keep labelling years by a statement the
    publisher withdrew.
    """
    note_id = next((i for i, text in notes.items() if contains in text), None)
    if note_id is None:
        raise ValueError(
            f"no cube note contains {contains!r}; the period basis cannot be "
            f"assigned. Notes were: {list(notes.values())[:6]}"
        )
    ordered = sorted(set(periods))
    basis = {p: earlier for p in ordered}
    for period, label in zip(ordered[-len(labels):], labels):
        basis[period] = label
    return basis, note_id


def member_labels(
    header: list[str],
    rows: Iterable[list[str]],
    *,
    column: str,
    codes: set[str],
    total_code: str,
) -> dict[str, str]:
    """
    Code -> label for the members of a non-NAICS industry column, in the file's
    language, stopping once every wanted code is found.

    The cube's total is its one member with no bracketed code — "Total
    industries" in English, whatever the French file calls it — and is recorded
    under `total_code`, so the French total is found without guessing its
    wording. A second uncoded member raises: the total could no longer be told
    apart from it.
    """
    if column not in header:
        raise ValueError(f"no {column!r} column; header is {header}")
    i = header.index(column)
    out: dict[str, str] = {}
    uncoded: str | None = None
    for row in rows:
        if len(row) <= i:
            continue
        member = row[i].strip()
        code = code_of(member)
        if not code:
            if uncoded is not None and uncoded != member:
                raise ValueError(f"two members without a code: {uncoded!r} and {member!r}")
            uncoded, code = member, total_code
        if code in codes and code not in out:
            out[code] = label_of(member)
            if codes <= out.keys():
                break
    return out


def build_crosswalk_series(
    header: list[str],
    rows: Iterable[list[str]],
    *,
    pid: str,
    measure: str,
    frequency: str,
    column: str,
    crosswalk: dict[str, list[str]],
    total_member: str,
    total_code: str,
    labels: dict[str, Text],
    geo_codes: dict[str, str] | None = None,
    release: str = "",
    status_out: dict[str, tuple[str, ...]] | None = None,
) -> list[Series]:
    """
    Sector series summed from a cube that is NOT classified by NAICS.

    Table 36-10-0488 (output by industry) uses the Input-Output Industry
    Classification, and splits every industry by institutional sector: business
    (BS…), non-profit institutions serving households (NP…) and government
    (GS…). No member of it is "NAICS 61" — education is BS610 + NP61000 + GS610.
    `crosswalk` maps each registry sector to the members that make it up, and
    the sum is this project's, so every summed series is `Provenance.DERIVED`.
    The cube's own total is reproduced under `total_code` and stays
    OFFICIAL_DATASET.

    A sector is None in any period where ANY of its members is blank or
    missing. Summing the published members and skipping the blank one would
    report part of a sector as all of it.

    A member mapped to two sectors raises: it would be counted twice, and
    nothing downstream would notice except a total that no longer adds up.
    """
    owner: dict[str, str] = {}
    for sector, members in crosswalk.items():
        for member in members:
            if member in owner:
                raise ValueError(f"cube {pid}: member {member} is mapped to both {owner[member]} and {sector}")
            owner[member] = sector
    if column not in header:
        raise ValueError(f"cube {pid}: no {column!r} column; header is {header}")
    idx = {name: i for i, name in enumerate(header)}
    width = len(header)

    # (geo, period) -> code -> (value or None, STATUS)
    cells: dict[tuple[str, str], dict[str, tuple[float | None, str]]] = defaultdict(dict)
    unit = scalar = ""
    for row in rows:
        if len(row) < width:
            continue
        member = row[idx[column]].strip()
        code = total_code if member == total_member else code_of(member)
        if code != total_code and code not in owner:
            continue
        raw = row[idx["VALUE"]].strip()
        status = row[idx["STATUS"]].strip() if "STATUS" in idx else ""
        cells[(row[idx["GEO"]].strip(), row[idx["REF_DATE"]].strip())][code] = (float(raw) if raw else None, status)
        if not unit:
            unit = row[idx["UOM"]].strip()
            scalar = SCALARS.get(row[idx["SCALAR_ID"]].strip(), row[idx["SCALAR_FACTOR"]].strip())

    published = {code for by_code in cells.values() for code in by_code}
    unseen = sorted((set(owner) | {total_code}) - published)
    if unseen:
        raise ValueError(f"cube {pid}: crosswalk members never published: {unseen}")

    out: list[Series] = []
    for geo in sorted({g for g, _ in cells}):
        geo_code = (geo_codes or {}).get(geo, geo)
        periods = sorted(p for g, p in cells if g == geo)
        plan = [(total_code, [total_code], Provenance.OFFICIAL_DATASET)]
        plan += [(sector, members, Provenance.DERIVED) for sector, members in crosswalk.items()]
        for code, members, provenance in plan:
            if code not in labels:
                raise ValueError(f"cube {pid}: no label for {code}")
            values: list[float | None] = []
            statuses: list[str] = []
            for period in periods:
                got = [cells[(geo, period)].get(m) for m in members]
                flags = ",".join(sorted({g[1] for g in got if g is not None and g[1]}))
                if any(g is None or g[0] is None for g in got):
                    values.append(None)
                else:
                    values.append(sum(g[0] for g in got))
                statuses.append(flags)
            if status_out is not None and any(statuses):
                status_out[f"{geo_code}/{code}"] = tuple(statuses)
            out.append(Series(
                code=code, label=labels[code], geo=geo_code, measure=measure, unit=unit,
                scalar=scalar, frequency=frequency, periods=tuple(periods), values=tuple(values),
                source_table=pid, release_time=release, provenance=provenance,
            ))
    return out


def release_time(fetch: Fetcher, pid: str) -> str:
    """
    The cube's own publication stamp, via `getCubeMetadata`.

    Recorded beside every series because GDP is revised: two runs a month apart
    legitimately disagree about a recent month, and without the vintage stored
    that reads as a bug rather than a revision. It also travels into
    `country.json` for the sibling repo, where Canada sits beside countries
    whose figures are years stale — the vintage is what makes that comparison
    honest rather than flattering.

    Returns "" on failure rather than raising: a missing vintage should degrade
    the display, not abort a pull that otherwise succeeded.
    """
    try:
        body = fetch.post_json(f"{WDS}/getCubeMetadata", [{"productId": int(pid)}])
        return (body[0].get("object", {}) or {}).get("releaseTime", "")
    except Exception as exc:                          # noqa: BLE001
        log.warning("no release time for cube %s: %s", pid, exc)
        return ""
