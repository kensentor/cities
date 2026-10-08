"""What drives the application: one use case per command."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Collection, Sequence
from datetime import date
from typing import Protocol

from cities.melrose.domain.entries import EntryVersion
from cities.melrose.domain.places import Placement
from cities.melrose.domain.reference import ReferenceReport
from cities.melrose.domain.reports import RunReport


class CollectLogs(Protocol):
    """Download logs not seen before and load their entries."""

    __slots__ = ()

    @abstractmethod
    def collect(self, since: date | None = None) -> RunReport: ...


class RebuildFromArchive(Protocol):
    """Re-read every archived log and derive everything again."""

    __slots__ = ()

    @abstractmethod
    def rebuild(self) -> RunReport: ...


class FetchReference(Protocol):
    """Replace the snapshot of the reference layers."""

    __slots__ = ()

    @abstractmethod
    def fetch_reference(self) -> ReferenceReport: ...


class SamplePlacements(Protocol):
    """Random placed entries, for checking by eye that each lies where its log says (design AC3)."""

    __slots__ = ()

    @abstractmethod
    def sample(self, n: int, seed: int, call_types: Collection[str] = ()) -> Sequence[tuple[EntryVersion, Placement]]:
        """`call_types` limits the sample to those call types; empty means every placed entry."""
