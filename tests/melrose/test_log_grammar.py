"""The line grammar, on synthetic lines. Each rule here was found in a published log; see test_pdf_reader.py."""

from __future__ import annotations

from datetime import date

from cities.melrose.adapters.outbound.log_grammar import Line, could_continue, parse
from cities.melrose.domain.entries import SegmentKind

# Courier at 14 pt advances 8.4 pt per character from a 72 pt left margin; the text block ends near 540.
WIDTH = 8.4


def line(text: str, *, full: bool = False, page: int = 1) -> Line:
    """A line ending where its text does, or at the right margin when `full`."""
    x1 = 539.5 if full else 72 + WIDTH * len(text)
    return Line(page=page, text=text, x1=x1, char_width=WIDTH)


def read(*lines: Line):
    texts = [ln.text for ln in lines]
    return parse(lines, ["\n".join(texts)])


def test_a_word_that_would_not_fit_is_a_wrap() -> None:
    assert could_continue(line("Location/Address: 580 LYNN FELLS PKWY @ 52 BATCHELDER", full=True), line("ST"))


def test_a_word_that_would_have_fitted_is_not_a_wrap() -> None:
    assert not could_continue(line("26-10514 1815 MOTOR VEHICLE STOP Unit Clear"), line("42 GROVE ST"))


def test_a_line_that_ended_exactly_at_the_margin_wrapped() -> None:
    exactly_full = Line(page=1, text="x" * 55, x1=540.0, char_width=WIDTH)
    assert could_continue(exactly_full, line("A"))


def test_entry_fields_are_labelled_and_wrapped_lines_joined() -> None:
    log = read(
        line("For Date: 09/21/2026 - Monday"),
        line("26-11102 0858 MOTOR VEHICLE STOP Citation/Warning", full=True),
        line("Issued"),
        line("Location/Address: [MEL 1243] POPE RESIDENCE - 744 LYNN", full=True),
        line("FELLS PKWY"),
        line("ID:"),
    )
    (entry,) = log.entries
    assert (entry.call_number, entry.date, entry.time) == ("26-11102", date(2026, 9, 21), "0858")
    assert entry.header_lines == ("MOTOR VEHICLE STOP Citation/Warning", "Issued")
    assert [(s.kind, s.text) for s in entry.segments] == [
        (SegmentKind.LOCATION_ADDRESS, "[MEL 1243] POPE RESIDENCE - 744 LYNN FELLS PKWY"),
        (SegmentKind.ID, ""),
    ]
    assert len(entry.lines) == 5


def test_hyphen_ending_a_word_joins_without_a_space() -> None:
    log = read(
        line("For Date: 09/14/2026 - Monday"),
        line("26-1 0001 MEDICAL EMERGENCY Unit Clear"),
        line("Location/Address: [MEL 1] MELROSE CARE CENTER-", full=True),
        line("NURSING HOME - 40 MARTIN ST"),
    )
    assert log.entries[0].segments[0].text == "[MEL 1] MELROSE CARE CENTER-NURSING HOME - 40 MARTIN ST"


def test_redaction_marks_never_continue_a_field() -> None:
    log = read(
        line("For Date: 09/21/2026 - Monday"),
        line("26-11211 1836 COMPLAINT * Report taken"),
        line("Location/Address: 98 GREEN ST", full=True),
        line(":"),
    )
    assert [(s.kind, s.text) for s in log.entries[0].segments] == [
        (SegmentKind.LOCATION_ADDRESS, "98 GREEN ST"),
        (SegmentKind.LEFTOVER, ":"),
    ]


def test_page_furniture_is_dropped_without_closing_the_open_field() -> None:
    log = read(
        line("For Date: 09/21/2026 - Monday"),
        line("26-1 0001 MOTOR VEHICLE STOP Verbal Warning"),
        line("Location/Address: 580 LYNN FELLS PKWY @ 52 BATCHELDER", full=True),
        line("Melrose Police Department Page: 13"),
        line("Dispatch Log From: 09/21/2026 Thru: 09/27/2026 0001 -"),
        line("2359 Printed: 10/01/2026"),
        line("ST"),
    )
    assert log.entries[0].segments[0].text == "580 LYNN FELLS PKWY @ 52 BATCHELDER ST"
    assert (log.declared_from, log.declared_thru) == (date(2026, 9, 21), date(2026, 9, 27))


def test_text_after_furniture_that_would_have_fitted_is_left_over() -> None:
    log = read(
        line("For Date: 09/06/2026 - Sunday"),
        line("26-10514 1815 MOTOR VEHICLE STOP Unit Clear"),
        line("Melrose Police Department Page: 15"),
        line("42 GROVE ST"),
        line("ID:"),
    )
    assert [(s.kind, s.text) for s in log.entries[0].segments] == [
        (SegmentKind.LEFTOVER, "42 GROVE ST"),
        (SegmentKind.ID, ""),
    ]


def test_a_time_on_a_line_of_its_own_opens_an_entry_without_a_call_number() -> None:
    log = read(
        line("For Date: 08/20/2026 - Thursday"),
        line("26-9816 1522 MEDICAL EMERGENCY Unit Clear"),
        line("1559 Well Being Check * Report taken"),
        line("Location/Address: 49 CONRAD RD"),
    )
    first, second = log.entries
    assert first.segments == ()
    assert (second.call_number, second.time, second.header_lines) == (None, "1559", ("Well Being Check * Report taken",))
    assert second.segments[0].text == "49 CONRAD RD"


def test_charges_are_a_list_so_every_unlabelled_line_under_them_is_a_charge() -> None:
    log = read(
        line("For Date: 07/17/2026 - Friday"),
        line("26-8450 1701 MOTOR VEHICLE STOP * Report taken"),
        line("Charges: UNINSURED MOTOR VEHICLE"),
        line("UNREGISTERED MOTOR VEHICLE *"),
    )
    (charges,) = log.entries[0].segments
    assert charges.kind is SegmentKind.CHARGES
    assert "UNREGISTERED MOTOR VEHICLE *" in charges.text


def test_refer_to_without_refer_is_still_a_reference() -> None:
    log = read(line("For Date: 07/30/2026 - Thursday"), line("26-8499 1716 ROBBERY Unit Clear"), line("To Arrest: 26-8499-AR"))
    assert log.entries[0].segments[0].kind is SegmentKind.REFER


def test_entries_before_the_first_heading_have_no_date() -> None:
    log = read(line("26-1 0001 MEDICAL EMERGENCY Unit Clear"), line("For Date: 07/21/2026 - Tuesday"))
    assert log.entries[0].date is None


def test_unlabelled_lines_before_any_entry_are_stray() -> None:
    log = read(line("For Date: 07/21/2026 - Tuesday"), line("something else"), line("26-1 0001 MEDICAL EMERGENCY Unit Clear"))
    assert log.stray_lines == ("something else",)


def test_call_numbers_are_counted_from_the_text_not_from_the_grammar() -> None:
    log = parse([], ["26-11101 0839 ALARM ... 26-11102 0858 MOTOR ... Refer To Incident: 26-11122-OF"])
    assert log.call_numbers_in_text == 2
