"""
verify.checks — run the checks declared in `registry/checks.yaml`.

THIS MODULE MUST NOT IMPORT `atlas`. See `verify/run.py`.

Every check in here is generic over a dataset's declared shape. Nothing knows
that the Major Projects Office has `sites`, that a site's geometry holds
`coordinates`, or that projects are called projects — those are strings in the
registry. Adding verification for a second event is a YAML entry; only a new
KIND of question needs a function here, registered in `KINDS`.

THE PATH LANGUAGE

Dotted, with `[]` meaning "every element of this array":

    name.en                     one value
    sites[].geometry            one value per site
    sites[].geometry.coordinates[]   one value per coordinate, per site

Resolution always returns a LIST, even for a single value, so a caller never
has to branch on whether a path fanned out. A path that does not resolve
returns an empty list rather than raising: a dataset that declares no geometry
skips the geometry checks, which is what lets one registry describe events that
are not shaped alike.

`expect_from` is the same idea pointed at a registry file:

    events.yaml:events[slug=major-projects-office].expected.projects

The `[field=value]` selector picks one element of an array by a field's value,
so the reference survives someone reordering the events list.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import yaml

from verify.geo import containing_features, distance_to_geometry_km

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "registry"

#: `name[field=value]` or `name[]` or `name`.
_SEGMENT = re.compile(r"^([^\[\]]+)(?:\[([^\]]*)\])?$")


# ── The path language ──────────────────────────────────────────────────────────

def resolve(obj: Any, path: str) -> list[Any]:
    """
    Every value `path` reaches in `obj`, as a flat list.

    An unresolvable path yields `[]`. That is deliberate and load-bearing: it
    is how a dataset that declares no `geometry_path` skips geometry checks
    instead of failing them, and it keeps a typo in the registry from crashing
    the whole verifier — the check simply reports zero values, which its own
    message then names.
    """
    if not path:
        return []
    current: list[Any] = [obj]
    for raw in path.split("."):
        m = _SEGMENT.match(raw)
        if not m:
            return []
        key, selector = m.group(1), m.group(2)
        nxt: list[Any] = []
        for item in current:
            if not isinstance(item, dict) or key not in item:
                continue
            value = item[key]
            if selector is None:
                nxt.append(value)
            elif selector == "":
                if isinstance(value, list):
                    nxt.extend(value)
            else:
                field, _, want = selector.partition("=")
                if isinstance(value, list):
                    nxt.extend(
                        v for v in value
                        if isinstance(v, dict) and str(v.get(field)) == want
                    )
        current = nxt
        if not current:
            return []
    return current


def resolve_one(obj: Any, path: str) -> Any:
    """The first value `path` reaches, or None."""
    got = resolve(obj, path)
    return got[0] if got else None


def resolve_registry(ref: str) -> Any:
    """
    One value from a registry file, addressed as `file.yaml:dotted.path`.

    Used by `expect_from`, so an asserted count lives beside the thing it
    describes rather than being restated here and drifting from it.
    """
    filename, _, path = ref.partition(":")
    doc = yaml.safe_load((REGISTRY / filename).read_text(encoding="utf-8"))
    return resolve_one(doc, path)


# ── Check kinds ────────────────────────────────────────────────────────────────
#
# Each takes (records, spec, ctx) and returns (ok, label, detail). `ctx` carries
# the dataset declaration, the shared region definitions, and the whole parsed
# `document`, for checks that compare records to figures published beside them.

def _points(record: dict, ctx: dict) -> list[tuple[float, float]]:
    """Every [lon, lat] pair a record declares, however deeply nested."""
    raw = resolve(record, ctx["dataset"].get("geometry_path", ""))
    out = []
    for value in raw:
        # A geometry_path may land on a single [lon, lat] or on a list of them —
        # a point site and a corridor site differ exactly there, and the
        # registry should not have to declare which a record happens to be.
        if (isinstance(value, list) and len(value) == 2
                and all(isinstance(n, (int, float)) for n in value)):
            out.append((float(value[0]), float(value[1])))
        elif isinstance(value, list):
            out.extend(
                (float(v[0]), float(v[1])) for v in value
                if isinstance(v, list) and len(v) == 2
                and all(isinstance(n, (int, float)) for n in v)
            )
    return out


def _region(spec: dict, ctx: dict) -> dict:
    name = spec.get("region", "")
    region = ctx["regions"].get(name)
    if not region:
        raise KeyError(f"checks.yaml declares no region named {name!r}")
    if "_loaded" not in region:
        region["_loaded"] = json.loads((ROOT / region["file"]).read_text(encoding="utf-8"))
    return region


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _present(values: list[Any]) -> bool:
    """
    Whether a resolved path reached a real value.

    NOT truthiness. `fields_present` used to test `not resolve_one(...)`, which
    reads 0, 0.0 and False as missing — so a municipality with no usual
    residents, a coordinate on the equator or an explicit
    `overlaps_provinces: false` would fail a presence gate while being exactly
    right. Absent means: the path did not resolve, or it reached None, a blank
    string, or an empty collection.
    """
    if not values or _blank(values[0]):
        return False
    if isinstance(values[0], (list, dict)):
        return bool(values[0])
    return True


def check_unique_ids(records, spec, ctx):
    """
    Every record has an identity, and no two share one.

    Two defects in the version this replaced. `ids.count(i)` inside a set
    comprehension is quadratic — harmless at 18 projects, ~27 million
    comparisons at 5,161 municipalities. And a record with NO id passed, since
    one missing id is not a duplicate; with two missing, sorting None against
    strings raised TypeError, which reported that the check had crashed rather
    than which records were wrong.
    """
    field = ctx["dataset"]["id_field"]
    counts = Counter(r.get(field) for r in records)
    missing = sum(n for i, n in counts.items() if _blank(i))
    dupes = sorted(str(i) for i, n in counts.items() if n > 1 and not _blank(i))
    detail = []
    if dupes:
        detail.append(f"duplicated: {dupes[:12]}")
    if missing:
        detail.append(f"{missing} records have no {field}")
    return not detail, f"{ctx['name']}: {field} is present and unique", " · ".join(detail)


def check_record_count(records, spec, ctx):
    want = spec.get("expect") if "expect" in spec else resolve_registry(spec["expect_from"])
    return (
        len(records) == want,
        f"{ctx['name']}: {len(records)} records, as declared",
        f"got {len(records)}, registry declares {want}",
    )


def check_fields_present(records, spec, ctx):
    idf = ctx["dataset"]["id_field"]
    missing = [
        f"{r.get(idf)}.{path}"
        for r in records
        for path in spec["fields"]
        if not _present(resolve(r, path))
    ]
    return (
        not missing,
        f"{ctx['name']}: every record carries {', '.join(spec['fields'])}",
        str(missing[:12]),
    )


def check_enum_field(records, spec, ctx):
    idf, field = ctx["dataset"]["id_field"], spec["field"]
    allowed = set(spec["allowed"])
    bad = [f"{r.get(idf)}={resolve_one(r, field)!r}"
           for r in records if resolve_one(r, field) not in allowed]
    return not bad, f"{ctx['name']}: {field} within {sorted(allowed)}", str(bad[:12])


def check_coverage_manifest(records, spec, ctx):
    """
    Committed records against what the source's own index listed.

    The manifest is written by the pipeline because reading it needs the
    network; comparing against it does not, which is what makes this a check
    that actually runs rather than one that needs a live site to mean anything.

    A manifest recording `site_index: null` means the index could not be read
    on the last run. That is reported as a failure, not skipped — an
    unverifiable coverage claim and a verified one must not look the same.
    """
    path = ROOT / spec["manifest"]
    if not path.exists():
        return False, f"{ctx['name']}: coverage manifest exists", f"{spec['manifest']} missing"

    entry = (json.loads(path.read_text(encoding="utf-8"))
             .get("sources", {}).get(spec["source_kind"], {}))
    listed = entry.get("site_index")
    if listed is None:
        return (False, f"{ctx['name']}: coverage checked against the site index",
                f"index unreadable on the last run: {entry.get('reason', 'no reason recorded')}")

    idf = ctx["dataset"]["id_field"]
    have = {r.get(idf) for r in records}
    missing = sorted(set(listed) - have)
    extra = sorted(have - set(listed))
    detail = []
    if missing:
        detail.append(f"listed by the source but not captured: {missing}")
    if extra:
        detail.append(f"captured but not listed by the source: {extra}")
    return (
        not detail,
        f"{ctx['name']}: every item the source lists is captured ({len(listed)})",
        " · ".join(detail),
    )


def check_geometry_within_region(records, spec, ctx):
    region = _region(spec, ctx)
    tolerance = float(spec.get("tolerance_km", 0))
    geoms = [f["geometry"] for f in region["_loaded"]["features"]]
    idf = ctx["dataset"]["id_field"]

    strays = []
    for r in records:
        for pt in _points(r, ctx):
            gap = min(distance_to_geometry_km(pt, g) for g in geoms)
            if gap > tolerance:
                strays.append(f"{r.get(idf)} {pt} is {gap:.0f} km outside")
    return (
        not strays,
        f"{ctx['name']}: every coordinate is within {tolerance:.0f} km of "
        f"{region.get('label', spec['region'])}",
        str(strays[:12]),
    )


def check_geometry_region_matches_text(records, spec, ctx):
    """
    Does the coordinate land in the region the record's own prose names?

    Advisory by design. A mismatch is usually a real boundary case rather than
    an error, and the point is to put those in front of a person, not to block
    on them. Matching is on the region's own published names — never on a list
    of place names written here, which would be this file inventing geography.
    """
    region = _region(spec, ctx)
    tolerance = float(spec.get("tolerance_km", 0))
    features = region["_loaded"]["features"]
    name_fields = region.get("name_fields", [])
    idf = ctx["dataset"]["id_field"]

    disagreements = []
    for r in records:
        texts = [str(t) for t in resolve(r, ctx["dataset"].get("place_text_path", "")) if t]
        if not texts:
            continue
        blob = " ".join(texts).lower()
        for pt in _points(r, ctx):
            hits = containing_features(pt, features)
            if not hits:
                # Outside every region: either marine, or genuinely wrong. The
                # containment gate above already judged that; not this one's job.
                continue
            names = [str(h["properties"].get(f, "")) for h in hits for f in name_fields]
            if not any(n and n.lower() in blob for n in names):
                disagreements.append(
                    f"{r.get(idf)} {pt} falls in {names[0] or '?'}, text says "
                    f"{texts[0][:48]!r}"
                )
    _ = tolerance  # declared for symmetry; containment here is exact by design
    return (
        not disagreements,
        f"{ctx['name']}: coordinates agree with the location text",
        " · ".join(disagreements[:8]),
    )


def check_source_section_shape(records, spec, ctx):
    """
    Did a category of page appear on the source that nothing accounts for?

    This is the check that answers "was anything omitted" in the only way that
    generalises. Comparing captured records against a named index page confirms
    the categories you already knew; it is structurally blind to a THIRD kind
    of page, which is exactly what a coverage check is for.

    So stage 01 crawls the section and records every group of sibling pages it
    found. `record_groups` in the registry says which carry records and
    `prose_groups` says which are known not to. Anything in neither is
    reported — that is a new category of referred item on its first day, and it
    is a note rather than a gate because the correct response is a person
    deciding what it is, not a blocked release.

    Broken links on the source are reported for the same reason: canada.ca
    links a "Projects designated under the Building Canada Act" page that 404s,
    and "designated" is a further legal status than "referred". When that page
    goes live it is a new dataset, and this is what notices.
    """
    path = ROOT / spec["manifest"]
    if not path.exists():
        return False, f"{ctx['name']}: section manifest exists", f"{spec['manifest']} missing"

    disc = (json.loads(path.read_text(encoding="utf-8"))
            .get("sources", {}).get("_discovered"))
    if not disc:
        return (False, f"{ctx['name']}: the source section was crawled",
                "no _discovered block — stage 01 could not crawl the section")

    source = yaml.safe_load((REGISTRY / "sources.yaml").read_text(encoding="utf-8"))
    src = source["sources"][spec["source"]]
    known = set(src.get("record_groups", {})) | set(src.get("prose_groups", []))

    surprises = {g: v for g, v in disc.get("undeclared_groups", {}).items() if g not in known}
    broken = [b["path"].rsplit("/", 1)[-1] for b in disc.get("broken_links", [])]

    detail = []
    if surprises:
        detail.append(
            "undeclared page groups: "
            + "; ".join(f"{g} ({len(v)}: {', '.join(v[:4])})" for g, v in surprises.items())
        )
    if broken:
        detail.append(f"broken links on the source: {broken}")
    return (
        not detail,
        f"{ctx['name']}: every page group under the source is accounted for "
        f"({disc['pages_crawled']} pages crawled)",
        " · ".join(detail),
    )


def check_records_are_reachable(records, spec, ctx):
    """
    Can a reader actually GET to every record from the map?

    This exists because of a bug that no other check could see. Markers were
    built from a `kind === "point"` filter and lines from a `kind === "corridor"`
    filter, so the four linear projects rendered as dashed lines with no marker:
    nothing to click, no headpiece, no route into the project. Every count was
    right, every field was present, every coordinate was inside Canada — and
    four of eighteen projects were unreachable on the map.

    Coverage checks compare what we captured against what the source published.
    This asks the different question: of what we captured, how much can the
    reader reach. A record whose geometry yields no anchor is reachable only
    from the list, which is a decision — `kinds_without_anchor` names the kinds
    for which that is intended, and anything else fails.
    """
    idf = ctx["dataset"]["id_field"]
    geom_path = ctx["dataset"].get("geometry_path_root", "")
    allowed = set(spec.get("kinds_without_anchor", []))

    unreachable = []
    for r in records:
        geoms = resolve(r, geom_path)
        if not geoms:
            continue
        if any(g.get("anchor") for g in geoms if isinstance(g, dict)):
            continue
        kinds = {g.get("kind") for g in geoms if isinstance(g, dict)}
        if kinds - allowed:
            unreachable.append(f"{r.get(idf)} ({', '.join(sorted(k or '?' for k in kinds))})")
    return (
        not unreachable,
        f"{ctx['name']}: every record with geometry has a map anchor",
        str(unreachable[:12]),
    )


def check_cross_source_agreement(records, spec, ctx):
    """
    Two independent publications of the same quantity, compared.

    Every other check here is internal: counts match a declared number, fields
    are present, components sum to their aggregate. All of those can pass while
    the whole ingestion is quietly reading the wrong column — internal
    consistency is exactly what a systematic error preserves.

    This is the one external check. StatCan publishes national GDP by industry
    monthly (36100434) and provincial GDP by industry annually (36100711) from
    separately compiled source data. Summing the provinces and comparing to the
    national figure, per sector, is a genuine second opinion.

    Measured on 2026-09-08: no sector diverges by more than 1.62%. The tolerance
    is declared rather than tuned to that result — the two cubes are built from
    different survey vintages and are not expected to agree exactly, so a
    threshold tight enough to catch a real error and loose enough to survive an
    ordinary revision is a judgement, and it belongs in the registry where it
    can be argued with.
    """
    left = json.loads((ROOT / spec["left"]).read_text(encoding="utf-8"))["series"]
    right = json.loads((ROOT / spec["right"]).read_text(encoding="utf-8"))["series"]
    period, tol = spec["period"], float(spec["tolerance_pct"])

    def annual_mean(series, geo=None):
        out = {}
        for s in series:
            if geo and s.get("geo") != geo:
                continue
            vals = [v for p, v in zip(s["periods"], s["values"])
                    if str(p).startswith(period) and v is not None]
            if vals:
                out[s["code"]] = out.get(s["code"], 0) + sum(vals) / len(vals)
        return out

    L = annual_mean(left, spec.get("left_geo"))
    R = annual_mean(right)
    shared = set(L) & set(R)
    if not shared:
        return (False, f"{ctx['name']}: the two sources share sector codes",
                f"no codes in common for {period} — a classification changed")

    off = []
    for code in sorted(shared):
        if not L[code]:
            continue
        drift = 100 * (R[code] - L[code]) / L[code]
        if abs(drift) > tol:
            off.append(f"{code} {drift:+.2f}%")
    return (
        not off,
        f"{ctx['name']}: {len(shared)} sectors agree across two StatCan cubes "
        f"within {tol}%",
        str(off[:12]),
    )


def check_sums_to_published_totals(records, spec, ctx):
    """
    Components against the aggregate the SAME publisher printed for them.

    For census subdivisions: every province's published 2021 population is the
    sum of its subdivisions, exactly — measured on table 98-10-0002 for all
    thirteen, with the unpublished reserves blank on both sides. A record count
    catches a dropped or duplicated record; this also catches a subdivision
    filed under the wrong province and a value read from the wrong column,
    neither of which changes the count.

    It does NOT hold for every column of that table. The 2016 counts differ from
    the published 2016 province totals in NL, QC and ON (cause not established),
    so the registry declares this per field, and a field is declared only after
    the identity has been measured.

    Unpublished values (None) are skipped, never summed as zero. A group with
    records but no published total, or a total with no records, fails — each is
    a join that went wrong without changing any single number.
    """
    idf = ctx["dataset"]["id_field"]
    group_field, value_field = spec["group_field"], spec["value_field"]
    total_field = spec.get("totals_value_field", value_field)
    tolerance = float(spec.get("tolerance", 0))
    totals = resolve_one(ctx.get("document", {}), spec["totals_path"])
    if not isinstance(totals, dict) or not totals:
        return (False, f"{ctx['name']}: published totals at {spec['totals_path']}",
                "the document carries no totals at that path")

    sums: dict[str, int | float] = {}
    for r in records:
        group = str(resolve_one(r, group_field))
        value = resolve_one(r, value_field)
        sums.setdefault(group, 0)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return (False, f"{ctx['name']}: {value_field} is numeric",
                    f"{r.get(idf)} has {value!r}")
        sums[group] += value

    problems = []
    for group in sorted(set(sums) | set(totals)):
        entry = totals.get(group)
        published = entry.get(total_field) if isinstance(entry, dict) else entry
        if group not in sums:
            problems.append(f"{group}: a published total with no records")
        elif entry is None:
            problems.append(f"{group}: records with no published total")
        elif published is None:
            problems.append(f"{group}: the published {total_field} is not available")
        elif abs(sums[group] - published) > tolerance:
            problems.append(f"{group}: components sum to {sums[group]:,} "
                            f"against a published {published:,}")
    return (
        not problems,
        f"{ctx['name']}: {value_field} sums to the published total in all "
        f"{len(totals)} {group_field} groups (tolerance {tolerance:g})",
        " · ".join(problems[:12]),
    )


KINDS: dict[str, Callable] = {
    "unique_ids": check_unique_ids,
    "record_count": check_record_count,
    "fields_present": check_fields_present,
    "enum_field": check_enum_field,
    "coverage_manifest": check_coverage_manifest,
    "geometry_within_region": check_geometry_within_region,
    "geometry_region_matches_text": check_geometry_region_matches_text,
    "source_section_shape": check_source_section_shape,
    "records_are_reachable": check_records_are_reachable,
    "cross_source_agreement": check_cross_source_agreement,
    "sums_to_published_totals": check_sums_to_published_totals,
}


# ── The runner ─────────────────────────────────────────────────────────────────

def run_declared_checks(report) -> None:
    """
    Every check in `registry/checks.yaml`, against every dataset it declares.

    `report` is `verify.run.Report`; passed in rather than imported so this
    module stays a library and the entry point stays the entry point.
    """
    spec_file = REGISTRY / "checks.yaml"
    if not spec_file.exists():
        report.note("registry/checks.yaml is absent — no declared checks ran")
        return

    doc = yaml.safe_load(spec_file.read_text(encoding="utf-8"))
    regions = doc.get("regions", {})

    for name, dataset in (doc.get("datasets") or {}).items():
        path = ROOT / dataset["path"]
        if not path.exists():
            report.gate(False, f"{name}: dataset exists", f"{dataset['path']} missing")
            continue

        # A renamed or missing records key used to become `[]` — and every check
        # that asks "is anything wrong with these records" passes on an empty
        # list: no duplicates, no missing fields, no strays. Only a dataset that
        # also declared a record_count would have noticed. So the array must
        # exist, and be non-empty unless the registry says empty is legitimate.
        document = json.loads(path.read_text(encoding="utf-8"))
        records = document.get(dataset["records"]) if isinstance(document, dict) else None
        if not isinstance(records, list):
            found = "missing" if records is None else f"a {type(records).__name__}, not an array"
            keys = sorted(document)[:12] if isinstance(document, dict) else "(not an object)"
            report.gate(False, f"{name}: {dataset['records']!r} is an array in {dataset['path']}",
                        f"{found}; top-level keys are {keys}")
            continue
        if not records and not dataset.get("allow_empty", False):
            report.gate(False, f"{name}: {dataset['path']} carries records",
                        f"{dataset['records']!r} is empty and the dataset does not declare allow_empty")
            continue
        ctx = {"name": name, "dataset": dataset, "regions": regions, "document": document}

        for spec in dataset.get("checks", []):
            kind = spec.get("kind")
            fn = KINDS.get(kind)
            if fn is None:
                # An unknown kind is a registry error, and silently skipping it
                # would leave a check that reads as passing because nobody ran it.
                report.gate(False, f"{name}: check kind {kind!r} is implemented",
                            f"no such kind; known kinds are {sorted(KINDS)}")
                continue
            try:
                ok, label, detail = fn(records, spec, ctx)
            except Exception as exc:                      # noqa: BLE001
                report.gate(False, f"{name}: {kind} ran", f"{type(exc).__name__}: {exc}")
                continue

            if spec.get("severity", "gate") == "gate":
                report.gate(ok, label, detail)
            elif ok:
                report.gate(True, label, "")
            else:
                report.note(f"{label} — {detail}")
