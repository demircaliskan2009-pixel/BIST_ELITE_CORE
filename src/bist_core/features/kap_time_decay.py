"""Time decay for KAP alpha — deterministic, fail-closed."""

from __future__ import annotations


def compute_time_decay(event_ts: int, now_ts: int) -> float:
    """
    Decay factor from event age in minutes.

    <5 min → 1.0
    <30 min → 0.7
    <120 min → 0.4
    else → 0.1

    Invalid timestamps (non-int, negative, event after now) → 0.0.
    """
    try:
        et = int(event_ts)
        nt = int(now_ts)
    except (TypeError, ValueError):
        return 0.0
    if et < 0 or nt < 0 or et > nt:
        return 0.0

    age_min = (nt - et) / 60.0
    if age_min < 5.0:
        return 1.0
    if age_min < 30.0:
        return 0.7
    if age_min < 120.0:
        return 0.4
    return 0.1


__all__ = ["compute_time_decay"]
