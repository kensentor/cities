"""What the environment and the packaged configuration say, and nothing more. Read only by composition."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from importlib import resources
from pathlib import Path

from cities.melrose.domain.places import BoundaryThresholds
from cities.melrose.domain.public import Category
from cities.melrose.domain.reference import ReferenceLayer

# Week of Jul 20, 2026: where collection starts (design spec R1).
COLLECT_SINCE = date(2026, 7, 20)
USER_AGENT = "cities-melrose/0.1 (personal research: a map of the published Melrose dispatch logs)"
REQUEST_INTERVAL_S = 2.0
REQUEST_TIMEOUT_S = 60.0

# Appendix C rule 5: the spec's own settings, not measured; Ken reviews the boundary streets they give (Q2).
BOUNDARY_RULE = BoundaryThresholds(edge_m=40.0, window_m=60.0, along_m=20.0, share=0.6)

REFERENCE_LAYERS: tuple[ReferenceLayer, ...] = (
    ReferenceLayer(
        name="address_points",
        url="https://arcgisserver.digital.mass.gov/arcgisserver/rest/services/AGOL/MassGIS_Master_Address_Points/FeatureServer/0",
        where="GEOGRAPHIC_TOWN='MELROSE'",
        out_fields=("MASTER_ADDRESS_ID", "FULL_NUMBER_STANDARDIZED", "STREET_NAME"),
    ),
    ReferenceLayer(
        name="roads",
        url="https://services1.arcgis.com/hGdibHYSPO59RG1h/ArcGIS/rest/services/MassDOTRoads_gdb/FeatureServer/0",
        where="MGIS_TOWN='MELROSE'",
        out_fields=("RD_SEG_ID", "STREET_NAME", "AADT"),
    ),
    ReferenceLayer(
        name="wards",
        url="https://services1.arcgis.com/hGdibHYSPO59RG1h/ArcGIS/rest/services/Wards_Precincts_gdb/FeatureServer/0",
        where="TOWN='MELROSE'",
        out_fields=("WP_NAME", "WARD", "PRECINCT"),
    ),
)


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path  # data/melrose
    export_dir: Path  # site/public/data/melrose, which the map page reads
    since: date
    user_agent: str
    request_interval_s: float
    request_timeout_s: float
    known_call_types: frozenset[str]
    reference_layers: tuple[ReferenceLayer, ...]
    boundary_rule: BoundaryThresholds
    categories: tuple[Category, ...]

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def reference_dir(self) -> Path:
        return self.data_dir / "reference"

    @property
    def database(self) -> Path:
        return self.data_dir / "db.sqlite"


def load_settings(environ: Mapping[str, str] = os.environ) -> Settings:
    """`CITIES_DATA_DIR` overrides the data root, which defaults to ./data in the working directory, and
    `CITIES_SITE_DATA_DIR` the map page's data root, which defaults to ./site/public/data."""
    root = Path(environ.get("CITIES_DATA_DIR", "data"))
    site_root = Path(environ.get("CITIES_SITE_DATA_DIR", "site/public/data"))
    return Settings(
        data_dir=root / "melrose",
        export_dir=site_root / "melrose",
        since=COLLECT_SINCE,
        user_agent=USER_AGENT,
        request_interval_s=REQUEST_INTERVAL_S,
        request_timeout_s=REQUEST_TIMEOUT_S,
        known_call_types=known_call_types(),
        reference_layers=REFERENCE_LAYERS,
        boundary_rule=BOUNDARY_RULE,
        categories=categories(),
    )


def known_call_types() -> frozenset[str]:
    """Every call type seen in collected logs so far; `collect` reports any it has not seen."""
    text = resources.files("cities.melrose").joinpath("call_types.txt").read_text(encoding="utf-8")
    return frozenset(line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#"))


def categories() -> tuple[Category, ...]:
    """The categories the map shows, in the file's order (technical spec T14)."""
    text = resources.files("cities.melrose").joinpath("categories.toml").read_text(encoding="utf-8")
    return parse_categories(tomllib.loads(text))


def parse_categories(tables: Mapping[str, object]) -> tuple[Category, ...]:
    """Raises ValueError for a file the page could not use: a category without a label or call types,
    a call type in two categories, or no `stops` or `crashes`, which the ward table and ranking read."""
    found: list[Category] = []
    for key, table in tables.items():
        if not isinstance(table, dict):
            raise ValueError(f"categories.toml: [{key}] is not a table")
        label, call_types = table.get("label"), table.get("call_types")
        if not isinstance(label, str) or not label:
            raise ValueError(f"categories.toml: [{key}] needs a label")
        if not isinstance(call_types, list) or not call_types or not all(isinstance(t, str) and t for t in call_types):
            raise ValueError(f"categories.toml: [{key}] needs a list of call types")
        found.append(Category(key, label, tuple(call_types)))
    seen: dict[str, str] = {}
    for category in found:
        for call_type in category.call_types:
            if call_type in seen:
                raise ValueError(f"categories.toml: {call_type!r} is in both [{seen[call_type]}] and [{category.key}]")
            seen[call_type] = category.key
    missing = {"stops", "crashes"} - {c.key for c in found}
    if missing:
        raise ValueError(f"categories.toml: missing [{'], ['.join(sorted(missing))}]")
    return tuple(found)
