"""Reading a location as printed: its form and its parts, before any lookup (Appendix C rules 1–2)."""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass

from cities.melrose.domain.places import LocationForm
from cities.melrose.domain.streets import ALIASES, HOME_TOWN, SUFFIXES

_LABEL = re.compile(r"^\[([A-Z]+)\b[^\]]*\]\s*")
_APARTMENT = re.compile(r"\s+Apt\b.*$")
_NUMBERED = re.compile(r"^(\d+)([A-Z]?)\s+(\S.*)$")


@dataclass(frozen=True, slots=True)
class Part:
    number: str | None  # as printed, e.g. "752" or "12A"
    street: str  # as printed, e.g. "FRANKLIN ST"

    @property
    def house_number(self) -> int | None:
        return int(self.number.rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")) if self.number else None


@dataclass(frozen=True, slots=True)
class ParsedLocation:
    form: LocationForm
    parts: tuple[Part, ...] = ()
    town: str | None = None  # the other town's code, for OTHER_TOWN


def parse_location(prefix: str | None, text: str | None) -> ParsedLocation:
    """Rule 1: drop the label, keep the address after the last " - ", drop the apartment."""
    if not text or not text.strip():
        return ParsedLocation(LocationForm.NONE)
    if prefix == "Location":  # this label introduces a named place, never an address
        return ParsedLocation(LocationForm.PLACE)
    rest = " ".join(text.replace("`", " ").split())
    labelled = False
    if m := _LABEL.match(rest):
        if m.group(1) != HOME_TOWN:
            return ParsedLocation(LocationForm.OTHER_TOWN, town=m.group(1))
        rest, labelled = rest[m.end() :], True
    if " - " in rest:
        rest = rest.rsplit(" - ", 1)[1]
    rest = _APARTMENT.sub("", rest).strip()
    sides = [s.strip() for s in rest.split("@") if s.strip()]
    parts = tuple(_part(s) for s in sides[:2])
    if not parts:
        return ParsedLocation(LocationForm.NONE)
    if len(parts) == 2:
        return ParsedLocation(LocationForm.INTERSECTION, parts)
    if parts[0].number is not None:
        return ParsedLocation(LocationForm.ADDRESS, parts)
    # A label followed by a name and no address ("[MEL 13575] FULLER HSE ELDERLY") is a place.
    return ParsedLocation(LocationForm.PLACE if labelled else LocationForm.STREET, parts)


def _part(side: str) -> Part:
    if m := _NUMBERED.match(side):
        return Part(m.group(1) + m.group(2), m.group(3))
    return Part(None, side)


def match_street(printed: str, reference: Collection[str]) -> str | None:
    """Rule 2: the reference street a printed name means, or None when it names no known street.

    Leading abbreviations are expanded (W → WEST) and the suffix spelled out (ST → STREET). A name
    printed without a suffix matches only when exactly one reference street is that name plus one.
    """
    words = printed.upper().replace(".", "").split()
    if not words:
        return None
    if len(words) > 1 and words[0] in ALIASES:
        words[0] = ALIASES[words[0]]
    if len(words) > 1 and words[-1] in SUFFIXES:
        words[-1] = SUFFIXES[words[-1]]
    name = " ".join(words)
    if name in reference:
        return name
    with_suffix = sorted(r for r in reference if r.startswith(name + " ") and len(r.split()) == len(words) + 1)
    return with_suffix[0] if len(with_suffix) == 1 else None
