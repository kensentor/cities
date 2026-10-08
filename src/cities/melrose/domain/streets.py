"""How the log abbreviates street names, and how the reference spells them (technical spec Appendix C rule 2)."""

from __future__ import annotations

# Log suffix → reference suffix. Suffixes the two share (PARK, WAY, BROADWAY …) need no entry.
SUFFIXES: dict[str, str] = {
    "ST": "STREET",
    "AVE": "AVENUE",
    "AV": "AVENUE",
    "RD": "ROAD",
    "PKWY": "PARKWAY",
    "PL": "PLACE",
    "DR": "DRIVE",
    "LN": "LANE",
    "TER": "TERRACE",
    "TERR": "TERRACE",
    "TPKE": "TURNPIKE",
    "CIR": "CIRCLE",
    "CT": "COURT",
    "HTS": "HEIGHTS",
    "EXT": "EXTENSION",
    "PLZ": "PLAZA",
    "SQ": "SQUARE",
    "HWY": "HIGHWAY",
    "BLVD": "BOULEVARD",
}
ABBREVIATIONS: dict[str, str] = {full: short for short, full in SUFFIXES.items() if short not in ("AV", "TERR")}

# Leading words the log abbreviates.
ALIASES: dict[str, str] = {"W": "WEST", "E": "EAST", "N": "NORTH", "S": "SOUTH", "MT": "MOUNT"}

# The town code in location labels such as "[MEL 1243]"; any other code is another town.
HOME_TOWN = "MEL"


def abbreviate(name: str) -> str:
    """A reference name in the log's style: "LYNN FELLS PARKWAY" → "LYNN FELLS PKWY"."""
    words = name.split()
    if len(words) > 1 and words[-1] in ABBREVIATIONS:
        words[-1] = ABBREVIATIONS[words[-1]]
    return " ".join(words)


def display(name: str) -> str:
    """A reference name as the ranking shows it: "FRANKLIN STREET" → "Franklin St"."""
    return " ".join(w.capitalize() for w in abbreviate(name).split())
