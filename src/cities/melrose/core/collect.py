"""`collect`: download logs not seen before and load their entries."""

from __future__ import annotations

from collections.abc import Collection
from datetime import date

from cities.melrose.core.loading import LoadedDocument, Snapshot, derive_and_report, load_document
from cities.melrose.domain.reports import RunReport
from cities.melrose.ports.inbound import CollectLogs
from cities.melrose.ports.outbound import Clock, EntryRepository, LogArchive, LogReader, LogSource


class CollectService(CollectLogs):
    __slots__ = ("_archive", "_clock", "_known_call_types", "_reader", "_repository", "_since", "_source")

    def __init__(
        self,
        *,
        source: LogSource,
        reader: LogReader,
        archive: LogArchive,
        repository: EntryRepository,
        clock: Clock,
        since: date,
        known_call_types: Collection[str],
    ) -> None:
        self._source = source
        self._reader = reader
        self._archive = archive
        self._repository = repository
        self._clock = clock
        self._since = since
        self._known_call_types = known_call_types

    def collect(self, since: date | None = None) -> RunReport:
        since = since or self._since
        started_at = self._clock.now()
        known = self._repository.document_ids()
        new = [log for log in self._source.list_logs(uploaded_since=since) if log.media_id not in known]
        # Every download finishes before anything is written, so a network failure writes nothing.
        downloads = [(log, self._source.fetch(log), self._clock.now()) for log in new]
        before = Snapshot.of(self._repository)
        loaded: list[LoadedDocument] = []
        for log, pdf, fetched_at in downloads:
            archived = self._archive.keep(log, pdf, fetched_at)
            document = load_document(archived, pdf, self._reader, since)
            self._repository.save_document(document.record, document.versions)
            loaded.append(document)
        report = derive_and_report(
            self._repository,
            command="collect",
            started_at=started_at,
            finished_at=self._clock.now(),
            since=since,
            known_call_types=self._known_call_types,
            before=before,
            loaded=loaded,
            wrote=bool(loaded),
        )
        if report.wrote:
            self._repository.record_run(report)
        return report
