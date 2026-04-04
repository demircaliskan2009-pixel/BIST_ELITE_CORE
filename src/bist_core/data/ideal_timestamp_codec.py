"""
Decode iDeal binary time field (int32 / uint32) to Unix seconds.

Observed on-disk values ~13.7M–20M are **minutes since 2000-01-01 00:00:00**
in **Europe/Istanbul** (not Unix seconds). Values >= 1e9 are treated as Unix seconds.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Final
from zoneinfo import ZoneInfo

# Modern Unix seconds (BIST-relevant history; below int32 max)
_UNIX_LO: Final[int] = 1_000_000_000
_UNIX_HI: Final[int] = 2_147_483_647

# Minutes since 2000-01-01 00:00 Europe/Istanbul.
# Production intraday files use ~13.7M–20M (2024–2030s). Unit tests use small positive steps (1,2,3 / 1000+i).
# Upper bound must stay << 1e9 so we never consume would-be Unix values below the Unix floor.
_IDEAL_MINUTES_LO: Final[int] = 1
_IDEAL_MINUTES_HI: Final[int] = 60_000_000


def _ist_tz():
    try:
        return ZoneInfo("Europe/Istanbul")
    except Exception:
        return timezone(timedelta(hours=3))


def _minutes_anchor_unix() -> int:
    ist = _ist_tz()
    dt = datetime(2000, 1, 1, 0, 0, 0, tzinfo=ist)
    return int(dt.timestamp())


_ANCHOR_UNIX: Final[int] = _minutes_anchor_unix()


def is_market_time(ts: int) -> bool:
    """BIST cash-style hour gate in Europe/Istanbul (deterministic across hosts)."""
    from datetime import datetime

    ist = _ist_tz()
    dt = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(ist)
    return 9 <= dt.hour <= 18


def _encoding_for_label(label: str) -> str:
    if label == "unix":
        return "unix_seconds"
    if label == "minutes":
        return "minutes_since_2000_01_01_europe_istanbul"
    if label == "uint32_unix":
        return "unix_seconds"
    return label


def decode_ideal_struct_timestamp(raw: int) -> tuple[int, str]:
    """
    Deterministic decode. Returns (unix_seconds, encoding_label).

    Raises:
        TypeError: not int
        ValueError: cannot map to Unix seconds
    """
    if not isinstance(raw, int):
        raise TypeError(f"IDEAL_TS_TYPE: expected int, got {type(raw).__name__}")

    # sanity window: 2010–2035
    MIN_TS = 1262304000  # 2010-01-01
    MAX_TS = 2051222400  # 2035-01-01

    candidates: list[tuple[str, int]] = []

    if _UNIX_LO <= raw <= _UNIX_HI:
        candidates.append(("unix", raw))

    if _IDEAL_MINUTES_LO <= raw <= _IDEAL_MINUTES_HI:
        candidates.append(("minutes", _ANCHOR_UNIX + raw * 60))

    if raw < 0:
        u32 = raw & 0xFFFFFFFF
        if _UNIX_LO <= u32 <= _UNIX_HI:
            candidates.append(("uint32_unix", u32))

    valid_candidates: list[tuple[int, str]] = []

    for label, ts in candidates:
        in_range = MIN_TS <= ts <= MAX_TS
        market_ok = is_market_time(ts)
        # Minutes-since-2000 is intraday-oriented: require session hours.
        # Unix on-disk values include daily bars outside 09–18 local.
        eligible = in_range and (label != "minutes" or market_ok)
        if eligible:
            valid_candidates.append((ts, label))

    if valid_candidates:
        best_ts, best_label = max(valid_candidates, key=lambda x: x[0])
        return best_ts, _encoding_for_label(best_label)

    if candidates:
        raise ValueError(f"INVALID_TIMESTAMP_ENCODING: {raw}")
    raise ValueError(f"IDEAL_TIMESTAMP_UNDECODABLE: {raw}")


__all__ = [
    "decode_ideal_struct_timestamp",
]
