"""EntryRepository over SQLite. The database is derived: `rebuild` recreates it from the archive."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from cities.melrose.domain.entries import EntryState, EntryStatus, EntryVersion
from cities.melrose.domain.logs import ArchivedLog, DocumentRecord, DocumentStatus, PublishedLog
from cities.melrose.domain.places import LocationForm, NearEdge, Placement, PlacementKind, Point
from cities.melrose.domain.reports import RunReport
from cities.melrose.ports.outbound import EntryRepository, StorageFailed

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    source_url TEXT NOT NULL,
    title TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    modified_at TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    first_date TEXT,
    last_date TEXT,
    status TEXT NOT NULL,
    error TEXT
);
CREATE TABLE IF NOT EXISTS entry_versions (
    call_number TEXT NOT NULL,
    document_id INTEGER NOT NULL REFERENCES documents (id),
    page INTEGER NOT NULL,
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    call_type TEXT NOT NULL,
    result TEXT NOT NULL,
    location_prefix TEXT,
    location_raw TEXT,
    raw_block TEXT NOT NULL,
    PRIMARY KEY (call_number, document_id)
);
CREATE TABLE IF NOT EXISTS entries (
    call_number TEXT PRIMARY KEY,
    current_document_id INTEGER NOT NULL REFERENCES documents (id),
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS placements (
    call_number TEXT PRIMARY KEY,
    form TEXT NOT NULL,
    kind TEXT NOT NULL,
    address_display TEXT,
    lon REAL,
    lat REAL,
    streets TEXT NOT NULL,
    wards TEXT NOT NULL,
    near_edges TEXT NOT NULL,
    method TEXT NOT NULL,
    reference_version TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    command TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    documents_new INTEGER NOT NULL,
    entries_new INTEGER NOT NULL,
    quarantined INTEGER NOT NULL,
    conflicts INTEGER NOT NULL,
    versions_differing INTEGER NOT NULL,
    withdrawn INTEGER NOT NULL,
    new_call_types INTEGER NOT NULL,
    dates_without_entries INTEGER NOT NULL,
    notices INTEGER NOT NULL,
    placed_rate REAL
);
"""

_VERSION_COLUMNS = "call_number, document_id, page, date, time, call_type, result, location_prefix, location_raw, raw_block"


class SqliteEntryRepository(EntryRepository):
    __slots__ = ("_connection",)

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    @classmethod
    def open(cls, path: Path) -> SqliteEntryRepository:
        """Open the database, creating it. A database from another schema version must be rebuilt."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path)
            connection.execute("PRAGMA foreign_keys = ON")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            has_tables = connection.execute("SELECT count(*) FROM sqlite_master WHERE type = 'table'").fetchone()[0]
            if has_tables and version != SCHEMA_VERSION:
                connection.close()
                raise StorageFailed(f"{path} has schema version {version}, expected {SCHEMA_VERSION}: delete it and run rebuild")
            connection.executescript(SCHEMA)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error as exc:
            raise StorageFailed(f"{path}: {exc}") from exc
        return cls(connection)

    def close(self) -> None:
        self._connection.close()

    def document_ids(self) -> frozenset[int]:
        with self._reading() as db:
            return frozenset(row[0] for row in db.execute("SELECT id FROM documents"))

    def documents(self) -> Sequence[DocumentRecord]:
        with self._reading() as db:
            rows = db.execute(
                "SELECT id, source_url, title, uploaded_at, modified_at, sha256, fetched_at, first_date, last_date, status, error"
                " FROM documents ORDER BY id"
            ).fetchall()
        return [_document(row) for row in rows]

    def versions(self) -> Sequence[EntryVersion]:
        with self._reading() as db:
            rows = db.execute(f"SELECT {_VERSION_COLUMNS} FROM entry_versions ORDER BY call_number, document_id").fetchall()
        return [_version(row) for row in rows]

    def entries(self) -> Sequence[EntryState]:
        with self._reading() as db:
            rows = db.execute("SELECT call_number, current_document_id, status FROM entries ORDER BY call_number").fetchall()
        return [EntryState(row[0], row[1], EntryStatus(row[2])) for row in rows]

    def save_document(self, record: DocumentRecord, versions: Sequence[EntryVersion]) -> None:
        log = record.archived.log
        with self._writing() as db:
            db.execute(
                "INSERT INTO documents (id, source_url, title, uploaded_at, modified_at, sha256, fetched_at,"
                " first_date, last_date, status, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (id) DO UPDATE SET source_url = excluded.source_url, title = excluded.title,"
                " uploaded_at = excluded.uploaded_at, modified_at = excluded.modified_at, sha256 = excluded.sha256,"
                " fetched_at = excluded.fetched_at, first_date = excluded.first_date, last_date = excluded.last_date,"
                " status = excluded.status, error = excluded.error",
                (
                    log.media_id,
                    log.source_url,
                    log.title,
                    log.uploaded_at.isoformat(),
                    log.modified_at.isoformat(),
                    record.archived.sha256,
                    record.archived.fetched_at.isoformat(),
                    _iso(record.first_date),
                    _iso(record.last_date),
                    record.status.value,
                    record.error,
                ),
            )
            db.execute("DELETE FROM entry_versions WHERE document_id = ?", (log.media_id,))
            db.executemany(
                f"INSERT INTO entry_versions ({_VERSION_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        v.call_number,
                        v.document_id,
                        v.page,
                        v.date.isoformat(),
                        v.time,
                        v.call_type,
                        v.result,
                        v.location_prefix,
                        v.location_raw,
                        v.raw_block,
                    )
                    for v in versions
                ],
            )

    def replace_entries(self, states: Sequence[EntryState]) -> None:
        with self._writing() as db:
            db.execute("DELETE FROM entries")
            db.executemany(
                "INSERT INTO entries (call_number, current_document_id, status) VALUES (?, ?, ?)",
                [(s.call_number, s.current_document_id, s.status.value) for s in states],
            )

    def placements(self) -> Sequence[Placement]:
        with self._reading() as db:
            rows = db.execute(
                "SELECT call_number, form, kind, address_display, lon, lat, streets, wards, near_edges, method, reference_version"
                " FROM placements ORDER BY call_number"
            ).fetchall()
        return [_placement(row) for row in rows]

    def replace_placements(self, placements: Sequence[Placement]) -> None:
        with self._writing() as db:
            db.execute("DELETE FROM placements")
            db.executemany(
                "INSERT INTO placements (call_number, form, kind, address_display, lon, lat, streets, wards, near_edges,"
                " method, reference_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        p.call_number,
                        p.form.value,
                        p.kind.value,
                        p.address_display,
                        p.point.lon if p.point else None,
                        p.point.lat if p.point else None,
                        json.dumps(list(p.streets)),
                        json.dumps(list(p.wards)),
                        json.dumps([{"wards": list(e.wards), "along": e.along} for e in p.near_edges]),
                        p.method,
                        p.reference_version,
                    )
                    for p in placements
                ],
            )

    def clear_versions(self) -> None:
        with self._writing() as db:
            db.execute("DELETE FROM placements")
            db.execute("DELETE FROM entries")
            db.execute("DELETE FROM entry_versions")

    def record_run(self, report: RunReport) -> None:
        with self._writing() as db:
            db.execute(
                "INSERT INTO runs (command, started_at, finished_at, documents_new, entries_new, quarantined, conflicts,"
                " versions_differing, withdrawn, new_call_types, dates_without_entries, notices, placed_rate)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    report.command,
                    report.started_at.isoformat(),
                    report.finished_at.isoformat(),
                    len(report.documents_new),
                    report.entries_new,
                    len(report.quarantined),
                    len(report.conflicts),
                    len(report.versions_differing),
                    len(report.withdrawn),
                    len(report.new_call_types),
                    len(report.dates_without_entries),
                    len(report.notices),
                    report.placement.stop_rate if report.placement else None,
                ),
            )

    @contextmanager
    def _reading(self) -> Generator[sqlite3.Connection]:
        try:
            yield self._connection
        except sqlite3.Error as exc:
            raise StorageFailed(str(exc)) from exc

    @contextmanager
    def _writing(self) -> Generator[sqlite3.Connection]:
        try:
            with self._connection:  # one transaction: committed on success, rolled back on error
                yield self._connection
        except sqlite3.Error as exc:
            raise StorageFailed(str(exc)) from exc


def _iso(day: date | None) -> str | None:
    return day.isoformat() if day else None


def _day(text: str | None) -> date | None:
    return date.fromisoformat(text) if text else None


def _document(row: tuple[object, ...]) -> DocumentRecord:
    media_id, source_url, title, uploaded_at, modified_at, sha256, fetched_at, first, last, status, error = row
    log = PublishedLog(
        media_id=int(str(media_id)),
        source_url=str(source_url),
        title=str(title),
        uploaded_at=datetime.fromisoformat(str(uploaded_at)),
        modified_at=datetime.fromisoformat(str(modified_at)),
    )
    archived = ArchivedLog(log, str(sha256), datetime.fromisoformat(str(fetched_at)))
    return DocumentRecord(
        archived,
        _day(first if isinstance(first, str) else None),
        _day(last if isinstance(last, str) else None),
        DocumentStatus(str(status)),
        error if isinstance(error, str) else None,
    )


def _version(row: tuple[object, ...]) -> EntryVersion:
    call_number, document_id, page, day, hhmm, call_type, result, prefix, location, block = row
    return EntryVersion(
        call_number=str(call_number),
        document_id=int(str(document_id)),
        page=int(str(page)),
        date=date.fromisoformat(str(day)),
        time=str(hhmm),
        call_type=str(call_type),
        result=str(result),
        location_prefix=prefix if isinstance(prefix, str) else None,
        location_raw=location if isinstance(location, str) else None,
        raw_block=str(block),
    )


def _placement(row: tuple[object, ...]) -> Placement:
    call_number, form, kind, address, lon, lat, streets, wards, edges, method, version = row
    point = Point(float(str(lon)), float(str(lat))) if lon is not None and lat is not None else None
    return Placement(
        call_number=str(call_number),
        form=LocationForm(str(form)),
        kind=PlacementKind(str(kind)),
        address_display=address if isinstance(address, str) else None,
        point=point,
        streets=tuple(json.loads(str(streets))),
        wards=tuple(json.loads(str(wards))),
        near_edges=tuple(NearEdge((e["wards"][0], e["wards"][1]), e["along"]) for e in json.loads(str(edges))),
        method=str(method),
        reference_version=str(version),
    )
