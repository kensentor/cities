"""What drives the application: one use case per command."""

from __future__ import annotations

from abc import abstractmethod
from datetime import date
from typing import Protocol

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
