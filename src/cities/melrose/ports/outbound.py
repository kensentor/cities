"""What the application drives. Each port is named for what the core needs, never for a technology.

Implementers inherit their port by name, so the type checker verifies their signatures, and every
method is abstract, so a drifted implementer fails at construction (tests/melrose/test_ports.py).
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Protocol

from cities.melrose.domain.entries import EntryState, EntryVersion, ReadLog
from cities.melrose.domain.logs import ArchivedLog, DocumentRecord, PublishedLog
from cities.melrose.domain.places import Located, Placement, Point, StreetRef, WardSurroundings
from cities.melrose.domain.reference import LayerSnapshot, ReferenceLayer
from cities.melrose.domain.reports import RunReport


class LogSourceUnavailable(Exception):
    """The site listing or serving the logs could not be reached, or refused the request."""


class LogUnreadable(Exception):
    """A downloaded log is not a PDF the reader can open."""


class StorageFailed(Exception):
    """A local store (the database or the archive directory) could not be read or written."""


class ReferenceSourceUnavailable(Exception):
    """A reference layer could not be fetched completely."""


class LogSource(Protocol):
    """Find and fetch the logs the department publishes."""

    __slots__ = ()

    @abstractmethod
    def list_logs(self, uploaded_since: date) -> Sequence[PublishedLog]: ...

    @abstractmethod
    def fetch(self, log: PublishedLog) -> bytes: ...


class LogReader(Protocol):
    """Read the entries printed in one log."""

    __slots__ = ()

    @abstractmethod
    def read(self, pdf: bytes) -> ReadLog: ...


class LogArchive(Protocol):
    """Keep each published log exactly as downloaded, with what is known about it."""

    __slots__ = ()

    @abstractmethod
    def keep(self, log: PublishedLog, pdf: bytes, fetched_at: datetime) -> ArchivedLog: ...

    @abstractmethod
    def archived(self) -> Sequence[ArchivedLog]: ...

    @abstractmethod
    def load(self, archived: ArchivedLog) -> bytes: ...


class EntryRepository(Protocol):
    """Keep documents, entry versions, which version is current, and runs."""

    __slots__ = ()

    @abstractmethod
    def document_ids(self) -> frozenset[int]: ...

    @abstractmethod
    def documents(self) -> Sequence[DocumentRecord]: ...

    @abstractmethod
    def versions(self) -> Sequence[EntryVersion]: ...

    @abstractmethod
    def entries(self) -> Sequence[EntryState]: ...

    @abstractmethod
    def save_document(self, record: DocumentRecord, versions: Sequence[EntryVersion]) -> None:
        """Record a document and replace its versions, together."""

    @abstractmethod
    def replace_entries(self, states: Sequence[EntryState]) -> None: ...

    @abstractmethod
    def placements(self) -> Sequence[Placement]: ...

    @abstractmethod
    def replace_placements(self, placements: Sequence[Placement]) -> None: ...

    @abstractmethod
    def clear_versions(self) -> None:
        """Remove every version, entry and placement, keeping documents, before a rebuild."""

    @abstractmethod
    def record_run(self, report: RunReport) -> None: ...


class ReferenceSource(Protocol):
    """Fetch reference layers."""

    __slots__ = ()

    @abstractmethod
    def count(self, layer: ReferenceLayer) -> int: ...

    @abstractmethod
    def features(self, layer: ReferenceLayer) -> Sequence[Mapping[str, object]]: ...


class ReferenceStore(Protocol):
    """Keep the snapshot of every reference layer, replacing the previous one as a whole."""

    __slots__ = ()

    @abstractmethod
    def replace(self, snapshots: Sequence[LayerSnapshot], fetched_at: datetime) -> None: ...


class Gazetteer(Protocol):
    """Locate addresses and street crossings in Melrose, and describe the wards around a point.

    Street names are the reference's own, spelled out ("FRANKLIN STREET"). Locating applies
    Appendix C rules 3 and 4; describing the wards applies the geometry of rule 5. What the entry
    then counts toward is the core's decision.
    """

    __slots__ = ()

    @abstractmethod
    def reference_version(self) -> str:
        """The snapshot's version. Loads the snapshot, so a missing one fails before anything is written."""

    @abstractmethod
    def street_names(self) -> frozenset[str]: ...

    @abstractmethod
    def locate_address(self, street: StreetRef) -> Located: ...

    @abstractmethod
    def locate_intersection(self, first: StreetRef, second: StreetRef) -> Located: ...

    @abstractmethod
    def distance_outside_city_m(self, point: Point) -> float:
        """0 inside Melrose; otherwise metres to its boundary."""

    @abstractmethod
    def wards_around(self, point: Point, streets: Sequence[str]) -> WardSurroundings: ...


class Clock(Protocol):
    __slots__ = ()

    @abstractmethod
    def now(self) -> datetime:
        """The current time, timezone-aware UTC."""
