"""Building the map export from stored entries and placements: which records leave, and with what."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from support import published

from cities.melrose.core.publishing import build_export, public_result
from cities.melrose.domain.entries import EntryState, EntryStatus, EntryVersion
from cities.melrose.domain.logs import ArchivedLog, DocumentRecord, DocumentStatus
from cities.melrose.domain.places import LocationForm, Placement, PlacementKind, Point
from cities.melrose.domain.public import Category
from cities.melrose.ports.inbound import ExportRefused

CATEGORIES = (
    Category("stops", "Stops", ("MOTOR VEHICLE STOP",)),
    Category("crashes", "Crashes", ("MOTOR VEHICLE ACCIDENT", "ACCIDENT HIT & RUN", "MVA - Not Investigated")),
)
AT = datetime(2026, 10, 8, 12, tzinfo=UTC)
VERSION = "2026-10-08"


def document(media_id: int, first: date, last: date) -> DocumentRecord:
    log = published(media_id, last)
    return DocumentRecord(ArchivedLog(log, f"sha{media_id}", log.uploaded_at), first, last, DocumentStatus.LOADED)


def version(call: str, call_type: str = "MOTOR VEHICLE STOP", *, doc: int = 1, day: int = 21, time: str = "1200",
            result: str = "Verbal Warning", prefix: str | None = "Location/Address", location: str | None = "1 MAIN ST") -> EntryVersion:
    return EntryVersion(call, doc, 3, date(2026, 9, day), time, call_type, result, prefix, location, f"{call} {time} {call_type}")


def placement(call: str, kind: PlacementKind = PlacementKind.ADDRESS, *, address: str | None = "1 MAIN ST",
              streets: tuple[str, ...] = ("Main St",), wards: tuple[str, ...] = ("4",), version: str = VERSION) -> Placement:
    placed = kind in (PlacementKind.ADDRESS, PlacementKind.INTERSECTION)
    return Placement(call, LocationForm.ADDRESS, kind, address if placed else None, Point(-71.06, 42.46) if placed else None,
                     streets, wards if placed else (), (), "exact address", version)


def export(versions: list[EntryVersion], placements: list[Placement], states: list[EntryState] | None = None,
           documents: tuple[DocumentRecord, ...] = (document(1, date(2026, 9, 21), date(2026, 9, 27)),)):
    states = states if states is not None else [EntryState(v.call_number, v.document_id, EntryStatus.CURRENT) for v in versions]
    return build_export(list(documents), states, versions, placements, CATEGORIES, (), VERSION, AT)


@pytest.mark.parametrize(
    ("published_result", "shown"),
    [
        ("* Arrest 17 and Over Male", "Arrest"),
        ("* Arrest 17 and Over Female", "Arrest"),
        ("* Arrest Under 17 Male", "Arrest"),
        ("* Arrest 17", "Arrest"),
        ("* Arrest", "Arrest"),
        ("Citation/Warning", "Citation/Warning Issued"),
        ("* Report", "* Report taken"),
        ("Taken/Referred to Other", "Taken/Referred to Other Agency"),
        ("Summons Not", "Summons Not Served"),
        ("Restraining", "Restraining"),
        ("Restraining Order Not", "Restraining Order Not Served"),
        ("Transported to", "Transported to Hospital"),
        ("Unit", "Unit Clear"),
        ("*", "*"),
        ("False Alarm/Cancelled Alarm Co", "False Alarm/Cancelled Alarm Co"),
        ("Verbal Warning", "Verbal Warning"),
    ],
)
def test_arrests_collapse_and_a_cut_short_result_takes_its_one_full_form(published_result: str, shown: str) -> None:
    assert public_result(published_result) == shown


def test_only_listed_call_types_of_current_entries_leave() -> None:
    versions = [version("26-1"), version("26-2", "MEDICAL EMERGENCY"), version("26-3", "ACCIDENT HIT & RUN"), version("26-4")]
    states = [
        EntryState("26-1", 1, EntryStatus.CURRENT),
        EntryState("26-2", 1, EntryStatus.CURRENT),
        EntryState("26-3", 1, EntryStatus.CURRENT),
        EntryState("26-4", 1, EntryStatus.WITHDRAWN),
    ]
    out = export(versions, [placement(c) for c in ("26-1", "26-2", "26-3")], states)
    assert [(r.call, r.category) for r in out.records] == [("26-1", "stops"), ("26-3", "crashes")]


def test_an_unmapped_record_carries_no_address_point_or_ward() -> None:
    kinds = [PlacementKind.STREET_ONLY, PlacementKind.NONE, PlacementKind.UNPLACED, PlacementKind.OUTSIDE]
    versions = [version(f"26-{i}") for i in range(len(kinds))]
    # Even if a placement carried an address, an unmapped record must not.
    placements = [
        Placement(v.call_number, LocationForm.ADDRESS, k, "1 MAIN ST", Point(-71.06, 42.46), ("Main St",), ("4",), (), "x", VERSION)
        for v, k in zip(versions, kinds, strict=True)
    ]
    for r in export(versions, placements).records:
        assert (r.address, r.point, r.wards) == (None, None, ()), r.kind


def test_an_entry_outside_melrose_counts_toward_no_street() -> None:
    out = export([version("26-1"), version("26-2")], [placement("26-1", PlacementKind.OUTSIDE), placement("26-2", PlacementKind.UNPLACED)])
    assert [r.streets for r in out.records] == [(), ("Main St",)]


def test_records_are_ordered_and_documents_are_only_those_referenced() -> None:
    docs = (
        document(1, date(2026, 9, 14), date(2026, 9, 20)),
        document(2, date(2026, 9, 21), date(2026, 9, 27)),
        document(3, date(2026, 9, 28), date(2026, 10, 4)),
    )
    versions = [version("26-9", doc=3, day=28), version("26-2", doc=2, day=22, time="0900"), version("26-1", doc=2, day=22, time="0800")]
    out = export(versions, [placement(v.call_number) for v in versions], documents=docs)
    assert [r.call for r in out.records] == ["26-1", "26-2", "26-9"]
    assert [d.url for d in out.documents] == [docs[1].archived.log.source_url, docs[2].archived.log.source_url]
    assert [r.doc for r in out.records] == [0, 0, 1]


def test_vicinity_comes_from_the_published_label() -> None:
    out = export([version("26-1", prefix="Vicinity of"), version("26-2")], [placement("26-1"), placement("26-2")])
    assert [r.vicinity for r in out.records] == [True, False]


def test_a_shown_entry_without_a_placement_refuses_the_export() -> None:
    with pytest.raises(ExportRefused, match="no placement"):
        export([version("26-1"), version("26-2")], [placement("26-1")])


def test_placements_from_another_snapshot_refuse_the_export() -> None:
    with pytest.raises(ExportRefused, match="run rebuild"):
        export([version("26-1")], [placement("26-1", version="2026-01-01")])
