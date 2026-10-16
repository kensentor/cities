"""The map export built from every published log in the archive: what the page could ever show."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from support import RAW, REPO

from cities.melrose.adapters.outbound.gazetteer import SnapshotGazetteer
from cities.melrose.adapters.outbound.json_publisher import JsonMapPublisher
from cities.melrose.adapters.outbound.log_archive import FileLogArchive
from cities.melrose.adapters.outbound.pdf_reader import PdfLogReader
from cities.melrose.core import rules
from cities.melrose.core.publishing import ARREST, public_result
from cities.melrose.core.rebuild import RebuildService
from cities.melrose.domain.places import PlacementKind
from cities.melrose.domain.streets import abbreviate
from cities.melrose.domain.vocabulary import KNOWN_RESULTS, TRUNCATED_RESULTS
from cities.melrose.settings import BOUNDARY_RULE, COLLECT_SINCE, categories, known_call_types
from cities.melrose.stubs import FakeClock, InMemoryEntryRepository

GAZETTEER = SnapshotGazetteer(REPO / "data" / "melrose" / "reference", BOUNDARY_RULE)
WORD = re.compile(r"[A-Za-z][A-Za-z']*")
PLACED = {PlacementKind.ADDRESS.value, PlacementKind.INTERSECTION.value}


class Built:
    def __init__(self, repository: InMemoryEntryRepository, text: str) -> None:
        self.repository = repository
        self.text = text
        self.export = json.loads(text)
        self.current = rules.current_versions(repository.entries(), repository.versions())


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Built:
    out: Path = tmp_path_factory.mktemp("site")
    repository = InMemoryEntryRepository()
    RebuildService(
        reader=PdfLogReader(),
        archive=FileLogArchive(RAW),
        repository=repository,
        gazetteer=GAZETTEER,
        publisher=JsonMapPublisher(out),
        clock=FakeClock(),
        since=COLLECT_SINCE,
        known_call_types=known_call_types(),
        categories=categories(),
    ).rebuild()
    return Built(repository, (out / "entries.json").read_text(encoding="utf-8"))


def test_ac10_the_pope_entries_show_only_their_address(built: Built) -> None:
    pope = [r for r in built.export["records"] if r["call"] in ("26-11115", "26-11116")]
    assert [r["address"] for r in pope] == ["744 LYNN FELLS PKWY"] * 2
    assert "POPE" not in built.text.upper()


def test_r10_no_word_of_any_published_location_reaches_the_export_unless_it_names_a_street(built: Built) -> None:
    """Every word printed in a location, of every current entry and not only those exported, is
    searched for. Street names are exempt, being what an address is made of. The fields drawn from
    closed vocabularies (call type, result, category, kind, document URL) are left out of the
    search and checked against their vocabulary instead, in the test below: "HOSPITAL" from a label
    is also in the result "Transported to Hospital", and "UNIT" in "Unit Clear"."""
    streets = {w for name in GAZETTEER.street_names() for w in f"{name} {abbreviate(name)}".split()}
    location_words = {w.upper() for v in built.current for w in WORD.findall(v.location_raw or "")} - streets
    # Values only: key names such as "time" and "generated_at" are not shown, and a label word like
    # "TIME" (CHIME TIME CHILDREN'S CENTER) would otherwise match them.
    open_text = json.dumps(
        [
            built.export["generated_at"],
            built.export["reference_version"],
            [[r[k] for k in ("call", "date", "time", "address", "streets", "wards")] for r in built.export["records"]],
            [[d[k] for k in ("first_date", "last_date")] for d in built.export["documents"]],
        ]
    )
    shown = {w.upper() for w in WORD.findall(open_text)}
    assert location_words, "the search must have words to look for"
    assert not location_words & shown


def test_every_closed_field_holds_only_its_own_vocabulary(built: Built) -> None:
    listed = {t: c.key for c in categories() for t in c.call_types}
    results = (KNOWN_RESULTS | {public_result(t) for t in TRUNCATED_RESULTS} | {ARREST})
    urls = {d.archived.log.source_url for d in built.repository.documents()}
    assert [(c["key"], c["label"]) for c in built.export["categories"]] == [(c.key, c.label) for c in categories()]
    assert {d["url"] for d in built.export["documents"]} <= urls
    for r in built.export["records"]:
        assert listed[r["type"]] == r["category"]
        assert r["result"] in results, r
        assert r["kind"] in {k.value for k in PlacementKind}
        assert re.fullmatch(r"\d{2}-\d+", r["call"]) and re.fullmatch(r"\d{4}", r["time"])
        assert 0 <= r["doc"] < len(built.export["documents"]) and r["page"] >= 1


def test_no_arrest_result_carries_sex_or_age(built: Built) -> None:
    results = {r["result"] for r in built.export["records"]}
    assert ARREST in results
    assert not {w for res in results for w in res.split()} & {"Male", "Female", "17", "Under"}


def test_ac5_every_current_entry_of_a_listed_call_type_is_exported_and_nothing_else(built: Built) -> None:
    listed = {t for c in categories() for t in c.call_types}
    expected = sorted(v.call_number for v in built.current if v.call_type in listed)
    assert sorted(r["call"] for r in built.export["records"]) == expected
    assert len(expected) == 7073


def test_a_record_is_on_the_map_exactly_when_it_has_an_address_a_point_and_one_to_three_wards(built: Built) -> None:
    for r in built.export["records"]:
        if r["kind"] in PLACED:
            assert r["address"] and r["lat"] is not None and r["lon"] is not None and 1 <= len(r["wards"]) <= 3, r
            assert set(r["wards"]) <= {str(n) for n in range(1, 8)}
        else:
            assert (r["address"], r["lat"], r["lon"], r["wards"]) == (None, None, None, []), r


def test_ac8_a_street_only_stop_and_ac8a_an_intersection_stop_carry_their_ranking_streets(built: Built) -> None:
    by_call = {r["call"]: r for r in built.export["records"]}
    street_only = [r for r in by_call.values() if r["kind"] == "street_only" and r["type"] == "MOTOR VEHICLE STOP"]
    assert street_only and all(len(r["streets"]) == 1 and r["address"] is None for r in street_only)
    assert by_call["26-8807"]["streets"] == ["Franklin St", "Vinton St"]
