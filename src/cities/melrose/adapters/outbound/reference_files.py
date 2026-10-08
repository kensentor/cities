"""ReferenceStore as committed GeoJSON files, one per layer, plus manifest.json describing the snapshot."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from cities.melrose.domain.reference import LayerSnapshot
from cities.melrose.ports.outbound import ReferenceStore, StorageFailed


class GeoJsonReferenceStore(ReferenceStore):
    __slots__ = ("_directory",)

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def replace(self, snapshots: Sequence[LayerSnapshot], fetched_at: datetime) -> None:
        """Write every layer to a temporary file first, then move them all into place, manifest last."""
        manifest = {
            "reference_version": fetched_at.date().isoformat(),
            "fetched_at": fetched_at.isoformat(),
            "layers": [
                {
                    "name": s.layer.name,
                    "url": s.layer.url,
                    "where": s.layer.where,
                    "out_fields": list(s.layer.out_fields),
                    "feature_count": len(s.features),
                }
                for s in snapshots
            ],
        }
        staged: list[tuple[Path, Path]] = []
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            for snapshot in snapshots:
                collection = {"type": "FeatureCollection", "features": list(snapshot.features)}
                staged.append(self._stage(f"{snapshot.layer.name}.geojson", json.dumps(collection, separators=(",", ":"))))
            staged.append(self._stage("manifest.json", json.dumps(manifest, indent=2) + "\n"))
            for temporary, final in staged:
                os.replace(temporary, final)
        except OSError as exc:
            for temporary, _ in staged:
                temporary.unlink(missing_ok=True)
            raise StorageFailed(f"reference {self._directory}: {exc}") from exc

    def _stage(self, name: str, text: str) -> tuple[Path, Path]:
        final = self._directory / name
        temporary = final.with_name(name + ".tmp")
        temporary.write_text(text + ("" if text.endswith("\n") else "\n"))
        return temporary, final
