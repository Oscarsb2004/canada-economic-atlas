"""
Stage 03 — listed companies by sector.

    python pipeline/03_companies.py [--refresh]

Output
    data/companies/xic.json

Panel B of the two-panel split described in the plan. Panel A — how large a
sector is commercially — comes from StatCan operating revenue and is a real
economic measure. This panel is MARKET data: which large listed companies
operate in a sector, ranked by index weight.

They are kept apart deliberately. Company revenue is gross output and GDP is
value added, so summing companies within a sector overshoots that sector's GDP
by two to three times. Presenting this as "top GDP contributors" would not be
imprecise, it would be wrong, and no amount of caveating fixes a wrong number in
a chart title.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from atlas.core import registry as R
from atlas.core.schema import to_jsonable
from atlas.net import Fetcher
from atlas.sources import companies as C

log = logging.getLogger("03_companies")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _strip_volatile(obj):
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items() if k != "generated_at"}
    if isinstance(obj, list):
        return [_strip_volatile(v) for v in obj]
    return obj


def _write_if_changed(path: Path, payload: dict) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            if _strip_volatile(json.loads(path.read_text(encoding="utf-8"))) == \
               _strip_volatile(payload):
                return False
        except json.JSONDecodeError:
            pass
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8")
    return True


def load_crosswalk() -> tuple[dict[str, dict], list[str]]:
    """GICS sector -> {primary, also}, plus the values that are not sectors."""
    with (R.REGISTRY_DIR / "gics_naics.yaml").open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return {e["gics"]: e for e in raw["map"]}, list(raw.get("not_sectors", []))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true", help="bypass the HTTP cache")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    src = R.source("xic_holdings")
    crosswalk, not_sectors = load_crosswalk()
    fetch = Fetcher(cache_dir=R.DATA_DIR / "raw" / "cache", use_cache=not args.refresh)

    log.info("Stage 03 — %s", src["title"])
    as_of, rows = C.parse_holdings(fetch.text(src["csv"]))
    log.info("fund as of %s — %d rows", as_of, len(rows))

    firms = C.to_companies(rows, crosswalk)
    log.info("%d companies kept", len(firms))

    # Every GICS sector present must have a crosswalk entry, or the company
    # panel silently loses a whole sector. Checked, not trusted.
    seen = {(r.get("Sector") or "").strip() for r in rows}
    unmapped = {s for s in seen if s and s not in crosswalk and s not in not_sectors}
    if unmapped:
        log.warning("GICS sectors with no crosswalk entry: %s", sorted(unmapped))

    by_naics = Counter(c.naics_codes[0] for c in firms)
    log.info("primary NAICS coverage: %s",
             ", ".join(f"{k}={v}" for k, v in sorted(by_naics.items())))

    out = R.DATA_DIR / "companies" / "xic.json"
    changed = _write_if_changed(out, {
        "generated_at": _now(),
        "as_of": as_of,
        "count": len(firms),
        "source": {
            "title": src["title"],
            "url": src["csv"],
            "licence": src["licence"],
            "attribution": src["attribution"],
        },
        # Carried in the payload so the app cannot render this panel without the
        # caveat travelling alongside the numbers.
        "caveat": {
            "en": "Index weight, not company output. Capped at 10% per holding. "
                  "Not a measure of contribution to GDP.",
            "fr": "Pondération de l'indice, et non la production des entreprises. "
                  "Plafonnée à 10 % par titre. Ne mesure pas la contribution au PIB.",
        },
        "companies": to_jsonable(firms),
    })

    log.info("xic.json %d companies  %.0f KB  %s",
             len(firms), out.stat().st_size / 1000, "updated" if changed else "unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
