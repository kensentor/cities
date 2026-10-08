"""What the map page may show: the categories, and finished public records (design R4, R9, R10)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from cities.melrose.domain.places import PlacementKind, Point


@dataclass(frozen=True, slots=True)
class Category:
    """A group of call types the map shows as one layer and filter option (categories.toml)."""

    key: str  # e.g. "crashes"; the page's ward table and ranking read "stops" and "crashes"
    label: str  # e.g. "Crashes"
    call_types: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PublicDocument:
    """A log a record links to."""

    url: str
    first_date: date
    last_date: date


@dataclass(frozen=True, slots=True)
class PublicRecord:
    """One entry as the page may show it. No free text from a location reaches it (design R10)."""

    call: str
    date: date
    time: str  # HHMM as published
    category: str  # a Category key
    call_type: str  # as published
    result: str  # as published, except arrests become "Arrest" and a cut-short result its one full form
    address: str | None  # rebuilt from the house number and the reference street; None unless placed
    vicinity: bool  # published as "Vicinity of:"
    kind: PlacementKind
    point: Point | None  # set only when placed
    streets: tuple[str, ...]  # ranking keys, display form
    wards: tuple[str, ...]  # "1".."7"; empty unless placed
    doc: int  # index into PublicExport.documents
    page: int


@dataclass(frozen=True, slots=True)
class WardOutline:
    """A ward as the page draws it: polygons of rings of (lon, lat), and where its label goes."""

    ward: str
    polygons: tuple[tuple[tuple[tuple[float, float], ...], ...], ...]
    label: Point


@dataclass(frozen=True, slots=True)
class PublicExport:
    generated_at: datetime
    reference_version: str
    categories: tuple[Category, ...]
    documents: tuple[PublicDocument, ...]
    records: tuple[PublicRecord, ...]
    wards: tuple[WardOutline, ...]


@dataclass(frozen=True, slots=True)
class ExportSummary:
    reference_version: str
    counts: tuple[tuple[str, int], ...]  # (category label, records)

    @property
    def records(self) -> int:
        return sum(n for _, n in self.counts)
