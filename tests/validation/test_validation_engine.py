"""Validation engine unit tests — metrics, drawdown, regimes, pass/fail logic."""

from __future__ import annotations

import pytest

from bist_core.validation.validation_engine import (
    ValidationEngine,
    ValidationThresholds,
    compute_metrics_from_trades,
    segment_by_regime,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _closed_trade(
    pnl: float,
    entry_price: float = 100.0,
    stop_price: float = 95.0,
    r_multiple: float | None = None,
    entry_time: str = "2026-01-01",
) -> dict:
    risk = entry_price - stop_price
    if r_multiple is None and risk > 0:
        r_multiple = round(pnl / (risk * 10), 4)
    return {
        "trade_id": "t",
        "symbol": "SYM",
        "entry_price": entry_price,
        "stop_price": stop_price,
        "target_price": entry_price * 1.1,
        "position_size": 10,
        "entry_time": entry_time,
        "exit_time": "2026-01-02",
        "status": "CLOSED",
        "pnl": pnl,
        "fees": 0,
        "slippage": 0,
        "r_multiple": r_multiple,
    }


def _equity_curve(values: list[float]) -> list[dict]:
    return [
        {"timestamp": f"2026-01-{i + 1:02d}", "equity": v, "close": v}
        for i, v in enumerate(values)
    ]


# ── Metric calculations ──────────────────────────────────────────────────

class TestMetricCalculations:
    def test_expectancy_positive(self) -> None:
        trades = [_closed_trade(100), _closed_trade(50), _closed_trade(-30)]
        m = compute_metrics_from_trades(trades)
        assert m["expectancy"] == pytest.approx(40.0, abs=0.01)

    def test_expectancy_negative(self) -> None:
        trades = [_closed_trade(-100), _closed_trade(-50), _closed_trade(30)]
        m = compute_metrics_from_trades(trades)
        assert m["expectancy"] < 0

    def test_win_rate(self) -> None:
        trades = [_closed_trade(100), _closed_trade(-50)]
        m = compute_metrics_from_trades(trades)
        assert m["win_rate"] == 0.5

    def test_profit_factor(self) -> None:
        trades = [_closed_trade(200), _closed_trade(-100)]
        m = compute_metrics_from_trades(trades)
        assert m["profit_factor"] == pytest.approx(2.0, abs=0.01)

    def test_profit_factor_no_losses(self) -> None:
        trades = [_closed_trade(100)]
        m = compute_metrics_from_trades(trades)
        assert m["profit_factor"] == float("inf")

    def test_avg_r_multiple(self) -> None:
        trades = [
            _closed_trade(50, r_multiple=1.0),
            _closed_trade(100, r_multiple=2.0),
        ]
        m = compute_metrics_from_trades(trades)
        assert m["avg_R_multiple"] == pytest.approx(1.5, abs=0.01)

    def test_empty_trades(self) -> None:
        m = compute_metrics_from_trades([])
        assert m["expectancy"] == 0.0
        assert m["closed_trades"] == 0

    def test_sharpe_ratio_from_equity(self) -> None:
        curve = _equity_curve([100_000, 101_000, 102_000, 103_000])
        trades = [_closed_trade(3000)]
        m = compute_metrics_from_trades(trades, curve, 100_000)
        assert m["sharpe_ratio"] > 0


# ── Drawdown computation ─────────────────────────────────────────────────

class TestDrawdownComputation:
    def test_max_drawdown_percentage(self) -> None:
        curve = _equity_curve([100_000, 110_000, 95_000, 105_000])
        trades = [_closed_trade(5000)]
        m = compute_metrics_from_trades(trades, curve, 100_000)
        expected_dd_pct = ((110_000 - 95_000) / 110_000) * 100.0
        assert m["max_drawdown"] == pytest.approx(expected_dd_pct, abs=0.1)

    def test_zero_drawdown(self) -> None:
        curve = _equity_curve([100_000, 101_000, 102_000])
        m = compute_metrics_from_trades([], curve, 100_000)
        assert m["max_drawdown"] == 0.0

    def test_drawdown_with_no_equity_curve(self) -> None:
        trades = [_closed_trade(100)]
        m = compute_metrics_from_trades(trades, None)
        assert m["max_drawdown"] == 0.0


# ── Regime segmentation ──────────────────────────────────────────────────

class TestRegimeSegmentation:
    def test_bullish_regime_detected(self) -> None:
        values = [100_000 + i * 500 for i in range(40)]
        curve = _equity_curve(values)
        trades = [_closed_trade(1000, entry_time=f"2026-01-{i + 1:02d}") for i in range(5)]
        regimes = segment_by_regime(curve, trades, window_size=20)
        assert "bullish" in regimes
        assert "bearish" in regimes
        assert "sideways" in regimes

    def test_bearish_regime_detected(self) -> None:
        values = [100_000 - i * 500 for i in range(40)]
        curve = _equity_curve(values)
        trades = [_closed_trade(-500, entry_time=f"2026-01-{i + 1:02d}") for i in range(5)]
        regimes = segment_by_regime(curve, trades, window_size=20)
        assert regimes["bearish"]["window_count"] >= 1 or regimes["sideways"]["window_count"] >= 1

    def test_empty_curve(self) -> None:
        regimes = segment_by_regime([], [])
        for regime in ("bullish", "bearish", "sideways"):
            assert regimes[regime]["window_count"] == 0

    def test_regime_metrics_have_required_keys(self) -> None:
        values = [100_000 + i * 300 for i in range(40)]
        curve = _equity_curve(values)
        regimes = segment_by_regime(curve, [], window_size=20)
        for regime_data in regimes.values():
            assert "expectancy" in regime_data
            assert "profit_factor" in regime_data
            assert "win_rate" in regime_data
            assert "max_drawdown" in regime_data


# ── Validation pass/fail ─────────────────────────────────────────────────

class TestValidationPassFail:
    def test_valid_strategy(self) -> None:
        trades = [_closed_trade(200), _closed_trade(150), _closed_trade(-50)]
        curve = _equity_curve([100_000, 100_200, 100_350, 100_300])
        result = {"trades": trades, "equity_curve": curve}
        engine = ValidationEngine(ValidationThresholds(
            min_expectancy=0.0,
            min_profit_factor=1.2,
            max_drawdown_pct=20.0,
        ))
        v = engine.validate(result)
        assert v["valid"] is True
        assert v["warnings"] == []
        assert "metrics" in v
        assert "regime_metrics" in v

    def test_fail_low_expectancy(self) -> None:
        trades = [_closed_trade(-100), _closed_trade(-50), _closed_trade(30)]
        curve = _equity_curve([100_000, 99_900, 99_850, 99_880])
        result = {"trades": trades, "equity_curve": curve}
        engine = ValidationEngine(ValidationThresholds(min_expectancy=0.0))
        v = engine.validate(result)
        assert v["valid"] is False
        assert any("expectancy" in w for w in v["warnings"])

    def test_fail_low_profit_factor(self) -> None:
        trades = [_closed_trade(100), _closed_trade(-90)]
        curve = _equity_curve([100_000, 100_010])
        result = {"trades": trades, "equity_curve": curve}
        engine = ValidationEngine(ValidationThresholds(
            min_expectancy=-999,
            min_profit_factor=1.5,
        ))
        v = engine.validate(result)
        assert v["valid"] is False
        assert any("profit_factor" in w for w in v["warnings"])

    def test_fail_high_drawdown(self) -> None:
        curve = _equity_curve([100_000, 110_000, 80_000, 90_000])
        trades = [_closed_trade(-10_000)]
        result = {"trades": trades, "equity_curve": curve}
        engine = ValidationEngine(ValidationThresholds(
            min_expectancy=-999,
            min_profit_factor=0.0,
            max_drawdown_pct=20.0,
        ))
        v = engine.validate(result)
        assert v["valid"] is False
        assert any("max_drawdown" in w for w in v["warnings"])

    def test_fail_no_trades(self) -> None:
        result = {"trades": [], "equity_curve": []}
        engine = ValidationEngine()
        v = engine.validate(result)
        assert v["valid"] is False
        assert "no_closed_trades" in v["warnings"]

    def test_optional_win_rate_threshold(self) -> None:
        trades = [_closed_trade(100), _closed_trade(-50), _closed_trade(-40)]
        curve = _equity_curve([100_000, 100_010])
        result = {"trades": trades, "equity_curve": curve}
        engine = ValidationEngine(ValidationThresholds(
            min_expectancy=-999,
            min_profit_factor=0.0,
            max_drawdown_pct=100.0,
            min_win_rate=0.5,
        ))
        v = engine.validate(result)
        assert v["valid"] is False
        assert any("win_rate" in w for w in v["warnings"])

    def test_structured_output_schema(self) -> None:
        trades = [_closed_trade(100)]
        curve = _equity_curve([100_000, 100_100])
        result = {"trades": trades, "equity_curve": curve}
        engine = ValidationEngine()
        v = engine.validate(result)
        assert "valid" in v
        assert "metrics" in v
        assert "regime_metrics" in v
        assert "warnings" in v
        assert isinstance(v["valid"], bool)
        assert isinstance(v["metrics"], dict)
        assert isinstance(v["regime_metrics"], dict)
        assert isinstance(v["warnings"], list)


# ── Determinism ───────────────────────────────────────────────────────────

class TestDeterminism:
    def test_identical_inputs_identical_outputs(self) -> None:
        trades = [_closed_trade(200), _closed_trade(-100)]
        curve = _equity_curve([100_000, 100_200, 100_100])
        result = {"trades": trades, "equity_curve": curve}
        engine = ValidationEngine()
        v1 = engine.validate(result)
        v2 = engine.validate(result)
        assert v1 == v2
