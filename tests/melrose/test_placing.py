"""Reading locations and the placement policy, against a fixed in-memory street plan."""

from __future__ import annotations

from datetime import date

import pytest

from cities.melrose.core.locations import match_street, parse_location
from cities.melrose.core.placing import place_all, summarise
from cities.melrose.domain.entries import EntryVersion
from cities.melrose.domain.places import LocationForm, NearEdge, PlacementKind, Point
from cities.melrose.domain.streets import display
from cities.melrose.stubs import InMemoryGazetteer

REFERENCE = frozenset({"FRANKLIN STREET", "GARDEN STREET", "WEST EMERSON STREET", "LYNN FELLS PARKWAY", "MAIN STREET", "MAIN STREET EXTENSION"})


@pytest.mark.parametrize(
    ("prefix", "text", "form", "parts"),
    [
        ("Location/Address", "752 FRANKLIN ST @ 8 GARDEN ST", LocationForm.INTERSECTION, [("752", "FRANKLIN ST"), ("8", "GARDEN ST")]),
        ("Location/Address", "[MEL 1243] POPE RESIDENCE - 744 LYNN FELLS PKWY", LocationForm.ADDRESS, [("744", "LYNN FELLS PKWY")]),
        ("Location/Address", "[MEL 14187] DUNKIN DONUTS, 348 MAIN ST (SOUSA, NELSON) - 348 MAIN ST", LocationForm.ADDRESS, [("348", "MAIN ST")]),
        ("Location/Address", "[MEL MEL13555] MELROSE WAKEFIELD HOSPITAL - 585 LEBANON ST", LocationForm.ADDRESS, [("585", "LEBANON ST")]),
        ("Location/Address", "42 WARREN ST Apt. #3", LocationForm.ADDRESS, [("42", "WARREN ST")]),
        ("Location/Address", "910 MAIN ST Apt", LocationForm.ADDRESS, [("910", "MAIN ST")]),
        ("Location/Address", "344 VINTON ST @ 700 FRANKLIN ST `", LocationForm.INTERSECTION, [("344", "VINTON ST"), ("700", "FRANKLIN ST")]),
        ("Vicinity of", "FRANKLIN ST", LocationForm.STREET, [(None, "FRANKLIN ST")]),
        ("Location/Address", "[MEL 13575] FULLER HSE ELDERLY", LocationForm.PLACE, [(None, "FULLER HSE ELDERLY")]),
        ("Location", "PETRONES", LocationForm.PLACE, []),
        ("Location/Address", "[MED] MEDFORD POLICE DEPT - 100 MAIN ST", LocationForm.OTHER_TOWN, []),
        (None, None, LocationForm.NONE, []),
    ],
)
def test_location_form_and_parts(prefix: str | None, text: str | None, form: LocationForm, parts: list[tuple[str | None, str]]) -> None:
    parsed = parse_location(prefix, text)
    assert parsed.form is form
    assert [(p.number, p.street) for p in parsed.parts] == parts


@pytest.mark.parametrize(
    ("printed", "matched"),
    [
        ("FRANKLIN ST", "FRANKLIN STREET"),
        ("LYNN FELLS PKWY", "LYNN FELLS PARKWAY"),
        ("W EMERSON ST", "WEST EMERSON STREET"),
        ("W EMERSON", "WEST EMERSON STREET"),  # no suffix: one reference street is this name plus one
        ("MAIN", "MAIN STREET"),  # MAIN STREET EXTENSION adds two words, so it is not a candidate
        ("PETRONES", None),
    ],
)
def test_street_names_match_the_reference(printed: str, matched: str | None) -> None:
    assert match_street(printed, REFERENCE) == matched


def test_a_name_without_a_suffix_that_could_be_two_streets_does_not_match() -> None:
    assert match_street("ELM", frozenset({"ELM STREET", "ELM PLACE"})) is None


def test_display_forms() -> None:
    assert display("LYNN FELLS PARKWAY") == "Lynn Fells Pkwy"
    assert display("WEST WYOMING AVENUE") == "West Wyoming Ave"


A, B, C = Point(-71.07, 42.46), Point(-71.06, 42.45), Point(-71.08, 42.47)


def gazetteer() -> InMemoryGazetteer:
    return InMemoryGazetteer(
        addresses={("LYNN FELLS PARKWAY", 744): A, ("MAIN STREET", 100): C},
        crossings={frozenset({"FRANKLIN STREET", "GARDEN STREET"}): B},
        ward_of={A: "4", B: "1", C: "7"},
        near_edges={
            A: (NearEdge(("2", "4"), "LYNN FELLS PARKWAY"),),
            B: (NearEdge(("1", "3"), None),),
        },
        outside={C: 300.0},
        extra_streets=frozenset({"WEST EMERSON STREET"}),
    )


def version(call_number: str, location: str | None, prefix: str | None = "Location/Address", call_type: str = "MOTOR VEHICLE STOP") -> EntryVersion:
    return EntryVersion(call_number, 1, 1, date(2026, 9, 21), "1200", call_type, "Verbal Warning", prefix if location else None, location, "")


def placed(*versions: EntryVersion):
    return {p.call_number: p for p in place_all(versions, gazetteer())}


def test_ac10_the_address_shown_is_rebuilt_without_the_place_name() -> None:
    p = placed(version("26-11115", "[MEL 1243] POPE RESIDENCE - 744 LYNN FELLS PKWY"))["26-11115"]
    assert (p.kind, p.address_display, p.point) == (PlacementKind.ADDRESS, "744 LYNN FELLS PKWY", A)
    assert "POPE" not in (p.address_display or "")


def test_a_street_on_a_ward_edge_counts_toward_both_wards() -> None:
    assert placed(version("26-1", "744 LYNN FELLS PKWY"))["26-1"].wards == ("2", "4")


def test_an_edge_no_street_runs_along_adds_no_ward() -> None:
    p = placed(version("26-1", "752 FRANKLIN ST @ 8 GARDEN ST"))["26-1"]
    assert p.wards == ("1",)
    assert p.near_edges == (NearEdge(("1", "3"), None),)


def test_ac8a_an_intersection_counts_toward_both_streets() -> None:
    p = placed(version("26-11102", "752 FRANKLIN ST @ 8 GARDEN ST"))["26-11102"]
    assert (p.kind, p.streets, p.address_display) == (PlacementKind.INTERSECTION, ("Franklin St", "Garden St"), "752 FRANKLIN ST @ 8 GARDEN ST")


def test_ac8_a_street_without_a_number_ranks_but_is_not_placed() -> None:
    p = placed(version("26-11097", "FRANKLIN ST"))["26-11097"]
    assert (p.kind, p.streets, p.point, p.wards) == (PlacementKind.STREET_ONLY, ("Franklin St",), None, ())


@pytest.mark.parametrize(
    ("location", "prefix", "kind", "method"),
    [
        ("[MED] MEDFORD POLICE DEPT - 100 MAIN ST", "Location/Address", PlacementKind.OUTSIDE, "another town (MED)"),
        ("100 MAIN ST", "Location/Address", PlacementKind.OUTSIDE, "300 m outside Melrose"),
        ("PETRONES", "Location", PlacementKind.UNPLACED, "named place without an address"),
        ("9 NOWHERE LN", "Location/Address", PlacementKind.UNPLACED, "unknown street: NOWHERE LN"),
        ("12 FRANKLIN ST", "Location/Address", PlacementKind.UNPLACED, "address not found"),
    ],
)
def test_what_cannot_be_placed_in_melrose_is_unmapped_with_its_reason(location: str, prefix: str, kind: PlacementKind, method: str) -> None:
    """Another town or a point beyond the city is "outside Melrose" (A9); anything else is "address not found"."""
    p = placed(version("26-1", location, prefix))["26-1"]
    assert (p.kind, p.method, p.point, p.address_display, p.wards) == (kind, method, None, None, ())


def test_an_unknown_street_is_never_displayed() -> None:
    p = placed(version("26-1", "9 NOWHERE LN"))["26-1"]
    assert p.streets == () and p.address_display is None


def test_ac2_rate_counts_stops_whose_location_gives_something_to_place() -> None:
    placements = place_all(
        [
            version("26-1", "744 LYNN FELLS PKWY"),
            version("26-2", "12 FRANKLIN ST"),  # address not found: counts against the rate
            version("26-3", "PETRONES", "Location"),  # named place: counts against the rate
            version("26-4", "FRANKLIN ST"),  # street only: not in the rate
            version("26-5", None),  # no location: not in the rate
            version("26-6", "744 LYNN FELLS PKWY", call_type="MEDICAL EMERGENCY"),  # not a stop
            version("26-7", "[MED] 100 MAIN ST"),  # another town: counts against the rate
        ],
        gazetteer(),
    )
    versions = [version("26-6", "x", call_type="MEDICAL EMERGENCY")] + [version(f"26-{n}", "x") for n in (1, 2, 3, 4, 5, 7)]
    summary = summarise(placements, versions)
    assert summary is not None
    assert (summary.stops_placed, summary.stops_placeable) == (1, 4)
    assert [call for call, _ in summary.unplaced_stops] == ["26-2", "26-3", "26-7"]


def test_boundary_rows_credit_only_the_street_that_runs_along_the_edge() -> None:
    edge_plan = InMemoryGazetteer(
        crossings={frozenset({"LYNN FELLS PARKWAY", "MAIN STREET"}): A},
        ward_of={A: "4"},
        near_edges={A: (NearEdge(("2", "4"), "LYNN FELLS PARKWAY"),)},
    )
    placements = place_all([version("26-1", "1 LYNN FELLS PKWY @ 2 MAIN ST")], edge_plan)
    summary = summarise(placements, [version("26-1", "x")])
    assert summary is not None
    rows = {(r.street, r.wards): (r.near, r.counted) for r in summary.boundary}
    assert rows == {("Lynn Fells Pkwy", ("2", "4")): (1, 1), ("Main St", ("2", "4")): (1, 0)}
