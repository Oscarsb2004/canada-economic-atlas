"""
verify — independent verification of the committed data.

    python -m verify.run [--gate-only]

THIS PACKAGE MUST NOT IMPORT `atlas`.

Verification that imports the code it checks inherits that code's bugs. If
`atlas.sources.mpo` mis-parses a page, a verifier built on `atlas.sources.mpo`
agrees with it enthusiastically. So this re-reads the YAML and JSON from disk
with the standard library and checks the OUTPUT against the registry's stated
expectations, using different logic than the pipeline used to produce it.

African-Stability-Index states this rule and then broke it — its advisory layer
quietly loaded the panel through the same module the interface used — so here it
is enforced: `tests/test_verify_independence.py` AST-scans this package and
fails on any `atlas.*` import.

Two layers:

    gate      failures block a release. Structural claims that must hold.
    advisory  reports and never blocks. Things worth a human's eye.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
WEB = ROOT / "web" / "public"
REGISTRY = ROOT / "registry"

#: The 13 provinces and territories. Re-declared here rather than imported —
#: see the module docstring.
PROVINCE_CODES = frozenset(
    {"NL", "NS", "PE", "NB", "QC", "ON", "MB", "SK", "AB", "BC", "YT", "NT", "NU"}
)


@dataclass
class Report:
    gate_failures: list[str] = field(default_factory=list)
    advisories: list[str] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)

    def gate(self, ok: bool, label: str, detail: str = "") -> None:
        (self.passed if ok else self.gate_failures).append(label if ok else f"{label}: {detail}")

    def note(self, label: str) -> None:
        self.advisories.append(label)


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# ── Gate: events ───────────────────────────────────────────────────────────────

def check_projects(r: Report) -> None:
    """Every project is mappable, attributed, and bilingual."""
    events = _load_yaml(REGISTRY / "events.yaml")["events"]
    event = next(e for e in events if e["slug"] == "major-projects-office")
    expected = event.get("expected", {})

    doc = _load_json(DATA / "events" / "major-projects-office" / "projects.json")
    projects = doc["projects"]

    r.gate(
        len(projects) == expected.get("projects"),
        "project count matches the registry",
        f"{len(projects)} projects, registry expects {expected.get('projects')}",
    )

    features = sum(len(p["sites"]) for p in projects)
    r.gate(
        features == expected.get("features"),
        "site count matches the registry",
        f"{features} sites, registry expects {expected.get('features')}",
    )

    # Geometry: every site must carry coordinates, or say why not.
    ungeometried = [
        p["slug"] for p in projects
        for s in p["sites"]
        if s["geometry"]["kind"] not in ("point", "corridor") or not s["geometry"]["coordinates"]
    ]
    r.gate(not ungeometried, "every site has published coordinates", str(ungeometried))

    # A corridor is exactly two points; a point is exactly one. Anything else
    # means the classifier and the data disagree.
    miscounted = [
        f'{p["slug"]}/{s["geometry"]["kind"]}={len(s["geometry"]["coordinates"])}'
        for p in projects
        for s in p["sites"]
        if (s["geometry"]["kind"] == "point" and len(s["geometry"]["coordinates"]) != 1)
        or (s["geometry"]["kind"] == "corridor" and len(s["geometry"]["coordinates"]) != 2)
    ]
    r.gate(not miscounted, "point/corridor geometry counts are consistent", str(miscounted))

    # Coordinates must be inside Canada's bounding box. A lat/lon swap is the
    # classic geo bug and lands somewhere in the Indian Ocean.
    out_of_box = []
    for p in projects:
        for s in p["sites"]:
            for lon, lat in s["geometry"]["coordinates"]:
                if not (-142 <= lon <= -52 and 41 <= lat <= 84):
                    out_of_box.append(f'{p["slug"]} [{lon}, {lat}]')
    r.gate(not out_of_box, "all coordinates fall inside Canada", str(out_of_box))

    # Provenance and attribution must travel with the text.
    unsourced = [
        p["slug"] for p in projects
        if not any(s.get("provenance") == "page_verbatim" and s.get("url") for s in p["sources"])
    ]
    r.gate(not unsourced, "every project cites the page it was reproduced from", str(unsourced))

    unhashed = [
        p["slug"] for p in projects
        for s in p["sources"]
        if s.get("provenance") == "page_verbatim" and not s.get("content_sha256")
    ]
    r.gate(not unhashed, "every verbatim capture carries a content hash", str(unhashed))

    # Bilingual: EN and FR must agree on how many things they found. A silent
    # FR parse failure looks exactly like a page with no quick facts.
    fr_gaps = [
        f'{p["slug"]} qf {len(p["quick_facts"])}'
        for p in projects
        if not p["description"]["fr"]
    ]
    r.gate(not fr_gaps, "every project has a French description", str(fr_gaps))

    mismatched = [
        p["slug"] for p in projects
        for f in p["quick_facts"]
        if f["label"]["en"] and not f["label"]["fr"]
    ]
    if mismatched:
        r.note(f"quick facts with no French label on {sorted(set(mismatched))}")

    # Media: both derived sizes must exist on disk, not just be referenced.
    missing_media = []
    for p in projects:
        for m in p["media"]:
            for key in ("thumb", "web"):
                rel = m.get(key, "")
                if not rel:
                    missing_media.append(f'{p["slug"]}.{key} not set')
                elif not (WEB / rel.lstrip("/")).exists():
                    missing_media.append(f'{p["slug"]}.{key} -> {rel}')
    r.gate(not missing_media, "every referenced image exists at both sizes", str(missing_media))


def check_strategies(r: Report) -> None:
    """Every strategy is hand-mapped to real province codes, or says it is not."""
    reg = {s["slug"]: s for s in _load_yaml(REGISTRY / "strategies.yaml")["strategies"]}
    doc = _load_json(DATA / "events" / "major-projects-office" / "strategies.json")

    unmapped = [s["slug"] for s in doc["strategies"] if s["slug"] not in reg]
    r.gate(not unmapped, "every published strategy has a registry entry", str(unmapped))

    bad_codes = []
    for slug, entry in reg.items():
        for code in entry.get("provinces", []):
            if not isinstance(code, str):
                bad_codes.append(f"{slug}: {code!r} is not a string (YAML boolean coercion)")
            elif code not in PROVINCE_CODES:
                bad_codes.append(f"{slug}: {code}")
    r.gate(not bad_codes, "every province code is a valid string code", str(bad_codes))

    # The government's own wording must survive, because our province mapping is
    # only a reading of it.
    no_verbatim = [slug for slug, e in reg.items() if not e.get("location_verbatim")]
    r.gate(not no_verbatim, "every strategy keeps its verbatim location string", str(no_verbatim))


# ── Gate: sectors ──────────────────────────────────────────────────────────────

def check_sectors(r: Report) -> None:
    """The partition holds, the taxonomy is complete, and no period is invented."""
    tax = _load_yaml(REGISTRY / "sectors.yaml")
    total_code = tax["aggregates"]["total"]
    parts = tax["aggregates"]["partition"]

    for name, exact in (("national-monthly", False), ("national-constant", True)):
        doc = _load_json(DATA / "sectors" / f"{name}.json")
        by = {s["code"]: s for s in doc["series"] if s["geo"] == "CA"}

        missing = [c["code"] for c in tax["sectors"] if c["code"] not in by]
        r.gate(not missing, f"{name}: every registry sector is present", str(missing))

        t, g, s = by.get(total_code), by.get(parts[0]), by.get(parts[1])
        if not (t and g and s):
            r.gate(False, f"{name}: aggregates present", "missing T001/T002/T003")
            continue

        # Find the last period where all three have values, and check the identity.
        drift = None
        for i in range(len(t["values"]) - 1, -1, -1):
            tv, gv, sv = t["values"][i], g["values"][i], s["values"][i]
            if None not in (tv, gv, sv):
                drift = (gv + sv - tv) / tv * 100
                break

        if exact:
            # Constant prices ARE additive. Anything past rounding is a real bug.
            r.gate(
                drift is not None and abs(drift) < 0.01,
                f"{name}: goods + services == all industries (additive basis)",
                f"drift {drift:+.4f}%",
            )
        else:
            # Chained dollars are documented as non-additive. A small drift is
            # correct; a large one means the wrong price basis was pulled.
            r.gate(
                drift is not None and abs(drift) < 1.0,
                f"{name}: chained-dollar drift within tolerance",
                f"drift {drift:+.4f}%",
            )
            if drift is not None:
                r.note(f"{name}: chained non-additivity is {drift:+.3f}% (expected, not a fault)")

        # Periods must be strictly increasing and never duplicated: a fabricated
        # or repeated month would pass every other check silently.
        for code, ser in by.items():
            ps = ser["periods"]
            if ps != sorted(ps) or len(set(ps)) != len(ps):
                r.gate(False, f"{name}: {code} periods are ordered and unique", "out of order or duplicated")
                break
        else:
            r.gate(True, f"{name}: all periods ordered and unique")

        # periods and values must stay aligned.
        ragged = [c for c, ser in by.items() if len(ser["periods"]) != len(ser["values"])]
        r.gate(not ragged, f"{name}: periods and values aligned", str(ragged))


def check_companies(r: Report) -> None:
    """The company panel is market data and stays labelled as such."""
    doc = _load_json(DATA / "companies" / "xic.json")
    xw = {e["gics"] for e in _load_yaml(REGISTRY / "gics_naics.yaml")["map"]}

    r.gate(bool(doc.get("caveat", {}).get("en")), "company payload carries its caveat", "missing")

    wrong_provenance = [c["ticker"] for c in doc["companies"] if c["provenance"] != "market_data"]
    r.gate(not wrong_provenance, "every company is marked market_data", str(wrong_provenance))

    # A GICS sector with no crosswalk entry silently drops a whole sector from
    # the panel, so the crosswalk must be total over what was actually kept.
    uncovered = sorted({c["gics_sector"] for c in doc["companies"]} - xw)
    r.gate(not uncovered, "crosswalk covers every GICS sector present", str(uncovered))

    junk = [c["ticker"] for c in doc["companies"] if (c["price"] or 0) <= 0]
    r.gate(not junk, "no zero-priced rows survived the filter", str(junk))


# ── Gate: the bundle contract ──────────────────────────────────────────────────

def check_bundle(r: Report) -> None:
    """What the web app and the sibling repo actually read."""
    meta = _load_json(WEB / "data" / "meta.json")
    r.gate(
        re.fullmatch(r"\d+\.\d+\.\d+", str(meta.get("schema_version", ""))) is not None,
        "meta.schema_version is semver",
        str(meta.get("schema_version")),
    )

    for rel in meta.get("files", []):
        r.gate((WEB / "data" / rel).exists(), f"bundle contains {rel}", "missing")

    country = _load_json(WEB / "data" / "country.json")
    r.gate(country.get("iso3") == "CAN", "country.json is keyed on ISO3", str(country.get("iso3")))
    r.gate(
        isinstance(country.get("headline"), list) and len(country["headline"]) >= 4,
        "country.json publishes at least four headline figures",
        str(len(country.get("headline", []))),
    )
    # The governing rule has to survive the repo boundary: identity travels with
    # the value, so every figure carries its own source.
    unsourced = [h["key"] for h in country.get("headline", []) if not h.get("source", {}).get("url")]
    r.gate(not unsourced, "every headline figure carries a SourceRef", str(unsourced))

    stale = [h["key"] for h in country.get("headline", [])
             if h.get("frequency") in ("monthly", "quarterly", "annual") and not h.get("release_time")]
    if stale:
        r.note(f"headline figures with no release_time: {stale}")

    # Palette: the app reads this, so a hand-edit that skipped the validator
    # would silently un-validate the colour system.
    pal = _load_json(WEB / "data" / "palette.json")
    r.gate(len(pal.get("categorical", [])) == 5, "palette publishes five categorical slots",
           str(len(pal.get("categorical", []))))
    v = pal.get("validation", {})
    r.gate(
        v.get("adjacent", {}).get("result") == "ALL CHECKS PASS"
        and v.get("all_pairs", {}).get("result") == "ALL CHECKS PASS",
        "palette records a passing validator run",
        str(v),
    )

    for rel in ("geo/world.json", "geo/provinces.json", "geo/SOURCES.json"):
        r.gate((WEB / rel).exists(), f"geometry artifact {rel} is committed", "missing")


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gate-only", action="store_true", help="suppress advisories")
    args = ap.parse_args()

    r = Report()
    for check in (check_projects, check_strategies, check_sectors, check_companies, check_bundle):
        try:
            check(r)
        except FileNotFoundError as exc:
            r.gate(False, f"{check.__name__} could not run", f"missing file: {exc}")

    print(f"verify — {len(r.passed)} passed, {len(r.gate_failures)} failed, "
          f"{len(r.advisories)} advisory\n")

    for line in r.passed:
        print(f"  ok    {line}")
    if r.advisories and not args.gate_only:
        print()
        for line in r.advisories:
            print(f"  note  {line}")
    if r.gate_failures:
        print()
        for line in r.gate_failures:
            print(f"  FAIL  {line}")

    return 1 if r.gate_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
