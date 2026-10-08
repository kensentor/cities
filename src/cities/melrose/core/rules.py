"""The rules every reader and every store must obey, written as pure functions."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from cities.melrose.domain.entries import (
    LOCATION_KINDS,
    EntryState,
    EntryStatus,
    EntryVersion,
    RawEntry,
    SegmentKind,
    join_wrapped,
)
from cities.melrose.domain.logs import DocumentRecord, DocumentStatus
from cities.melrose.domain.reports import Notice, NoticeKind
from cities.melrose.domain.vocabulary import ARREST_RESULT, KNOWN_RESULTS, TRUNCATED_RESULTS

_LISTED_RESULTS = sorted(KNOWN_RESULTS | TRUNCATED_RESULTS, key=len, reverse=True)
# A reference such as "26-9817-OF" or "26-8468-A-OF" names the call it was filed under.
_REFERENCED_CALL = re.compile(r"^(\d{2}-\d+)-")
# Segments after which a location line no longer belongs to the entry.
_CLOSING_KINDS = frozenset({SegmentKind.ID, SegmentKind.REFER, SegmentKind.CHARGES})


class DocumentRejected(Exception):
    """The log cannot be loaded as read; it is quarantined with this message."""


@dataclass(frozen=True, slots=True)
class Header:
    call_type: str
    result: str
    truncated: bool


def split_header(lines: Sequence[str]) -> Header | None:
    """Split "CALL TYPE Result" by the known results. None when the result is not recognised."""
    text = join_wrapped(lines)
    arrest_at = text.find(" * Arrest")
    if arrest_at > 0 and ARREST_RESULT.fullmatch(text[arrest_at + 1 :]):
        return Header(text[:arrest_at], text[arrest_at + 1 :], truncated=False)
    for result in _LISTED_RESULTS:
        if text.endswith(" " + result) and len(text) > len(result) + 1:
            return Header(text[: -len(result) - 1], result, truncated=result in TRUNCATED_RESULTS)
    return None


def assign_dates(entries: Sequence[RawEntry], declared_from: date | None) -> list[date]:
    """Each entry's date. Entries before the first date heading take the day before it.

    Some logs lose their first "For Date:" heading. The day before the first heading is then
    checked against the document's "Dispatch Log From" header where it has one.
    """
    first_heading = next((e.date for e in entries if e.date is not None), None)
    if first_heading is None:
        raise DocumentRejected("no date heading")
    inferred = first_heading - timedelta(days=1)
    if any(e.date is None for e in entries) and declared_from is not None and declared_from != inferred:
        raise DocumentRejected(
            f"entries before the first heading would fall on {inferred}, but the log declares it starts {declared_from}"
        )
    return [e.date if e.date is not None else inferred for e in entries]


@dataclass(frozen=True, slots=True)
class Interpreted:
    versions: list[EntryVersion]
    notices: list[Notice]
    # Call numbers taken from an entry's own Refer To line because the page does not print them.
    inferred: frozenset[str] = frozenset()


def interpret(entries: Sequence[RawEntry], dates: Sequence[date], media_id: int) -> Interpreted:
    """Turn observed entries into versions. Raises DocumentRejected for a header it cannot split."""
    versions: list[EntryVersion] = []
    notices: list[Notice] = []
    inferred: set[str] = set()
    printed = {e.call_number for e in entries if e.call_number is not None}
    for raw, day in zip(entries, dates, strict=True):
        block = "\n".join(raw.lines)
        call_number = raw.call_number
        if call_number is None:
            call_number = _referenced_call(raw)
            if call_number is None or call_number in printed or call_number in inferred:
                notices.append(Notice(media_id, None, NoticeKind.UNNUMBERED_ENTRY, block))
                continue
            inferred.add(call_number)
            notices.append(Notice(media_id, call_number, NoticeKind.INFERRED_CALL_NUMBER, block))
        header, spare = _split_longest(raw.header_lines)
        if header is None:
            raise DocumentRejected(f"unknown result in {call_number}: {join_wrapped(raw.header_lines)!r}")
        notices.extend(Notice(media_id, call_number, NoticeKind.LEFTOVER_LINE, line) for line in spare)
        if header.truncated:
            notices.append(Notice(media_id, call_number, NoticeKind.TRUNCATED_RESULT, header.result))
        prefix, location = _location(raw, call_number, media_id, notices)
        versions.append(
            EntryVersion(
                call_number=call_number,
                document_id=media_id,
                page=raw.page,
                date=day,
                time=raw.time,
                call_type=header.call_type,
                result=header.result,
                location_prefix=prefix,
                location_raw=location,
                raw_block=block,
            )
        )
    return Interpreted(versions, notices, frozenset(inferred))


def _referenced_call(raw: RawEntry) -> str | None:
    """The call number named by an unnumbered entry's own first Refer To line (design A7).

    Not used when it names a call printed elsewhere in the same log: the line then belongs to
    that call, not to this entry.
    """
    reference = next((s.text for s in raw.segments if s.kind is SegmentKind.REFER), None)
    match = _REFERENCED_CALL.match(reference) if reference else None
    return match.group(1) if match else None


def _split_longest(lines: Sequence[str]) -> tuple[Header | None, Sequence[str]]:
    """Split the most header lines that end in a known result; lines after them are left over.

    A wrapped-looking line under a complete header can be what remains of a withheld entry, such
    as the "26" of a removed call number, so the header ends where the result does.
    """
    for end in range(len(lines), 0, -1):
        if (header := split_header(lines[:end])) is not None:
            return header, lines[end:]
    return None, ()


def _location(raw: RawEntry, call_number: str, media_id: int, notices: list[Notice]) -> tuple[str | None, str | None]:
    """The entry's own location: its first location line, if no ID, Refer To or Charges line precedes it.

    Any other location line is reported and kept only in the raw block. Such lines are usually
    left behind when the department withholds the entry that owned them, and must never reach the map.
    """
    found: tuple[str | None, str | None] = (None, None)
    closed = False
    for segment in raw.segments:
        if segment.kind in _CLOSING_KINDS:
            closed = True
        elif segment.kind in LOCATION_KINDS:
            if found == (None, None) and not closed:
                found = (segment.kind.value, segment.text)
            else:
                notices.append(Notice(media_id, call_number, NoticeKind.TRAILING_LOCATION, segment.text))
        elif segment.kind is SegmentKind.LEFTOVER:
            notices.append(Notice(media_id, call_number, NoticeKind.LEFTOVER_LINE, segment.text))
    return found


def check_complete(versions: Sequence[EntryVersion], call_numbers_in_text: int, inferred: Collection[str] = ()) -> None:
    """Every call number printed in the log must have become exactly one version.

    Inferred call numbers are not printed as call numbers, so they are not in the text's count.
    """
    counts: dict[str, int] = defaultdict(int)
    for v in versions:
        counts[v.call_number] += 1
    duplicates = sorted(c for c, n in counts.items() if n > 1)
    if duplicates:
        raise DocumentRejected(f"call numbers printed more than once: {', '.join(duplicates)}")
    printed = len(versions) - len(inferred)
    if printed != call_numbers_in_text:
        raise DocumentRejected(f"read {printed} entries but the text holds {call_numbers_in_text} call numbers")


def current_entries(documents: Iterable[DocumentRecord], versions: Iterable[EntryVersion]) -> list[EntryState]:
    """Which version of each entry counts (technical spec T15).

    The current version comes from the most recently uploaded loaded log whose date range covers
    the entry's date, ties broken by media id. If that log does not contain the entry, the entry is
    withdrawn: the department's latest publication for that day no longer shows it.
    """
    loaded = [d for d in documents if d.status is DocumentStatus.LOADED]
    order = {d.media_id: (d.archived.log.uploaded_at, d.media_id) for d in loaded}
    by_call: dict[str, list[EntryVersion]] = defaultdict(list)
    for v in versions:
        if v.document_id in order:
            by_call[v.call_number].append(v)
    states: list[EntryState] = []
    for call_number, held in sorted(by_call.items()):
        latest = max(held, key=lambda v: order[v.document_id])
        covering = max((d for d in loaded if d.covers(latest.date)), key=lambda d: order[d.media_id])
        if any(v.document_id == covering.media_id for v in held):
            states.append(EntryState(call_number, covering.media_id, EntryStatus.CURRENT))
        else:
            states.append(EntryState(call_number, latest.document_id, EntryStatus.WITHDRAWN))
    return states


def current_versions(states: Iterable[EntryState], versions: Iterable[EntryVersion]) -> list[EntryVersion]:
    """The version shown for each current entry; withdrawn entries have none."""
    shown = {(s.call_number, s.current_document_id) for s in states if s.status is EntryStatus.CURRENT}
    return [v for v in versions if (v.call_number, v.document_id) in shown]


def differing_versions(versions: Iterable[EntryVersion]) -> set[str]:
    """Call numbers whose versions disagree on any published field."""
    seen: dict[str, set[tuple[object, ...]]] = defaultdict(set)
    for v in versions:
        seen[v.call_number].add(v.published_fields())
    return {c for c, fields in seen.items() if len(fields) > 1}


def dates_without_entries(since: date, until: date | None, current_dates: Iterable[date]) -> list[date]:
    """Days from `since` through `until` on which no current entry falls."""
    if until is None or until < since:
        return []
    have = set(current_dates)
    return [since + timedelta(days=n) for n in range((until - since).days + 1) if since + timedelta(days=n) not in have]
