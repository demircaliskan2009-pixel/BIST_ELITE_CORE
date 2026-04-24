"""iDeal timestamp codec tests — verified epoch 1987-05-30 00:00 TRT.

Epoch verification evidence:
  .60 ts=333969 → 2025-07-04 09:00 TRT (exact match, Fri BIST open)
  .60 ts=333945 → 2025-07-03 09:00 TRT (exact match, Thu BIST open)
  .G  dc=778078 → 2025-07-07 (Mon), dc=764379 → 1988-01-04 (Mon)
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from bist_core.data.ideal_timestamp_codec import (
    DAILY_EPOCH_UNIX,
    INTRADAY_EPOCH_UNIX,
    decode_ideal_struct_timestamp,
    decode_ideal_timestamp,
    is_market_time,
)

IST = ZoneInfo("Europe/Istanbul")


# ---------------------------------------------------------------------------
# decode_ideal_timestamp (timeframe-aware, primary API)
# ---------------------------------------------------------------------------

class TestDecodeIdealTimestamp:
    """Tests for the timeframe-aware decoder."""

    def test_60_bar_decodes_to_bist_open_fri_jul4(self) -> None:
        unix = decode_ideal_timestamp(333969, "60")
        dt = datetime.fromtimestamp(unix, tz=IST)
        assert dt.year == 2025
        assert dt.month == 7
        assert dt.day == 4
        assert dt.hour == 9
        assert dt.minute == 0

    def test_60_bar_decodes_to_bist_open_thu_jul3(self) -> None:
        unix = decode_ideal_timestamp(333945, "60")
        dt = datetime.fromtimestamp(unix, tz=IST)
        assert dt.year == 2025
        assert dt.month == 7
        assert dt.day == 3
        assert dt.hour == 9
        assert dt.minute == 0

    def test_01_bar_decodes_to_market_hours(self) -> None:
        # .01 ts=15217538 → 2016-05-04 17:38 TRT
        unix = decode_ideal_timestamp(15217538, "01")
        dt = datetime.fromtimestamp(unix, tz=IST)
        assert dt.year == 2016
        assert dt.month == 5
        assert dt.day == 4
        assert 8 <= dt.hour <= 18

    def test_05_bar_decodes_correctly(self) -> None:
        # .05 ts=14103930 → 2014-03-23
        unix = decode_ideal_timestamp(14103930, "05")
        dt = datetime.fromtimestamp(unix, tz=IST)
        assert dt.year == 2014
        assert dt.month == 3

    def test_g_daily_bar_decodes_to_correct_date(self) -> None:
        unix = decode_ideal_timestamp(778078, "G")
        dt = datetime.fromtimestamp(unix, tz=timezone.utc)
        assert dt.year == 2025
        assert dt.month == 7
        assert dt.day == 7

    def test_g_early_daily_bar(self) -> None:
        unix = decode_ideal_timestamp(764379, "G")
        dt = datetime.fromtimestamp(unix, tz=timezone.utc)
        assert dt.year == 1988
        assert dt.month == 1
        assert dt.day == 4

    def test_invalid_tf_raises(self) -> None:
        with pytest.raises(ValueError, match="IDEAL_TS_UNKNOWN_TF"):
            decode_ideal_timestamp(100, "XX")

    def test_out_of_range_raises(self) -> None:
        # ts=0 for .01 → epoch + 0 = 1987, which is within sanity window
        # Use a negative value that produces a date before 1986
        with pytest.raises(ValueError, match="IDEAL_TS_OUT_OF_RANGE"):
            decode_ideal_timestamp(-1_000_000, "01")

    def test_type_error_on_non_int(self) -> None:
        with pytest.raises(TypeError, match="IDEAL_TS_TYPE"):
            decode_ideal_timestamp(3.14, "01")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# decode_ideal_struct_timestamp (legacy auto-detect)
# ---------------------------------------------------------------------------

class TestDecodeIdealStructTimestamp:
    """Tests for the legacy auto-detect decoder."""

    def test_unix_identity(self) -> None:
        u = 1_704_067_200  # 2024-01-01 00:00 UTC
        got, enc = decode_ideal_struct_timestamp(u)
        assert got == u
        assert enc == "unix_seconds"

    def test_minutes_range_decodes(self) -> None:
        # .01-style value in minutes range
        got, enc = decode_ideal_struct_timestamp(15217538)
        assert enc == "minutes_since_19870530_europe_istanbul"
        dt = datetime.fromtimestamp(got, tz=IST)
        assert dt.year == 2016

    def test_hours_range_decodes(self) -> None:
        # .60-style value in hours range
        got, enc = decode_ideal_struct_timestamp(333969)
        assert enc == "hours_since_19870530_europe_istanbul"
        dt = datetime.fromtimestamp(got, tz=IST)
        assert dt.year == 2025
        assert dt.month == 7
        assert dt.day == 4

    def test_daily_range_decodes(self) -> None:
        got, enc = decode_ideal_struct_timestamp(778078)
        assert enc == "days_since_daily_epoch"
        dt = datetime.fromtimestamp(got, tz=timezone.utc)
        assert dt.year == 2025
        assert dt.month == 7
        assert dt.day == 7

    def test_undecodable_raises(self) -> None:
        with pytest.raises(ValueError, match="IDEAL_TIMESTAMP_UNDECODABLE"):
            decode_ideal_struct_timestamp(0)

    def test_type_error(self) -> None:
        with pytest.raises(TypeError, match="IDEAL_TS_TYPE"):
            decode_ideal_struct_timestamp("abc")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Epoch constants
# ---------------------------------------------------------------------------

class TestEpochConstants:
    def test_intraday_epoch(self) -> None:
        assert INTRADAY_EPOCH_UNIX == 549_320_400

    def test_daily_epoch(self) -> None:
        assert DAILY_EPOCH_UNIX == -65_474_092_800

    def test_market_time_during_session(self) -> None:
        # 2025-07-04 10:00 TRT = within BIST session
        unix = INTRADAY_EPOCH_UNIX + 333970 * 3600
        assert is_market_time(unix)

    def test_market_time_outside_session(self) -> None:
        # Very early morning should fail
        unix = INTRADAY_EPOCH_UNIX + 333960 * 3600  # ~23:00 previous day
        assert not is_market_time(unix)
