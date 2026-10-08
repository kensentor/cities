"""The line grammar of the Melrose dispatch log, over lines already extracted from the PDF.

The log is a Word document in Courier, printed without columns, so every line starts at the same
left margin. Two facts make it readable line by line:

- Each entry opens with a call line ("26-11102 0858 MOTOR VEHICLE STOP Citation/Warning"), and
  each field after it opens with a label ("Location/Address:", "ID:", "Refer To Incident:" ...).
- Word wraps a line only when the next word does not fit. In a fixed-width font, a line's right
  edge says how much room was left, so an unlabelled line can be a wrapped continuation only if its
  first word would not have fitted on the line before it. Anything else is left over from a line
  the department removed (":", "L", the tail of a withheld location) or, when it starts with a
  time, an entry whose call number is missing.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime

from cities.melrose.domain.entries import RawEntry, ReadLog, Segment, SegmentKind, join_wrapped

# The right edge text can reach, less a tolerance: a line that ended exactly at the margin wrapped.
RIGHT_LIMIT = 539.0

CALL_LINE = re.compile(r"^(\d{2}-\d+) (\d{4}) (.+)$")
# A call line printed on the same line as the previous entry's empty ID label, or what a redaction left
# of it: "ID: 25-2176 1530 ALARM, RESIDENTIAL Unit Clear" (441855), ": 25-10369 0804 HARASSMENT …" (442209).
GLUED_CALL_LINE = re.compile(r"^(ID:|:) (?=\d{2}-\d+ \d{4} )")
UNNUMBERED_LINE = re.compile(r"^(\d{4}) ([A-Za-z*].*)$")
# Headings are sometimes printed cut short: "or Date:" (442028), "Date:" (442309).
DATE_HEADING = re.compile(r"^(?:F?or )?Date: (\d{2}/\d{2}/\d{4})\b")
DECLARED_RANGE = re.compile(r"^Dispatch Log From: (\d{2}/\d{2}/\d{4}) Thru: (\d{2}/\d{2}/\d{4})")
PAGE_FURNITURE = re.compile(
    r"^(?:Melrose Police Department Page: \d+|Call Number Time Call Reason Action|Dispatch Log From: .*|(?:\d{4} )?Printed: .*)$"
)
LABELS: tuple[tuple[re.Pattern[str], SegmentKind], ...] = (
    (re.compile(r"^Location/Address:\s?"), SegmentKind.LOCATION_ADDRESS),
    (re.compile(r"^Vicinity of:\s?"), SegmentKind.VICINITY),
    (re.compile(r"^Location:\s?"), SegmentKind.LOCATION),
    (re.compile(r"^ID:\s?"), SegmentKind.ID),
    (re.compile(r"^(?:Refer )?To (?:Incident|Summons|Arrest):\s?"), SegmentKind.REFER),
    (re.compile(r"^Charges:\s?"), SegmentKind.CHARGES),
)
# Lines that are only what a redaction leaves behind, whatever their position.
REDACTION_MARKS = frozenset({":", "L"})
# Counts call numbers in the page text without the grammar, for the completeness check.
CALL_NUMBER_IN_TEXT = re.compile(r"(?<![\w-])\d{2}-\d+ \d{4} ")


@dataclass(frozen=True, slots=True)
class Line:
    page: int
    text: str
    x1: float  # right edge of the last character
    char_width: float  # advance of one character in this line's font


def could_continue(previous: Line, line: Line) -> bool:
    """Whether `line` can be a wrap of `previous`: its first word would not have fitted after it."""
    first_word = line.text.split(" ", 1)[0]
    return previous.x1 + previous.char_width * (1 + len(first_word)) > RIGHT_LIMIT


@dataclass(slots=True)
class _OpenField:
    kind: SegmentKind | None  # None while the call line's header is open
    lines: list[str]


@dataclass(slots=True)
class _Entry:
    call_number: str | None
    page: int
    date: date | None
    time: str
    header: list[str]
    fields: list[_OpenField] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    def finish(self) -> RawEntry:
        return RawEntry(
            call_number=self.call_number,
            page=self.page,
            date=self.date,
            time=self.time,
            header_lines=tuple(self.header),
            segments=tuple(Segment(f.kind, join_wrapped(f.lines)) for f in self.fields if f.kind is not None),
            lines=tuple(self.lines),
        )


def parse(lines: Iterable[Line], page_texts: Sequence[str]) -> ReadLog:
    entries: list[_Entry] = []
    stray: list[str] = []
    current_date: date | None = None
    declared: tuple[date, date] | None = None
    entry: _Entry | None = None
    open_field: _OpenField | None = None
    previous: Line | None = None

    for line in lines:
        text = line.text
        if PAGE_FURNITURE.match(text):
            if m := DECLARED_RANGE.match(text):
                declared = (_us_date(m.group(1)), _us_date(m.group(2)))
            continue  # furniture neither opens nor closes a field
        if entry is not None and (glued := GLUED_CALL_LINE.match(text)):
            prefix = glued.group(1)
            labelled = _label(prefix)
            entry.fields.append(_OpenField(labelled[0], []) if labelled else _OpenField(SegmentKind.LEFTOVER, [prefix]))
            entry.lines.append(prefix)
            text = text[glued.end() :]
        if m := DATE_HEADING.match(text):
            current_date = _us_date(m.group(1))
            entry, open_field = None, None
        elif m := CALL_LINE.match(text):
            entry = _Entry(m.group(1), line.page, current_date, m.group(2), [m.group(3)], lines=[text])
            entries.append(entry)
            open_field = _OpenField(None, entry.header)
        elif entry is None:
            stray.append(text)
        elif labelled := _label(text):
            kind, rest = labelled
            open_field = _OpenField(kind, [rest] if rest else [])
            entry.fields.append(open_field)
            entry.lines.append(text)
        elif text not in REDACTION_MARKS and open_field is not None and _continues(open_field, previous, line):
            open_field.lines.append(text)
            entry.lines.append(text)
        elif m := UNNUMBERED_LINE.match(text):
            entry = _Entry(None, line.page, current_date, m.group(1), [m.group(2)], lines=[text])
            entries.append(entry)
            open_field = _OpenField(None, entry.header)
        else:
            leftover = _OpenField(SegmentKind.LEFTOVER, [text])
            entry.fields.append(leftover)
            entry.lines.append(text)
            open_field = None  # nothing continues a leftover
        previous = line

    return ReadLog(
        entries=tuple(e.finish() for e in entries),
        call_numbers_in_text=sum(len(CALL_NUMBER_IN_TEXT.findall(t)) for t in page_texts),
        declared_from=declared[0] if declared else None,
        declared_thru=declared[1] if declared else None,
        stray_lines=tuple(stray),
    )


def _continues(open_field: _OpenField, previous: Line | None, line: Line) -> bool:
    # Charges print one per line, as a list, so every unlabelled line under them is another charge.
    if open_field.kind is SegmentKind.CHARGES:
        return not UNNUMBERED_LINE.match(line.text)
    return previous is not None and could_continue(previous, line)


def _label(text: str) -> tuple[SegmentKind, str] | None:
    for pattern, kind in LABELS:
        if m := pattern.match(text):
            return kind, text[m.end() :]
    return None


def _us_date(text: str) -> date:
    return datetime.strptime(text, "%m/%d/%Y").date()
