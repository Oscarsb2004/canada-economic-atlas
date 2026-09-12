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
is enforced: `tests/test_pipeline.py::test_verify_does_not_import_atlas`
AST-scans this package and fails on any `atlas.*` import.

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

from verify.checks import run_declared_checks

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


#: Month names for re-reading an update's date independently of the pipeline.
_MONTH_NUMBER = {
    "en": {m: i for i, m in enumerate(
        "january february march april may june july august september october november december".split(), 1)},
    "fr": {m: i for i, m in enumerate(
        "janvier février mars avril mai juin juillet août septembre octobre novembre décembre".split(), 1)},
}


def _iso_from_written_date(text: str, lang: str) -> str:
    """
    ISO 8601, at the precision written, from a date as a page wrote it.

    Tokenised rather than matched with a pattern, so it does not share the
    pipeline's parser or its mistakes: "January 5,2026" and "19 mai, 2026"
    split into the same tokens as their tidy forms. Returns "?" when the words
    hold no year, which no stored date can equal.
    """
    months = _MONTH_NUMBER[lang]
    day = month = year = None
    for token in text.replace(",", " ").split():
        low = token.lower()
        if low in months:
            month = months[low]
        elif low.endswith("er") and low[:-2].isdigit():
            day = int(low[:-2])
        elif token.isdigit() and len(token) == 4:
            year = token
        elif token.isdigit():
            day = int(token)
    if year is None:
        return "?"
    if month is None:
        return year
    if day is None:
        return f"{year}-{month:02d}"
    return f"{year}-{month:02d}-{day:02d}"


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
    # Report the slugs that actually failed the predicate. An earlier version
    # tested the French description but printed the quick-facts count, which
    # would have pointed a reader at the wrong field the one time it fired.
    fr_gaps = [p["slug"] for p in projects if not p["description"]["fr"]]
    r.gate(not fr_gaps, "every project has a French description", str(fr_gaps))

    mismatched = [
        p["slug"] for p in projects
        for f in p["quick_facts"]
        if f["label"]["en"] and not f["label"]["fr"]
    ]
    if mismatched:
        r.note(f"quick facts with no French label on {sorted(set(mismatched))}")

    # Benefits is a <ul> under an <h3> rather than its own <h2> section, so a
    # template change that moves or renames it would empty this field on every
    # page at once while every other field still parsed. All 18 pages carry it
    # in both languages today; a zero is a parser failure, not a quiet page.
    no_benefits = [p["slug"] for p in projects if not p.get("benefits")]
    r.gate(not no_benefits, "every project has Benefits bullets", str(no_benefits))

    # Both languages must be represented, but NOT necessarily bullet-for-bullet:
    # the French Taltson page publishes a fifth benefit the English page omits,
    # so its bullets are carried unpaired on purpose. What would be a real
    # failure is a project whose Benefits parsed in one language only — that is
    # the FR-heading trap ("Faits saillants", not "Faits en bref") coming back.
    one_sided = [
        p["slug"] for p in projects
        if p.get("benefits")
        and not (any(b["en"] for b in p["benefits"]) and any(b["fr"] for b in p["benefits"]))
    ]
    r.gate(not one_sided, "Benefits parsed in both languages for every project",
           str(one_sided))

    unpaired = [
        p["slug"] for p in projects
        if any(not b["fr"] for b in p.get("benefits", []))
    ]
    if unpaired:
        r.note(f"EN and FR publish a different number of benefits on {sorted(set(unpaired))}"
               f" — carried unpaired, each language rendering its own list")

    # Latest updates (BACKLOG B3). `date` is what the portfolio timeline orders
    # by, and it held a copy of the verbatim text while its schema comment said
    # ISO — because nothing read it. So every stored date must be ISO at day,
    # month or year precision or empty, and must equal the date re-read here from
    # the words each page wrote, in both languages.
    iso_shape = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
    malformed, disagree, dated, total = [], [], 0, 0
    for p in projects:
        for u in p.get("updates", []):
            total += 1
            stored = u.get("date", "")
            dated += bool(stored)
            if stored and not iso_shape.match(stored):
                malformed.append(f'{p["slug"]}: {stored!r}')
            for words, lang in ((u.get("date_verbatim", ""), "en"), (u.get("date_verbatim_fr", ""), "fr")):
                if words and _iso_from_written_date(words, lang) != stored:
                    disagree.append(f'{p["slug"]}: {words!r} ({lang}) vs {stored!r}')
            if stored and not (u.get("date_verbatim") or u.get("date_verbatim_fr")):
                disagree.append(f'{p["slug"]}: {stored!r} with no written date in either language')
    r.gate(not malformed, "every update date is ISO 8601 at day, month or year precision, or empty",
           str(malformed[:6]))
    r.gate(not disagree, "every stored update date matches the words its page wrote, in both languages",
           str(disagree[:6]))
    r.note(f"updates: {dated} of {total} open with a date; the rest are undated and are never "
           f"placed on the timeline")

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

        # The latest period where all three have values, aligned BY PERIOD.
        # This used to walk one index over three lists, which assumes the
        # series start and end together: one series a month longer and every
        # comparison pairs different months, or an IndexError stops verify. And
        # the detail was formatted eagerly as f"{drift:+.4f}", which raises
        # TypeError when no period qualifies — so the one case this gate exists
        # to report crashed the verifier instead of failing the gate.
        tp, gp, sp = (dict(zip(x["periods"], x["values"])) for x in (t, g, s))
        drift, at = None, None
        for period in sorted(set(tp) & set(gp) & set(sp), reverse=True):
            tv, gv, sv = tp[period], gp[period], sp[period]
            if None not in (tv, gv, sv) and tv:
                drift, at = (gv + sv - tv) / tv * 100, period
                break
        detail = (f"drift {drift:+.4f}% at {at}" if drift is not None
                  else "no period where all three aggregates have values")

        if exact:
            # Constant prices ARE additive. Anything past rounding is a real bug.
            r.gate(
                drift is not None and abs(drift) < 0.01,
                f"{name}: goods + services == all industries (additive basis)",
                detail,
            )
        else:
            # Chained dollars are documented as non-additive. A small drift is
            # correct; a large one means the wrong price basis was pulled.
            r.gate(
                drift is not None and abs(drift) < 1.0,
                f"{name}: chained-dollar drift within tolerance",
                detail,
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


def check_sector_pulls(r: Report) -> None:
    """
    Every pull in `sectors.yaml` that declares a `verify` block (BACKLOG B2).

    The identities and tolerances live beside each pull in the registry, and
    every tolerance there was MEASURED on the cube before it was written down —
    so a failure here is a change in the data, not a guess about it.

    Two gates exist because of how these cubes fail silently. A code declared
    ABSENT must stay absent: SEPH excludes agriculture, and if a later release
    starts publishing [11] the join to GDP needs a person, not an automatic pass.
    And where a cube mixes actuals with intentions, every period must carry its
    basis and cite the cube's own note.
    """
    tax = _load_yaml(REGISTRY / "sectors.yaml")
    sectors = [s["code"] for s in tax["sectors"]]
    everywhere = PROVINCE_CODES | {"CA"}

    for key, pull in (tax.get("pulls") or {}).items():
        spec = pull.get("verify")
        if not spec:
            continue
        name = pull["output"]
        path = DATA / "sectors" / name
        if not path.exists():
            r.gate(False, f"{name}: written by stage 02",
                   f"missing — python pipeline/02_sectors.py --pull {key}")
            continue
        doc = _load_json(path)
        series = doc.get("series", [])
        if not series:
            r.gate(False, f"{name}: carries series", "no series in the file")
            continue

        r.gate(doc.get("count") == len(series), f"{name}: count matches its {len(series)} series",
               f"count says {doc.get('count')}")
        foreign = sorted({f"{s['geo']}/{s['code']}" for s in series
                          if s.get("source_table") != pull["pid"] or s.get("measure") != pull["measure"]})
        r.gate(not foreign, f"{name}: every series is {pull['measure']} from cube {pull['pid']}", str(foreign[:8]))
        r.gate(all(s.get("release_time") for s in series),
               f"{name}: every series carries the cube's release stamp", "blank release_time")
        no_fr = sorted({s["code"] for s in series if not s["label"].get("fr")})
        r.gate(not no_fr, f"{name}: every series has its French label from the -fra cube", str(no_fr[:8]))
        title = doc.get("title") or {}
        r.gate(bool(title.get("en") and title.get("fr")),
               f"{name}: the cube's own title in both languages", str(title))

        absent = {str(c) for c in (pull.get("absent_codes") or {})}
        national = {s["code"] for s in series if s["geo"] == "CA"}
        missing = [c for c in sectors if c not in national and c not in absent]
        r.gate(not missing, f"{name}: every registry sector present, less {len(absent)} declared absent",
               str(missing))
        back = sorted(absent & national)
        r.gate(not back, f"{name}: codes declared absent are still absent",
               f"now published: {back} — re-check the reason in sectors.yaml before these join anything")

        geos = {s["geo"] for s in series}
        extra_geos = {str(g) for g in spec.get("extra_geos", [])}
        if spec.get("provinces"):
            want = everywhere | extra_geos
            r.gate(geos == want,
                   f"{name}: Canada and all 13 provinces and territories"
                   + (f", plus {', '.join(sorted(extra_geos))}" if extra_geos else ""),
                   str(sorted(geos ^ want)))

        disordered = [f"{s['geo']}/{s['code']}" for s in series
                      if s["periods"] != sorted(s["periods"]) or len(set(s["periods"])) != len(s["periods"])
                      or len(s["periods"]) != len(s["values"])]
        r.gate(not disordered, f"{name}: periods ordered, unique and aligned with values", str(disordered[:8]))

        by = {(s["geo"], s["code"]): dict(zip(s["periods"], s["values"])) for s in series}

        for ident in spec.get("identities", []):
            parts = [str(p) for p in ident["parts"]]
            total, tol, geo = str(ident["total"]), float(ident["tolerance_pct"]), ident.get("geo", "CA")
            worst, at, compared = _worst_gap([by.get((geo, p)) for p in parts], by.get((geo, total)))
            label = f"{name}: {' + '.join(parts)} = {total} within {tol}%"
            if not compared:
                r.gate(False, label, "no period where every part and the total are published")
            else:
                r.gate(worst <= tol, f"{label} ({compared} periods)", f"worst {worst:.4f}% at {at}")

        if spec.get("provinces_sum_to_canada"):
            tol = float(spec["provinces_sum_to_canada"]["tolerance_pct"])
            # Some cubes publish a geography beyond the thirteen — "Canadian
            # territorial enclaves abroad" in 36100488 — without which the
            # provinces do not sum to Canada (0.56% short in public administration).
            parts_geos = sorted(PROVINCE_CODES) + (
                sorted(extra_geos) if spec["provinces_sum_to_canada"].get("include_extra_geos") else [])
            worst, at, compared = 0.0, "", 0
            for (geo, code), values in by.items():
                if geo != "CA":
                    continue
                gap, when, n = _worst_gap([by.get((p, code)) for p in parts_geos], values)
                compared += n
                if gap > worst:
                    worst, at = gap, f"{code} {when}"
            r.gate(compared > 0 and worst <= tol,
                   f"{name}: provinces sum to Canada within {tol}% "
                   f"({compared:,} comparisons with no province suppressed)",
                   f"worst {worst:.4f}% at {at}" if compared else "nothing comparable")

        for floor in spec.get("not_below", []):
            other = _load_json(DATA / "sectors" / floor["file"])
            geo = floor.get("geo", "CA")
            theirs = {s["code"]: dict(zip(s["periods"], s["values"])) for s in other["series"] if s["geo"] == geo}
            below, compared = [], 0
            for (g, code), values in by.items():
                if g != geo or code not in theirs:
                    continue
                for period, value in values.items():
                    floor_value = theirs[code].get(period)
                    if value is None or floor_value is None:
                        continue
                    compared += 1
                    if value < floor_value:
                        below.append(f"{code} {period}: {value:,.0f} < {floor_value:,.0f}")
            r.gate(compared > 0 and not below,
                   f"{name}: {floor['label']} ({compared} code-and-year comparisons against {floor['file']})",
                   str(below[:6]) if compared else "nothing comparable")

        if pull.get("crosswalk"):
            total_code = str(pull["total"]["code"])
            mislabelled = [f"{s['geo']}/{s['code']}" for s in series
                           if (s["code"] == total_code) != (s.get("provenance") == "official_dataset")
                           or (s["code"] != total_code and s.get("provenance") != "derived")]
            r.gate(not mislabelled,
                   f"{name}: summed sectors are labelled derived; only the cube's own total is official",
                   str(mislabelled[:6]))
            members = [str(m) for ms in pull["crosswalk"].values() for m in ms]
            twice = sorted({m for m in members if members.count(m) > 1})
            shown = {k: [e.get("code") for e in v] for k, v in (doc.get("crosswalk") or {}).items()}
            declared = {str(k): [str(m) for m in v] for k, v in pull["crosswalk"].items()}
            r.gate(not twice and shown == declared,
                   f"{name}: every member is summed into exactly one sector, and the payload shows which",
                   f"counted twice: {twice}" if twice else "payload crosswalk differs from the registry")

        if pull.get("period_basis"):
            pb = pull["period_basis"]
            latest = [str(x) for x in pb["latest"]]
            periods = sorted({p for s in series for p in s["periods"]})
            expected = {p: "actual" for p in periods}
            expected.update(zip(periods[-len(latest):], latest))
            basis = doc.get("period_basis") or {}
            r.gate(basis == expected,
                   f"{name}: the latest {len(latest)} periods are labelled {', '.join(latest)}",
                   f"got {dict(list(basis.items())[-3:])}")
            note = ((doc.get("notes") or {}).get("en") or {}).get(str(doc.get("period_basis_note_id")), "")
            r.gate(pb["note_contains"] in note, f"{name}: the period basis cites the cube's own note",
                   f"note {doc.get('period_basis_note_id')!r} reads {note[:80]!r}")

        if pull.get("keep_status"):
            lengths = {f"{s['geo']}/{s['code']}": len(s["periods"]) for s in series}
            status = doc.get("status") or {}
            misaligned = [k for k, v in status.items() if lengths.get(k) != len(v)]
            r.gate(bool(status) and not misaligned,
                   f"{name}: quality and suppression codes travel with {len(status)} series",
                   str(misaligned[:8]) if status else "no status carried")


def _worst_gap(parts: list[dict | None], total: dict | None) -> tuple[float, str, int]:
    """
    Largest |sum(parts) - total| / |total| in percent, over the periods where the
    total and every part are published. Returns (worst, its period, periods compared).

    A suppressed part means that period is not comparable, never that the part is
    zero: summing around a suppressed cell is how a correct table fails a gate.
    """
    if total is None or any(p is None for p in parts):
        return 0.0, "", 0
    worst, at, compared = 0.0, "", 0
    for period, t in total.items():
        values = [p.get(period) for p in parts]
        if not t or any(v is None for v in values):
            continue
        compared += 1
        gap = abs(sum(values) - t) / abs(t) * 100
        if gap > worst:
            worst, at = gap, period
    return worst, at, compared


def check_business_counts(r: Report) -> None:
    """
    BACKLOG Q2b — StatCan's Canadian Business Counts, with employees.

    The three identities were measured exact on 33101174 before they became
    gates: size ranges sum to the total, the provinces and territories to
    Canada, and the twenty sectors plus "Unclassified" to all industries.
    """
    doc = _load_json(DATA / "sectors" / "business-counts.json")
    sectors = [s["code"] for s in _load_yaml(REGISTRY / "sectors.yaml")["sectors"]]
    counts = doc.get("counts", {})
    industries = ["total", *sectors, "unclassified"]
    n = len(doc.get("size_ranges", []))

    r.gate(re.fullmatch(r"Canadian Business Counts, with employees, [A-Z][a-z]+ \d{4}", doc.get("title", {}).get("en", ""))
           is not None and bool(doc.get("title", {}).get("fr")),
           "business counts: the table is a 'with employees' half-year table, titled in both languages",
           str(doc.get("title")))
    r.gate(set(counts) == PROVINCE_CODES | {"CA"},
           "business counts: Canada and all thirteen provinces and territories", str(sorted(counts)))
    holes = [f"{g}:{k}" for g in counts for k in industries
             if len(counts[g].get(k, [])) != n or counts[g][k][0] is None]
    r.gate(n > 1 and not holes, "business counts: every sector has a published total and a slot for every size range",
           str(holes[:8]))
    if holes:
        return
    # StatCan publishes no zero rows; an unpublished size range is null. It counts
    # as 0 below only because every identity then holds exactly — if one did not,
    # reading the gaps as zeros would be wrong and these gates would say so.
    counts = {g: {k: [0 if v is None else v for v in row] for k, row in by.items()} for g, by in doc["counts"].items()}
    nulls = sum(v is None for by in doc["counts"].values() for row in by.values() for v in row)
    r.gate(nulls == doc.get("absent_cells"), "business counts: the unpublished cells match the stated count",
           f'{nulls} null, {doc.get("absent_cells")} stated')

    bands = [f"{g}:{k}" for g in counts for k in industries if sum(counts[g][k][1:]) != counts[g][k][0]]
    r.gate(not bands, "business counts: size ranges sum exactly to the total", str(bands[:8]))
    geo = [f"{k}:{i}" for k in industries for i in range(n)
           if sum(counts[p][k][i] for p in PROVINCE_CODES) != counts["CA"][k][i]]
    r.gate(not geo, "business counts: provinces and territories sum exactly to Canada", str(geo[:8]))
    parts = [f"{g}:{i}" for g in counts for i in range(n)
             if sum(counts[g][s][i] for s in sectors) + counts[g]["unclassified"][i] != counts[g]["total"][i]]
    r.gate(not parts, "business counts: sectors plus Unclassified sum exactly to all industries", str(parts[:8]))
    labels = [i["code"] for i in doc.get("industries", []) if not (i["label"]["en"] and i["label"]["fr"])]
    r.gate(not labels and all(nt["text"]["en"] and nt["text"]["fr"] for nt in doc.get("notes", [])),
           "business counts: labels and StatCan's notes carry both languages", str(labels))
    r.note(f'business counts: table {doc.get("table")} ({doc["title"]["en"]}), '
           f'Canada, all industries: {counts["CA"]["total"][0]} locations with employees')


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

    # Read from the manifest the geometry build itself writes, rather than a
    # tuple restated here. The bundle manifest had already drifted this way once
    # — `corridors.json` was written and omitted from the list, so nothing
    # checked it — and a hardcoded tuple here would have left `nhs.json`
    # unchecked the moment it was added.
    geo_sources = json.loads((WEB / "geo/SOURCES.json").read_text(encoding="utf-8"))
    for key in sorted(geo_sources.get("commands", {})):
        rel = f"geo/{key}.json"
        r.gate((WEB / rel).exists(), f"geometry artifact {rel} is committed", "missing")

    # Every NHS coordinate must be in DEGREES, not Lambert metres.
    #
    # The layer's own extent is WKID 3978 and the fetch asks for `outSR=4326`.
    # If that were ever dropped, a seven-digit metre coordinate would render as
    # nothing at all rather than raising — the network would simply be absent
    # from the map and every other check would still pass.
    nhs = json.loads((WEB / "geo/nhs.json").read_text(encoding="utf-8"))["features"]
    pts = [c for f in nhs if f.get("geometry")
           for part in (f["geometry"]["coordinates"]
                        if f["geometry"]["type"] == "MultiLineString"
                        else [f["geometry"]["coordinates"]])
           for c in part]
    off = [c for c in pts if not (-142.0 <= c[0] <= -52.0 and 41.0 <= c[1] <= 84.0)]
    r.gate(not off,
           f"every National Highway System coordinate is in degrees ({len(pts):,} points)",
           f"{len(off)} outside Canada's bounding box — first {off[:2]}")

    # `type_code` is Transport Canada's own classification and the map colours a
    # `match` on it. A fourth code would fall into the default and draw as the
    # wrong class rather than failing, so it is caught here instead.
    codes = sorted({f["properties"].get("type_code") for f in nhs})
    r.gate(set(codes) <= {1, 2, 3},
           "NHS route classes stay within Core / Feeder / Northern-Remote",
           f"unexpected type_code values: {codes}")

    # A feature with properties and no geometry is one the map silently ignores
    # and a count silently includes. `build_geo.mjs` prunes them; this is what
    # notices if that ever stops happening.
    empty = [f["properties"] for f in nhs if not f.get("geometry")]
    r.gate(not empty,
           "no NHS feature has collapsed geometry",
           f"{len(empty)} with properties and no geometry: {empty[:3]}")

    # ── Rail (NRWN) ────────────────────────────────────────────────────────────
    #
    # The rail layer arrived with an existence check and nothing else, where the
    # National Highway System carries three. Same failure modes, same gates: a
    # projected coordinate renders as nothing rather than raising, collapsed
    # geometry is counted but never drawn, and the build's own claim that it
    # kept only operational track should hold in the file it wrote.
    rail_path = WEB / "geo/rail.json"
    if rail_path.exists():
        rail = json.loads(rail_path.read_text(encoding="utf-8"))["features"]
        rail_pts = [c for f in rail if f.get("geometry")
                    for part in (f["geometry"]["coordinates"]
                                 if f["geometry"]["type"] == "MultiLineString"
                                 else [f["geometry"]["coordinates"]])
                    for c in part]
        off = [c for c in rail_pts if not (-142.0 <= c[0] <= -52.0 and 41.0 <= c[1] <= 84.0)]
        r.gate(not off,
               f"every NRWN rail coordinate is in degrees ({len(rail_pts):,} points)",
               f"{len(off)} outside Canada's bounding box — first {off[:2]}")
        collapsed = sum(1 for f in rail if not f.get("geometry"))
        r.gate(not collapsed,
               "no rail feature has collapsed geometry",
               f"{collapsed} with properties and no geometry")
        statuses = sorted({str(f["properties"].get("STATUS")) for f in rail})
        r.gate(statuses == ["Operational"],
               "rail carries only track the publisher calls Operational",
               f"STATUS values: {statuses}")

    # ── Place labels ──────────────────────────────────────────────────────────
    #
    # Nothing checked these until 2026-09-10, when a population join that looked
    # entirely plausible turned out to leave 12,071 of 13,018 places unranked:
    # Ottawa, Mississauga, Brampton, Surrey, Laval and Gatineau were all pushed to
    # street zoom while every gate passed. These hold the label contract itself.
    # Coverage is REPORTED rather than thresholded, because any fixed "enough
    # places matched" number would be invented.
    places_doc = json.loads((WEB / "geo/places.json").read_text(encoding="utf-8"))
    place_props = [f["properties"] for f in places_doc["features"]]

    # A larger population must never get a LATER label than a smaller one.
    # Stated as an ordering rather than by restating the zoom tiers, so this
    # catches a broken join or a broken tier table without duplicating either.
    ranked = sorted((p for p in place_props if not p.get("capital")),
                    key=lambda p: -(p.get("population") or 0))
    inversions, latest_zoom_above = [], None
    prev_pop, group_max = None, None
    for p in ranked:
        pop, zoom = p.get("population") or 0, p["min_zoom"]
        if pop != prev_pop:
            latest_zoom_above = group_max if latest_zoom_above is None else max(latest_zoom_above, group_max or 0)
            prev_pop, group_max = pop, zoom
        else:
            group_max = max(group_max, zoom)
        if latest_zoom_above is not None and zoom < latest_zoom_above:
            inversions.append(f"{p['name_en']} ({p['province']}, {pop}) at {zoom}")
    r.gate(not inversions,
           "a larger population never gets a later place label",
           f"{len(inversions)} inversions, e.g. {inversions[:3]}")

    # One capital per province and territory, counted against the boundary file
    # rather than a list of codes restated here.
    capitals = [p["province"] for p in place_props if p.get("capital")]
    n_provinces = len(json.loads((WEB / "geo/provinces.json").read_text(encoding="utf-8"))["features"])
    r.gate(len(capitals) == n_provinces and len(set(capitals)) == n_provinces,
           f"exactly one capital label per province and territory ({n_provinces})",
           f"capitals found: {sorted(capitals)}")

    # A population must say which published figure it is, and only those two.
    bad_source = [p["name_en"] for p in place_props
                  if (p.get("population") is None) != (p.get("population_source") is None)
                  or p.get("population_source") not in (None, "population_centre", "census_subdivision")]
    r.gate(not bad_source,
           "every ranked place names which census figure ranks it",
           f"{len(bad_source)} inconsistent, e.g. {bad_source[:5]}")

    by_source = {}
    for p in place_props:
        by_source[p.get("population_source")] = by_source.get(p.get("population_source"), 0) + 1
    unmatched = places_doc.get("unmatched_large_municipalities", [])
    r.note(f"place labels: {len(place_props) - by_source.get(None, 0):,} of {len(place_props):,} ranked "
           f"({by_source.get('population_centre', 0):,} census centre, "
           f"{by_source.get('census_subdivision', 0):,} municipal); municipalities of 100k+ with no "
           f"same-named place: {[u['name'] for u in unmatched]}")

    # The globe highlights Canada from canada.json rather than from Natural
    # Earth filtered to CAN, because the 1:110m feature is 9 polygons with no
    # Vancouver Island and almost no Arctic archipelago. A regression to that
    # source, or a rebuild that dropped `keep-shapes`, would show up here as a
    # collapsed polygon count long before anyone noticed the coastline was wrong.
    outline = json.loads((WEB / "geo/canada.json").read_text(encoding="utf-8"))
    geom = outline["features"][0]["geometry"]
    parts = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    r.gate(len(parts) > 400,
           "the Canada outline keeps its islands (>400 polygons)",
           f"{len(parts)} polygons — Natural Earth 1:110m would give 9")

    ys = [c[1] for part in parts for ring in part for c in ring]
    r.gate(max(ys) > 83,
           "the Canada outline reaches Ellesmere (>83 degrees N)",
           f"northernmost point is {max(ys):.2f}")

    # ── Canada's detail tier ──────────────────────────────────────────────────
    #
    # Fetched only when the reader zooms in, so the globe's first load never
    # parses it — which also means no first-load symptom would reveal a broken
    # file. Same failure modes as the other polygon layers: a projected
    # coordinate renders as nothing, collapsed geometry is counted but never
    # drawn, and a detail file that lost a province would leave a hole exactly
    # where a reader has zoomed in to look.
    def polygon_parts(geometry):
        if geometry["type"] == "Polygon":
            return [geometry["coordinates"]]
        if geometry["type"] == "MultiPolygon":
            return geometry["coordinates"]
        return []

    province_ids = {f["properties"]["PRUID"] for f in
                    json.loads((WEB / "geo/provinces.json").read_text(encoding="utf-8"))["features"]}
    for rel in ("geo/provinces-detail.json", "geo/canada-detail.json", "geo/water.json"):
        path = WEB / rel
        r.gate(path.exists(), f"{rel} is committed", "missing")
        if not path.exists():
            continue
        feats = json.loads(path.read_text(encoding="utf-8"))["features"]
        collapsed = sum(1 for f in feats if not f.get("geometry"))
        r.gate(not collapsed, f"no {rel} feature has collapsed geometry",
               f"{collapsed} with properties and no geometry")
        coords = [c for f in feats if f.get("geometry")
                  for part in polygon_parts(f["geometry"]) for ring in part for c in ring]
        # NRCan's waterbodies include the lakes and rivers that cross the border,
        # whole: measured 2026-09-12, water.json reaches -152.37 (Alaska) and
        # 41.27 N (Lake Erie's US shore). So water gets a North American box.
        # The gate exists to catch Lambert metres, which no box of degrees admits.
        lon0, lon1, lat0, lat1 = (-170.0, -50.0, 38.0, 85.0) if rel.endswith("water.json") \
            else (-142.0, -52.0, 41.0, 84.0)
        off = [c for c in coords if not (lon0 <= c[0] <= lon1 and lat0 <= c[1] <= lat1)]
        r.gate(bool(coords) and not off, f"every {rel} coordinate is in degrees ({len(coords):,} points)",
               f"{len(off)} outside lon {lon0}..{lon1}, lat {lat0}..{lat1} — first {off[:2]}")
        if rel.endswith("provinces-detail.json"):
            ids = {f["properties"].get("PRUID") for f in feats}
            r.gate(ids == province_ids, "the detailed provinces are the same 13 PRUIDs as provinces.json",
                   f"detail has {sorted(ids)}")
        if rel.endswith("canada-detail.json"):
            n_parts = sum(len(polygon_parts(f["geometry"])) for f in feats if f.get("geometry"))
            r.gate(n_parts >= len(parts), f"the detailed outline keeps at least the overview's islands ({n_parts:,})",
                   f"{n_parts} polygons against {len(parts)} in canada.json")


# ── Entry point ────────────────────────────────────────────────────────────────

#: Mean Earth radius for the join distances. Re-declared, not imported.
EARTH_RADIUS_KM = 6371.0


def _km(a: list[float], b: list[float]) -> float:
    """Great-circle distance between two [lon, lat] points."""
    import math
    lon1, lat1, lon2, lat2 = (math.radians(v) for v in (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def _in_sector(code: str, sector: str) -> bool:
    """Whether a NAICS code sits in a sector, read from the codes themselves."""
    if "-" in sector:                        # "31-33", "44-45", "48-49"
        lo, hi = sector.split("-")
        return len(code) >= 2 and lo <= code[:2] <= hi
    return code.startswith(sector)


def check_industries(r: Report) -> None:
    """
    BACKLOG C1 — every MPO project placed in NAICS, checked against what it cites.

    Stage 06 refuses a quote that is not in its source. This re-reads the
    OUTPUT: each asset quote against the committed project page text, each
    sector against the registry's twenty and against the code's own digits, each
    construction listing against the inventory status it carries, and each
    inventory join against a distance recomputed here from the committed points.
    """
    base = DATA / "events" / "major-projects-office"
    doc = _load_json(base / "industries.json")
    projects = {p["slug"]: p for p in _load_json(base / "projects.json")["projects"]}
    reg = _load_yaml(REGISTRY / "mpo_naics.yaml")
    sectors = {s["code"] for s in _load_yaml(REGISTRY / "sectors.yaml")["sectors"]}
    records = doc.get("projects", [])
    slugs = [x["slug"] for x in records]

    r.gate(len(slugs) == len(set(slugs)) and set(slugs) == set(projects),
           "industries: every project is placed exactly once",
           f"missing {sorted(set(projects) - set(slugs))}, extra {sorted(set(slugs) - set(projects))}")

    bad_sector, not_derived, unquoted, untitled, unsupported = [], [], [], [], []
    for x in records:
        page = projects.get(x["slug"], {}).get("description", {})
        for a in x["operating"]:
            where = f'{x["slug"]}:{a["code"]}'
            if a["sector"] not in sectors or not _in_sector(a["code"], a["sector"]):
                bad_sector.append(f'{where} in {a["sector"]}')
            if a.get("provenance") != "derived":
                not_derived.append(where)
            for lang in ("en", "fr"):
                if not a["asset"][lang] or a["asset"][lang] not in page.get(lang, ""):
                    unquoted.append(f"{where} ({lang})")
                if (not a["title"][lang] or not a["sector_title"][lang]
                        or any(not e["text"][lang] for e in a["evidence"])):
                    untitled.append(f"{where} ({lang})")
            if not any(e["code"] == a["code"] for e in a["evidence"]):
                unsupported.append(where)
    r.gate(not bad_sector, "industries: every placement sits in one of the twenty sectors its code belongs to",
           str(bad_sector))
    r.gate(not not_derived, "industries: every placement is marked derived", str(not_derived))
    r.gate(not unquoted, "industries: every asset quote is on its project page, in both languages", str(unquoted))
    r.gate(not untitled, "industries: every code, sector and quote carries both languages", str(untitled))
    r.gate(not unsupported, "industries: every placement quotes Statistics Canada on its own code", str(unsupported))

    rule = reg["construction"]["listed_when_status"]
    max_km = reg["join_max_km"]
    wrong_listing, bad_join = [], []
    for x in records:
        c = x["construction"]
        st = c.get("status")
        declared = reg["projects"][x["slug"]]["inventory"]
        if st:
            en = st["status"]["en"].strip().casefold() == rule["en"].casefold()
            fr = st["status"]["fr"].strip().casefold() == rule["fr"].casefold()
            expected = en
            if en != fr:
                wrong_listing.append(f'{x["slug"]}: languages disagree')
        else:
            expected = False
        basis = ("not_in_inventory" if not st else "under_construction" if expected
                 else "not_under_construction")
        if c["listed"] != expected or c["basis"] != basis or c["sector"] != reg["construction"]["sector"]:
            wrong_listing.append(f'{x["slug"]}: listed={c["listed"]} basis={c["basis"]}')

        if (declared is None) != (st is None) or (st and st["inventory_id"] != declared["id"]):
            bad_join.append(f'{x["slug"]}: carries a join the registry does not declare')
        elif st and st["points"]:
            anchors = [s["geometry"]["anchor"] for s in projects[x["slug"]]["sites"]
                       if s["geometry"].get("anchor")]
            km = min(_km(pt, an) for pt in st["points"] for an in anchors)
            limit = declared.get("accept_distance_km") or max_km
            if declared.get("accept_distance_km") and not (c.get("note") or {}).get("en"):
                bad_join.append(f'{x["slug"]}: waives the distance limit without saying so on screen')
            if km > limit or st["distance_km"] is None or abs(km - st["distance_km"]) > 0.01:
                bad_join.append(f'{x["slug"]}: {km:.2f} km recomputed, {st["distance_km"]} recorded')
        elif st and (st["distance_km"] is not None or not declared.get("accept_without_coordinates")):
            bad_join.append(f'{x["slug"]}: no inventory point and no declared acceptance')
    r.gate(not wrong_listing,
           "industries: a project is listed in construction exactly when the inventory says so, in both languages",
           str(wrong_listing))
    r.gate(not bad_join,
           f"industries: every inventory join is declared, and within {max_km} km or under a disclosed waiver",
           str(bad_join))

    listed = sorted(x["slug"] for x in records if x["construction"]["listed"])
    joined = sum(1 for x in records if x["construction"].get("status"))
    r.note(f"industries: {joined} of {len(records)} projects joined to the Major Projects Inventory; "
           f"also counted in construction: {listed}")


#: Fields the vessel register words per language. Re-declared, not imported.
VESSEL_WORD_FIELDS = ("port_of_registry", "descriptor", "construction_type", "construction_material",
                      "engine_type", "propulsion_type", "propulsion_method")


def _imo_valid(imo: str) -> bool:
    """IMO check digit: last digit of the sum of the first six times 7..2. Re-implemented here."""
    if len(imo) != 7 or not imo.isdigit():
        return False
    return sum(int(imo[i]) * (7 - i) for i in range(6)) % 10 == int(imo[6])


def check_vessels(r: Report) -> None:
    """
    BACKLOG S1 — the Canadian register entries that AIS can be joined to.

    Re-reads the committed output: identity, the IMO filter the stage states,
    the check-digit flag recomputed independently, and both languages present
    wherever the register words a field.
    """
    doc = _load_json(DATA / "vessels" / "large-vessel-register.json")
    vs = doc.get("vessels", [])
    counts = doc.get("counts", {})

    keys = [(v["official_number"], v["register_row"]) for v in vs]
    r.gate(bool(vs) and len(keys) == len(set(keys)),
           "vessels: every entry is identified by official number and register row", f"{len(vs)} entries")
    r.gate(all(v["imo"] for v in vs), "vessels: every committed entry carries the IMO number it is kept for",
           str([v["official_number"] for v in vs if not v["imo"]][:8]))
    r.gate(counts.get("entries_with_imo") == len(vs),
           "vessels: the committed entries are all of the register's IMO-bearing entries, by its own count",
           f'{counts.get("entries_with_imo")} counted, {len(vs)} committed')
    wrong = [v["official_number"] for v in vs if v["imo_check_digit_valid"] != _imo_valid(v["imo"])]
    r.gate(not wrong, "vessels: every IMO check-digit flag matches the formula, recomputed", str(wrong[:8]))
    r.gate(counts.get("imo_failing_check_digit") == sum(not v["imo_check_digit_valid"] for v in vs),
           "vessels: the failing check-digit count matches the entries", str(counts.get("imo_failing_check_digit")))
    undated = [v["official_number"] for v in vs if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v["registration_date"])]
    r.gate(not undated, "vessels: every registration date is an ISO date", str(undated[:8]))
    one_sided = [f'{v["official_number"]}:{k}' for v in vs for k in VESSEL_WORD_FIELDS
                 if bool(v[k]["en"]) != bool(v[k]["fr"])]
    r.gate(not one_sided, "vessels: every field the register words is present in both languages", str(one_sided[:8]))
    r.gate(all(v.get("provenance") == "official_dataset" for v in vs),
           "vessels: every entry is marked official_dataset", "")
    listed = counts.get("official_numbers_listed_twice", [])
    repeated = sorted({n for n in (v["official_number"] for v in vs) if [x["official_number"] for x in vs].count(n) > 1})
    r.gate(set(repeated) <= set(listed),
           "vessels: every official number repeated among the entries is one the register lists twice",
           f"repeated {repeated}, listed {listed}")
    r.note(f'vessels: {len(vs)} of {counts.get("register_entries")} register entries carry an IMO number; '
           f'{counts.get("imo_failing_check_digit")} fail the IMO check digit; '
           f"official numbers listed twice in the register: {listed}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gate-only", action="store_true", help="suppress advisories")
    args = ap.parse_args()

    r = Report()
    for check in (check_projects, check_strategies, check_sectors, check_sector_pulls,
                  check_industries, check_vessels, check_business_counts, check_bundle):
        try:
            check(r)
        except FileNotFoundError as exc:
            r.gate(False, f"{check.__name__} could not run", f"missing file: {exc}")

    # Everything declared in registry/checks.yaml. The functions above name
    # their fields inline, which is correct for the one event that exists and
    # wrong for the second; these are generic over a dataset's declared shape,
    # so covering a new event is a YAML entry rather than a new branch here.
    run_declared_checks(r)

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
