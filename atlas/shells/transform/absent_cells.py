"""
atlas.shells.transform.absent_cells — an unpublished part is zero only when its total says so.

(Taken from `build` in atlas/sources/business_counts.py in step S3 of
docs/REBUILD.md; unchanged in behaviour. Card: registry/shells/absent_cells.yaml.)

Statistics Canada's business counts publish no zero rows: a size range with no
businesses simply has no row. Reading an absent row as zero is only allowed when
arithmetic proves it — the published total minus the published parts is 0 —
and otherwise the absence cannot be read at all. The cell stays null either way;
the page says why it shows zero.
"""

from __future__ import annotations

from collections.abc import Sequence


class AbsentCellError(ValueError):
    """The published total leaves something for the unpublished parts, so they are not zero."""


def proven_zero(row: Sequence[int | float | None], *, where: str,
                error: type[Exception] = AbsentCellError) -> int:
    """
    How many parts of `row` are unpublished, once proven zero.

    `row` is the total followed by its parts; the total must be published.
    Raises when the total less the published parts is not 0.
    """
    gaps = list(row).count(None)
    if gaps:
        implied = row[0] - sum(v for v in row[1:] if v is not None)
        if implied != 0:
            raise error(
                f"{where}: {gaps} size range(s) unpublished, and the total less the published "
                f"ranges is {implied}, not 0 — the absent rows cannot be read as zero"
            )
    return gaps
