"""DataValidator OHLC vs reference."""

from __future__ import annotations

from bist_core.live.data_validator import DataValidator


def test_compare_ohlc_to_ref() -> None:
    v = DataValidator(threshold=0.02)
    assert v.compare_ohlc_to_ref(100.0, 101.0, 99.0, 100.5, 100.0) is True
    assert v.compare_ohlc_to_ref(100.0, 101.0, 99.0, 100.5, 120.0) is False
