"""`rebuild`: re-read every archived log and derive everything again from the archive alone."""

from __future__ import annotations

from collections.abc import Collection
from datetime import date

from cities.melrose.core.loading import LoadedDocument, Snapshot, derive_and_report, load_document
from cities.melrose.domain.reports import RunReport
from cities.melrose.ports.inbound import RebuildFromArchive
from cities.melrose.ports.outbound import Clock, EntryRepository, LogArchive, LogReader


class RebuildService(RebuildFromArchive):
    __slots__ = ("_archive", "_clock", "_known_call_types", "_reader", "_repository", "_since")

    def __init__(
        self,
        *,
        reader: LogReader,
        archive: LogArchive,
        repository: EntryRepository,
        clock: Clock,
        since: date,
        known_call_types: Collection[str],
    ) -> None:
        self._reader = reader
        self._archive = archive
        self._repository = repository
        self._clock = clock
        self._since = since
        self._known_call_types = known_call_types

    def rebuild(self) -> RunReport:
        started_at = self._clock.now()
        before = Snapshot.of(self._repository)
        self._repository.clear_versions()
        loaded: list[LoadedDocument] = []
        for archived in sorted(self._archive.archived(), key=lambda a: a.log.media_id):
            document = load_document(archived, self._archive.load(archived), self._reader, self._since)
            self._repository.save_document(document.record, document.versions)
            loaded.append(document)
        report = derive_and_report(
            self._repository,
            command="rebuild",
            started_at=started_at,
            finished_at=self._clock.now(),
            since=self._since,
            known_call_types=self._known_call_types,
            before=before,
            loaded=loaded,
            wrote=True,
        )
        self._repository.record_run(report)
        return report
