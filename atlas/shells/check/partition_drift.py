"""
atlas.shells.check.partition_drift — how far a set of parts is from its whole.

(Taken from `check_partition` in pipeline/02_sectors.py in step S3 of
docs/REBUILD.md; unchanged in behaviour. Card: registry/shells/partition_drift.yaml.)

Goods plus services should equal all industries. On StatCan's 2017 constant
prices they do; on chained dollars they drift (+0.311% measured), because
chained dollars are not additive (CLAUDE.md §8). The stage uses this as an
early look and `verify/` gates the identity.

Series are aligned BY PERIOD, never by position: one series a month longer
than the others would otherwise pair every comparison with the wrong month.
"""

from __future__ import annotations


def latest_drift(total: dict[str, float | None], parts: list[dict[str, float | None]]) -> tuple[str, float] | None:
    """
    (period, percent) at the latest period where the total and every part publish a value.

    Percent is (sum of parts − total) / total × 100. None when no such period
    exists, including when the total is zero there.
    """
    common = set(total).intersection(*parts) if parts else set()
    for period in sorted(common, reverse=True):
        t = total[period]
        values = [p[period] for p in parts]
        if t is not None and None not in values and t:
            return period, (sum(values) - t) / t * 100
    return None
