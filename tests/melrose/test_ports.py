"""The nominal half of the hexagon: every implementer inherits its port.

`@abstractmethod` makes a drifted implementer fail at construction instead of silently
inheriting a `...` body that returns None -- but only for classes that inherit the Protocol, and
only for methods that carry the decorator. `__slots__ = ()` keeps inheritance from giving every
`slots=True` implementer a `__dict__`. Removing any of the three has no other symptom, so these
tests make it loud.
"""

from __future__ import annotations

import pytest

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
from cities.melrose.ports.outbound import (
    Clock,
    EntryRepository,
    LogArchive,
    LogReader,
    LogSource,
    ReferenceSource,
    ReferenceStore,
)
from cities.melrose.stubs import (
    FakeClock,
    InMemoryEntryRepository,
    InMemoryLogArchive,
    InMemoryLogSource,
    InMemoryReferenceSource,
    InMemoryReferenceStore,
    ScriptedLogReader,
)

PORTS: list[type] = [
    CollectLogs,
    RebuildFromArchive,
    FetchReference,
    LogSource,
    LogReader,
    LogArchive,
    EntryRepository,
    ReferenceSource,
    ReferenceStore,
    Clock,
]

IMPLEMENTERS: list[tuple[type, type]] = [
    (CollectService, CollectLogs),
    (RebuildService, RebuildFromArchive),
    (FetchReferenceService, FetchReference),
    (WordPressLogSource, LogSource),
    (InMemoryLogSource, LogSource),
    (PdfLogReader, LogReader),
    (ScriptedLogReader, LogReader),
    (FileLogArchive, LogArchive),
    (InMemoryLogArchive, LogArchive),
    (SqliteEntryRepository, EntryRepository),
    (InMemoryEntryRepository, EntryRepository),
    (ArcGisReferenceSource, ReferenceSource),
    (InMemoryReferenceSource, ReferenceSource),
    (GeoJsonReferenceStore, ReferenceStore),
    (InMemoryReferenceStore, ReferenceStore),
    (SystemClock, Clock),
    (FakeClock, Clock),
]


@pytest.mark.parametrize(("implementer", "port"), IMPLEMENTERS)
def test_every_implementer_inherits_its_port(implementer: type, port: type) -> None:
    assert port in implementer.__mro__


@pytest.mark.parametrize("port", PORTS)
def test_every_port_method_is_abstract(port: type) -> None:
    methods = {name for name, value in vars(port).items() if callable(value) and (not name.startswith("_") or name == "__call__")}
    assert methods == set(port.__abstractmethods__)


@pytest.mark.parametrize("port", PORTS)
def test_every_port_declares_empty_slots(port: type) -> None:
    assert port.__dict__.get("__slots__") == ()


def test_every_port_has_an_implementer() -> None:
    implemented = {port for _, port in IMPLEMENTERS}
    assert set(PORTS) <= implemented, set(PORTS) - implemented
