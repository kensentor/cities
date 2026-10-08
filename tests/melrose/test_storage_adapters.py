"""The file and SQLite adapters, on temporary directories."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from support import published

from cities.melrose.adapters.outbound.log_archive import FileLogArchive
from cities.melrose.adapters.outbound.reference_files import GeoJsonReferenceStore
from cities.melrose.adapters.outbound.sqlite_repo import SqliteEntryRepository
from cities.melrose.domain.entries import EntryState, EntryStatus, EntryVersion
from cities.melrose.domain.logs import ArchivedLog, DocumentRecord, DocumentStatus
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
