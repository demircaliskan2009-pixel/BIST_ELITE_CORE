"""Tests for Risk Engine v1 (PRD §1.14–§1.28)."""

from __future__ import annotations

import pytest

from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.guard.models import NoTradeDecision, NoTradeReason
from crypto_core.risk.engine import RiskEngine
from crypto_core.risk.models import RiskBlockReason, RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_T0_NS = 1_000_000_000_000


def _valid_edge(direction: str = SignalDirection.BUY, confidence: float = 0.5) -> EdgeSignal:
    return EdgeSignal(
        family=EdgeFamily.ORDER_FLOW_IMBALANCE,
        symbol="BTCUSDT",
        exchange="binance",
        direction=direction,
        confidence=confidence,
        score=0.5,
        evidence={"ofi": 0.5, "trade_count": 50},
        timestamp_ns=_T0_NS,
        is_valid=True,
        block_reason=None,
    )


def _invalid_edge(reason: str = "test_block") -> EdgeSignal:
    return EdgeSignal.invalid(EdgeFamily.ORDER_FLOW_IMBALANCE, "BTCUSDT", "binance", reason, _T0_NS)


def _allow() -> NoTradeDecision:
    return NoTradeDecision.allow()


def _block_nt() -> NoTradeDecision:
    return NoTradeDecision.block(NoTradeReason.STALE_DATA)


def _engine() -> RiskEngine:
    return RiskEngine()


# ---------------------------------------------------------------------------
# Approval path
# ---------------------------------------------------------------------------


class TestRiskApproval:
    def test_healthy_inputs_approved(self) -> None:
        eng = _engine()
        result = eng.evaluate(_valid_edge(), SystemState.NORMAL, _allow(), _T0_NS)
        assert result.approved is True
        assert result.decision == RiskDecision.APPROVED
        assert result.block_reason is None

    def test_degraded_state_still_approved(self) -> None:
        """DEGRADED < DEFENSIVE — should still be approved."""
        eng = _engine()
        result = eng.evaluate(_valid_edge(), SystemState.DEGRADED, _allow(), _T0_NS)
        assert result.approved is True

    def test_approved_evidence_populated(self) -> None:
        eng = _engine()
        result = eng.evaluate(_valid_edge(), SystemState.NORMAL, _allow(), _T0_NS)
        assert "system_state" in result.evidence
        assert "edge_confidence" in result.evidence

    def test_shs_snapshot_in_evidence(self) -> None:
        eng = _engine()
        result = eng.evaluate(_valid_edge(), SystemState.NORMAL, _allow(), _T0_NS, shs_snapshot=0.95)
        assert result.evidence["shs_snapshot"] == 0.95


# ---------------------------------------------------------------------------
# Gate 1: system state defensive
# ---------------------------------------------------------------------------


class TestGateSystemState:
    @pytest.mark.parametrize(
        "state",
        [SystemState.DEFENSIVE, SystemState.CRISIS, SystemState.HALT],
    )
    def test_defensive_and_above_blocked(self, state: str) -> None:
        eng = _engine()
        result = eng.evaluate(_valid_edge(), state, _allow(), _T0_NS)
        assert result.decision == RiskDecision.BLOCKED
        assert result.block_reason == RiskBlockReason.SYSTEM_STATE_DEFENSIVE

    @pytest.mark.parametrize("state", [SystemState.NORMAL, SystemState.DEGRADED])
    def test_normal_and_degraded_pass_gate(self, state: str) -> None:
        eng = _engine()
        result = eng.evaluate(_valid_edge(), state, _allow(), _T0_NS)
        assert result.decision == RiskDecision.APPROVED


# ---------------------------------------------------------------------------
# Gate 2: no-trade guard blocked
# ---------------------------------------------------------------------------


class TestGateNoTrade:
    def test_no_trade_block_propagates(self) -> None:
        eng = _engine()
        result = eng.evaluate(_valid_edge(), SystemState.NORMAL, _block_nt(), _T0_NS)
        assert result.decision == RiskDecision.BLOCKED
        assert result.block_reason == RiskBlockReason.NO_TRADE_BLOCKED
        assert "no_trade_reason" in result.evidence


# ---------------------------------------------------------------------------
# Gate 3: edge signal not valid
# ---------------------------------------------------------------------------


class TestGateEdgeNotValid:
    def test_invalid_edge_blocked(self) -> None:
        eng = _engine()
        result = eng.evaluate(_invalid_edge(), SystemState.NORMAL, _allow(), _T0_NS)
        assert result.decision == RiskDecision.BLOCKED
        assert result.block_reason == RiskBlockReason.EDGE_NOT_VALID
        assert "edge_reason" in result.evidence

    def test_invalid_edge_with_custom_reason(self) -> None:
        eng = _engine()
        edge = _invalid_edge("stale_state_block")
        result = eng.evaluate(edge, SystemState.NORMAL, _allow(), _T0_NS)
        assert result.evidence.get("edge_reason") == "stale_state_block"


# ---------------------------------------------------------------------------
# Gate 4: edge evidence incomplete
# ---------------------------------------------------------------------------


class TestGateEdgeEvidence:
    def test_empty_evidence_blocked(self) -> None:
        eng = _engine()
        edge = EdgeSignal(
            family=EdgeFamily.ORDER_FLOW_IMBALANCE,
            symbol="BTCUSDT",
            exchange="binance",
            direction=SignalDirection.BUY,
            confidence=0.5,
            score=0.5,
            evidence={},  # empty!
            timestamp_ns=_T0_NS,
            is_valid=True,
            block_reason=None,
        )
        result = eng.evaluate(edge, SystemState.NORMAL, _allow(), _T0_NS)
        assert result.decision == RiskDecision.BLOCKED
        assert result.block_reason == RiskBlockReason.EDGE_EVIDENCE_INCOMPLETE


# ---------------------------------------------------------------------------
# RiskEvaluation model
# ---------------------------------------------------------------------------


class TestRiskEvaluationModel:
    def test_approved_property(self) -> None:
        eng = _engine()
        r = eng.evaluate(_valid_edge(), SystemState.NORMAL, _allow(), _T0_NS)
        assert r.approved is True

    def test_blocked_property(self) -> None:
        eng = _engine()
        r = eng.evaluate(_valid_edge(), SystemState.HALT, _allow(), _T0_NS)
        assert r.approved is False

    def test_result_is_frozen(self) -> None:
        eng = _engine()
        r = eng.evaluate(_valid_edge(), SystemState.NORMAL, _allow(), _T0_NS)
        assert isinstance(r, RiskEvaluation)
        with pytest.raises((AttributeError, TypeError)):
            r.decision = RiskDecision.BLOCKED  # type: ignore[misc]

    def test_telemetry_emit_data_available(self) -> None:
        eng = _engine()
        r = eng.evaluate(_valid_edge(), SystemState.NORMAL, _allow(), _T0_NS, shs_snapshot=0.88)
        # Verify all fields needed for telemetry are present
        assert r.evidence["shs_snapshot"] == 0.88
        assert r.evidence["system_state"] == str(SystemState.NORMAL)
