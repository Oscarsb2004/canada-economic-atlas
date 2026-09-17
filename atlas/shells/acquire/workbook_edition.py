"""
atlas.shells.acquire.workbook_edition — the newest edition of a yearly workbook, found by its contents.

(Moved from atlas/sources/fiscal_tables.py in step S2 of docs/REBUILD.md;
unchanged in behaviour. Card: registry/shells/workbook_edition.yaml.)

canada.ca answers a HEAD request with 200 for a file that does not exist, and
its index pages list no editions. So an edition exists only when a real
download of every language's workbook returns a zip body (every .xlsx is one).
"""

from __future__ import annotations

from collections.abc import Callable


class EditionError(ValueError):
    """No year in the range has every workbook published."""


def latest(get: Callable[[str], bytes | None], template: dict[str, str], newest: int, oldest: int, *,
           error: type[Exception] = EditionError) -> tuple[int, dict[str, bytes]]:
    """
    The newest year, from `newest` down to `oldest`, with every language's workbook published.

    `template` maps a language to a URL with `{year}` and `{yy}` fields. `get`
    returns the body, or None where the download fails. A body that is not a zip
    is a 404 page, not an edition. Languages are tried in the template's order.
    """
    for year in range(newest, oldest - 1, -1):
        bodies: dict[str, bytes] = {}
        for lang in template:
            body = get(template[lang].format(year=year, yy=f"{year % 100:02d}"))
            if not body or not body.startswith(b"PK"):
                break
            bodies[lang] = body
        if len(bodies) == len(template):
            return year, bodies
    raise error(f"no edition with both workbooks between {oldest} and {newest}")
