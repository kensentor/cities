"""The core's pure rules."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest
from support import entry, published

from cities.melrose.core import rules
from cities.melrose.domain.entries import EntryStatus, EntryVersion, SegmentKind
from cities.melrose.domain.logs import ArchivedLog, DocumentRecord, DocumentStatus
from cities.melrose.domain.reports import NoticeKind

DAY = date(2026, 9, 21)


@pytest.mark.parametrize(
    ("header", "call_type", "result", "truncated"),
    [
        ("MOTOR VEHICLE STOP Citation/Warning Issued", "MOTOR VEHICLE STOP", "Citation/Warning Issued", False),
        ("MOTOR VEHICLE STOP Citation/Warning", "MOTOR VEHICLE STOP", "Citation/Warning", True),
        ("911 HANGUP / MISDIAL Unit Clear", "911 HANGUP / MISDIAL", "Unit Clear", False),
        ("ALARM, COMMERCIAL Building Checked - Secure", "ALARM, COMMERCIAL", "Building Checked - Secure", False),
        ("MEDICAL EMERGENCY Taken/Referred to Other", "MEDICAL EMERGENCY", "Taken/Referred to Other", True),
        ("SERVE RESTRAINING ORDER Restraining Order", "SERVE RESTRAINING ORDER", "Restraining Order", True),
        ("MOTOR VEHICLE STOP * Arrest 17 and Over Male", "MOTOR VEHICLE STOP", "* Arrest 17 and Over Male", False),
        ("DISTURBANCE * Arrest Under 17 Male", "DISTURBANCE", "* Arrest Under 17 Male", False),
        ("Restraining Order Violation * Arrest 17", "Restraining Order Violation", "* Arrest 17", False),
        ("SUSPICIOUS ACTIVITY * Prot. Cust. 18 & Over Male", "SUSPICIOUS ACTIVITY", "* Prot. Cust. 18 & Over Male", False),
    ],
)
def test_split_header_by_known_results(header: str, call_type: str, result: str, truncated: bool) -> None:
    assert rules.split_header([header]) == rules.Header(call_type, result, truncated)


@pytest.mark.parametrize(
    "header",
    ["MOTOR VEHICLE STOP Warned Loudly", "MOTOR VEHICLE STOP * Arrest 18 and Over Male", "Unit Clear", "MOTOR VEHICLE STOP Issued"],
)
def test_an_unknown_result_does_not_split(header: str) -> None:
    assert rules.split_header([header]) is None


def test_an_unknown_result_rejects_the_document() -> None:
    with pytest.raises(rules.DocumentRejected, match="unknown result in 26-1"):
        rules.interpret([entry("26-1", DAY, "MOTOR VEHICLE STOP Warned Loudly")], [DAY], 1, ())


def test_a_header_line_after_a_complete_result_is_left_over() -> None:
    raw = replace(entry("26-8623", DAY), header_lines=("MEDICAL EMERGENCY Transported to Hospital", "26"))
    out = rules.interpret([raw], [DAY], 1, ())
    assert out.versions[0].result == "Transported to Hospital"
    assert [(n.kind, n.text) for n in out.notices] == [(NoticeKind.LEFTOVER_LINE, "26")]


def test_entries_before_the_first_heading_take_the_day_before_it() -> None:
    entries = [entry("26-1", None), entry("26-2", date(2026, 7, 21))]
    assert rules.assign_dates(entries, declared_from=date(2026, 7, 20)) == [date(2026, 7, 20), date(2026, 7, 21)]


def test_an_inferred_date_that_contradicts_the_declared_range_rejects_the_document() -> None:
    with pytest.raises(rules.DocumentRejected, match="declares it starts"):
        rules.assign_dates([entry("26-1", None), entry("26-2", date(2026, 7, 21))], declared_from=date(2026, 7, 19))


def test_a_log_without_any_date_heading_is_rejected() -> None:
    with pytest.raises(rules.DocumentRejected, match="no date heading"):
        rules.assign_dates([entry("26-1", None)], declared_from=None)


def test_location_is_the_first_location_line_before_any_id_or_reference() -> None:
    raw = entry(
        "26-8317",
        DAY,
        "MOTOR VEHICLE STOP Verbal Warning",
        (SegmentKind.VICINITY, "350 LYNN FELLS PKWY @ 102 TREMONT ST"),
        (SegmentKind.ID, ""),
        (SegmentKind.VICINITY, "1053 MAIN ST @ 12 LOVELL RD"),
    )
    out = rules.interpret([raw], [DAY], 1, ())
    assert (out.versions[0].location_prefix, out.versions[0].location_raw) == ("Vicinity of", "350 LYNN FELLS PKWY @ 102 TREMONT ST")
    assert [(n.kind, n.text) for n in out.notices] == [(NoticeKind.TRAILING_LOCATION, "1053 MAIN ST @ 12 LOVELL RD")]


def test_trailing_location_never_becomes_the_entry_location() -> None:
    """A withheld entry's location left on the page after an ID line must not be shown as this entry's."""
    raw = entry("26-11075", DAY, "Restraining Order Violation * Arrest 17", (SegmentKind.REFER, "26-11075-AR"), (SegmentKind.LOCATION_ADDRESS, "10 COREY ST"))
    out = rules.interpret([raw], [DAY], 1, ())
    assert out.versions[0].location_raw is None
    assert out.notices[0].kind is NoticeKind.TRAILING_LOCATION


def test_second_location_line_is_trailing_even_before_an_id_line() -> None:
    raw = entry("26-1", DAY, "MOTOR VEHICLE STOP Verbal Warning", (SegmentKind.LOCATION_ADDRESS, "A ST"), (SegmentKind.VICINITY, "B ST"))
    out = rules.interpret([raw], [DAY], 1, ())
    assert out.versions[0].location_raw == "A ST"
    assert [n.text for n in out.notices] == ["B ST"]


def test_an_entry_without_a_call_number_or_a_refer_to_is_reported_not_stored() -> None:
    out = rules.interpret([entry("26-1", DAY), entry(None, DAY, "Well Being Check * Report taken")], [DAY, DAY], 1, ())
    assert [v.call_number for v in out.versions] == ["26-1"]
    assert [n.kind for n in out.notices] == [NoticeKind.UNNUMBERED_ENTRY]


def test_an_entry_without_a_call_number_takes_the_one_its_refer_to_names() -> None:
    unnumbered = entry(None, DAY, "Well Being Check * Report taken", (SegmentKind.REFER, "26-9817-OF"), time="1559")
    out = rules.interpret([entry("26-9816", DAY), unnumbered], [DAY, DAY], 1, ())
    assert [v.call_number for v in out.versions] == ["26-9816", "26-9817"]
    assert out.inferred == frozenset({"26-9817"})
    assert [n.kind for n in out.notices] == [NoticeKind.INFERRED_CALL_NUMBER]
    rules.check_complete(out.versions, call_numbers_in_text=1, inferred=out.inferred)


def test_a_refer_to_naming_a_call_printed_in_the_same_log_is_not_used() -> None:
    unnumbered = entry(None, DAY, "Well Being Check * Report taken", (SegmentKind.REFER, "26-9816-OF"))
    out = rules.interpret([entry("26-9816", DAY), unnumbered], [DAY, DAY], 1, ())
    assert [v.call_number for v in out.versions] == ["26-9816"]
    assert [n.kind for n in out.notices] == [NoticeKind.UNNUMBERED_ENTRY]


def test_a_lettered_reference_names_its_base_call() -> None:
    unnumbered = entry(None, DAY, "Well Being Check * Report taken", (SegmentKind.REFER, "26-8468-A-OF"))
    assert rules.interpret([unnumbered], [DAY], 1, ()).versions[0].call_number == "26-8468"


def test_completeness_rejects_a_count_mismatch_and_duplicates() -> None:
    v = _version("26-1", 1)
    with pytest.raises(rules.DocumentRejected, match="read 1 entries but the text holds 2"):
        rules.check_complete([v], 2)
    with pytest.raises(rules.DocumentRejected, match="more than once: 26-1"):
        rules.check_complete([v, v], 2)


def test_current_version_is_the_latest_upload_covering_the_entry_date() -> None:
    early, late = _doc(1, date(2026, 4, 14)), _doc(2, date(2026, 4, 20))
    states = rules.current_entries([early, late], [_version("26-1", 1), _version("26-1", 2)])
    assert [(s.current_document_id, s.status) for s in states] == [(2, EntryStatus.CURRENT)]


def test_an_entry_missing_from_the_latest_covering_log_is_withdrawn() -> None:
    early, late = _doc(1, date(2026, 4, 14)), _doc(2, date(2026, 4, 20))
    states = rules.current_entries([early, late], [_version("26-1", 1), _version("26-2", 1), _version("26-2", 2)])
    assert {s.call_number: s.status for s in states} == {"26-1": EntryStatus.WITHDRAWN, "26-2": EntryStatus.CURRENT}
    assert states[0].current_document_id == 1


def test_upload_ties_are_broken_by_media_id() -> None:
    a, b = _doc(7, date(2026, 4, 14)), _doc(5, date(2026, 4, 14))
    states = rules.current_entries([a, b], [_version("26-1", 5), _version("26-1", 7)])
    assert states[0].current_document_id == 7


def test_versions_differ_when_a_published_field_changes() -> None:
    assert rules.differing_versions([_version("26-1", 1), _version("26-1", 2)]) == set()
    assert rules.differing_versions([_version("26-1", 1), replace(_version("26-1", 2), location_raw=None)]) == {"26-1"}


def test_dates_without_entries() -> None:
    since = date(2026, 7, 20)
    assert rules.dates_without_entries(since, date(2026, 7, 23), [date(2026, 7, 20), date(2026, 7, 22)]) == [
        date(2026, 7, 21),
        date(2026, 7, 23),
    ]


def _doc(media_id: int, uploaded: date) -> DocumentRecord:
    archived = ArchivedLog(published(media_id, uploaded), f"sha{media_id}", published(media_id, uploaded).uploaded_at)
    return DocumentRecord(archived, date(2026, 4, 6), date(2026, 4, 12), DocumentStatus.LOADED)


def _version(call_number: str, document_id: int) -> EntryVersion:
    return EntryVersion(call_number, document_id, 1, date(2026, 4, 8), "1200", "MOTOR VEHICLE STOP", "Verbal Warning", "Location/Address", "1 MAIN ST", "")


def test_a_header_that_is_exactly_a_known_call_type_has_no_result() -> None:
    out = rules.interpret([entry("25-13757", DAY, "MISSING PERSON")], [DAY], 1, {"MISSING PERSON"})
    assert (out.versions[0].call_type, out.versions[0].result) == ("MISSING PERSON", "")
    assert [(n.kind, n.text) for n in out.notices] == [(NoticeKind.MISSING_RESULT, "MISSING PERSON")]


def test_a_call_type_ending_in_a_results_words_stays_whole() -> None:
    out = rules.interpret([entry("26-1", DAY, "Make Notification")], [DAY], 1, {"Make Notification"})
    assert (out.versions[0].call_type, out.versions[0].result) == ("Make Notification", "")


def test_a_header_with_no_result_that_is_not_a_known_call_type_still_rejects_the_document() -> None:
    with pytest.raises(rules.DocumentRejected, match="unknown result in 26-1"):
        rules.interpret([entry("26-1", DAY, "MISSING PERSONS")], [DAY], 1, {"MISSING PERSON"})


MAY_11, MAY_12, MAY_13 = date(2026, 5, 11), date(2026, 5, 12), date(2026, 5, 13)


def test_a_lost_heading_is_restored_at_the_one_overnight_reset() -> None:
    entries = [entry("26-5500", MAY_11, time="1923"), entry("26-5501", MAY_11, time="2007"), entry("26-5516", MAY_11, time="0203"), entry("26-5583", MAY_13, time="0010")]
    dates, starts = rules.restore_lost_headings(entries, [e.date for e in entries if e.date])
    assert dates == [MAY_11, MAY_11, MAY_12, MAY_13]
    assert starts == [2]


def test_a_skipped_day_without_one_overnight_reset_rejects_the_document() -> None:
    late_filed = [entry("26-1", MAY_11, time="2212"), entry("26-2", MAY_11, time="1110"), entry("26-3", MAY_13)]
    with pytest.raises(rules.DocumentRejected, match="skip 2026-05-12"):
        rules.restore_lost_headings(late_filed, [e.date for e in late_filed if e.date])


def test_consecutive_days_and_longer_gaps_are_left_alone() -> None:
    entries = [entry("26-1", MAY_11, time="2300"), entry("26-2", MAY_11, time="0100"), entry("26-3", date(2026, 5, 15))]
    dates = [e.date for e in entries if e.date]
    assert rules.restore_lost_headings(entries, dates) == (dates, [])
