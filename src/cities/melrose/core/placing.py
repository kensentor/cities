"""Where each current entry goes on the map, and what it counts toward (design R3, R5, R7, R8, R10)."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence

from cities.melrose.core.locations import ParsedLocation, Part, match_street, parse_location
from cities.melrose.domain.entries import EntryVersion
from cities.melrose.domain.places import LocationForm, NearEdge, Placement, PlacementKind, Point, StreetRef
from cities.melrose.domain.reports import BoundaryRow, PlacementSummary
from cities.melrose.domain.streets import abbreviate, display
from cities.melrose.domain.vocabulary import STOP_CALL_TYPE
from cities.melrose.ports.outbound import Gazetteer

# A point farther than this outside the city lines is not in Melrose (design R3).
OUTSIDE_CITY_LIMIT_M = 25.0


def place_all(versions: Iterable[EntryVersion], gazetteer: Gazetteer) -> list[Placement]:
    version = gazetteer.reference_version()
    streets = gazetteer.street_names()
    return [place(v, gazetteer, streets, version) for v in sorted(versions, key=lambda v: v.call_number)]


def place(v: EntryVersion, gazetteer: Gazetteer, reference_streets: frozenset[str], reference_version: str) -> Placement:
    parsed = parse_location(v.location_prefix, v.location_raw)

    def result(
        kind: PlacementKind,
        method: str,
        *,
        streets: tuple[str, ...] = (),
        address_display: str | None = None,
        point: Point | None = None,
        wards: tuple[str, ...] = (),
        near_edges: tuple[NearEdge, ...] = (),
    ) -> Placement:
        return Placement(
            call_number=v.call_number,
            form=parsed.form,
            kind=kind,
            address_display=address_display,
            point=point,
            streets=streets,
            wards=wards,
            near_edges=near_edges,
            method=method,
            reference_version=reference_version,
        )

    match parsed.form:
        case LocationForm.NONE:
            return result(PlacementKind.NONE, "no location")
        case LocationForm.PLACE:
            return result(PlacementKind.UNPLACED, "named place without an address")
        case LocationForm.OTHER_TOWN:
            return result(PlacementKind.OUTSIDE, f"another town ({parsed.town})")
    matched = [match_street(p.street, reference_streets) for p in parsed.parts]
    unknown = [p.street for p, m in zip(parsed.parts, matched, strict=True) if m is None]
    if unknown:
        return result(PlacementKind.UNPLACED, "unknown street: " + "; ".join(unknown))
    names = [m for m in matched if m is not None]
    ranking = tuple(dict.fromkeys(display(n) for n in names))
    if parsed.form is LocationForm.STREET:
        return result(PlacementKind.STREET_ONLY, "street only", streets=ranking)

    refs = [StreetRef(n, p.house_number) for p, n in zip(parsed.parts, names, strict=True)]
    if parsed.form is LocationForm.ADDRESS:
        located, kind = gazetteer.locate_address(refs[0]), PlacementKind.ADDRESS
    else:
        located, kind = gazetteer.locate_intersection(refs[0], refs[1]), PlacementKind.INTERSECTION
    if located.point is None:
        return result(PlacementKind.UNPLACED, located.method, streets=ranking)
    outside = gazetteer.distance_outside_city_m(located.point)
    if outside > OUTSIDE_CITY_LIMIT_M:
        return result(PlacementKind.OUTSIDE, f"{outside:.0f} m outside Melrose", streets=ranking)
    surroundings = gazetteer.wards_around(located.point, names)
    wards = {w for edge in surroundings.near_edges if edge.along is not None for w in edge.wards}
    if surroundings.ward is not None:
        wards.add(surroundings.ward)
    return result(
        kind,
        located.method,
        address_display=_address_display(parsed, names),
        point=located.point,
        streets=ranking,
        wards=tuple(sorted(wards, key=int)),
        near_edges=surroundings.near_edges,
    )


def _address_display(parsed: ParsedLocation, names: Sequence[str]) -> str:
    """Rebuilt from the printed house number and the matched reference name only (design R10)."""
    return " @ ".join(_side(p, n) for p, n in zip(parsed.parts, names, strict=True))


def _side(part: Part, name: str) -> str:
    return f"{part.number} {abbreviate(name)}" if part.number else abbreviate(name)


def summarise(placements: Sequence[Placement], versions: Sequence[EntryVersion]) -> PlacementSummary | None:
    if not placements:
        return None
    call_types = {v.call_number: v.call_type for v in versions}
    stops = [p for p in placements if call_types.get(p.call_number) == STOP_CALL_TYPE and p.form.placeable]
    placed = [p for p in stops if p.kind in (PlacementKind.ADDRESS, PlacementKind.INTERSECTION)]
    unknown = Counter(
        street for p in placements if p.method.startswith("unknown street: ") for street in p.method.removeprefix("unknown street: ").split("; ")
    )
    return PlacementSummary(
        reference_version=placements[0].reference_version,
        counts=tuple(sorted(Counter(p.kind.value for p in placements).items())),
        stops_placeable=len(stops),
        stops_placed=len(placed),
        unplaced_stops=tuple((p.call_number, p.method) for p in stops if p not in placed),
        unknown_streets=tuple(sorted(unknown.items(), key=lambda kv: (-kv[1], kv[0]))),
        boundary=_boundary_rows(placements),
    )


def _boundary_rows(placements: Sequence[Placement]) -> tuple[BoundaryRow, ...]:
    """For each street and ward pair: placed entries within reach of that edge, and how many counted toward both wards."""
    near: dict[tuple[str, tuple[str, str]], int] = defaultdict(int)
    counted: dict[tuple[str, tuple[str, str]], int] = defaultdict(int)
    for p in placements:
        for edge in p.near_edges:
            for street in p.streets:
                near[(street, edge.wards)] += 1
            if edge.along is not None:
                counted[(display(edge.along), edge.wards)] += 1
    keys = sorted(set(counted) | {k for k, n in near.items() if n}, key=lambda k: (k[1], k[0]))
    return tuple(BoundaryRow(street, wards, near[(street, wards)], counted[(street, wards)]) for street, wards in keys)

