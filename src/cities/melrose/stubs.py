"""Working in-memory implementations of every outbound port, for driving the core in tests."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from cities.melrose.domain.entries import EntryState, EntryVersion, ReadLog
from cities.melrose.domain.logs import ArchivedLog, DocumentRecord, PublishedLog
from cities.melrose.domain.reference import LayerSnapshot, ReferenceLayer
from cities.melrose.domain.reports import RunReport
from cities.melrose.ports.outbound import (
    Clock,
    EntryRepository,
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

    def clear_versions(self) -> None:
        self.writes += 1
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
