"""The file and SQLite adapters, on temporary directories."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from support import FIXTURES, published

from cities.melrose.adapters.outbound.json_publisher import JsonMapPublisher
from cities.melrose.adapters.outbound.log_archive import FileLogArchive
from cities.melrose.adapters.outbound.reference_files import GeoJsonReferenceStore
from cities.melrose.adapters.outbound.sqlite_repo import SqliteEntryRepository
from cities.melrose.domain.entries import EntryState, EntryStatus, EntryVersion
from cities.melrose.domain.logs import ArchivedLog, DocumentRecord, DocumentStatus
from cities.melrose.domain.places import LocationForm, NearEdge, Placement, PlacementKind, Point
from cities.melrose.domain.public import Category, PublicDocument, PublicExport, PublicRecord, WardOutline
from cities.melrose.domain.reference import LayerSnapshot, ReferenceLayer
from cities.melrose.domain.reports import RunReport
from cities.melrose.ports.outbound import StorageFailed

AT = datetime(2026, 10, 7, 12, tzinfo=UTC)


def test_archive_keeps_the_pdf_under_its_hash_and_reads_its_sidecar_back(tmp_path: Path) -> None:
    archive = FileLogArchive(tmp_path)
    kept = archive.keep(published(442445, date(2026, 10, 1)), b"%PDF one", AT)
    assert (tmp_path / f"{kept.sha256}.pdf").read_bytes() == b"%PDF one"
    assert json.loads((tmp_path / "442445.json").read_text())["sha256"] == kept.sha256
    assert archive.archived() == [kept]
    assert archive.load(kept) == b"%PDF one"


def test_the_same_pdf_under_two_uploads_keeps_both_sidecars(tmp_path: Path) -> None:
    archive = FileLogArchive(tmp_path)
    archive.keep(published(1, date(2026, 5, 25)), b"%PDF same", AT)
    archive.keep(published(2, date(2026, 5, 26)), b"%PDF same", AT)
    assert [a.log.media_id for a in archive.archived()] == [1, 2]
    assert len(list(tmp_path.glob("*.pdf"))) == 1


def test_a_pdf_changed_on_disk_no_longer_loads(tmp_path: Path) -> None:
    archive = FileLogArchive(tmp_path)
    kept = archive.keep(published(1, date(2026, 10, 1)), b"%PDF one", AT)
    (tmp_path / f"{kept.sha256}.pdf").write_bytes(b"%PDF edited")
    with pytest.raises(StorageFailed, match="no longer matches"):
        archive.load(kept)


def test_reference_store_writes_each_layer_and_a_manifest(tmp_path: Path) -> None:
    layer = ReferenceLayer("wards", "https://gis.example.test/FeatureServer/0", "TOWN='MELROSE'", ("WARD",))
    GeoJsonReferenceStore(tmp_path).replace([LayerSnapshot(layer, 1, ({"type": "Feature", "properties": {"WARD": "1"}},))], AT)
    collection = json.loads((tmp_path / "wards.geojson").read_text())
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert collection["features"][0]["properties"] == {"WARD": "1"}
    assert (manifest["reference_version"], manifest["layers"][0]["feature_count"]) == ("2026-10-07", 1)
    assert not list(tmp_path.glob("*.tmp"))


def test_repository_round_trips_documents_versions_and_entries(tmp_path: Path) -> None:
    repository = SqliteEntryRepository.open(tmp_path / "db.sqlite")
    record = DocumentRecord(ArchivedLog(published(7, date(2026, 10, 1)), "abc", AT), date(2026, 9, 21), date(2026, 9, 27), DocumentStatus.LOADED)
    v = EntryVersion("26-11102", 7, 1, date(2026, 9, 21), "0858", "MOTOR VEHICLE STOP", "Citation/Warning Issued", "Location/Address", "752 FRANKLIN ST @ 8 GARDEN ST", "26-11102 0858 …")
    repository.save_document(record, [v])
    repository.replace_entries([EntryState("26-11102", 7, EntryStatus.CURRENT)])
    repository.record_run(RunReport("collect", AT, AT))
    assert repository.document_ids() == frozenset({7})
    assert repository.documents() == [record]
    assert repository.versions() == [v]
    assert repository.entries() == [EntryState("26-11102", 7, EntryStatus.CURRENT)]


def test_repository_round_trips_placements_and_clears_them_with_the_versions(tmp_path: Path) -> None:
    repository = SqliteEntryRepository.open(tmp_path / "db.sqlite")
    placed = Placement(
        "26-11115",
        LocationForm.ADDRESS,
        PlacementKind.ADDRESS,
        "744 LYNN FELLS PKWY",
        Point(-71.071786, 42.450733),
        ("Lynn Fells Pkwy",),
        ("2", "4"),
        (NearEdge(("2", "4"), "LYNN FELLS PARKWAY"),),
        "exact address",
        "2026-10-08",
    )
    unplaced = Placement("26-1", LocationForm.NONE, PlacementKind.NONE, None, None, (), (), (), "no location", "2026-10-08")
    repository.replace_placements([placed, unplaced])
    assert repository.placements() == [unplaced, placed]
    repository.clear_versions()
    assert repository.placements() == []


def test_saving_a_document_again_replaces_its_versions(tmp_path: Path) -> None:
    repository = SqliteEntryRepository.open(tmp_path / "db.sqlite")
    record = DocumentRecord(ArchivedLog(published(7, date(2026, 10, 1)), "abc", AT), None, None, DocumentStatus.QUARANTINED, "unknown result")
    v = EntryVersion("26-1", 7, 1, date(2026, 9, 21), "0858", "T", "Unit Clear", None, None, "")
    repository.save_document(record, [v])
    repository.save_document(record, [])
    assert repository.versions() == []
    assert repository.documents()[0].error == "unknown result"


def test_a_database_from_another_schema_version_must_be_rebuilt(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE documents (id INTEGER)")
        db.execute("PRAGMA user_version = 99")
    with pytest.raises(StorageFailed, match="run rebuild"):
        SqliteEntryRepository.open(path)


SAMPLE_EXPORT = PublicExport(
    generated_at=datetime(2026, 10, 8, 12, tzinfo=UTC),
    reference_version="2026-10-08",
    categories=(Category("stops", "Stops", ("MOTOR VEHICLE STOP",)), Category("crashes", "Crashes", ("MOTOR VEHICLE ACCIDENT",))),
    documents=(PublicDocument("https://example.test/sep-21.pdf", date(2026, 9, 21), date(2026, 9, 27)),),
    records=(
        PublicRecord("26-11102", date(2026, 9, 21), "0858", "stops", "MOTOR VEHICLE STOP", "Citation/Warning Issued",
                     "752 FRANKLIN ST @ 8 GARDEN ST", False, PlacementKind.INTERSECTION, Point(-71.07, 42.46),
                     ("Franklin St", "Garden St"), ("1", "4"), 0, 12),
        PublicRecord("26-11103", date(2026, 9, 21), "0915", "stops", "MOTOR VEHICLE STOP", "Verbal Warning",
                     None, True, PlacementKind.STREET_ONLY, None, ("Franklin St",), (), 0, 12),
        PublicRecord("26-11120", date(2026, 9, 22), "1730", "crashes", "MOTOR VEHICLE ACCIDENT", "* Report taken",
                     "744 LYNN FELLS PKWY", False, PlacementKind.ADDRESS, Point(-71.06, 42.47), ("Lynn Fells Pkwy",), ("2",), 0, 13),
    ),
    wards=(WardOutline("1", ((((-71.08, 42.46), (-71.07, 42.46), (-71.07, 42.47), (-71.08, 42.46)),),), Point(-71.075, 42.463)),),
)
# Technical spec Appendix D: the contract with the page's types.ts. A key added here without the
# spec and types.ts would be a field the page never checked, so the sets are pinned exactly.
EXPORT_KEYS = {"generated_at", "reference_version", "categories", "documents", "records"}
RECORD_KEYS = {"call", "date", "time", "category", "type", "result", "address", "vicinity", "kind", "lat", "lon", "streets", "wards", "doc", "page"}
GOLDEN_EXPORT = FIXTURES / "golden" / "export_sample.json"


def test_the_export_file_has_exactly_the_appendix_d_shape(tmp_path: Path) -> None:
    JsonMapPublisher(tmp_path).publish(SAMPLE_EXPORT)
    written = json.loads((tmp_path / "entries.json").read_text())
    assert set(written) == EXPORT_KEYS
    assert [set(c) for c in written["categories"]] == [{"key", "label"}] * 2
    assert set(written["documents"][0]) == {"url", "first_date", "last_date"}
    assert all(set(r) == RECORD_KEYS for r in written["records"])


def test_the_export_file_matches_the_golden_file_the_page_tests_read(tmp_path: Path) -> None:
    """site/tests/aggregate.test.ts reads the same golden file, so both sides pin one contract."""
    JsonMapPublisher(tmp_path).publish(SAMPLE_EXPORT)
    assert (tmp_path / "entries.json").read_text() == GOLDEN_EXPORT.read_text()


def test_the_wards_file_is_one_labelled_multipolygon_per_ward(tmp_path: Path) -> None:
    JsonMapPublisher(tmp_path).publish(SAMPLE_EXPORT)
    wards = json.loads((tmp_path / "wards.geojson").read_text())
    (feature,) = wards["features"]
    assert feature["properties"] == {"ward": "1", "label": [-71.075, 42.463]}
    assert feature["geometry"]["type"] == "MultiPolygon"
    assert feature["geometry"]["coordinates"][0][0][0] == [-71.08, 42.46]
    assert not list(tmp_path.glob("*.tmp"))


def test_an_export_directory_that_cannot_be_written_is_a_storage_failure(tmp_path: Path) -> None:
    blocked = tmp_path / "file"
    blocked.write_text("")
    with pytest.raises(StorageFailed):
        JsonMapPublisher(blocked / "melrose").publish(SAMPLE_EXPORT)
