"""What the environment and the packaged configuration say, and nothing more. Read only by composition."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from importlib import resources
from pathlib import Path

from cities.melrose.domain.reference import ReferenceLayer

# Week of Jul 20, 2026: where collection starts (design spec R1).
COLLECT_SINCE = date(2026, 7, 20)
USER_AGENT = "cities-melrose/0.1 (personal research: a map of the published Melrose dispatch logs)"
REQUEST_INTERVAL_S = 2.0
REQUEST_TIMEOUT_S = 60.0

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
    since: date
    user_agent: str
    request_interval_s: float
    request_timeout_s: float
    known_call_types: frozenset[str]
    reference_layers: tuple[ReferenceLayer, ...]

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
    """`CITIES_DATA_DIR` overrides the data root, which defaults to ./data in the working directory."""
    root = Path(environ.get("CITIES_DATA_DIR", "data"))
    return Settings(
        data_dir=root / "melrose",
        since=COLLECT_SINCE,
        user_agent=USER_AGENT,
        request_interval_s=REQUEST_INTERVAL_S,
        request_timeout_s=REQUEST_TIMEOUT_S,
        known_call_types=known_call_types(),
        reference_layers=REFERENCE_LAYERS,
    )


def known_call_types() -> frozenset[str]:
    """Every call type seen in collected logs so far; `collect` reports any it has not seen."""
    text = resources.files("cities.melrose").joinpath("call_types.txt").read_text(encoding="utf-8")
    return frozenset(line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#"))
