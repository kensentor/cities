"""Clock over the system clock."""

from __future__ import annotations

from datetime import UTC, datetime

from cities.melrose.ports.outbound import Clock


class SystemClock(Clock):
    __slots__ = ()

    def now(self) -> datetime:
        return datetime.now(UTC).replace(microsecond=0)
