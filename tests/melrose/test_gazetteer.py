"""The gazetteer adapter on the committed reference snapshot."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from support import REPO

from cities.melrose.adapters.outbound.gazetteer import SnapshotGazetteer
from cities.melrose.domain.places import StreetRef
from cities.melrose.ports.outbound import StorageFailed
from cities.melrose.settings import BOUNDARY_RULE

REFERENCE = REPO / "data" / "melrose" / "reference"


@pytest.fixture(scope="module")
def gazetteer() -> SnapshotGazetteer:
    return SnapshotGazetteer(REFERENCE, BOUNDARY_RULE)


def test_the_street_list_joins_both_layers(gazetteer: SnapshotGazetteer) -> None:
    names = gazetteer.street_names()
    assert "NEWBURYPORT TURNPIKE" in names  # in the address points only
    assert "LYNN FELLS PARKWAY" in names


def test_an_exact_address(gazetteer: SnapshotGazetteer) -> None:
    located = gazetteer.locate_address(StreetRef("LYNN FELLS PARKWAY", 744))
    assert located.method == "exact address" and located.point is not None
    assert gazetteer.distance_outside_city_m(located.point) == 0


def test_rule_3_the_nearest_number_on_the_same_side(gazetteer: SnapshotGazetteer) -> None:
    """12 Main St has no address point; 8 is the nearest even number."""
    assert gazetteer.locate_address(StreetRef("MAIN STREET", 12)).method == "nearest number (8)"


def test_rule_3_nothing_within_40_numbers_is_not_found(gazetteer: SnapshotGazetteer) -> None:
    assert gazetteer.locate_address(StreetRef("LARRABEE PLACE", 2)).point is None


def test_rule_4_the_crossing_nearest_the_cited_addresses(gazetteer: SnapshotGazetteer) -> None:
    located = gazetteer.locate_intersection(StreetRef("FRANKLIN STREET", 752), StreetRef("GARDEN STREET", 8))
    assert located.method.startswith("crossing, ")


def test_rule_4_without_a_crossing_the_midpoint_of_close_cited_addresses(gazetteer: SnapshotGazetteer) -> None:
    located = gazetteer.locate_intersection(StreetRef("MAIN STREET", 1169), StreetRef("HAWLEY ROAD", 15))
    assert located.method.startswith("midpoint of the cited addresses")


def test_rule_5_a_corner_of_three_wards_is_near_three_edges(gazetteer: SnapshotGazetteer) -> None:
    point = gazetteer.locate_intersection(StreetRef("LYNN FELLS PARKWAY", 470), StreetRef("MELROSE STREET", 27)).point
    assert point is not None
    around = gazetteer.wards_around(point, ["LYNN FELLS PARKWAY", "MELROSE STREET"])
    assert {e.wards for e in around.near_edges if e.along} == {("1", "2"), ("1", "4"), ("2", "4")}


def test_the_same_question_gets_the_same_answer(gazetteer: SnapshotGazetteer) -> None:
    again = SnapshotGazetteer(REFERENCE, BOUNDARY_RULE)
    question = (StreetRef("LEBANON STREET", 547), StreetRef("UPHAM STREET", 11))
    assert gazetteer.locate_intersection(*question) == again.locate_intersection(*question)


def test_a_missing_snapshot_fails_as_storage(tmp_path: Path) -> None:
    shutil.copy(REFERENCE / "manifest.json", tmp_path / "manifest.json")
    with pytest.raises(StorageFailed, match="reference snapshot"):
        SnapshotGazetteer(tmp_path, BOUNDARY_RULE).reference_version()
