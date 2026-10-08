"""The use cases, wired from the in-memory fakes."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest
from support import entry, published, read_log

from cities.melrose.core.collect import CollectService
from cities.melrose.core.export import ExportService
from cities.melrose.core.rebuild import RebuildService
from cities.melrose.core.reference import FetchReferenceService
from cities.melrose.domain.entries import EntryStatus, ReadLog, SegmentKind
from cities.melrose.domain.logs import DocumentStatus, PublishedLog
from cities.melrose.domain.public import Category
from cities.melrose.domain.reference import ReferenceLayer
from cities.melrose.ports.outbound import LogSourceUnavailable, ReferenceSourceUnavailable, StorageFailed
from cities.melrose.stubs import (
    FakeClock,
    InMemoryEntryRepository,
    InMemoryGazetteer,
    InMemoryLogArchive,
    InMemoryLogSource,
    InMemoryMapPublisher,
    InMemoryReferenceSource,
    InMemoryReferenceStore,
    ScriptedLogReader,
)

SINCE = date(2026, 7, 20)
KNOWN_TYPES = frozenset({"MOTOR VEHICLE STOP", "MEDICAL EMERGENCY"})
CATEGORIES = (Category("stops", "Stops", ("MOTOR VEHICLE STOP",)), Category("crashes", "Crashes", ("MOTOR VEHICLE ACCIDENT",)))

WEEK_1 = read_log(entry("26-1", date(2026, 7, 20)), entry("26-2", date(2026, 7, 21), "MEDICAL EMERGENCY Unit Clear"))
WEEK_0 = read_log(entry("26-0", date(2026, 7, 13)))  # uploaded late, covers only earlier dates


class World:
    def __init__(self, logs: dict[PublishedLog, tuple[bytes, ReadLog]], failing: frozenset[int] = frozenset()) -> None:
        self.source = InMemoryLogSource({log: pdf for log, (pdf, _) in logs.items()}, failing)
        self.reader = ScriptedLogReader({pdf: read for pdf, read in logs.values()})
        self.archive = InMemoryLogArchive()
        self.repository = InMemoryEntryRepository()
        self.gazetteer = InMemoryGazetteer()
        self.publisher = InMemoryMapPublisher()

    def collect(self) -> CollectService:
        return CollectService(
            source=self.source,
            reader=self.reader,
            archive=self.archive,
            repository=self.repository,
            gazetteer=self.gazetteer,
            publisher=self.publisher,
            clock=FakeClock(),
            since=SINCE,
            known_call_types=KNOWN_TYPES,
            categories=CATEGORIES,
        )

    def rebuild(self, repository: InMemoryEntryRepository | None = None) -> RebuildService:
        return RebuildService(
            reader=self.reader,
            archive=self.archive,
            repository=repository or self.repository,
            gazetteer=self.gazetteer,
            publisher=self.publisher,
            clock=FakeClock(),
            since=SINCE,
            known_call_types=KNOWN_TYPES,
            categories=CATEGORIES,
        )


def test_collect_loads_new_logs_and_marks_late_uploads_of_earlier_weeks_out_of_scope() -> None:
    world = World({published(10, date(2026, 7, 29)): (b"w0", WEEK_0), published(11, date(2026, 7, 29), minute=1): (b"w1", WEEK_1)})
    report = world.collect().collect()
    statuses = {d.media_id: d.status for d in world.repository.documents()}
    assert statuses == {10: DocumentStatus.OUT_OF_SCOPE, 11: DocumentStatus.LOADED}
    assert sorted(world.archive.logs) == [10, 11], "out-of-scope logs are archived too, so rebuild matches collect"
    assert report.entries_new == 2
    assert [s.call_number for s in world.repository.entries()] == ["26-1", "26-2"]
    assert len(world.repository.runs) == 1


def test_collecting_again_writes_nothing() -> None:
    world = World({published(11, date(2026, 7, 29)): (b"w1", WEEK_1)})
    world.collect().collect()
    writes = world.repository.writes
    report = world.collect().collect()
    assert (report.wrote, world.repository.writes, world.source.fetched) == (False, writes, [11])
    assert (len(world.publisher.exports), report.exported) == (1, None), "a second collect publishes nothing either"


def test_a_failed_download_writes_nothing() -> None:
    world = World(
        {published(11, date(2026, 7, 29)): (b"w1", WEEK_1), published(12, date(2026, 8, 9)): (b"w2", WEEK_1)},
        failing=frozenset({12}),
    )
    with pytest.raises(LogSourceUnavailable):
        world.collect().collect()
    assert (world.repository.writes, world.archive.logs) == (0, {})


def test_an_unreadable_log_is_archived_and_quarantined_and_the_rest_load() -> None:
    world = World({published(11, date(2026, 7, 29)): (b"w1", WEEK_1)})
    world.source.logs[published(12, date(2026, 8, 9))] = b"not a pdf"
    report = world.collect().collect()
    assert [d.media_id for d in report.quarantined] == [12]
    assert 12 in world.archive.logs
    assert report.entries_new == 2


def test_new_call_types_are_reported() -> None:
    week = read_log(entry("26-1", date(2026, 7, 20), "ROBBERY Unit Clear"))
    report = World({published(11, date(2026, 7, 29)): (b"w1", week)}).collect().collect()
    assert report.new_call_types == ("ROBBERY",)


def test_a_reissued_log_without_an_entry_withdraws_it_and_reports_differences() -> None:
    first = read_log(entry("26-1", date(2026, 4, 6), "MOTOR VEHICLE STOP Verbal Warning", (SegmentKind.LOCATION_ADDRESS, "1 MAIN ST")), entry("26-2", date(2026, 4, 12)))
    reissue = read_log(entry("26-1", date(2026, 4, 6), "MOTOR VEHICLE STOP Verbal Warning"), entry("26-3", date(2026, 4, 12)))
    world = World({published(1, date(2026, 4, 14)): (b"a", first)})
    world.collect().collect(since=date(2026, 4, 1))
    world.source.logs[published(2, date(2026, 4, 20))] = b"b"
    world.reader.reads[b"b"] = reissue
    report = world.collect().collect(since=date(2026, 4, 1))
    states = {s.call_number: s for s in world.repository.entries()}
    assert states["26-2"].status is EntryStatus.WITHDRAWN
    assert (states["26-1"].current_document_id, states["26-1"].status) == (2, EntryStatus.CURRENT)
    assert report.withdrawn == ("26-2",)
    assert report.versions_differing == ("26-1",)


def test_rebuild_from_the_archive_equals_incremental_collection() -> None:
    """AC11 at the storage level: the same documents give the same documents, versions and entries."""
    world = World({published(10, date(2026, 7, 29)): (b"w0", WEEK_0), published(11, date(2026, 7, 29), minute=1): (b"w1", WEEK_1)})
    world.collect().collect()
    fresh = InMemoryEntryRepository()
    world.rebuild(fresh).rebuild()
    assert fresh.documents() == world.repository.documents()
    assert fresh.versions() == world.repository.versions()
    assert fresh.entries() == world.repository.entries()
    assert fresh.placements() == world.repository.placements()
    assert len(fresh.placements()) == 2
    incremental, rebuilt = world.publisher.exports
    assert replace(rebuilt, generated_at=incremental.generated_at) == incremental
    assert [r.call for r in rebuilt.records] == ["26-1"], "only the stop is a listed call type"


def test_export_publishes_from_what_is_stored_without_collecting() -> None:
    world = World({published(11, date(2026, 7, 29)): (b"w1", WEEK_1)})
    world.collect().collect()
    summary = ExportService(
        repository=world.repository, gazetteer=world.gazetteer, publisher=world.publisher, clock=FakeClock(), categories=CATEGORIES
    ).export()
    assert (summary.counts, summary.records) == ((("Stops", 1), ("Crashes", 0)), 1)
    assert world.publisher.exports[-1].records == world.publisher.exports[0].records
    assert world.source.fetched == [11]


def test_a_missing_reference_snapshot_writes_nothing() -> None:
    class MissingSnapshot(InMemoryGazetteer):
        def reference_version(self) -> str:
            raise StorageFailed("reference snapshot missing")

    world = World({published(11, date(2026, 7, 29)): (b"w1", WEEK_1)})
    world.gazetteer = MissingSnapshot()
    with pytest.raises(StorageFailed):
        world.collect().collect()
    assert (world.repository.writes, world.archive.logs) == (0, {})


def test_a_collect_that_writes_nothing_still_reports_the_stored_placements() -> None:
    world = World({published(11, date(2026, 7, 29)): (b"w1", WEEK_1)})
    world.collect().collect()
    report = world.collect().collect()
    assert not report.wrote
    assert report.placement is not None and dict(report.placement.counts) == {"none": 2}


def test_reference_snapshot_is_kept_when_a_layer_comes_back_short() -> None:
    layer = ReferenceLayer("wards", "https://example.test/FeatureServer/0", "TOWN='MELROSE'", ("WARD",))
    store = InMemoryReferenceStore()
    service = FetchReferenceService(
        source=InMemoryReferenceSource({"wards": [{"type": "Feature"}]}, reported={"wards": 14}), store=store, clock=FakeClock(), layers=[layer]
    )
    with pytest.raises(ReferenceSourceUnavailable, match="reports 14 features but 1"):
        service.fetch_reference()
    assert store.fetched_at is None


def test_reference_snapshot_is_replaced_when_every_layer_is_complete() -> None:
    layer = ReferenceLayer("wards", "https://example.test/FeatureServer/0", "TOWN='MELROSE'", ("WARD",))
    store = InMemoryReferenceStore()
    report = FetchReferenceService(
        source=InMemoryReferenceSource({"wards": [{"type": "Feature"}] * 14}), store=store, clock=FakeClock(), layers=[layer]
    ).fetch_reference()
    assert report.counts == (("wards", 14),)
    assert len(store.snapshots[0].features) == 14

