"""Tests for BIST scheduler."""

from __future__ import annotations

from datetime import datetime, time, timezone

import pytest

from bist_core.live.scheduler import BIST_TZ, is_market_open


def test_scheduler_market_hours() -> None:
    before = datetime(2024, 1, 15, 9, 50, tzinfo=BIST_TZ)
    assert not is_market_open(before)
    during = datetime(2024, 1, 15, 10, 30, tzinfo=BIST_TZ)
    assert is_market_open(during)
    after = datetime(2024, 1, 15, 18, 15, tzinfo=BIST_TZ)
    assert not is_market_open(after)
    buffer_start = datetime(2024, 1, 15, 9, 55, tzinfo=BIST_TZ)
    assert is_market_open(buffer_start)
    buffer_end = datetime(2024, 1, 15, 18, 10, tzinfo=BIST_TZ)
    assert is_market_open(buffer_end)
