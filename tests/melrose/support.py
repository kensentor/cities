"""Shared test helpers. Real logs are read from the committed archive in data/melrose/raw by media id."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from cities.melrose.adapters.outbound.log_archive import FileLogArchive
from cities.melrose.domain.entries import RawEntry, ReadLog, Segment, SegmentKind
from cities.melrose.domain.logs import ArchivedLog, PublishedLog

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "data" / "melrose" / "raw"
FIXTURES = Path(__file__).parent / "fixtures"

# The logs uploaded from Jul 20, 2026 to Oct 1, 2026, by media id.
JUL_13 = 442380  # Jul 13-19: uploaded after Jul 20, covers only earlier dates
JUL_20 = 442381
AUG_17 = 442426
AUG_31 = 442431
SEP_7 = 442432
SEP_14 = 442443
SEP_21 = 442445
ALL_LOGS = (442380, 442381, 442404, 442405, 442423, 442426, 442427, 442431, 442432, 442443, 442445)


def archived(media_id: int) -> ArchivedLog:
    return next(a for a in FileLogArchive(RAW).archived() if a.log.media_id == media_id)


def archived_pdf(media_id: int) -> bytes:
    return FileLogArchive(RAW).load(archived(media_id))


def published(media_id: int, uploaded: date, *, minute: int = 0) -> PublishedLog:
    at = datetime(uploaded.year, uploaded.month, uploaded.day, 12, minute, tzinfo=UTC)
    return PublishedLog(media_id, f"https://example.test/{media_id}.pdf", f"log {media_id}", at, at)


def entry(
    call_number: str | None,
    day: date | None,
    header: str = "MOTOR VEHICLE STOP Verbal Warning",
    *segments: tuple[SegmentKind, str],
    time: str = "1200",
) -> RawEntry:
    lines = [f"{call_number or ''} {time} {header}".strip()]
    lines += [f"{kind.value}: {text}" for kind, text in segments]
    return RawEntry(
        call_number=call_number,
        page=1,
        date=day,
        time=time,
        header_lines=(header,),
        segments=tuple(Segment(kind, text) for kind, text in segments),
        lines=tuple(lines),
    )


def read_log(*entries: RawEntry, declared_from: date | None = None) -> ReadLog:
    numbered = sum(1 for e in entries if e.call_number is not None)
    return ReadLog(entries=entries, call_numbers_in_text=numbered, declared_from=declared_from, declared_thru=None)
