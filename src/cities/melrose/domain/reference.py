"""Reference layers: the outside geography entries are placed against."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ReferenceLayer:
    """One feature layer and the query that selects Melrose from it."""

    name: str  # snapshot file stem, e.g. "address_points"
    url: str  # the layer's query endpoint parent, ending in /FeatureServer/<n>
    where: str
    out_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LayerSnapshot:
    layer: ReferenceLayer
    expected_count: int  # what the server reported before the download
    features: tuple[Mapping[str, object], ...]  # GeoJSON Feature objects, WGS84


@dataclass(frozen=True, slots=True)
class ReferenceReport:
    fetched_at: datetime
    reference_version: str  # the date of the snapshot, ISO format
    counts: tuple[tuple[str, int], ...]  # (layer name, features written)
