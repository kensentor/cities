"""Gazetteer over the committed reference snapshot (data/melrose/reference), with shapely and pyproj.

Geometry is projected once to Massachusetts State Plane (EPSG:26986), so every distance is in
metres. Each choice between candidates has an explicit tie-break, so the same snapshot always
gives the same points.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from cities.melrose.domain.places import BoundaryThresholds, Located, NearEdge, Point, StreetRef, WardSurroundings
from cities.melrose.domain.public import WardOutline
from cities.melrose.ports.outbound import Gazetteer, StorageFailed

# Appendix C rule 3: the nearest number on the same side of the street, within this many numbers.
NEAREST_NUMBER_WINDOW = 40
# Appendix C rule 4: with no crossing, the midpoint of the two cited addresses if they are this close.
MIDPOINT_LIMIT_M = 150.0
METRES = "EPSG:26986"
_LEADING_NUMBER = re.compile(r"^\d+")


@dataclass(frozen=True, slots=True)
class _Address:
    number: int
    master_id: str
    point: shapely.Point


@dataclass(frozen=True, slots=True)
class _Snapshot:
    version: str
    streets: frozenset[str]
    addresses: dict[str, list[_Address]]  # by street, sorted by (number, master id)
    roads: dict[str, BaseGeometry]  # centrelines merged by street
    wards: dict[str, BaseGeometry]  # precincts merged by ward
    edges: list[tuple[tuple[str, str], BaseGeometry]]  # shared ward boundaries
    city: BaseGeometry
    to_degrees: Transformer
    to_metres: Transformer


class SnapshotGazetteer(Gazetteer):
    __slots__ = ("_directory", "_snapshot", "_thresholds")

    def __init__(self, directory: Path, thresholds: BoundaryThresholds) -> None:
        self._directory = directory
        self._thresholds = thresholds
        self._snapshot: _Snapshot | None = None

    def reference_version(self) -> str:
        return self._data().version

    def street_names(self) -> frozenset[str]:
        return self._data().streets

    def locate_address(self, street: StreetRef) -> Located:
        point, method = self._address_point(street)
        return Located(self._degrees(point) if point is not None else None, method)

    def locate_intersection(self, first: StreetRef, second: StreetRef) -> Located:
        data = self._data()
        cited = [p for p, _ in (self._address_point(first), self._address_point(second)) if p is not None]
        crossings = _crossings(data.roads.get(first.name), data.roads.get(second.name))
        if crossings and cited:
            best = min(crossings, key=lambda c: (sum(c.distance(p) for p in cited), c.x, c.y))
            nearer = min(best.distance(p) for p in cited)
            return Located(self._degrees(best), f"crossing, {nearer:.0f} m from the nearer cited address")
        if len(crossings) == 1:
            return Located(self._degrees(crossings[0]), "crossing; no cited address found")
        if crossings:
            return Located(None, f"{len(crossings)} crossings and no cited address to choose between them")
        if len(cited) == 2 and (apart := cited[0].distance(cited[1])) <= MIDPOINT_LIMIT_M:
            middle = shapely.Point((cited[0].x + cited[1].x) / 2, (cited[0].y + cited[1].y) / 2)
            return Located(self._degrees(middle), f"midpoint of the cited addresses, {apart:.0f} m apart")
        return Located(None, "intersection not found")

    def distance_outside_city_m(self, point: Point) -> float:
        data = self._data()
        return float(data.city.distance(self._metres(point)))

    def wards_around(self, point: Point, streets: Sequence[str]) -> WardSurroundings:
        data, rule = self._data(), self._thresholds
        here = self._metres(point)
        containing = next((w for w in sorted(data.wards, key=int) if data.wards[w].covers(here)), None)
        if containing is None:
            containing = min(data.wards, key=lambda w: (data.wards[w].distance(here), int(w)))
        near: list[NearEdge] = []
        window = here.buffer(rule.window_m)
        for pair, edge in data.edges:
            if edge.distance(here) > rule.edge_m:
                continue
            band = edge.buffer(rule.along_m)
            along = None
            for name in sorted(streets):
                road = data.roads.get(name)
                local = road.intersection(window) if road is not None else None
                if local is not None and local.length > 0 and local.intersection(band).length / local.length >= rule.share:
                    along = name
                    break
            near.append(NearEdge(pair, along))
        return WardSurroundings(containing, tuple(near))

    def ward_outlines(self) -> Sequence[WardOutline]:
        data = self._data()
        outlines = []
        for ward in sorted(data.wards, key=int):
            shape_m = data.wards[ward]
            polygons = getattr(shape_m, "geoms", [shape_m])
            rings = tuple(
                tuple(self._ring(ring) for ring in (polygon.exterior, *polygon.interiors)) for polygon in polygons
            )
            # A point inside the ward even when its shape is concave, unlike the centre of its bounds.
            inside = shape_m.representative_point()
            outlines.append(WardOutline(ward, rings, self._degrees(inside)))
        return outlines

    def _ring(self, ring: BaseGeometry) -> tuple[tuple[float, float], ...]:
        xs, ys = np.asarray(ring.coords).T
        lons, lats = self._data().to_degrees.transform(xs, ys)
        return tuple((round(float(lon), 6), round(float(lat), 6)) for lon, lat in zip(lons, lats, strict=True))

    def _address_point(self, street: StreetRef) -> tuple[shapely.Point | None, str]:
        number = street.number
        if number is None:
            return None, "no house number"
        candidates = self._data().addresses.get(street.name, [])
        if exact := [a for a in candidates if a.number == number]:
            return exact[0].point, "exact address"
        same_side = [a for a in candidates if a.number % 2 == number % 2 and abs(a.number - number) <= NEAREST_NUMBER_WINDOW]
        if same_side:
            nearest = min(same_side, key=lambda a: (abs(a.number - number), a.number, a.master_id))
            return nearest.point, f"nearest number ({nearest.number})"
        return None, "address not found"

    def _degrees(self, point: shapely.Point) -> Point:
        lon, lat = self._data().to_degrees.transform(point.x, point.y)
        return Point(round(lon, 6), round(lat, 6))

    def _metres(self, point: Point) -> shapely.Point:
        x, y = self._data().to_metres.transform(point.lon, point.lat)
        return shapely.Point(x, y)

    def _data(self) -> _Snapshot:
        if self._snapshot is None:
            try:
                self._snapshot = _load(self._directory)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise StorageFailed(f"reference snapshot {self._directory}: {exc}") from exc
        return self._snapshot


def _load(directory: Path) -> _Snapshot:
    manifest = json.loads((directory / "manifest.json").read_text())
    to_metres = Transformer.from_crs("EPSG:4326", METRES, always_xy=True)
    project = _projector(to_metres)

    addresses: dict[str, list[_Address]] = defaultdict(list)
    for feature in _features(directory / "address_points.geojson"):
        props = feature["properties"]
        street, number = (props.get("STREET_NAME") or "").strip(), _LEADING_NUMBER.match(props.get("FULL_NUMBER_STANDARDIZED") or "")
        if street and number and feature.get("geometry"):
            lon, lat = feature["geometry"]["coordinates"][:2]
            point = shapely.Point(*to_metres.transform(lon, lat))
            addresses[street].append(_Address(int(number.group()), str(props.get("MASTER_ADDRESS_ID")), point))
    for found in addresses.values():
        found.sort(key=lambda a: (a.number, a.master_id))

    segments: dict[str, list[BaseGeometry]] = defaultdict(list)
    for feature in _features(directory / "roads.geojson"):
        street = (feature["properties"].get("STREET_NAME") or "").strip()
        if street and feature.get("geometry"):
            segments[street].append(project(shape(feature["geometry"])))
    roads = {street: unary_union(parts) for street, parts in segments.items()}

    precincts: dict[str, list[BaseGeometry]] = defaultdict(list)
    for feature in _features(directory / "wards.geojson"):
        precincts[str(int(feature["properties"]["WARD"]))].append(project(shape(feature["geometry"])))
    wards = {ward: unary_union(parts) for ward, parts in precincts.items()}
    edges = []
    for a, b in combinations(sorted(wards, key=int), 2):
        shared = wards[a].boundary.intersection(wards[b].boundary)
        if shared.length > 0:
            edges.append(((a, b), shared))

    return _Snapshot(
        version=str(manifest["reference_version"]),
        streets=frozenset(addresses) | frozenset(roads),
        addresses=dict(addresses),
        roads=roads,
        wards=wards,
        edges=edges,
        city=unary_union(list(wards.values())),
        to_degrees=Transformer.from_crs(METRES, "EPSG:4326", always_xy=True),
        to_metres=to_metres,
    )


def _features(path: Path) -> list[dict]:
    return json.loads(path.read_text())["features"]


def _projector(transformer: Transformer) -> Callable[[BaseGeometry], BaseGeometry]:
    def to_xy(coordinates: np.ndarray) -> np.ndarray:
        x, y = transformer.transform(coordinates[:, 0], coordinates[:, 1])
        return np.column_stack([x, y])

    return lambda geometry: shapely.transform(geometry, to_xy)


def _crossings(first: BaseGeometry | None, second: BaseGeometry | None) -> list[shapely.Point]:
    """Where two streets' centrelines meet, each once, in a fixed order. A shared stretch counts at its middle."""
    if first is None or second is None:
        return []
    shared = first.intersection(second)
    points: dict[tuple[float, float], shapely.Point] = {}
    for part in getattr(shared, "geoms", [shared]):
        if part.is_empty:
            continue
        point = part if isinstance(part, shapely.Point) else part.interpolate(0.5, normalized=True)
        points.setdefault((round(point.x, 1), round(point.y, 1)), point)
    return [points[k] for k in sorted(points)]
