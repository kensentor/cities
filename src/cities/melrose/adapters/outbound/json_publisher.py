"""The map page's data as static files: entries.json (technical spec Appendix D) and wards.geojson.

Each file is written beside itself and renamed into place, so the page never reads half a file.
Output depends only on the export, so the same export always gives the same bytes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from cities.melrose.domain.public import PublicExport, PublicRecord, WardOutline
from cities.melrose.ports.outbound import MapPublisher, StorageFailed

ENTRIES = "entries.json"
WARDS = "wards.geojson"


class JsonMapPublisher(MapPublisher):
    __slots__ = ("_directory",)

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def publish(self, export: PublicExport) -> None:
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            self._write(ENTRIES, _entries(export))
            self._write(WARDS, _wards(export.wards))
        except OSError as exc:
            raise StorageFailed(f"map export {self._directory}: {exc}") from exc

    def _write(self, name: str, document: object) -> None:
        path = self._directory / name
        partial = path.with_name(path.name + ".tmp")
        partial.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        os.replace(partial, path)


def _entries(export: PublicExport) -> dict[str, object]:
    return {
        "generated_at": export.generated_at.isoformat(timespec="seconds"),
        "reference_version": export.reference_version,
        "categories": [{"key": c.key, "label": c.label} for c in export.categories],
        "documents": [
            {"url": d.url, "first_date": d.first_date.isoformat(), "last_date": d.last_date.isoformat()}
            for d in export.documents
        ],
        "records": [_record(r) for r in export.records],
    }


def _record(r: PublicRecord) -> dict[str, object]:
    return {
        "call": r.call,
        "date": r.date.isoformat(),
        "time": r.time,
        "category": r.category,
        "type": r.call_type,
        "result": r.result,
        "address": r.address,
        "vicinity": r.vicinity,
        "kind": r.kind.value,
        "lat": r.point.lat if r.point else None,
        "lon": r.point.lon if r.point else None,
        "streets": list(r.streets),
        "wards": list(r.wards),
        "doc": r.doc,
        "page": r.page,
    }


def _wards(outlines: tuple[WardOutline, ...]) -> dict[str, object]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"ward": o.ward, "label": [o.label.lon, o.label.lat]},
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [[[list(xy) for xy in ring] for ring in polygon] for polygon in o.polygons],
                },
            }
            for o in outlines
        ],
    }
