"""
atlas.sources.companies — listed-company holdings.

This module answers "which large listed companies operate in this sector". It
does NOT answer "which companies contribute most to GDP", and the distinction is
not pedantry:

    GDP is value added. Company revenue is gross output. Summing revenues within
    a sector double-counts intermediate inputs and overshoots that sector's GDP
    by roughly two to three times.

Statistics Canada is barred by the Statistics Act s.17 from publishing
identifiable enterprise data, so no official company-level output series exists
for Canada at any price. Everything here is therefore `Provenance.MARKET_DATA`
and is labelled market data throughout the UI.

Source: the iShares S&P/TSX Capped Composite (XIC) published holdings CSV — free,
daily, no auth, and it carries ticker, name, GICS sector, index weight, shares
and price for ~220 constituents. That is enough to answer the question above,
which is why the TMX listed-company workbook was dropped from v1: it adds the
full listing universe but no size measure.

Two things the file will mislead you about if taken at face value:

  `Weight (%)` is CAPPED index weight, not market capitalisation and not output.
  The index caps any constituent at 10%, so the largest holdings are understated
  relative to their true float.

  The tail contains non-companies. Cash collateral and futures rows carry an
  asset class of "Cash and/or Derivatives", and at least one stale equity row
  ships with a price of 0.00 and a numeric placeholder ticker.
"""

from __future__ import annotations

import csv
import io
import logging
import re

from atlas.core.schema import Company, Provenance

log = logging.getLogger(__name__)

#: The file opens with "Fund Holdings as of","<date>" then a blank line, and the
#: real header is line 3. Parsed positionally rather than by sniffing, because
#: the preamble is stable and a sniffer would silently pick the wrong row.
HEADER_LINE = 2

_ASOF = re.compile(r'"?Fund Holdings as of"?,\s*"?([^"]+)"?')


def _num(raw: str) -> float | None:
    """
    Parse a holdings-file number.

    Values carry thousands separators ("3,047.11"), so a bare float() raises on
    roughly every large row — which is how a naive reader ends up with only the
    small constituents.
    """
    raw = (raw or "").strip().replace(",", "")
    if not raw or raw == "-":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_holdings(text: str) -> tuple[str, list[dict]]:
    """Return the fund's as-of date and its raw holding rows."""
    text = text.lstrip("\ufeff")
    lines = text.splitlines()

    as_of = ""
    m = _ASOF.match(lines[0]) if lines else None
    if m:
        as_of = m.group(1).strip()

    reader = csv.DictReader(io.StringIO("\n".join(lines[HEADER_LINE:])))
    return as_of, [r for r in reader if r.get("Ticker")]


def to_companies(rows: list[dict], crosswalk: dict[str, dict]) -> list[Company]:
    """
    Filter to real equities and attach the NAICS codes from the crosswalk.

    Dropped, with a count logged rather than silently: anything that is not an
    Equity asset class, anything priced at or below zero, and anything whose
    GICS sector has no crosswalk entry.
    """
    out: list[Company] = []
    dropped: dict[str, int] = {}

    def drop(reason: str) -> None:
        dropped[reason] = dropped.get(reason, 0) + 1

    for r in rows:
        sector = (r.get("Sector") or "").strip()
        price = _num(r.get("Price", ""))

        if (r.get("Asset Class") or "").strip() != "Equity":
            drop("not equity")
            continue
        if price is None or price <= 0:
            drop("zero or missing price")
            continue

        entry = crosswalk.get(sector)
        if entry is None:
            drop(f"no crosswalk for {sector!r}")
            continue

        codes = [entry["primary"], *entry.get("also", [])]
        out.append(Company(
            ticker=(r.get("Ticker") or "").strip(),
            name=(r.get("Name") or "").strip(),
            gics_sector=sector,
            naics_codes=tuple(codes),
            weight_pct=_num(r.get("Weight (%)", "")),
            shares=_num(r.get("Shares", "")),
            price=price,
            currency=(r.get("Currency") or "CAD").strip(),
            provenance=Provenance.MARKET_DATA,
        ))

    for reason, n in sorted(dropped.items()):
        log.info("  dropped %d row(s): %s", n, reason)

    out.sort(key=lambda c: -(c.weight_pct or 0))
    return out
