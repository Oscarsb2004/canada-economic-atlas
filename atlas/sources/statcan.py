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


# ── Shaping ────────────────────────────────────────────────────────────────────

def build_series(
    header: list[str],
    rows: list[list[str]],
    *,
    pid: str,
    measure: str,
    frequency: str,
    filters: dict[str, str],
    keep_codes: set[str],
    labels_fr: dict[str, str] | None = None,
    geo_codes: dict[str, str] | None = None,
    release: str = "",
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

    grouped: dict[tuple[str, str], list[list[str]]] = defaultdict(list)
    for row in rows:
        if any(cell(row, col) != want for col, want in filters.items()):
            continue
        code = code_of(cell(row, naics_col))
        if code not in keep_codes:
            continue
        grouped[(cell(row, "GEO"), code)].append(row)

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

        out.append(Series(
            code=code,
            label=Text(en=label_of(raw_label),
                       fr=(labels_fr or {}).get(code, "")),
            geo=(geo_codes or {}).get(geo, geo),
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


def french_labels(header: list[str], rows: list[list[str]]) -> dict[str, str]:
    """Map classification code -> French industry label, from the -fra cube."""
    # "Système de classification des industries de l'Amérique du Nord (SCIAN)"
    # in the French cube; "North American Industry Classification System (NAICS)"
    # in the English one.
    i = next(n for n, c in enumerate(header)
             if "SCIAN" in c or c.startswith("North American Industry"))
    out: dict[str, str] = {}
    for row in rows:
        raw = row[i].strip()
        code = code_of(raw)
        if code and code not in out:
            out[code] = label_of(raw)
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
