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
# the dataset declaration and the shared region definitions.

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


def check_unique_ids(records, spec, ctx):
    field = ctx["dataset"]["id_field"]
    ids = [r.get(field) for r in records]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    return not dupes, f"{ctx['name']}: {field} is unique", str(dupes)


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
        if not resolve_one(r, path)
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


KINDS: dict[str, Callable] = {
    "unique_ids": check_unique_ids,
    "record_count": check_record_count,
    "fields_present": check_fields_present,
    "enum_field": check_enum_field,
    "coverage_manifest": check_coverage_manifest,
    "geometry_within_region": check_geometry_within_region,
    "geometry_region_matches_text": check_geometry_region_matches_text,
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

        records = json.loads(path.read_text(encoding="utf-8")).get(dataset["records"], [])
        ctx = {"name": name, "dataset": dataset, "regions": regions}

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
