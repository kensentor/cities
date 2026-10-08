"""`sample`: random placed entries with their published text, for checking by eye."""

from __future__ import annotations

import random
from collections.abc import Collection, Sequence

from cities.melrose.core import rules
from cities.melrose.domain.entries import EntryVersion
from cities.melrose.domain.places import Placement, PlacementKind
from cities.melrose.ports.inbound import SamplePlacements
from cities.melrose.ports.outbound import EntryRepository


class SampleService(SamplePlacements):
    __slots__ = ("_repository",)

    def __init__(self, *, repository: EntryRepository) -> None:
        self._repository = repository

    def sample(self, n: int, seed: int, call_types: Collection[str] = ()) -> Sequence[tuple[EntryVersion, Placement]]:
        current = {v.call_number: v for v in rules.current_versions(self._repository.entries(), self._repository.versions())}
        placed = [
            (current[p.call_number], p)
            for p in self._repository.placements()
            if p.kind in (PlacementKind.ADDRESS, PlacementKind.INTERSECTION)
            and p.call_number in current
            and (not call_types or current[p.call_number].call_type in call_types)
        ]
        placed.sort(key=lambda pair: pair[1].call_number)
        return random.Random(seed).sample(placed, min(n, len(placed)))
