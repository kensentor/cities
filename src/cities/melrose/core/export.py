"""`export`: write the map page's data again from what is stored, without collecting."""

from __future__ import annotations

from collections.abc import Sequence

from cities.melrose.core.publishing import publish_map
from cities.melrose.domain.public import Category, ExportSummary
from cities.melrose.ports.inbound import ExportMap
from cities.melrose.ports.outbound import Clock, EntryRepository, Gazetteer, MapPublisher


class ExportService(ExportMap):
    __slots__ = ("_categories", "_clock", "_gazetteer", "_publisher", "_repository")

    def __init__(
        self,
        *,
        repository: EntryRepository,
        gazetteer: Gazetteer,
        publisher: MapPublisher,
        clock: Clock,
        categories: Sequence[Category],
    ) -> None:
        self._repository = repository
        self._gazetteer = gazetteer
        self._publisher = publisher
        self._clock = clock
        self._categories = categories

    def export(self) -> ExportSummary:
        return publish_map(self._repository, self._gazetteer, self._publisher, self._categories, self._clock)
