"""
atlas.industries — each Major Projects Office project in the NAICS industries it
would operate in, and in construction while a published status says it is
being built.

Decided 2026-09-12 (docs/ROADMAP.md §A3, options B and C together). The mapping
is ours and every value built here is `Provenance.DERIVED`, except the inventory
status, which is NRCan's words carried verbatim.

TOTAL OVER THE PORTFOLIO

`build` raises unless the registry and the stage 01 output name exactly the same
projects. A project with no entry would drop out of every sector count with
nothing on screen to say so — the same class of silent loss CLAUDE.md §2b
describes for map markers.
"""

from __future__ import annotations

from typing import Any

from atlas.core.schema import (
    ConstructionListing, IndustryAssignment, InventoryStatus, ProjectIndustries, Text,
)
from atlas.sources import mpi, naics


class IndustryError(ValueError):
    """A registry entry does not hold against its sources."""


def _text(d: dict[str, str] | None) -> Text:
    return Text(en=(d or {}).get("en", "").strip(), fr=(d or {}).get("fr", "").strip())


def _anchors(project: dict[str, Any]) -> list[tuple[float, float]]:
    return [tuple(s["geometry"]["anchor"]) for s in project.get("sites", [])
            if s.get("geometry", {}).get("anchor")]


def _assignment(project: dict[str, Any], entry: dict[str, Any], c: naics.Classification) -> IndustryAssignment:
    slug = project["slug"]
    code = entry["code"]
    if code not in c.classes:
        raise IndustryError(f"{slug}: {code!r} is not a NAICS Canada 2022 code")

    asset = _text(entry["asset"])
    for lang in ("en", "fr"):
        if getattr(asset, lang) not in project["description"].get(lang, ""):
            raise IndustryError(
                f"{slug}: the asset quote ({lang}) {getattr(asset, lang)!r} is not in the "
                f"project page's description. The page's own words name the asset, or nothing does."
            )

    ev = tuple(naics.evidence(c, e["code"], e["kind"], _text(e)) for e in entry["evidence"])
    if not any(e.code == code for e in ev):
        raise IndustryError(f"{slug}: no evidence quote is on {code} itself")

    sector = naics.sector_of(c, code)
    return IndustryAssignment(
        code=code,
        title=c.classes[code].title,
        sector=sector,
        sector_title=c.classes[sector].title,
        asset=asset,
        evidence=ev,
        note=_text(entry.get("note")),
    )


def _construction(project: dict[str, Any], entry: dict[str, Any], rules: dict[str, Any],
                  c: naics.Classification, inventory: dict[str, mpi.InventoryRow],
                  status_field: str, max_km: float) -> ConstructionListing:
    slug = project["slug"]
    sector = rules["sector"]
    ev = rules["evidence"]
    rule = _text(rules["listed_when_status"])
    common = dict(
        sector=sector,
        sector_title=c.classes[sector].title,
        evidence=naics.evidence(c, ev["code"], ev["kind"], _text(ev)),
        rule=rule,
    )

    declared = entry.get("inventory")
    if declared is None:
        return ConstructionListing(listed=False, basis="not_in_inventory", status=None,
                                   note=_text(entry.get("inventory_note")), **common)

    row = inventory.get(declared["id"])
    if row is None:
        raise IndustryError(f"{slug}: inventory Project ID {declared['id']!r} is not in the inventory")
    km = mpi.check_join(row, _anchors(project), max_km=max_km, slug=slug,
                        accept_without_coordinates=bool(declared.get("accept_without_coordinates")),
                        accept_km=declared.get("accept_distance_km"))

    # Case-insensitive: the English file writes both "Under Construction" and
    # "Under construction". The two languages must agree, or one of the files is
    # saying something the other is not and neither can be shown alone.
    listed_en = row.status.en.casefold() == rule.en.casefold()
    listed_fr = row.status.fr.casefold() == rule.fr.casefold()
    if listed_en != listed_fr:
        raise IndustryError(
            f"{slug}: inventory {row.project_id} status disagrees between languages: "
            f"{row.status.en!r} / {row.status.fr!r}"
        )
    return ConstructionListing(
        listed=listed_en,
        basis="under_construction" if listed_en else "not_under_construction",
        status=InventoryStatus(
            inventory_id=row.project_id, name=row.name, proponent=row.proponent,
            status=row.status, status_field=status_field, prior_status=row.prior_status,
            points=row.points, distance_km=km,
        ),
        note=_text(entry.get("inventory_note")),
        **common,
    )


def build(projects: list[dict[str, Any]], registry: dict[str, Any], c: naics.Classification,
          inventory: dict[str, mpi.InventoryRow], *, status_field: str) -> tuple[ProjectIndustries, ...]:
    """One `ProjectIndustries` per project, in the stage 01 output's order."""
    declared = registry["projects"]
    slugs = [p["slug"] for p in projects]
    if set(slugs) != set(declared):
        raise IndustryError(
            f"mpo_naics.yaml and projects.json disagree: no entry for "
            f"{sorted(set(slugs) - set(declared))}, no project for {sorted(set(declared) - set(slugs))}"
        )
    out = []
    for p in projects:
        entry = declared[p["slug"]]
        out.append(ProjectIndustries(
            slug=p["slug"],
            operating=tuple(_assignment(p, e, c) for e in entry["operating"]),
            construction=_construction(p, entry, registry["construction"], c, inventory,
                                       status_field, float(registry["join_max_km"])),
        ))
    return tuple(out)
