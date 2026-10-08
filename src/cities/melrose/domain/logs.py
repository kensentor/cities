"""Published dispatch logs and what is known about each one."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class PublishedLog:
    """One PDF as the department's site lists it. Times are UTC."""

    media_id: int
    source_url: str
    title: str
    uploaded_at: datetime
    modified_at: datetime


@dataclass(frozen=True, slots=True)
class ArchivedLog:
    """A published log kept exactly as downloaded, identified by the SHA-256 of its bytes."""

    log: PublishedLog
    sha256: str
    fetched_at: datetime


class DocumentStatus(StrEnum):
    LOADED = "loaded"
    OUT_OF_SCOPE = "out_of_scope"
    QUARANTINED = "quarantined"


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    """An archived log after reading: the dates it covers and whether its entries were loaded."""

    archived: ArchivedLog
    first_date: date | None
    last_date: date | None
    status: DocumentStatus
    error: str | None = None

    @property
    def media_id(self) -> int:
        return self.archived.log.media_id

    def covers(self, day: date) -> bool:
        return self.first_date is not None and self.last_date is not None and self.first_date <= day <= self.last_date
