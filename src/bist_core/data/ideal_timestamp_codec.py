"""
Decode iDeal binary time field to Unix seconds.

Empirically verified encoding (2025-07-07 forensic analysis):

  .01 / .05 files: ts = MINUTES since 1987-05-30 00:00:00 Europe/Istanbul
  .60 files:       ts = HOURS   since 1987-05-30 00:00:00 Europe/Istanbul
  .G  files:       dc = CALENDAR DAYS, dc → Unix = EPOCH_G + dc × 86400

Verification evidence:
  .60 ts=333969 → 2025-07-04 09:00 TRT (exact match, Fri BIST open)
  .60 ts=333945 → 2025-07-03 09:00 TRT (exact match, Thu BIST open)
  .60 ts=333921 → 2025-07-02 09:00 TRT (exact match, Wed BIST open)
  .60 ts=333897 → 2025-07-01 09:00 TRT (exact match, Tue BIST open)
  .G  dc=778078 → 2025-07-07 (Mon), dc=778075 → 2025-07-04 (Fri)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Final
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Epoch constants — empirically verified
# ---------------------------------------------------------------------------

# Intraday epoch: 1987-05-30 00:00:00 Europe/Istanbul (UTC+3 summer)
# = 1987-05-29 21:00:00 UTC = Unix 549320400
_INTRADAY_EPOCH_UNIX: Final[int] = 549_320_400

# Daily (.G) epoch: ancient reference (~106 BCE)
# dc → Unix = _DAILY_EPOCH_UNIX + dc × 86400
# Verified: dc=778078 → 2025-07-07, dc=764379 → 1988-01-04
_DAILY_EPOCH_UNIX: Final[int] = -65_474_092_800

# Timeframe → seconds-per-unit mapping
_TF_UNIT_SECONDS: Final[dict[str, int]] = {
    "01": 60,      # 1 minute
    "05": 60,      # 1 minute (bars increment by 5)
    "60": 3600,    # 1 hour
    "G": 86400,    # 1 day (uses daily epoch)
}

# Sanity window: 1986–2035 (full BIST history + daily data starting 1988)
_SANITY_MIN_TS: Final[int] = 504_921_600   # 1986-01-01
_SANITY_MAX_TS: Final[int] = 2_051_222_400   # 2035-01-01

# Valid raw value ranges per timeframe (empirically observed)
# .01: 14M–21M (minutes), .05: 14M–21M, .60: 190K–340K (hours), .G: 760K–780K (days)
_RAW_RANGES: Final[dict[str, tuple[int, int]]] = {
    "01": (10_000_000, 30_000_000),
    "05": (10_000_000, 30_000_000),
    "60": (100_000, 500_000),
    "G":  (700_000, 900_000),
}


def _ist_tz() -> ZoneInfo | timezone:
    try:
        return ZoneInfo("Europe/Istanbul")
    except Exception:
        return timezone(timedelta(hours=3))


def is_market_time(ts: int) -> bool:
    """BIST cash-style hour gate in Europe/Istanbul."""
    ist = _ist_tz()
    dt = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(ist)
    return 8 <= dt.hour <= 18


def decode_ideal_timestamp(raw: int, timeframe: str) -> int:
    """
    Decode iDeal binary timestamp to Unix seconds (deterministic, fail-closed).

    Args:
        raw: Raw int32 timestamp from the binary record.
        timeframe: One of "01", "05", "60", "G".

    Returns:
        Unix timestamp in seconds.

    Raises:
        TypeError: raw is not int.
        ValueError: raw out of plausible range or decoded ts out of sanity window.
    """
    if not isinstance(raw, int):
        raise TypeError(f"IDEAL_TS_TYPE: expected int, got {type(raw).__name__}")

    tf = str(timeframe).strip().lstrip(".").upper()

    if tf == "G":
        unix_ts = _DAILY_EPOCH_UNIX + raw * 86400
    else:
        unit_sec = _TF_UNIT_SECONDS.get(tf)
        if unit_sec is None:
            raise ValueError(f"IDEAL_TS_UNKNOWN_TF: {timeframe}")
        unix_ts = _INTRADAY_EPOCH_UNIX + raw * unit_sec

    if not (_SANITY_MIN_TS <= unix_ts <= _SANITY_MAX_TS):
        raise ValueError(
            f"IDEAL_TS_OUT_OF_RANGE: raw={raw} tf={tf} "
            f"unix={unix_ts} range=[{_SANITY_MIN_TS},{_SANITY_MAX_TS}]"
        )

    return unix_ts


def decode_ideal_struct_timestamp(raw: int) -> tuple[int, str]:
    """
    Legacy auto-detect decode (backward compatible).

    Tries intraday-minutes first (most common), then daily, then Unix literal.
    Returns (unix_seconds, encoding_label).

    Raises:
        TypeError: not int
        ValueError: cannot map to Unix seconds
    """
    if not isinstance(raw, int):
        raise TypeError(f"IDEAL_TS_TYPE: expected int, got {type(raw).__name__}")

    # Try intraday minutes (covers .01 and .05 range: ~14M–20M)
    lo_m, hi_m = _RAW_RANGES["01"]
    if lo_m <= raw <= hi_m:
        unix_ts = _INTRADAY_EPOCH_UNIX + raw * 60
        if _SANITY_MIN_TS <= unix_ts <= _SANITY_MAX_TS:
            return unix_ts, "minutes_since_19870530_europe_istanbul"

    # Try intraday hours (covers .60 range: ~190K–340K)
    lo_h, hi_h = _RAW_RANGES["60"]
    if lo_h <= raw <= hi_h:
        unix_ts = _INTRADAY_EPOCH_UNIX + raw * 3600
        if _SANITY_MIN_TS <= unix_ts <= _SANITY_MAX_TS:
            return unix_ts, "hours_since_19870530_europe_istanbul"

    # Try daily (covers .G range: ~760K–780K)
    lo_d, hi_d = _RAW_RANGES["G"]
    if lo_d <= raw <= hi_d:
        unix_ts = _DAILY_EPOCH_UNIX + raw * 86400
        if _SANITY_MIN_TS <= unix_ts <= _SANITY_MAX_TS:
            return unix_ts, "days_since_daily_epoch"

    # Try raw Unix seconds (>= 1e9)
    if 1_000_000_000 <= raw <= 2_147_483_647:
        if _SANITY_MIN_TS <= raw <= _SANITY_MAX_TS:
            return raw, "unix_seconds"

    # Negative int32 → treat as uint32 Unix
    if raw < 0:
        u32 = raw & 0xFFFFFFFF
        if 1_000_000_000 <= u32 <= 2_147_483_647:
            if _SANITY_MIN_TS <= u32 <= _SANITY_MAX_TS:
                return u32, "unix_seconds"

    raise ValueError(f"IDEAL_TIMESTAMP_UNDECODABLE: {raw}")


# Public constants for external use
INTRADAY_EPOCH_UNIX: Final[int] = _INTRADAY_EPOCH_UNIX
DAILY_EPOCH_UNIX: Final[int] = _DAILY_EPOCH_UNIX
TF_UNIT_SECONDS: Final[dict[str, int]] = dict(_TF_UNIT_SECONDS)


__all__ = [
    "decode_ideal_struct_timestamp",
    "decode_ideal_timestamp",
    "is_market_time",
    "INTRADAY_EPOCH_UNIX",
    "DAILY_EPOCH_UNIX",
    "TF_UNIT_SECONDS",
]
