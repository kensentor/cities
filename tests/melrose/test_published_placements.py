"""Placement over every published log in the archive, against the committed reference snapshot."""

from __future__ import annotations

import re

import pytest
from support import RAW, REPO

from cities.melrose.adapters.outbound.gazetteer import SnapshotGazetteer
from cities.melrose.adapters.outbound.log_archive import FileLogArchive
from cities.melrose.adapters.outbound.pdf_reader import PdfLogReader
from cities.melrose.core.rebuild import RebuildService
from cities.melrose.domain.places import Placement, PlacementKind
from cities.melrose.domain.reports import RunReport
from cities.melrose.domain.streets import ABBREVIATIONS
from cities.melrose.settings import BOUNDARY_RULE, COLLECT_SINCE, known_call_types
from cities.melrose.stubs import FakeClock, InMemoryEntryRepository

GAZETTEER = SnapshotGazetteer(REPO / "data" / "melrose" / "reference", BOUNDARY_RULE)


@pytest.fixture(scope="module")
def built() -> tuple[InMemoryEntryRepository, RunReport]:
    repository = InMemoryEntryRepository()
    report = RebuildService(
        reader=PdfLogReader(),
        archive=FileLogArchive(RAW),
        repository=repository,
        gazetteer=GAZETTEER,
        clock=FakeClock(),
        since=COLLECT_SINCE,
        known_call_types=known_call_types(),
    ).rebuild()
    return repository, report


def placement(built: tuple[InMemoryEntryRepository, RunReport], call_number: str) -> Placement:
    return built[0].placement_rows[call_number]


def test_ac2_at_least_95_percent_of_stops_with_an_address_or_intersection_are_placed(built) -> None:
    """Phase 2 gate. Named places and other towns count against the rate as well."""
    summary = built[1].placement
    assert summary is not None and summary.stop_rate is not None
    assert summary.stop_rate >= 0.95, summary.unplaced_stops


def test_every_current_entry_has_a_placement(built) -> None:
    repository = built[0]
    assert {s.call_number for s in repository.entries()} == set(repository.placement_rows)


def test_ac10_the_pope_entry_shows_only_its_address(built) -> None:
    assert placement(built, "26-11115").address_display == "744 LYNN FELLS PKWY"


def test_ac8_franklin_st_alone_ranks_but_is_not_on_the_map(built) -> None:
    p = placement(built, "26-11097")
    assert (p.kind, p.streets, p.point) == (PlacementKind.STREET_ONLY, ("Franklin St",), None)


def test_ac8a_franklin_at_garden_counts_toward_both_streets(built) -> None:
    p = placement(built, "26-11102")
    assert (p.kind, p.streets) == (PlacementKind.INTERSECTION, ("Franklin St", "Garden St"))


def test_another_towns_address_is_never_placed_in_melrose(built) -> None:
    p = placement(built, "26-10277")  # [WAK] UNION ST
    assert (p.kind, p.method, p.point) == (PlacementKind.OUTSIDE, "another town (WAK)", None)


def test_r10_every_word_shown_is_a_house_number_an_at_sign_or_part_of_a_reference_street(built) -> None:
    """No text from a location label or a household can reach the displayed address."""
    allowed = {word for name in GAZETTEER.street_names() for word in name.split()} | set(ABBREVIATIONS.values())
    for p in built[0].placement_rows.values():
        for word in (p.address_display or "").split():
            assert word == "@" or re.fullmatch(r"\d+[A-Z]?", word) or word in allowed, (p.call_number, p.address_display)


def test_a_point_counts_toward_one_to_three_wards(built) -> None:
    placed = [p for p in built[0].placement_rows.values() if p.point is not None]
    assert all(1 <= len(p.wards) <= 3 for p in placed)
    assert all(not p.wards for p in built[0].placement_rows.values() if p.point is None)
