"""Loading one archived log, and deriving what follows from everything loaded. Shared by collect and rebuild."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime

from cities.melrose.core import rules
from cities.melrose.domain.entries import EntryState, EntryStatus, EntryVersion, RawEntry
from cities.melrose.domain.logs import ArchivedLog, DocumentRecord, DocumentStatus
from cities.melrose.domain.reports import Notice, NoticeKind, RunReport
from cities.melrose.ports.outbound import EntryRepository, LogReader, LogUnreadable


@dataclass(frozen=True, slots=True)
class LoadedDocument:
    record: DocumentRecord
    versions: list[EntryVersion]
    notices: list[Notice] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


def load_document(archived: ArchivedLog, pdf: bytes, reader: LogReader, since: date) -> LoadedDocument:
    """Read one log and decide whether its entries load, are out of scope, or are quarantined."""
    media_id = archived.log.media_id
    try:
        read = reader.read(pdf)
    except LogUnreadable as exc:
        return LoadedDocument(DocumentRecord(archived, None, None, DocumentStatus.QUARANTINED, f"unreadable: {exc}"), [])
    notices = [Notice(media_id, None, NoticeKind.STRAY_LINE, line) for line in read.stray_lines]
    first_date = last_date = None
    try:
        dates = rules.assign_dates(read.entries, read.declared_from)
        first_date, last_date = min(dates), max(dates)
        interpreted = rules.interpret(read.entries, dates, media_id)
        rules.check_complete(interpreted.versions, read.call_numbers_in_text, interpreted.inferred)
    except rules.DocumentRejected as exc:
        conflicts = _duplicates(read.entries)
        record = DocumentRecord(archived, first_date, last_date, DocumentStatus.QUARANTINED, str(exc))
        return LoadedDocument(record, [], notices, conflicts)
    if last_date < since:
        return LoadedDocument(DocumentRecord(archived, first_date, last_date, DocumentStatus.OUT_OF_SCOPE), [], notices)
    record = DocumentRecord(archived, first_date, last_date, DocumentStatus.LOADED)
    return LoadedDocument(record, interpreted.versions, notices + interpreted.notices)


def _duplicates(entries: Sequence[RawEntry]) -> list[str]:
    seen: set[str] = set()
    dupes: set[str] = set()
    for e in entries:
        if e.call_number is not None:
            (dupes if e.call_number in seen else seen).add(e.call_number)
    return sorted(dupes)


@dataclass(frozen=True, slots=True)
class Snapshot:
    """The derived state before a run writes, so the report can say what changed."""

    entry_ids: frozenset[str]
    withdrawn: frozenset[str]
    differing: frozenset[str]

    @classmethod
    def of(cls, repository: EntryRepository) -> Snapshot:
        states = repository.entries()
        return cls(
            entry_ids=frozenset(s.call_number for s in states),
            withdrawn=frozenset(s.call_number for s in states if s.status is EntryStatus.WITHDRAWN),
            differing=frozenset(rules.differing_versions(repository.versions())),
        )


def derive_and_report(
    repository: EntryRepository,
    *,
    command: str,
    started_at: datetime,
    finished_at: datetime,
    since: date,
    known_call_types: Collection[str],
    before: Snapshot,
    loaded: Sequence[LoadedDocument],
    wrote: bool,
) -> RunReport:
    """Re-derive the current entries when anything was written, and describe the result."""
    documents = repository.documents()
    versions = repository.versions()
    if wrote:
        repository.replace_entries(rules.current_entries(documents, versions))
    states = repository.entries()
    current = _current_versions(states, versions)
    loaded_last = [d.last_date for d in documents if d.status is DocumentStatus.LOADED and d.last_date is not None]
    differing = rules.differing_versions(versions)
    return RunReport(
        command=command,
        started_at=started_at,
        finished_at=finished_at,
        documents_new=tuple(d.record for d in loaded),
        entries_new=len({s.call_number for s in states} - before.entry_ids),
        quarantined=tuple(d.record for d in loaded if d.record.status is DocumentStatus.QUARANTINED),
        conflicts=tuple(c for d in loaded for c in d.conflicts),
        versions_differing=tuple(sorted(differing - before.differing)),
        withdrawn=tuple(sorted({s.call_number for s in states if s.status is EntryStatus.WITHDRAWN} - before.withdrawn)),
        new_call_types=tuple(sorted({v.call_type for v in current} - set(known_call_types))),
        dates_without_entries=tuple(
            rules.dates_without_entries(since, max(loaded_last, default=None), (v.date for v in current))
        ),
        notices=tuple(n for d in loaded for n in d.notices),
        wrote=wrote,
    )


def _current_versions(states: Sequence[EntryState], versions: Sequence[EntryVersion]) -> list[EntryVersion]:
    shown = {(s.call_number, s.current_document_id) for s in states if s.status is EntryStatus.CURRENT}
    return [v for v in versions if (v.call_number, v.document_id) in shown]
