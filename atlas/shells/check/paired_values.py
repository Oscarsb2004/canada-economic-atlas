"""
atlas.shells.check.paired_values — two renderings of one table agree, figure by figure.

(Taken from `read` in atlas/sources/fiscal_tables.py in step S3 of
docs/REBUILD.md; unchanged in behaviour. Card: registry/shells/paired_values.yaml.)

Finance Canada publishes the Fiscal Reference Tables in English and French, and
the French carries unrounded figures the English rounds. The two are paired by
position, never joined on a label (the French labels Manitoba's 2011-12 row
"2010-2011"), and every figure must agree within a tolerance; a figure present
in one language and blank in the other is a disagreement, not a rounding.
"""

from __future__ import annotations

from collections.abc import Sequence


def first_disagreement(left: Sequence[Sequence[float | None]], right: Sequence[Sequence[float | None]],
                       tolerance: float) -> tuple[int, int, float | None, float | None] | None:
    """
    (column, row, left value, right value) of the first pair that disagrees, or None.

    Columns are compared in order and, within a column, rows in order, over the
    shorter of each pair; checking that the two have the same shape is the
    caller's job, because it knows what the rows and columns are.
    """
    for k, (column_left, column_right) in enumerate(zip(left, right)):
        for i, (a, b) in enumerate(zip(column_left, column_right)):
            if (a is None) != (b is None) or (a is not None and abs(a - b) > tolerance):
                return k, i, a, b
    return None
