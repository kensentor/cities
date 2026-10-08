"""Dispatch-log entries: what a reader observes in a PDF, and what is stored."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class SegmentKind(StrEnum):
    """The labelled lines that follow an entry's call line, plus lines that continue nothing."""

    LOCATION_ADDRESS = "Location/Address"
    VICINITY = "Vicinity of"
    LOCATION = "Location"
    ID = "ID"
    REFER = "Refer To"
    CHARGES = "Charges"
    # A line that could not have wrapped from the line before it and carries no label: what is
    # left on the page after the department removes a line, such as ":" or the tail of a location.
    LEFTOVER = "leftover"


LOCATION_KINDS = frozenset({SegmentKind.LOCATION_ADDRESS, SegmentKind.VICINITY, SegmentKind.LOCATION})


@dataclass(frozen=True, slots=True)
class Segment:
    kind: SegmentKind
    text: str  # the text after the label, wrapped lines joined


@dataclass(frozen=True, slots=True)
class RawEntry:
    """One entry as a reader found it, before any rule is applied."""

    call_number: str | None  # None when the call number is missing from the page
    page: int  # 1-based index of the PDF page holding the entry's first line
    date: date | None  # None for entries before the document's first date heading
    time: str  # HHMM as published
    header_lines: tuple[str, ...]  # call type and result as printed, one item per printed line
    segments: tuple[Segment, ...]
    lines: tuple[str, ...]  # every printed line of the entry, verbatim, in order


@dataclass(frozen=True, slots=True)
class ReadLog:
    """Everything a reader observed in one PDF."""

    entries: tuple[RawEntry, ...]
    # Call numbers counted by a pattern over the page text, independent of the line grammar.
    call_numbers_in_text: int
    # The "Dispatch Log From … Thru …" header, when the document carries one.
    declared_from: date | None
    declared_thru: date | None
    # Lines before the first entry that are neither a date heading nor page furniture.
    stray_lines: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EntryVersion:
    """One entry as one log published it. Text fields are verbatim."""

    call_number: str
    document_id: int
    page: int
    date: date
    time: str
    call_type: str
    result: str
    location_prefix: str | None
    location_raw: str | None
    raw_block: str

    def published_fields(self) -> tuple[object, ...]:
        """The fields a re-issued log can change, for comparing versions."""
        return (self.date, self.time, self.call_type, self.result, self.location_prefix, self.location_raw)


class EntryStatus(StrEnum):
    CURRENT = "current"
    WITHDRAWN = "withdrawn"


@dataclass(frozen=True, slots=True)
class EntryState:
    """Which version of an entry counts now.

    For a current entry, `current_document_id` holds the version shown. For a withdrawn entry it
    holds the most recent log that still contained it.
    """

    call_number: str
    current_document_id: int
    status: EntryStatus


def join_wrapped(lines: Sequence[str]) -> str:
    """Join printed lines that wrapped: with a space, or with nothing after a hyphen ending a word."""
    text = ""
    for line in lines:
        if not text:
            text = line
        elif text.endswith("-") and len(text) > 1 and not text[-2].isspace():
            text += line
        else:
            text += " " + line
    return text
