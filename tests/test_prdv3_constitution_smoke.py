"""PRDV3: offline smoke checks that core constitution paths import and behave deterministically.

Maps to `docs/PRDV3_FINAL_GOD_ARCHITECTURE.md` — deterministic data, brain, edge, portfolio,
risk snapshot shape, execution realism, walk-forward split. No network, no iDeal path required.
"""

from __future__ import annotations

from bist_core.brain.ranking_engine import rank_symbols
from bist_core.live.data_feed import normalize_price
from bist_core.live.execution_engine import ExecutionEngine
from bist_core.live.risk_engine import RiskEngine
from bist_core.validation.walkforward import walkforward_split


def test_prdv3_normalize_price_deterministic() -> None:
    a = normalize_price(123.45)
    b = normalize_price(123.45)
    assert a == b
    assert 10 < a < 10000


def test_prdv3_rank_symbols_edge_dominance() -> None:
    decisions = [
        {"symbol": "A", "edge_score": 0.2},
        {"symbol": "B", "edge_score": 0.8},
        {"symbol": "C", "edge_score": 0.5},
    ]
    ranked = rank_symbols(decisions)
    assert ranked[0]["symbol"] == "B"


def test_prdv3_walkforward_no_leakage() -> None:
    data = list(range(100))
    train, test = walkforward_split(data, train_size=0.7)
    assert max(train) < min(test)
    assert len(train) == 70 and len(test) == 30


def test_prdv3_execution_deterministic() -> None:
    e = ExecutionEngine()
    r1 = e.try_fill("X", "enter", 100.0, last_price=100.0, confidence=0.5)
    r2 = e.try_fill("X", "enter", 100.0, last_price=100.0, confidence=0.5)
    assert r1 == r2


def test_prdv3_risk_snapshot_has_multiplier_and_kill_switch() -> None:
    r = RiskEngine()
    snap = r.build_snapshot(volatility=0.02, regime="MIXED", vol_spike=False)
    assert "risk_multiplier" in snap
    assert "kill_switch" in snap
    assert isinstance(snap["kill_switch"], bool)
    assert snap.get("operational_state") in ("ACTIVE", "DE_RISK", "PAUSE", "RECOVER")
    assert "fsm_transition_count" in snap
