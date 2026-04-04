"""Capital protection risk engine — drawdown tiers, streaks, snapshot."""

from __future__ import annotations

import pytest

from bist_core.live.risk_engine import (
    RiskEngine,
    drawdown_tier_factor,
    extreme_volatility,
    regime_factor,
)


def test_drawdown_tier_factor() -> None:
    assert drawdown_tier_factor(0.04) == (1.0, False)
    assert drawdown_tier_factor(0.06)[0] == pytest.approx(0.7)
    assert drawdown_tier_factor(0.11)[0] == pytest.approx(0.4)
    assert drawdown_tier_factor(0.16) == (0.0, True)


def test_risk_engine_equity_and_drawdown() -> None:
    r = RiskEngine()
    r.peak_equity = 100.0
    r.update_equity(94.0)
    assert r.drawdown_pct() == pytest.approx(0.06)
    fac, kill = drawdown_tier_factor(r.drawdown_pct())
    assert fac == pytest.approx(0.7)
    assert kill is False


def test_loss_streak_reduces_risk_multiplier() -> None:
    r = RiskEngine()
    for _ in range(3):
        r.record_closed_trade(-0.01, 1.0)
    assert r.losing_streak == 3
    snap = r.build_snapshot(volatility=0.02, regime="MIXED", vol_spike=False)
    assert snap["loss_streak_factor"] == pytest.approx(0.5)


def test_kill_switch_combined_zero() -> None:
    r = RiskEngine()
    r.peak_equity = 100.0
    r.update_equity(84.0)
    snap = r.build_snapshot(volatility=0.02, regime="MIXED", vol_spike=False)
    assert snap["kill_switch"] is True
    assert snap["combined_position_factor"] == 0.0
    assert snap["operational_state"] == "PAUSE"
    assert snap.get("fsm_transition_count", 0) >= 1


def test_fsm_persists_transition_history() -> None:
    r = RiskEngine()
    r.build_snapshot(volatility=0.02, regime="MIXED", vol_spike=False)
    n0 = int(r.fsm.transition_count)
    r.peak_equity = 100.0
    r.update_equity(84.0)
    r.build_snapshot(volatility=0.02, regime="MIXED", vol_spike=False)
    assert r.fsm.transition_count > n0
    assert r.fsm.last_transition is not None


def test_operational_state_active() -> None:
    r = RiskEngine()
    snap = r.build_snapshot(volatility=0.02, regime="MIXED", vol_spike=False)
    assert snap["operational_state"] == "ACTIVE"


def test_operational_state_recover_cooldown() -> None:
    r = RiskEngine()
    r.pause_cycles_remaining = 10
    snap = r.build_snapshot(volatility=0.02, regime="MIXED", vol_spike=False)
    assert snap["operational_state"] == "RECOVER"


def test_operational_state_de_risk_drawdown() -> None:
    r = RiskEngine()
    r.peak_equity = 100.0
    r.update_equity(93.0)
    snap = r.build_snapshot(volatility=0.02, regime="MIXED", vol_spike=False)
    assert snap["drawdown_pct"] == pytest.approx(0.07)
    assert snap["operational_state"] == "DE_RISK"


def test_operational_state_de_risk_extreme_vol() -> None:
    r = RiskEngine()
    snap = r.build_snapshot(volatility=0.13, regime="MIXED", vol_spike=False)
    assert snap["operational_state"] == "DE_RISK"


def test_extreme_volatility_flag() -> None:
    assert extreme_volatility(0.11) is False
    assert extreme_volatility(0.13) is True


def test_regime_factor() -> None:
    assert regime_factor("TRENDING") == pytest.approx(1.05)
    assert regime_factor("MIXED") == pytest.approx(1.0)
