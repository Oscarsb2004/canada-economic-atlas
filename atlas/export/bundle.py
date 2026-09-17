"""
atlas.export.bundle — assemble what the web app actually reads.

    python -m atlas.run bundle

(Was pipeline/99_bundle.py until step S8 of docs/REBUILD.md; the code is carried
unchanged. Its header said "Stage 04" — the stage it was split from years of
commits ago — which is one more reason the bundle is now named rather than
numbered. The runner writes its three generated files and performs its copies.)

Copies the stage outputs into `web/public/data/` and writes three files that
only exist at this stage:

    meta.json      the bundle contract: schema version, per-source licence and
                   attribution, and the file manifest
    country.json   Canada as one ISO3 node with a few headline figures, for the
                   sibling repo world-strategic-map
    palette.json   the validated colour system, from registry/palette.yaml

Vite serves `public/` verbatim, so the app is a plain fetch() against these
paths — no loader plumbing, no import graph, no build-time data step.

`schema_version` is a CROSS-REPO CONTRACT. It is semver, and it is bumped on any
breaking shape change, because world-strategic-map asserts compatibility against
it on load and fails loudly rather than rendering a half-read bundle.
"""

from __future__ import annotations

import json
import logging

import yaml

from atlas.core import clock
from atlas.core import frames  # noqa: F401  (kept so the module's shape matches the other builders)
from atlas.core import registry as R
from atlas.core.schema import Provenance, SourceRef
from atlas.datasets import Built, Context

log = logging.getLogger(__name__)

#: Bump on ANY breaking shape change. See the module docstring.
SCHEMA_VERSION = "1.0.0"

#: What gets copied into the bundle, and what each part is called there.
COPIES = [
    "events/major-projects-office/projects.json",
    "events/major-projects-office/strategies.json",
    "events/major-projects-office/industries.json",
    "events/trade-corridors/corridors.json",
    "sectors/national-monthly.json",
    "sectors/national-constant.json",
    "sectors/provincial-annual.json",
    "sectors/rates.json",
    "sectors/business-counts.json",
    "provinces/provinces.json",
]

#: The figures the sibling repo joins on. Stable keys — renaming one is a
#: breaking change and takes a schema_version bump with it.
HEADLINE = [
    ("gdp_real_all_industries", "T001"),
    ("gdp_real_goods", "T002"),
    ("gdp_real_services", "T003"),
]


def _load(rel: str) -> dict | None:
    p = R.DATA_DIR / rel
    if not p.exists():
        log.warning("missing %s — run its stage first", rel)
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _latest(series: dict) -> tuple[str, float] | None:
    """The most recent non-null (period, value) of a series."""
    for period, value in zip(reversed(series["periods"]), reversed(series["values"])):
        if value is not None:
            return period, value
    return None


def build_country(sectors: dict | None, rates: dict | None) -> dict:
    """
    Canada as one node, for world-strategic-map.

    `headline` is a LIST, not an object, so new figures append without breaking
    the sibling. Every entry carries its own SourceRef and provenance, so the
    governing rule — identity travels with the value, nothing is re-derived —
    survives the repo boundary.

    `release_time` sits beside `period` for the same reason it matters
    internally: the sibling shows Canada next to countries whose figures are
    annual and years stale, and the vintage is what makes that comparison
    honest rather than flattering.
    """
    statcan = R.source("statcan_wds")
    boc = R.source("boc_valet")
    licences = R.sources()["licences"]
    out: list[dict] = []

    # sha256 of the source cube zips, written by stage 02. Published so the
    # SourceRef carries a real change signal rather than an empty string; the
    # sibling repo correctly flagged the blank field as unusable.
    cubes = (_load("sectors/_cubes.json") or {}).get("cubes", {})

    if sectors:
        by_code = {s["code"]: s for s in sectors["series"] if s["geo"] == "CA"}
        for key, code in HEADLINE:
            s = by_code.get(code)
            if not s:
                log.warning("headline %s: no series for %s", key, code)
                continue
            latest = _latest(s)
            if not latest:
                continue
            period, value = latest
            table = s["source_table"]
            out.append({
                "key": key,
                "label": s["label"],
                "value": value,
                "unit": s["unit"],
                "scalar": s["scalar"],
                "period": period,
                "frequency": s["frequency"],
                "source_table": table,
                "release_time": s["release_time"],
                "provenance": s["provenance"],
                "source": SourceRef(
                    url=statcan["base"] + "getFullTableDownloadCSV/" + table + "/en",
                    retrieved_at=sectors.get("generated_at", ""),
                    provenance=Provenance.OFFICIAL_DATASET,
                    licence=statcan["licence"],
                    content_sha256=cubes.get(table, ""),
                ).to_dict(),
            })

    if rates and rates.get("policy_rate"):
        pr = rates["policy_rate"]
        out.append({
            "key": "policy_rate",
            "label": {"en": pr["label"], "fr": ""},
            "value": pr["value"],
            "unit": "percent",
            "scalar": "units",
            "period": pr["period"],
            "frequency": "daily",
            "source_table": pr["series"],
            "release_time": "",
            "provenance": pr["provenance"],
            "source": SourceRef(
                url=pr["source_url"],
                retrieved_at=rates.get("generated_at", ""),
                provenance=Provenance.OFFICIAL_DATASET,
                licence=boc["licence"],
            ).to_dict(),
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "iso3": "CAN",
        "iso2": "CA",
        "name": {"en": "Canada", "fr": "Canada"},
        "generated_at": clock.now_iso(),
        "atlas": {"repo": "canada-economic-atlas", "meta": "/data/meta.json"},
        "attribution": {
            "statcan": licences[statcan["licence"]]["name"],
            "boc": licences[boc["licence"]].get("attribution", ""),
        },
        "headline": out,
    }


def build(ctx: Context, *, dataset: str) -> Built:
    """The bundle: every dataset the site reads, plus meta, country and palette."""
    web = R.WEB_DATA_DIR
    log.info("bundle to %s", web.relative_to(R.ROOT))

    # Every file this stage puts in the bundle, accumulated as it goes.
    #
    # The manifest used to be `COPIES + ["country.json", "palette.json"]` — a
    # hand-maintained restatement that had ALREADY drifted: `corridors.json` was
    # written here and omitted there, so `verify/`'s existence loop never covered
    # it while `bundle.ts` fetched it eagerly and threw on a 404. The bundle
    # could have shipped without it and every gate would have passed.
    #
    # Generating the list from what was actually written makes that class of
    # omission impossible rather than fixed once.
    written: list[str] = []

    copies = []
    for rel in COPIES:
        src = R.DATA_DIR / rel
        if not src.exists():
            log.warning("skipping missing %s", rel)
            continue
        copies.append((src, web / rel))
        written.append(rel)

    sectors = _load("sectors/national-monthly.json")
    rates = _load("sectors/rates.json")
    country = build_country(sectors, rates)
    written.append("country.json")
    log.info("country.json: %d headline figures (%s)",
             len(country["headline"]), ", ".join(h["key"] for h in country["headline"]))

    palette = yaml.safe_load((R.REGISTRY_DIR / "palette.yaml").read_text(encoding="utf-8"))
    written.append("palette.json")

    srcs = R.sources()
    meta = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": clock.now_iso(),
        "app": "canada-economic-atlas",
        "licences": srcs["licences"],
        "sources": {k: {kk: vv for kk, vv in v.items() if isinstance(vv, str)}
                    for k, v in srcs["sources"].items()},
        "files": sorted(written),
    }

    return Built(
        outputs=[(web / "country.json", country), (web / "palette.json", palette), (web / "meta.json", meta)],
        copies=copies,
        receipt={"files": sorted(written), "schema_version": SCHEMA_VERSION,
                 "headline": [h["key"] for h in country["headline"]]},
    )
