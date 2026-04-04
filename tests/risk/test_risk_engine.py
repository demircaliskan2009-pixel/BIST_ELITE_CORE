"""Trade risk engine unit tests — rejection, sizing, limits, daily loss, reward/risk."""

from __future__ import annotations

import pytest

from bist_core.risk.trade_risk_engine import (
    RiskGateResult,
    RiskProfile,
    TradeRiskGate,
    compute_position_size,
)


# ── Position sizing ───────────────────────────────────────────────────────

class TestPositionSizing:
    def test_basic_sizing(self) -> None:
        size = compute_position_size(
            capital=100_000, entry=100.0, stop=95.0, max_risk_pct=2.0,
        )
        expected = int(100_000 * 0.02 / 5.0)
        assert size == expected

    def test_zero_capital(self) -> None:
        assert compute_position_size(0, 100, 95, 2.0) == 0

    def test_zero_stop_distance(self) -> None:
        assert compute_position_size(100_000, 100, 100, 2.0) == 0

    def test_zero_entry(self) -> None:
        assert compute_position_size(100_000, 0, 95, 2.0) == 0

    def test_floors_to_int(self) -> None:
        size = compute_position_size(10_000, 100.0, 97.0, 1.0)
        assert isinstance(size, int)
        assert size == int(10_000 * 0.01 / 3.0)


# ── Risk rejection ────────────────────────────────────────────────────────

class TestRiskRejection:
    def test_approve_valid_decision(self) -> None:
        gate = TradeRiskGate(RiskProfile(capital=100_000))
        result = gate.evaluate({
            "symbol": "ASELS",
            "entry": 100.0,
            "stop": 95.0,
            "target": 110.0,
            "position_size": 10,
        })
        assert result.approved is True
        assert result.reason == "APPROVED"
        assert result.position_size == 10
        assert result.violations == []

    def test_reject_missing_symbol(self) -> None:
        gate = TradeRiskGate()
        result = gate.evaluate({
            "symbol": "",
            "entry": 100.0,
            "stop": 95.0,
            "target": 110.0,
            "position_size": 10,
        })
        assert result.approved is False
        assert "symbol_empty" in result.violations

    def test_reject_zero_entry(self) -> None:
        gate = TradeRiskGate()
        result = gate.evaluate({
            "symbol": "X",
            "entry": 0,
            "stop": 95.0,
            "target": 110.0,
            "position_size": 10,
        })
        assert result.approved is False
        assert any("entry" in v for v in result.violations)

    def test_reject_zero_stop(self) -> None:
        gate = TradeRiskGate()
        result = gate.evaluate({
            "symbol": "X",
            "entry": 100.0,
            "stop": 0,
            "target": 110.0,
            "position_size": 10,
        })
        assert result.approved is False
        assert any("stop" in v for v in result.violations)

    def test_reject_zero_target(self) -> None:
        gate = TradeRiskGate()
        result = gate.evaluate({
            "symbol": "X",
            "entry": 100.0,
            "stop": 95.0,
            "target": 0,
            "position_size": 10,
        })
        assert result.approved is False
        assert any("target" in v for v in result.violations)

    def test_reject_stop_equals_entry(self) -> None:
        gate = TradeRiskGate()
        result = gate.evaluate({
            "symbol": "X",
            "entry": 100.0,
            "stop": 100.0,
            "target": 110.0,
            "position_size": 10,
        })
        assert result.approved is False
        assert "stop_distance_zero" in result.violations


# ── Reward/risk validation ────────────────────────────────────────────────

class TestRewardRiskValidation:
    def test_reject_low_reward_risk(self) -> None:
        gate = TradeRiskGate(RiskProfile(
            capital=100_000,
            min_reward_risk_ratio=2.0,
        ))
        result = gate.evaluate({
            "symbol": "ASELS",
            "entry": 100.0,
            "stop": 95.0,
            "target": 107.0,
            "position_size": 10,
        })
        assert result.approved is False
        assert any("reward_risk_ratio" in v for v in result.violations)

    def test_approve_good_reward_risk(self) -> None:
        gate = TradeRiskGate(RiskProfile(
            capital=100_000,
            min_reward_risk_ratio=1.5,
        ))
        result = gate.evaluate({
            "symbol": "ASELS",
            "entry": 100.0,
            "stop": 95.0,
            "target": 115.0,
            "position_size": 10,
        })
        assert result.approved is True

    def test_exact_ratio_boundary(self) -> None:
        gate = TradeRiskGate(RiskProfile(
            capital=100_000,
            min_reward_risk_ratio=2.0,
        ))
        result = gate.evaluate({
            "symbol": "X",
            "entry": 100.0,
            "stop": 95.0,
            "target": 110.0,
            "position_size": 10,
        })
        assert result.approved is True


# ── Max open positions ────────────────────────────────────────────────────

class TestMaxPositionLimit:
    def test_reject_when_at_max(self) -> None:
        gate = TradeRiskGate(RiskProfile(capital=100_000, max_open_positions=3))
        gate.set_open_positions(3)
        result = gate.evaluate({
            "symbol": "ASELS",
            "entry": 100.0,
            "stop": 95.0,
            "target": 115.0,
            "position_size": 10,
        })
        assert result.approved is False
        assert any("open_positions" in v for v in result.violations)

    def test_approve_below_max(self) -> None:
        gate = TradeRiskGate(RiskProfile(capital=100_000, max_open_positions=5))
        gate.set_open_positions(2)
        result = gate.evaluate({
            "symbol": "ASELS",
            "entry": 100.0,
            "stop": 95.0,
            "target": 115.0,
            "position_size": 10,
        })
        assert result.approved is True


# ── Daily loss guard ──────────────────────────────────────────────────────

class TestDailyLossGuard:
    def test_reject_when_daily_loss_exceeded(self) -> None:
        gate = TradeRiskGate(RiskProfile(capital=100_000, max_daily_loss_pct=2.0))
        gate.record_loss(2_500.0)
        result = gate.evaluate({
            "symbol": "THYAO",
            "entry": 50.0,
            "stop": 48.0,
            "target": 55.0,
            "position_size": 20,
        })
        assert result.approved is False
        assert any("daily_loss" in v for v in result.violations)

    def test_approve_when_below_daily_limit(self) -> None:
        gate = TradeRiskGate(RiskProfile(capital=100_000, max_daily_loss_pct=5.0))
        gate.record_loss(1_000.0)
        result = gate.evaluate({
            "symbol": "THYAO",
            "entry": 50.0,
            "stop": 48.0,
            "target": 55.0,
            "position_size": 20,
        })
        assert result.approved is True

    def test_reset_daily_clears_loss(self) -> None:
        gate = TradeRiskGate(RiskProfile(capital=100_000, max_daily_loss_pct=2.0))
        gate.record_loss(3_000.0)
        gate.reset_daily()
        assert gate.daily_loss == 0.0
        result = gate.evaluate({
            "symbol": "GARAN",
            "entry": 30.0,
            "stop": 28.0,
            "target": 35.0,
            "position_size": 50,
        })
        assert result.approved is True


# ── Risk per trade ────────────────────────────────────────────────────────

class TestRiskPerTrade:
    def test_reject_excess_risk(self) -> None:
        gate = TradeRiskGate(RiskProfile(capital=100_000, max_risk_per_trade_pct=1.0))
        result = gate.evaluate({
            "symbol": "X",
            "entry": 100.0,
            "stop": 90.0,
            "target": 120.0,
            "position_size": 200,
        })
        assert result.approved is False
        assert any("risk_per_trade" in v for v in result.violations)

    def test_approve_within_risk(self) -> None:
        gate = TradeRiskGate(RiskProfile(capital=100_000, max_risk_per_trade_pct=2.0))
        result = gate.evaluate({
            "symbol": "X",
            "entry": 100.0,
            "stop": 95.0,
            "target": 110.0,
            "position_size": 10,
        })
        assert result.approved is True


# ── Auto-sizing ───────────────────────────────────────────────────────────

class TestAutoSizing:
    def test_auto_size_when_missing(self) -> None:
        gate = TradeRiskGate(RiskProfile(capital=100_000, max_risk_per_trade_pct=2.0))
        result = gate.evaluate({
            "symbol": "ASELS",
            "entry": 100.0,
            "stop": 95.0,
            "target": 115.0,
        })
        assert result.approved is True
        expected = int(100_000 * 0.02 / 5.0)
        assert result.position_size == expected

    def test_auto_size_when_zero(self) -> None:
        gate = TradeRiskGate(RiskProfile(capital=50_000, max_risk_per_trade_pct=1.0))
        result = gate.evaluate({
            "symbol": "THYAO",
            "entry": 50.0,
            "stop": 48.0,
            "target": 55.0,
            "position_size": 0,
        })
        assert result.approved is True
        expected = int(50_000 * 0.01 / 2.0)
        assert result.position_size == expected


# ── Batch evaluation ──────────────────────────────────────────────────────

class TestBatchEvaluation:
    def test_batch_mixed(self) -> None:
        gate = TradeRiskGate(RiskProfile(capital=100_000))
        decisions = [
            {"symbol": "A", "entry": 100.0, "stop": 95.0, "target": 115.0, "position_size": 10},
            {"symbol": "", "entry": 100.0, "stop": 95.0, "target": 115.0, "position_size": 10},
        ]
        results = gate.evaluate_batch(decisions)
        assert len(results) == 2
        assert results[0].approved is True
        assert results[1].approved is False


# ── Determinism ───────────────────────────────────────────────────────────

class TestDeterminism:
    def test_identical_inputs_identical_outputs(self) -> None:
        profile = RiskProfile(capital=100_000)
        decision = {
            "symbol": "ASELS",
            "entry": 100.0,
            "stop": 95.0,
            "target": 115.0,
            "position_size": 10,
        }
        r1 = TradeRiskGate(profile).evaluate(decision)
        r2 = TradeRiskGate(profile).evaluate(decision)
        assert r1.to_dict() == r2.to_dict()


# ── Result serialization ─────────────────────────────────────────────────

class TestResultSerialization:
    def test_to_dict(self) -> None:
        result = RiskGateResult(
            approved=True, reason="APPROVED", position_size=100, violations=[],
        )
        d = result.to_dict()
        assert d["approved"] is True
        assert d["reason"] == "APPROVED"
        assert d["position_size"] == 100
        assert d["violations"] == []
