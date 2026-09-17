"""
atlas.shells.acquire.arcgis_layer — features from an ArcGIS MapServer layer.

(Collected from atlas/sources/mpo.py and atlas/sources/mpi.py in step S2 of
docs/REBUILD.md; unchanged in behaviour. Card: registry/shells/arcgis_layer.yaml.)

Two query forms, because the two services this project reads were written
against different ones, and a request is recorded by its exact URL:

  `geojson_query_url` / `attributes_query_url`
      one request for a whole small layer (the Major Projects Office layers).
      Written out literally, `*` unescaped, as the service has always been asked.

  `page_query_url` + `fetch_pages`
      every feature of a large layer, page by page, in a stable order (NRCan's
      Major Projects Inventory). Built with `urlencode`, `*` escaped.

Changing either form changes the requests the golden master recorded, and a
replay refuses them.
"""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib.parse import urlencode


class LayerError(ValueError):
    """A layer answered with something that is not a page of features."""


def geojson_query_url(service: str, layer: int) -> str:
    """The GeoJSON query that returns every feature of `layer`."""
    return (
        f"{service}/{layer}/query"
        "?where=1%3D1&outFields=*&returnGeometry=true&outSR=4326&f=geojson"
    )


def attributes_query_url(service: str, layer: int) -> str:
    """Every feature's attributes, geometry off, as ESRI JSON."""
    return (
        f"{service}/{layer}/query"
        "?where=1%3D1&outFields=*&returnGeometry=false&f=json"
    )


def page_query_url(layer: str, offset: int, page_size: int) -> str:
    """
    One page of the layer: every field, points in degrees, in a stable order.

    `orderByFields` is required, not decorative — ESRI promises no page order
    without it, and an unstable order would break the zero-line re-run.
    """
    return layer.rstrip("/") + "/query?" + urlencode({
        "where": "1=1", "outFields": "*", "returnGeometry": "true", "outSR": "4326",
        "orderByFields": "OBJECTID ASC", "resultOffset": offset, "resultRecordCount": page_size,
        "f": "json",
    })


def fetch_pages(get: Callable[[str], bytes], layer: str, page_size: int, *,
                error: type[Exception] = LayerError) -> tuple[list[dict[str, Any]], bytes]:
    """
    Every feature of a layer, and the raw bodies (for the content hash), page by page.

    `error` is the exception raised on a malformed page, so a caller keeps its
    own error type.
    """
    features: list[dict[str, Any]] = []
    raw = b""
    offset = 0
    while True:
        body = get(page_query_url(layer, offset, page_size))
        raw += body
        try:
            page = json.loads(body)
        except json.JSONDecodeError as exc:
            raise error(f"{layer}: page at {offset} is not JSON: {body[:120]!r}") from exc
        if "error" in page:
            raise error(f"{layer}: the service returned an error: {page['error']}")
        got = page.get("features") or []
        features.extend(got)
        if page.get("exceededTransferLimit"):
            if not got:
                raise error(f"{layer}: says more pages exist but returned none at {offset}")
        elif len(got) < page_size:
            return features, raw
        offset += len(got)
