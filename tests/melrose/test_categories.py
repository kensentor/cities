"""categories.toml decides which call types leave SQLite (technical spec T14)."""

from __future__ import annotations

import pytest

from cities.melrose.domain.public import Category
from cities.melrose.settings import categories, known_call_types, parse_categories


def test_ac5_the_committed_categories_are_exactly_stops_and_crashes() -> None:
    assert [(c.key, c.label) for c in categories()] == [("stops", "Stops"), ("crashes", "Crashes")]
    assert categories()[1].call_types == ("MOTOR VEHICLE ACCIDENT", "ACCIDENT HIT & RUN", "MVA - Not Investigated")


def test_every_listed_call_type_is_one_the_logs_use() -> None:
    """A misspelt call type would leave its entries off the map without any error."""
    listed = {t for c in categories() for t in c.call_types}
    assert listed <= known_call_types(), listed - known_call_types()


def test_a_call_type_in_two_categories_is_refused() -> None:
    tables = {
        "stops": {"label": "Stops", "call_types": ["MOTOR VEHICLE STOP"]},
        "crashes": {"label": "Crashes", "call_types": ["MOTOR VEHICLE STOP"]},
    }
    with pytest.raises(ValueError, match="in both"):
        parse_categories(tables)


@pytest.mark.parametrize(
    "tables",
    [
        {"stops": {"label": "Stops", "call_types": ["MOTOR VEHICLE STOP"]}},
        {"stops": {"label": "", "call_types": ["A"]}, "crashes": {"label": "Crashes", "call_types": ["B"]}},
        {"stops": {"label": "Stops", "call_types": []}, "crashes": {"label": "Crashes", "call_types": ["B"]}},
    ],
)
def test_a_file_the_page_cannot_use_is_refused(tables: dict[str, object]) -> None:
    with pytest.raises(ValueError, match=r"categories\.toml"):
        parse_categories(tables)


def test_a_further_category_is_kept_in_file_order() -> None:
    tables = {
        "stops": {"label": "Stops", "call_types": ["A"]},
        "crashes": {"label": "Crashes", "call_types": ["B"]},
        "patrol": {"label": "Directed Patrol", "call_types": ["C"]},
    }
    assert parse_categories(tables)[-1] == Category("patrol", "Directed Patrol", ("C",))
