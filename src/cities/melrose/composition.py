"""The only place adapters are built and wired into the use cases."""

from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager

import httpx

from cities.melrose.adapters.outbound.arcgis import ArcGisReferenceSource
from cities.melrose.adapters.outbound.clock import SystemClock
from cities.melrose.adapters.outbound.log_archive import FileLogArchive
from cities.melrose.adapters.outbound.pdf_reader import PdfLogReader
from cities.melrose.adapters.outbound.reference_files import GeoJsonReferenceStore
from cities.melrose.adapters.outbound.sqlite_repo import SqliteEntryRepository
from cities.melrose.adapters.outbound.wordpress import WordPressLogSource
from cities.melrose.core.collect import CollectService
from cities.melrose.core.rebuild import RebuildService
from cities.melrose.core.reference import FetchReferenceService
from cities.melrose.ports.inbound import CollectLogs, FetchReference, RebuildFromArchive
from cities.melrose.settings import Settings


@contextmanager
def collect_logs(
    settings: Settings, transport: httpx.BaseTransport | None = None, *, pause: bool = True
) -> Generator[CollectLogs]:
    """`pause=False` drops the wait between requests, for a transport that never reaches the site."""
    with _http(settings, transport) as client, _repository(settings) as repository:
        yield CollectService(
            source=WordPressLogSource(
                client, interval_s=settings.request_interval_s, sleep=time.sleep if pause else _no_sleep
            ),
            reader=PdfLogReader(),
            archive=FileLogArchive(settings.raw_dir),
            repository=repository,
            clock=SystemClock(),
            since=settings.since,
            known_call_types=settings.known_call_types,
        )


@contextmanager
def rebuild_from_archive(settings: Settings) -> Generator[RebuildFromArchive]:
    with _repository(settings) as repository:
        yield RebuildService(
            reader=PdfLogReader(),
            archive=FileLogArchive(settings.raw_dir),
            repository=repository,
            clock=SystemClock(),
            since=settings.since,
            known_call_types=settings.known_call_types,
        )


@contextmanager
def fetch_reference(settings: Settings, transport: httpx.BaseTransport | None = None) -> Generator[FetchReference]:
    with _http(settings, transport) as client:
        yield FetchReferenceService(
            source=ArcGisReferenceSource(client),
            store=GeoJsonReferenceStore(settings.reference_dir),
            clock=SystemClock(),
            layers=settings.reference_layers,
        )


def _http(settings: Settings, transport: httpx.BaseTransport | None) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": settings.user_agent},
        timeout=settings.request_timeout_s,
        follow_redirects=True,
        transport=transport,
    )


@contextmanager
def _repository(settings: Settings) -> Generator[SqliteEntryRepository]:
    repository = SqliteEntryRepository.open(settings.database)
    try:
        yield repository
    finally:
        repository.close()


def _no_sleep(seconds: float) -> None:
    return None
