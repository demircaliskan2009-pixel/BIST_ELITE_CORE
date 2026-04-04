"""Matriks adapter unit tests — conversion, sorting, validation, symbol normalization, determinism."""

from __future__ import annotations

import pytest

from bist_core.data.matriks_adapter import (
    convert_bar,
    convert_bars,
    normalize_symbol,
    prepare_bars_for_backtest,
)


# ── Symbol normalization ──────────────────────────────────────────────────

class TestSymbolNormalization:
    def test_uppercase(self) -> None:
        assert normalize_symbol("garan") == "GARAN"

    def test_strip_whitespace(self) -> None:
        assert normalize_symbol("  ASELS  ") == "ASELS"

    def test_strip_vendor_suffix_e(self) -> None:
        assert normalize_symbol("THYAO.E") == "THYAO"

    def test_strip_vendor_suffix_is(self) -> None:
        assert normalize_symbol("AKBNK.IS") == "AKBNK"

    def test_strip_vendor_suffix_bist(self) -> None:
        assert normalize_symbol("EREGL.BIST") == "EREGL"

    def test_empty_returns_empty(self) -> None:
        assert normalize_symbol("") == ""

    def test_none_returns_empty(self) -> None:
        assert normalize_symbol(None) == ""

    def test_no_suffix_unchanged(self) -> None:
        assert normalize_symbol("TUPRS") == "TUPRS"


# ── Single bar conversion ────────────────────────────────────────────────

class TestConvertBar:
    def test_valid_bar(self) -> None:
        raw = {
            "symbol": "GARAN",
            "date": "2026-01-15",
            "time": "10:00:00",
            "open": 30.5,
            "high": 31.0,
            "low": 30.0,
            "close": 30.8,
            "volume": 1_000_000,
        }
        bar = convert_bar(raw)
        assert bar is not None
        assert bar.symbol == "GARAN"
        assert bar.timestamp == "2026-01-15T10:00:00"
        assert bar.open == 30.5
        assert bar.high == 31.0
        assert bar.low == 30.0
        assert bar.close == 30.8
        assert bar.volume == 1_000_000

    def test_date_only_no_time(self) -> None:
        raw = {"symbol": "X", "date": "2026-01-15", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}
        bar = convert_bar(raw)
        assert bar is not None
        assert bar.timestamp == "2026-01-15"

    def test_timestamp_field(self) -> None:
        raw = {"symbol": "X", "timestamp": "2026-01-15T09:30:00", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}
        bar = convert_bar(raw)
        assert bar is not None
        assert bar.timestamp == "2026-01-15T09:30:00"

    def test_default_symbol(self) -> None:
        raw = {"date": "2026-01-15", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}
        bar = convert_bar(raw, default_symbol="ASELS")
        assert bar is not None
        assert bar.symbol == "ASELS"

    def test_reject_missing_open(self) -> None:
        raw = {"symbol": "X", "date": "2026-01-15", "high": 2, "low": 0.5, "close": 1.5, "volume": 100}
        assert convert_bar(raw) is None

    def test_reject_missing_close(self) -> None:
        raw = {"symbol": "X", "date": "2026-01-15", "open": 1, "high": 2, "low": 0.5, "volume": 100}
        assert convert_bar(raw) is None

    def test_reject_negative_price(self) -> None:
        raw = {"symbol": "X", "date": "2026-01-15", "open": -1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}
        assert convert_bar(raw) is None

    def test_reject_negative_volume(self) -> None:
        raw = {"symbol": "X", "date": "2026-01-15", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": -100}
        assert convert_bar(raw) is None

    def test_zero_volume_allowed_by_default(self) -> None:
        raw = {"symbol": "X", "date": "2026-01-15", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 0}
        bar = convert_bar(raw)
        assert bar is not None
        assert bar.volume == 0.0

    def test_reject_zero_volume_when_configured(self) -> None:
        raw = {"symbol": "X", "date": "2026-01-15", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 0}
        assert convert_bar(raw, reject_zero_volume=True) is None

    def test_reject_missing_timestamp(self) -> None:
        raw = {"symbol": "X", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}
        assert convert_bar(raw) is None

    def test_reject_missing_symbol_and_no_default(self) -> None:
        raw = {"date": "2026-01-15", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}
        assert convert_bar(raw) is None

    def test_vendor_symbol_normalized(self) -> None:
        raw = {"symbol": "garan.e", "date": "2026-01-15", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}
        bar = convert_bar(raw)
        assert bar is not None
        assert bar.symbol == "GARAN"

    def test_missing_volume_defaults_zero(self) -> None:
        raw = {"symbol": "X", "date": "2026-01-15", "open": 1, "high": 2, "low": 0.5, "close": 1.5}
        bar = convert_bar(raw)
        assert bar is not None
        assert bar.volume == 0.0


# ── Batch conversion & sorting ───────────────────────────────────────────

class TestConvertBars:
    def test_batch_converts_valid(self) -> None:
        raw = [
            {"symbol": "A", "date": "2026-01-02", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
            {"symbol": "A", "date": "2026-01-01", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
        ]
        bars = convert_bars(raw)
        assert len(bars) == 2

    def test_sorted_by_timestamp(self) -> None:
        raw = [
            {"symbol": "A", "date": "2026-01-03", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
            {"symbol": "A", "date": "2026-01-01", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
            {"symbol": "A", "date": "2026-01-02", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
        ]
        bars = convert_bars(raw)
        timestamps = [b.timestamp for b in bars]
        assert timestamps == sorted(timestamps)

    def test_sorted_by_timestamp_then_symbol(self) -> None:
        raw = [
            {"symbol": "B", "date": "2026-01-01", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
            {"symbol": "A", "date": "2026-01-01", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
        ]
        bars = convert_bars(raw)
        assert bars[0].symbol == "A"
        assert bars[1].symbol == "B"

    def test_skips_invalid_bars(self) -> None:
        raw = [
            {"symbol": "A", "date": "2026-01-01", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
            {"symbol": "B", "date": "2026-01-01", "open": -1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
            "not a dict",
        ]
        bars = convert_bars(raw)
        assert len(bars) == 1
        assert bars[0].symbol == "A"

    def test_empty_input(self) -> None:
        assert convert_bars([]) == []

    def test_default_symbol_batch(self) -> None:
        raw = [
            {"date": "2026-01-01", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
        ]
        bars = convert_bars(raw, default_symbol="THYAO")
        assert len(bars) == 1
        assert bars[0].symbol == "THYAO"


# ── prepare_bars_for_backtest ─────────────────────────────────────────────

class TestPrepareForBacktest:
    def test_returns_sorted_bars(self) -> None:
        raw = [
            {"symbol": "X", "date": "2026-01-02", "open": 2, "high": 3, "low": 1, "close": 2.5, "volume": 200},
            {"symbol": "X", "date": "2026-01-01", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
        ]
        bars = prepare_bars_for_backtest(raw)
        assert bars[0].timestamp < bars[1].timestamp

    def test_with_symbol_override(self) -> None:
        raw = [{"date": "2026-01-01", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}]
        bars = prepare_bars_for_backtest(raw, symbol="AKBNK")
        assert bars[0].symbol == "AKBNK"


# ── Determinism ───────────────────────────────────────────────────────────

class TestDeterminism:
    def test_identical_inputs_identical_outputs(self) -> None:
        raw = [
            {"symbol": "A", "date": "2026-01-02", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 500},
            {"symbol": "B", "date": "2026-01-01", "open": 20, "high": 22, "low": 19, "close": 21.0, "volume": 800},
            {"symbol": "A", "date": "2026-01-01", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 500},
        ]
        bars1 = convert_bars(raw)
        bars2 = convert_bars(raw)
        assert len(bars1) == len(bars2)
        for b1, b2 in zip(bars1, bars2):
            assert b1 == b2
