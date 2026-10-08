"""ReferenceSource over ArcGIS REST feature layers (MassGIS, MassDOT)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import httpx

from cities.melrose.domain.reference import ReferenceLayer
from cities.melrose.ports.outbound import ReferenceSource, ReferenceSourceUnavailable

# The servers' own limit per query; pages are requested at this size.
PAGE_SIZE = 2000


class ArcGisReferenceSource(ReferenceSource):
    __slots__ = ("_client",)

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def count(self, layer: ReferenceLayer) -> int:
        body = self._query(layer, {"where": layer.where, "returnCountOnly": "true", "f": "json"})
        count = body.get("count")
        if not isinstance(count, int):
            raise ReferenceSourceUnavailable(f"{layer.name}: no count in {body!r}")
        return count

    def features(self, layer: ReferenceLayer) -> Sequence[Mapping[str, object]]:
        features: list[Mapping[str, object]] = []
        while True:
            body = self._query(
                layer,
                {
                    "where": layer.where,
                    "outFields": ",".join(layer.out_fields),
                    "orderByFields": "OBJECTID",
                    "resultOffset": str(len(features)),
                    "resultRecordCount": str(PAGE_SIZE),
                    "outSR": "4326",
                    "f": "geojson",
                },
            )
            page = body.get("features")
            if not isinstance(page, list):
                raise ReferenceSourceUnavailable(f"{layer.name}: no features in response")
            features.extend(page)
            if len(page) < PAGE_SIZE:
                return features

    def _query(self, layer: ReferenceLayer, params: dict[str, str]) -> dict[str, object]:
        try:
            response = self._client.get(f"{layer.url}/query", params=params)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ReferenceSourceUnavailable(f"{layer.name}: {exc}") from exc
        # ArcGIS reports query errors with HTTP 200 and an "error" object.
        if not isinstance(body, dict) or "error" in body:
            raise ReferenceSourceUnavailable(f"{layer.name}: {body!r}"[:500])
        return body
