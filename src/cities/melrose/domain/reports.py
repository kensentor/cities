"""What a run found, for the person running it."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

from cities.melrose.domain.logs import DocumentRecord


class NoticeKind(StrEnum):
    """Damage in a published log that loads anyway, because no parser change could repair it."""

    # A line with a time and a call type but no call number, and no Refer To line of its own to take
    # one from: there is no key to store it under.
    UNNUMBERED_ENTRY = "unnumbered entry"
    # An entry printed without a call number, stored under the call its own Refer To line names.
    INFERRED_CALL_NUMBER = "inferred call number"
    # A location line after the entry's first location or after its ID / Refer To / Charges lines,
    # usually left behind when the department withheld the entry that owned it. Never displayed.
    TRAILING_LOCATION = "trailing location"
    # A line that continues nothing: left over from a line the department removed.
    LEFTOVER_LINE = "leftover line"
    # A result printed cut short, stored as printed.
    TRUNCATED_RESULT = "truncated result"
    # A line before the document's first entry that is neither a date heading nor page furniture.
    STRAY_LINE = "stray line"


@dataclass(frozen=True, slots=True)
class Notice:
    media_id: int
    call_number: str | None
    kind: NoticeKind
    text: str


@dataclass(frozen=True, slots=True)
class RunReport:
    command: str
    started_at: datetime
    finished_at: datetime
    documents_new: tuple[DocumentRecord, ...] = ()
    entries_new: int = 0
    quarantined: tuple[DocumentRecord, ...] = ()
    # Call numbers printed twice in one log; that log is quarantined.
    conflicts: tuple[str, ...] = ()
    # Entries whose versions now disagree between logs, that did not before this run.
    versions_differing: tuple[str, ...] = ()
    # Entries this run withdrew: missing from the latest log covering their date.
    withdrawn: tuple[str, ...] = ()
    new_call_types: tuple[str, ...] = ()
    dates_without_entries: tuple[date, ...] = ()
    notices: tuple[Notice, ...] = field(default=())
    # False when the run found nothing new and wrote nothing.
    wrote: bool = True
