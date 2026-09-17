"""
atlas.shells.acquire.commons_media — files from Wikimedia Commons, each with its own licence.

(Moved from atlas/sources/symbols.py in step S2 of docs/REBUILD.md; unchanged in
behaviour. Card: registry/shells/commons_media.yaml.)

One API request covers up to 50 files: each file's URL, a PNG rendering at the
requested width, its SHA-1, and the licence, artist, credit and restrictions
Commons records for it. A file without a stated licence is refused, never
assumed to be free.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from atlas.shells.acquire.document_text import strip_tags


class MediaError(ValueError):
    """Commons did not return a usable record for a requested file."""


def query_url(api: str, titles: list[str], width: int, *, error: type[Exception] = MediaError) -> str:
    """One Commons request for every file: URLs, a PNG rendering, and the licence metadata."""
    if len(titles) > 50:
        raise error("the Commons API takes at most 50 titles a request")
    return api + "?" + urlencode({
        "action": "query", "format": "json", "titles": "|".join(titles), "prop": "imageinfo",
        "iiprop": "url|sha1|extmetadata", "iiurlwidth": width,
        "iiextmetadatafilter": "LicenseShortName|LicenseUrl|Artist|Restrictions|Credit",
    })


def records(response: dict[str, Any], titles: list[str], *,
            error: type[Exception] = MediaError) -> dict[str, dict[str, Any]]:
    """Each requested file's record, keyed by its title as the registry writes it."""
    query = response.get("query") or {}
    # Commons normalises underscores and case; map its titles back to ours.
    back = {n["to"]: n["from"] for n in query.get("normalized", [])}
    out: dict[str, dict[str, Any]] = {}
    for page in (query.get("pages") or {}).values():
        title = back.get(page.get("title"), page.get("title"))
        if "missing" in page or not page.get("imageinfo"):
            raise error(f"Commons has no file {title!r}")
        info = page["imageinfo"][0]
        meta = {k: strip_tags(str((info.get("extmetadata") or {}).get(k, {}).get("value", "")))
                for k in ("LicenseShortName", "LicenseUrl", "Artist", "Restrictions", "Credit")}
        if not meta["LicenseShortName"]:
            raise error(f"Commons states no licence for {title!r}")
        if not info.get("thumburl"):
            raise error(f"Commons offers no rendering of {title!r}")
        out[title] = {
            "title": title,
            "page_url": info.get("descriptionurl", ""),
            "file_url": info.get("url", ""),
            "rendering_url": info["thumburl"],
            "source_sha1": info.get("sha1", ""),
            "licence": meta["LicenseShortName"],
            "licence_url": meta["LicenseUrl"],
            "artist": meta["Artist"],
            "credit": meta["Credit"],
            "restrictions": [r for r in meta["Restrictions"].split("|") if r],
        }
    missing = set(titles) - set(out)
    if missing:
        raise error(f"Commons returned no record for {sorted(missing)}")
    return out
