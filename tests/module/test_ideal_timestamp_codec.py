"""iDeal struct timestamp → Unix seconds (minutes-since-2000-Istanbul vs Unix)."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from bist_core.data.ideal_timestamp_codec import decode_ideal_struct_timestamp


def test_unix_identity_preserved() -> None:
    u = 1_704_067_200
    got, enc = decode_ideal_struct_timestamp(u)
    assert got == u
    assert enc == "unix_seconds"


def test_minutes_since_2000_istanbul_mar_2026_session() -> None:
    ist = ZoneInfo("Europe/Istanbul")
    anchor = datetime(2000, 1, 1, 0, 0, 0, tzinfo=ist)
    base = int(anchor.timestamp())
    # Same minute count as ideal_dataset live check (2026-03-18 09:30 TRT)
    t_open = datetime(2026, 3, 18, 9, 30, 0, tzinfo=ist)
    raw_mins = int((t_open.timestamp() - base) // 60)
    unix_got, enc = decode_ideal_struct_timestamp(raw_mins)
    assert enc == "minutes_since_2000_01_01_europe_istanbul"
    dt = datetime.fromtimestamp(unix_got, tz=ist)
    assert dt.date() == t_open.date()
    assert time(9, 30, 0) <= dt.time() <= time(18, 10, 0)


def test_small_positive_minutes_decode_outside_sanity_window_rejected() -> None:
    """Minute counts that decode before 2010 are rejected (INVALID_TIMESTAMP_ENCODING)."""
    with pytest.raises(ValueError, match="INVALID_TIMESTAMP_ENCODING"):
        decode_ideal_struct_timestamp(1000)


def test_undecodable_raises() -> None:
    with pytest.raises(ValueError, match="IDEAL_TIMESTAMP_UNDECODABLE"):
        decode_ideal_struct_timestamp(70_000_000)
    with pytest.raises(ValueError, match="IDEAL_TIMESTAMP_UNDECODABLE"):
        decode_ideal_struct_timestamp(0)
    with pytest.raises(ValueError, match="IDEAL_TIMESTAMP_UNDECODABLE"):
        decode_ideal_struct_timestamp(-1)
