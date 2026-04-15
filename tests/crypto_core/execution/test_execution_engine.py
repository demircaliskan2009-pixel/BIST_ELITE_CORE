"""Tests for Execution Engine skeleton (PRD §7)."""

from __future__ import annotations

import pytest

from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.engine import ExecutionConfig, ExecutionEngine
from crypto_core.execution.models import (
    ExecutionMode,
    ExecutionRequest,
    OrderIntent,
    RejectionReason,
)
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_T0_NS = 1_000_000_000_000


def _approved_risk(system_state: SystemState = SystemState.NORMAL) -> RiskEvaluation:
    edge = EdgeSignal(
        family=EdgeFamily.ORDER_FLOW_IMBALANCE,
        symbol="BTCUSDT",
        exchange="binance",
        direction=SignalDirection.BUY,
        confidence=0.5,
        score=0.5,
        evidence={"ofi": 0.5},
        timestamp_ns=_T0_NS,
        is_valid=True,
        block_reason=None,
    )
    return RiskEvaluation(
        decision=RiskDecision.APPROVED,
        block_reason=None,
        system_state=system_state,
        edge_signal=edge,
        no_trade_decision=NoTradeDecision.allow(),
        evidence={},
        timestamp_ns=_T0_NS,
    )


def _blocked_risk() -> RiskEvaluation:
    from crypto_core.risk.models import RiskBlockReason

    edge = EdgeSignal(
        family=EdgeFamily.ORDER_FLOW_IMBALANCE,
        symbol="BTCUSDT",
        exchange="binance",
        direction=SignalDirection.NEUTRAL,
        confidence=0.0,
        score=0.0,
        evidence={},
        timestamp_ns=_T0_NS,
        is_valid=False,
        block_reason="test_block",
    )
    return RiskEvaluation(
        decision=RiskDecision.BLOCKED,
        block_reason=RiskBlockReason.EDGE_NOT_VALID,
        system_state=SystemState.NORMAL,
        edge_signal=edge,
        no_trade_decision=NoTradeDecision.allow(),
        evidence={},
        timestamp_ns=_T0_NS,
    )


def _request(
    symbol: str = "BTCUSDT",
    size: float = 0.01,
    risk: RiskEvaluation | None = None,
) -> ExecutionRequest:
    return ExecutionRequest(
        symbol=symbol,
        exchange="binance",
        intent=OrderIntent.BUY,
        size=size,
        price_hint=50_000.0,
        risk_evaluation=risk or _approved_risk(),
        timestamp_ns=_T0_NS,
    )


def _engine(mode: ExecutionMode = ExecutionMode.DRY_RUN) -> ExecutionEngine:
    cfg = ExecutionConfig(
        mode=mode,
        supported_symbols=frozenset({"BTCUSDT", "ETHUSDT"}),
    )
    return ExecutionEngine(cfg)


# ---------------------------------------------------------------------------
# Allowed dry-run paths
# ---------------------------------------------------------------------------


class TestDryRunAllow:
    def test_valid_dry_run_request_allowed(self) -> None:
        engine = _engine()
        dec = engine.execute(_request())
        assert dec.allowed is True
        assert dec.rejection_reason is None
        assert dec.mode == ExecutionMode.DRY_RUN
        assert dec.order_id is not None

    def test_order_id_is_uuid(self) -> None:
        import uuid

        engine = _engine()
        dec = engine.execute(_request())
        # Should not raise
        uuid.UUID(dec.order_id)  # type: ignore[arg-type]

    def test_valid_paper_request_allowed(self) -> None:
        engine = _engine(mode=ExecutionMode.PAPER)
        dec = engine.execute(_request())
        assert dec.allowed is True
        assert dec.mode == ExecutionMode.PAPER

    def test_decision_is_frozen(self) -> None:
        engine = _engine()
        dec = engine.execute(_request())
        with pytest.raises((AttributeError, TypeError)):
            dec.allowed = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Hard blocks
# ---------------------------------------------------------------------------


class TestHardBlocks:
    def test_unsupported_symbol_rejected(self) -> None:
        engine = _engine()
        dec = engine.execute(_request(symbol="XYZUSDT"))
        assert dec.allowed is False
        assert dec.rejection_reason == RejectionReason.INVALID_SYMBOL
        assert "supported" in dec.evidence

    def test_zero_size_rejected(self) -> None:
        engine = _engine()
        dec = engine.execute(_request(size=0.0))
        assert dec.allowed is False
        assert dec.rejection_reason == RejectionReason.ZERO_SIZE

    def test_negative_size_rejected(self) -> None:
        engine = _engine()
        dec = engine.execute(_request(size=-1.0))
        assert dec.allowed is False
        assert dec.rejection_reason == RejectionReason.ZERO_SIZE

    def test_risk_not_approved_rejected(self) -> None:
        engine = _engine()
        dec = engine.execute(_request(risk=_blocked_risk()))
        assert dec.allowed is False
        assert dec.rejection_reason == RejectionReason.RISK_NOT_APPROVED

    def test_system_state_defensive_rejected(self) -> None:
        engine = _engine()
        risk = _approved_risk(system_state=SystemState.DEFENSIVE)
        dec = engine.execute(_request(risk=risk))
        assert dec.allowed is False
        assert dec.rejection_reason == RejectionReason.SYSTEM_STATE_DEFENSIVE

    def test_system_state_halt_rejected(self) -> None:
        engine = _engine()
        risk = _approved_risk(system_state=SystemState.HALT)
        dec = engine.execute(_request(risk=risk))
        assert dec.allowed is False

    def test_system_state_crisis_rejected(self) -> None:
        engine = _engine()
        risk = _approved_risk(system_state=SystemState.CRISIS)
        dec = engine.execute(_request(risk=risk))
        assert dec.allowed is False


# ---------------------------------------------------------------------------
# Mode enforcement
# ---------------------------------------------------------------------------


class TestModeEnforcement:
    def test_dry_run_mode_set_correctly(self) -> None:
        engine = _engine(ExecutionMode.DRY_RUN)
        dec = engine.execute(_request())
        assert dec.mode == ExecutionMode.DRY_RUN

    def test_paper_mode_set_correctly(self) -> None:
        engine = _engine(ExecutionMode.PAPER)
        dec = engine.execute(_request())
        assert dec.mode == ExecutionMode.PAPER


# ---------------------------------------------------------------------------
# Evidence integrity
# ---------------------------------------------------------------------------


class TestEvidenceIntegrity:
    def test_allowed_evidence_contains_order_id(self) -> None:
        engine = _engine()
        dec = engine.execute(_request())
        assert "order_id" in dec.evidence
        assert dec.evidence["order_id"] == dec.order_id

    def test_rejected_evidence_contains_symbol(self) -> None:
        engine = _engine()
        dec = engine.execute(_request(symbol="UNKNOWN"))
        assert dec.evidence["symbol"] == "UNKNOWN"

    def test_rejected_property(self) -> None:
        engine = _engine()
        dec = engine.execute(_request(size=0.0))
        assert dec.rejected is True
