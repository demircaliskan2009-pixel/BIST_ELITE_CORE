"""BIST session scheduler — market hours, interval loop support."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

BIST_TZ = timezone(timedelta(hours=3))
BIST_START = time(10, 0)
BIST_END = time(18, 0)
BUFFER_START = time(9, 55)
BUFFER_END = time(18, 10)


def is_market_open(now: datetime | None = None) -> bool:
    now = now or datetime.now(BIST_TZ)
    t = now.time()
    if BUFFER_START <= t <= BUFFER_END:
        return True
    return False


def is_within_bist_session(now: datetime | None = None) -> bool:
    now = now or datetime.now(BIST_TZ)
    t = now.time()
    return BIST_START <= t <= BIST_END


__all__ = ["is_market_open", "is_within_bist_session", "BIST_TZ", "BIST_START", "BIST_END", "BUFFER_START", "BUFFER_END"]
