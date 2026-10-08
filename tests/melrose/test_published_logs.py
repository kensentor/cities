"""The reader and the rules together, on the published logs kept in data/melrose/raw.

Each source-damage test names the log and call number where the pattern was found.
"""

from __future__ import annotations

import json
import random

import pytest
from support import ALL_LOGS, AUG_17, AUG_31, FIXTURES, JUL_13, JUL_20, SEP_7, SEP_14, SEP_21, archived, archived_pdf

from cities.melrose.adapters.outbound.pdf_reader import PdfLogReader
from cities.melrose.core.loading import LoadedDocument, load_document
from cities.melrose.domain.logs import DocumentStatus
from cities.melrose.domain.reports import NoticeKind
from cities.melrose.ports.outbound import LogUnreadable
from cities.melrose.settings import COLLECT_SINCE


def load(media_id: int) -> LoadedDocument:
    return load_document(archived(media_id), archived_pdf(media_id), PdfLogReader(), COLLECT_SINCE)


def version(document: LoadedDocument, call_number: str):
    return next(v for v in document.versions if v.call_number == call_number)


def notices(document: LoadedDocument, kind: NoticeKind) -> list[tuple[str | None, str]]:
    return [(n.call_number, n.text) for n in document.notices if n.kind is kind]


@pytest.mark.parametrize("media_id", ALL_LOGS)
def test_every_log_since_jul_20_passes_the_completeness_check(media_id: int) -> None:
    """Phase 1 gate: none quarantined."""
    document = load(media_id)
    assert document.record.status is not DocumentStatus.QUARANTINED, document.record.error


def test_the_jul_13_log_uploaded_after_jul_20_is_out_of_scope() -> None:
    assert load(JUL_13).record.status is DocumentStatus.OUT_OF_SCOPE


def test_ac1_sep_21_27_holds_187_entries() -> None:
    assert len(load(SEP_21).versions) == 187


def test_ac1_ten_seeded_entries_match_the_golden_file_field_by_field() -> None:
    golden = json.loads((FIXTURES / "golden" / "442445_sample.json").read_text())
    document = load(SEP_21)
    sample = random.Random(golden["seed"]).sample(sorted(v.call_number for v in document.versions), 10)
    assert sample == [g["call_number"] for g in golden["entries"]]
    for expected in golden["entries"]:
        v = version(document, expected["call_number"])
        actual = {
            "call_number": v.call_number,
            "page": v.page,
            "date": v.date.isoformat(),
            "time": v.time,
            "call_type": v.call_type,
            "result": v.result,
            "location_prefix": v.location_prefix,
            "location_raw": v.location_raw,
        }
        assert actual == expected


def test_label_stays_in_storage_with_the_location_as_published() -> None:
    v = version(load(SEP_21), "26-11115")
    assert v.location_raw == "[MEL 1243] POPE RESIDENCE - 744 LYNN FELLS PKWY"
    assert "POPE RESIDENCE" in v.raw_block


def test_a_withheld_entrys_location_left_after_an_arrest_is_not_this_entrys() -> None:
    document = load(SEP_7)
    assert version(document, "26-10767").location_raw == "161 WEST WYOMING AVE @ 8 CLEVELAND ST"
    assert ("26-10767", "[MEL 13720] HORACE MANN SCHOOL - 40 DAMON AVE") in notices(document, NoticeKind.TRAILING_LOCATION)


def test_a_second_location_from_a_withheld_entry_is_not_this_entrys() -> None:
    document = load(AUG_17)
    assert version(document, "26-9896").location_raw != "473 LEBANON ST"
    assert ("26-9896", "473 LEBANON ST") in notices(document, NoticeKind.TRAILING_LOCATION)


def test_entries_whose_call_number_is_missing_are_reported_not_stored() -> None:
    aug_17 = notices(load(AUG_17), NoticeKind.UNNUMBERED_ENTRY)
    jul_20 = notices(load(JUL_20), NoticeKind.UNNUMBERED_ENTRY)
    assert [text.splitlines()[0] for _, text in aug_17] == ["1559 Well Being Check * Report taken"]
    assert [text.splitlines()[0] for _, text in jul_20] == ["0913 Animal Complaint Unit Clear"]


def test_the_entry_before_a_lost_call_number_keeps_only_its_own_fields() -> None:
    v = version(load(AUG_17), "26-9816")
    assert (v.result, v.location_raw) == ("Unit Clear", None)


def test_a_colon_left_by_a_redaction_does_not_join_the_location() -> None:
    assert version(load(SEP_21), "26-11211").location_raw == "98 GREEN ST"


def test_text_after_page_furniture_that_would_have_fitted_is_not_a_location() -> None:
    document = load(AUG_31)
    assert version(document, "26-10514").location_raw is None
    assert ("26-10514", "42 GROVE ST") in notices(document, NoticeKind.LEFTOVER_LINE)


def test_a_remnant_call_number_under_a_complete_result_is_left_over() -> None:
    document = load(JUL_20)
    assert version(document, "26-8623").result == "Transported to Hospital"
    assert ("26-8623", "26") in notices(document, NoticeKind.LEFTOVER_LINE)


def test_a_location_wrapped_after_a_hyphen_joins_without_a_space() -> None:
    locations = [v.location_raw or "" for v in load(SEP_14).versions]
    assert any("MELROSE CARE CENTER-NURSING HOME" in loc for loc in locations)
    assert not any("CENTER- NURSING" in loc for loc in locations)


def test_results_printed_cut_short_are_kept_as_printed() -> None:
    document = load(AUG_31)
    assert version(document, "26-10241").result == "Summons Not"
    assert ("26-10241", "Summons Not") in notices(document, NoticeKind.TRUNCATED_RESULT)


def test_bytes_that_are_not_a_pdf_are_unreadable() -> None:
    with pytest.raises(LogUnreadable):
        PdfLogReader().read(b"<html>challenge</html>")
