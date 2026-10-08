"""Working in-memory implementations of every outbound port, for driving the core in tests."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from cities.melrose.domain.entries import EntryState, EntryVersion, ReadLog
from cities.melrose.domain.logs import ArchivedLog, DocumentRecord, PublishedLog
from cities.melrose.domain.places import Located, NearEdge, Placement, Point, StreetRef, WardSurroundings
from cities.melrose.domain.reference import LayerSnapshot, ReferenceLayer
from cities.melrose.domain.reports import RunReport
from cities.melrose.ports.outbound import (
    Clock,
    EntryRepository,
    Gazetteer,
    LogArchive,
    LogReader,
    LogSource,
    LogSourceUnavailable,
    LogUnreadable,
    ReferenceSource,
    ReferenceStore,
)


class InMemoryLogSource(LogSource):
    """Serves fixed logs; `failing` names media ids whose download fails."""

    __slots__ = ("failing", "fetched", "logs")

    def __init__(self, logs: Mapping[PublishedLog, bytes], failing: frozenset[int] = frozenset()) -> None:
        self.logs = dict(logs)
        self.failing = failing
        self.fetched: list[int] = []

    def list_logs(self, uploaded_since: date) -> Sequence[PublishedLog]:
        return sorted((log for log in self.logs if log.uploaded_at.date() >= uploaded_since), key=lambda log: log.media_id)

    def fetch(self, log: PublishedLog) -> bytes:
        if log.media_id in self.failing:
            raise LogSourceUnavailable(f"media {log.media_id} failed")
        self.fetched.append(log.media_id)
        return self.logs[log]


class ScriptedLogReader(LogReader):
    """Returns a prepared ReadLog for each PDF's bytes; unknown bytes are unreadable."""

    __slots__ = ("reads",)

    def __init__(self, reads: Mapping[bytes, ReadLog]) -> None:
        self.reads = dict(reads)

    def read(self, pdf: bytes) -> ReadLog:
        if pdf not in self.reads:
            raise LogUnreadable("not a scripted PDF")
        return self.reads[pdf]


class InMemoryLogArchive(LogArchive):
    __slots__ = ("files", "logs")

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.logs: dict[int, ArchivedLog] = {}

    def keep(self, log: PublishedLog, pdf: bytes, fetched_at: datetime) -> ArchivedLog:
        archived = ArchivedLog(log, hashlib.sha256(pdf).hexdigest(), fetched_at)
        self.files[archived.sha256] = pdf
        self.logs[log.media_id] = archived
        return archived

    def archived(self) -> Sequence[ArchivedLog]:
        return [self.logs[k] for k in sorted(self.logs)]

    def load(self, archived: ArchivedLog) -> bytes:
        return self.files[archived.sha256]


@dataclass(slots=True)
class InMemoryEntryRepository(EntryRepository):
    document_rows: dict[int, DocumentRecord] = field(default_factory=dict)
    version_rows: dict[tuple[str, int], EntryVersion] = field(default_factory=dict)
    entry_rows: dict[str, EntryState] = field(default_factory=dict)
    placement_rows: dict[str, Placement] = field(default_factory=dict)
    runs: list[RunReport] = field(default_factory=list)
    writes: int = 0

    def document_ids(self) -> frozenset[int]:
        return frozenset(self.document_rows)

    def documents(self) -> Sequence[DocumentRecord]:
        return [self.document_rows[k] for k in sorted(self.document_rows)]

    def versions(self) -> Sequence[EntryVersion]:
        return [self.version_rows[k] for k in sorted(self.version_rows)]

    def entries(self) -> Sequence[EntryState]:
        return [self.entry_rows[k] for k in sorted(self.entry_rows)]

    def save_document(self, record: DocumentRecord, versions: Sequence[EntryVersion]) -> None:
        self.writes += 1
        self.document_rows[record.media_id] = record
        for key in [k for k in self.version_rows if k[1] == record.media_id]:
            del self.version_rows[key]
        for v in versions:
            self.version_rows[(v.call_number, v.document_id)] = v

    def replace_entries(self, states: Sequence[EntryState]) -> None:
        self.writes += 1
        self.entry_rows = {s.call_number: s for s in states}

    def placements(self) -> Sequence[Placement]:
        return [self.placement_rows[k] for k in sorted(self.placement_rows)]

    def replace_placements(self, placements: Sequence[Placement]) -> None:
        self.writes += 1
        self.placement_rows = {p.call_number: p for p in placements}

    def clear_versions(self) -> None:
        self.writes += 1
        self.placement_rows.clear()
        self.entry_rows.clear()
        self.version_rows.clear()

    def record_run(self, report: RunReport) -> None:
        self.writes += 1
        self.runs.append(report)


class InMemoryReferenceSource(ReferenceSource):
    """Serves fixed features per layer; `reported` overrides the count the server claims."""

    __slots__ = ("layers", "reported")

    def __init__(self, layers: Mapping[str, Sequence[Mapping[str, object]]], reported: Mapping[str, int] | None = None) -> None:
        self.layers = dict(layers)
        self.reported = dict(reported or {})

    def count(self, layer: ReferenceLayer) -> int:
        return self.reported.get(layer.name, len(self.layers[layer.name]))

    def features(self, layer: ReferenceLayer) -> Sequence[Mapping[str, object]]:
        return self.layers[layer.name]


class InMemoryReferenceStore(ReferenceStore):
    __slots__ = ("fetched_at", "snapshots")

    def __init__(self) -> None:
        self.snapshots: list[LayerSnapshot] = []
        self.fetched_at: datetime | None = None

    def replace(self, snapshots: Sequence[LayerSnapshot], fetched_at: datetime) -> None:
        self.snapshots = list(snapshots)
        self.fetched_at = fetched_at


@dataclass(slots=True)
class InMemoryGazetteer(Gazetteer):
    """A fixed street plan: known addresses and crossings, one ward per point, and the edges each point is near.

    Points are placed where `addresses` and `crossings` say; `outside` names points beyond the city
    by their distance; `near_edges` gives each point's near edges, with the street running along.
    """

    addresses: dict[tuple[str, int], Point] = field(default_factory=dict)
    crossings: dict[frozenset[str], Point] = field(default_factory=dict)
    ward_of: dict[Point, str] = field(default_factory=dict)
    near_edges: dict[Point, tuple[NearEdge, ...]] = field(default_factory=dict)
    outside: dict[Point, float] = field(default_factory=dict)
    extra_streets: frozenset[str] = frozenset()
    version: str = "2026-10-08"

    def reference_version(self) -> str:
        return self.version

    def street_names(self) -> frozenset[str]:
        return frozenset(name for name, _ in self.addresses) | {n for pair in self.crossings for n in pair} | self.extra_streets

    def locate_address(self, street: StreetRef) -> Located:
        point = self.addresses.get((street.name, street.number or -1))
        return Located(point, "exact address" if point else "address not found")

    def locate_intersection(self, first: StreetRef, second: StreetRef) -> Located:
        point = self.crossings.get(frozenset({first.name, second.name}))
        return Located(point, "crossing" if point else "intersection not found")

    def distance_outside_city_m(self, point: Point) -> float:
        return self.outside.get(point, 0.0)

    def wards_around(self, point: Point, streets: Sequence[str]) -> WardSurroundings:
        edges = tuple(e if e.along is None or e.along in streets else NearEdge(e.wards, None) for e in self.near_edges.get(point, ()))
        return WardSurroundings(self.ward_of.get(point), edges)


class FakeClock(Clock):
    """Starts at a fixed instant and advances one second per reading."""

    __slots__ = ("_next", "_step")

    def __init__(self, start: datetime = datetime(2026, 10, 7, 12, tzinfo=UTC), step: Callable[[], timedelta] = lambda: timedelta(seconds=1)) -> None:
        self._next = start
        self._step = step

    def now(self) -> datetime:
        current = self._next
        self._next = current + self._step()
        return current
