"""LogArchive as files: each PDF under its SHA-256, and one JSON sidecar per media id.

The directory is committed. The sidecars carry what `rebuild` needs that the PDF does not: which
upload it was, where it was published and when, so a fresh clone or a hand-downloaded PDF can be
rebuilt without the database.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from cities.melrose.domain.logs import ArchivedLog, PublishedLog
from cities.melrose.ports.outbound import LogArchive, StorageFailed


class FileLogArchive(LogArchive):
    __slots__ = ("_directory",)

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def keep(self, log: PublishedLog, pdf: bytes, fetched_at: datetime) -> ArchivedLog:
        archived = ArchivedLog(log, hashlib.sha256(pdf).hexdigest(), fetched_at)
        try:
            self._directory.mkdir(parents=True, exist_ok=True)
            pdf_path = self._directory / f"{archived.sha256}.pdf"
            if not pdf_path.exists():
                _write_atomically(pdf_path, pdf)
            sidecar = json.dumps(_to_json(archived), indent=2, ensure_ascii=False) + "\n"
            _write_atomically(self._directory / f"{log.media_id}.json", sidecar.encode())
        except OSError as exc:
            raise StorageFailed(f"archive {self._directory}: {exc}") from exc
        return archived

    def archived(self) -> Sequence[ArchivedLog]:
        try:
            return [_from_json(json.loads(p.read_text())) for p in sorted(self._directory.glob("*.json"))]
        except FileNotFoundError:
            return []
        except (OSError, ValueError, KeyError) as exc:
            raise StorageFailed(f"archive {self._directory}: {exc}") from exc

    def load(self, archived: ArchivedLog) -> bytes:
        try:
            pdf = (self._directory / f"{archived.sha256}.pdf").read_bytes()
        except OSError as exc:
            raise StorageFailed(f"archive {self._directory}: {exc}") from exc
        if hashlib.sha256(pdf).hexdigest() != archived.sha256:
            raise StorageFailed(f"{archived.sha256}.pdf no longer matches its SHA-256")
        return pdf


def _write_atomically(path: Path, data: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def _to_json(archived: ArchivedLog) -> dict[str, object]:
    log = archived.log
    return {
        "media_id": log.media_id,
        "source_url": log.source_url,
        "title": log.title,
        "uploaded_at": log.uploaded_at.isoformat(),
        "modified_at": log.modified_at.isoformat(),
        "sha256": archived.sha256,
        "fetched_at": archived.fetched_at.isoformat(),
    }


def _from_json(data: dict[str, object]) -> ArchivedLog:
    log = PublishedLog(
        media_id=int(str(data["media_id"])),
        source_url=str(data["source_url"]),
        title=str(data["title"]),
        uploaded_at=datetime.fromisoformat(str(data["uploaded_at"])),
        modified_at=datetime.fromisoformat(str(data["modified_at"])),
    )
    return ArchivedLog(log, str(data["sha256"]), datetime.fromisoformat(str(data["fetched_at"])))
