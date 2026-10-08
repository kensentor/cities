"""Where an entry is on the map, and what it counts toward."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class Point:
    """WGS84 degrees."""

    lon: float
    lat: float


class LocationForm(StrEnum):
    """What the location text says, decided before any lookup."""

    ADDRESS = "address"  # a house number and a street
    INTERSECTION = "intersection"  # two streets joined by "@"
    STREET = "street"  # a street with no number
    PLACE = "place"  # a named place with no address
    OTHER_TOWN = "other_town"  # labelled with another town's code, e.g. "[MED]"
    NONE = "none"  # no location printed

    @property
    def placeable(self) -> bool:
        """Forms the department gave enough to put on a map, whether or not it could be found."""
        return self not in (LocationForm.STREET, LocationForm.NONE)


class PlacementKind(StrEnum):
    """What the map does with the entry (technical spec, Data model). The last four are the unmapped
    groups of design R8."""

    ADDRESS = "address"
    INTERSECTION = "intersection"
    STREET_ONLY = "street_only"
    NONE = "none"
    UNPLACED = "unplaced"  # "address not found": a location in Melrose that could not be put on the map
    OUTSIDE = "outside"  # "outside Melrose": another town's label, or a point beyond the city lines (A9)


@dataclass(frozen=True, slots=True)
class StreetRef:
    """A street as the reference names it, spelled out, with the house number the log cited on it."""

    name: str  # e.g. "LYNN FELLS PARKWAY"
    number: int | None


@dataclass(frozen=True, slots=True)
class Located:
    """A gazetteer's answer: the point, or None, and how it was found or why not."""

    point: Point | None
    method: str


@dataclass(frozen=True, slots=True)
class NearEdge:
    """A shared ward edge near a placed point, and which of the entry's streets runs along it, if any."""

    wards: tuple[str, str]
    along: str | None  # a reference street name, spelled out


@dataclass(frozen=True, slots=True)
class WardSurroundings:
    ward: str | None  # the ward containing the point, or the nearest one
    near_edges: tuple[NearEdge, ...]


@dataclass(frozen=True, slots=True)
class BoundaryThresholds:
    """Technical spec Appendix C rule 5. A shared ward edge within `edge_m` of the point counts when
    at least `share` of the street's centreline within `window_m` of the point lies within
    `along_m` of the edge. These are the spec's own settings, checked at the phase 2 gate (Q2).
    """

    edge_m: float
    window_m: float
    along_m: float
    share: float


@dataclass(frozen=True, slots=True)
class Placement:
    call_number: str
    form: LocationForm
    kind: PlacementKind
    address_display: str | None  # rebuilt from the number and the reference street name, never cut from the text
    point: Point | None
    streets: tuple[str, ...]  # ranking keys in display form, e.g. "Franklin St"
    wards: tuple[str, ...]  # "1".."7", empty unless placed
    near_edges: tuple[NearEdge, ...]
    method: str
    reference_version: str
