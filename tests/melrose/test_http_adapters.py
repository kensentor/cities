"""The HTTP adapters against recorded responses. Every failure must leave as the port's own exception."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import httpx
import pytest
from support import FIXTURES

from cities.melrose.adapters.outbound.arcgis import PAGE_SIZE, ArcGisReferenceSource
from cities.melrose.adapters.outbound.wordpress import POLICE_LOGS_PAGE_ID, WordPressLogSource
from cities.melrose.domain.logs import PublishedLog
from cities.melrose.domain.reference import ReferenceLayer
from cities.melrose.ports.outbound import LogSourceUnavailable, ReferenceSourceUnavailable

LISTING = json.loads((FIXTURES / "media_listing.json").read_text())


def client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def wordpress(handler, sleeps: list[float] | None = None) -> WordPressLogSource:
    clock = iter(float(n) for n in range(1000))
    return WordPressLogSource(
        client(handler), interval_s=2.0, sleep=(sleeps if sleeps is not None else []).append, monotonic=lambda: next(clock)
    )


def test_media_listing_becomes_published_logs() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=LISTING, headers={"X-WP-TotalPages": "1"})

    logs = wordpress(handler).list_logs(date(2026, 7, 20))
    assert len(logs) == 11
    assert logs[0].media_id == 442380
    assert logs[0].uploaded_at == datetime(2026, 7, 29, 14, 10, 7, tzinfo=UTC)
    assert seen[0].url.params["parent"] == str(POLICE_LOGS_PAGE_ID)
    assert seen[0].url.params["after"] == "2026-07-20T00:00:00"


def test_listing_follows_every_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        return httpx.Response(200, json=LISTING[(page - 1) * 6 : page * 6], headers={"X-WP-TotalPages": "2"})

    assert len(wordpress(handler).list_logs(date(2026, 7, 20))) == 11


def test_requests_to_the_site_are_spaced_by_the_interval() -> None:
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF-1.4 ...")

    source = wordpress(handler, sleeps)
    source.fetch(_a_log())
    source.fetch(_a_log())
    assert sleeps == [1.0]  # 2 s interval less the 1 s the fake monotonic clock advanced


def test_a_refusal_is_log_source_unavailable() -> None:
    with pytest.raises(LogSourceUnavailable, match="403"):
        wordpress(lambda request: httpx.Response(403)).list_logs(date(2026, 7, 20))


def test_a_timeout_is_log_source_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(LogSourceUnavailable):
        wordpress(handler).fetch(_a_log())


def test_a_page_that_is_not_a_pdf_is_log_source_unavailable() -> None:
    with pytest.raises(LogSourceUnavailable, match="did not return a PDF"):
        wordpress(lambda request: httpx.Response(200, text="<html>Just a moment...</html>")).fetch(_a_log())


def test_an_unexpected_listing_is_log_source_unavailable() -> None:
    with pytest.raises(LogSourceUnavailable, match="unexpected media listing"):
        wordpress(lambda request: httpx.Response(200, json=[{"id": 1}])).list_logs(date(2026, 7, 20))


LAYER = ReferenceLayer("wards", "https://gis.example.test/FeatureServer/0", "TOWN='MELROSE'", ("WARD",))


def test_arcgis_count_and_paged_features() -> None:
    total = PAGE_SIZE + 3

    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params
        assert request.url.path.endswith("/FeatureServer/0/query")
        if params.get("returnCountOnly") == "true":
            return httpx.Response(200, json={"count": total})
        offset, size = int(params["resultOffset"]), int(params["resultRecordCount"])
        assert (params["outSR"], params["f"], params["orderByFields"]) == ("4326", "geojson", "OBJECTID")
        features = [{"type": "Feature", "id": n} for n in range(offset, min(offset + size, total))]
        return httpx.Response(200, json={"type": "FeatureCollection", "features": features})

    source = ArcGisReferenceSource(client(handler))
    assert source.count(LAYER) == total
    assert [f["id"] for f in source.features(LAYER)] == list(range(total))


def test_arcgis_error_reported_with_http_200_is_reference_source_unavailable() -> None:
    body = {"error": {"code": 400, "message": "", "details": ["'Invalid field: TOWN' parameter is invalid"]}}
    with pytest.raises(ReferenceSourceUnavailable, match="Invalid field"):
        ArcGisReferenceSource(client(lambda request: httpx.Response(200, json=body))).count(LAYER)


def test_arcgis_http_failure_is_reference_source_unavailable() -> None:
    with pytest.raises(ReferenceSourceUnavailable):
        ArcGisReferenceSource(client(lambda request: httpx.Response(503))).features(LAYER)


def _a_log() -> PublishedLog:
    at = datetime(2026, 10, 1, tzinfo=UTC)
    return PublishedLog(1, "https://melrosepolice.net/wp-content/uploads/x.pdf", "x", at, at)
