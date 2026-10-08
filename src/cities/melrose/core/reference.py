"""`fetch-reference`: replace the reference snapshot, or keep the old one if any layer comes back short."""

from __future__ import annotations

from collections.abc import Sequence

from cities.melrose.domain.reference import LayerSnapshot, ReferenceLayer, ReferenceReport
from cities.melrose.ports.inbound import FetchReference
from cities.melrose.ports.outbound import Clock, ReferenceSource, ReferenceSourceUnavailable, ReferenceStore


class FetchReferenceService(FetchReference):
    __slots__ = ("_clock", "_layers", "_source", "_store")

    def __init__(
        self, *, source: ReferenceSource, store: ReferenceStore, clock: Clock, layers: Sequence[ReferenceLayer]
    ) -> None:
        self._source = source
        self._store = store
        self._clock = clock
        self._layers = layers

    def fetch_reference(self) -> ReferenceReport:
        snapshots: list[LayerSnapshot] = []
        for layer in self._layers:
            expected = self._source.count(layer)
            features = tuple(self._source.features(layer))
            if len(features) != expected:
                raise ReferenceSourceUnavailable(
                    f"{layer.name}: the server reports {expected} features but {len(features)} were downloaded"
                )
            snapshots.append(LayerSnapshot(layer, expected, features))
        fetched_at = self._clock.now()
        self._store.replace(snapshots, fetched_at)
        return ReferenceReport(
            fetched_at=fetched_at,
            reference_version=fetched_at.date().isoformat(),
            counts=tuple((s.layer.name, len(s.features)) for s in snapshots),
        )
