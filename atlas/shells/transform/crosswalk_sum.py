"""
atlas.shells.transform.crosswalk_sum — sum published members into a declared category.

(Taken from `build_crosswalk_series` in atlas/sources/statcan.py in step S3 of
docs/REBUILD.md; unchanged in behaviour. Card: registry/shells/crosswalk_sum.yaml.)

StatCan's gross output table is classified by IOIC, not NAICS, and splits every
industry by institutional sector, so no member of it is "NAICS 61": education
is BS610 + NP61000 + GS610. A declared crosswalk maps each sector to the
members that make it up, and the sum is this project's, so it is DERIVED.

Two rules keep the sum honest:

  one owner per member   a member mapped to two sectors would be counted twice,
                         and nothing downstream would notice except a total
                         that no longer adds up.
  all or nothing         a sector is None in any period where ANY member is
                         blank or missing; summing the published members and
                         skipping the blank one reports part of a sector as all.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping


def owners(crosswalk: Mapping[str, Iterable[str]], *, where: str) -> dict[str, str]:
    """member → the one category it belongs to. Raises ValueError on a member mapped twice."""
    owner: dict[str, str] = {}
    for category, members in crosswalk.items():
        for member in members:
            if member in owner:
                raise ValueError(f"{where}: member {member} is mapped to both {owner[member]} and {category}")
            owner[member] = category
    return owner


def total(values: Iterable[float | None]) -> float | None:
    """The sum, or None if any value is missing."""
    values = list(values)
    if any(v is None for v in values):
        return None
    return sum(values)
