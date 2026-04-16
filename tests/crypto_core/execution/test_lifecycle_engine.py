"""Tests for ExecutionLifecycleEngine — Phase 6D.

Covers:
- Validation gates (symbol, size, risk, system_state, mode)
- DRY_RUN path: gates pass → VALIDATED, no fills, approved=True
- PAPER path: full lifecycle → FILLED, fill_events populated
- Partial fill → PARTIALLY_FILLED + CANCELLED residual
- Pricer rejection → REJECTED lifecycle result
- cancel() / replace() in-flight order management
- to_execution_decision() backward compat
- SyntheticFillFactory.from_fill_event() integration
"""

from __future__ import annotations

import time

import pytest

from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.fill_pricer import FillPricerConfig
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import (
    BookContext,
    ExecutionMode,
    ExecutionRequest,
    OrderIntent,
    RejectionReason,
)
from crypto_core.execution.paper_adapter import PaperAdapterConfig
from crypto_core.execution.state_machine import OrderState
from crypto_core.guard.models import NoTradeDecision
from crypto_core.portfolio.fills import SyntheticFillFactory
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_ns() -> int:
    return time.time_ns()


_T0_NS = 1_000_000_000_000


def _edge_signal(direction: SignalDirection = SignalDirection.BUY) -> EdgeSignal:
    return EdgeSignal(
        family=EdgeFamily.ORDER_FLOW_IMBALANCE,
        symbol="BTCUSDT",
        exchange="binance",
        direction=direction,
        confidence=0.5,
        score=0.5,
        evidence={"ofi": 0.5},
        timestamp_ns=_T0_NS,
        is_valid=True,
        block_reason=None,
    )


def _risk_approved(system_state: SystemState = SystemState.NORMAL) -> RiskEvaluation:
    return RiskEvaluation(
        decision=RiskDecision.APPROVED,
        block_reason=None,
        system_state=system_state,
        edge_signal=_edge_signal(),
        no_trade_decision=NoTradeDecision.allow(),
        evidence={},
        timestamp_ns=_T0_NS,
    )


def _risk_rejected() -> RiskEvaluation:
    return RiskEvaluation(
        decision=RiskDecision.BLOCKED,
        block_reason="TEST_BLOCK",
        system_state=SystemState.NORMAL,
        edge_signal=_edge_signal(),
        no_trade_decision=NoTradeDecision.allow(),
        evidence={},
        timestamp_ns=_T0_NS,
    )


def _healthy_book() -> BookContext:
    return BookContext(
        bid_price=49990.0,
        ask_price=50010.0,
        bid_size=5.0,
        ask_size=5.0,
    )


def _request(
    symbol: str = "BTCUSDT",
    size: float = 0.01,
    intent: OrderIntent = OrderIntent.BUY,
    risk: RiskEvaluation | None = None,
    book: BookContext | None = None,
    mode: ExecutionMode = ExecutionMode.PAPER,
    price_hint: float = 50000.0,
) -> ExecutionRequest:
    if risk is None:
        risk = _risk_approved()
    if book is None:
        book = _healthy_book()
    return ExecutionRequest(
        symbol=symbol,
        exchange="binance",
        intent=intent,
        size=size,
        price_hint=price_hint,
        risk_evaluation=risk,
        book=book,
        timestamp_ns=_now_ns(),
    )


def _paper_engine(
    max_spread_bps: float = 100.0,
    allow_degraded: bool = True,
    max_participation_pct: float = 10.0,
    max_slippage_bps: float = 100.0,
) -> ExecutionLifecycleEngine:
    pricer_cfg = FillPricerConfig(
        max_spread_bps=max_spread_bps,
        max_participation_pct=max_participation_pct,
        max_slippage_bps=max_slippage_bps,
    )
    cfg = ExecutionLifecycleConfig(
        mode=ExecutionMode.PAPER,
        paper_adapter=PaperAdapterConfig(
            fill_pricer=pricer_cfg,
            allow_degraded_fill=allow_degraded,
        ),
        fill_pricer=pricer_cfg,
    )
    return ExecutionLifecycleEngine(cfg)


def _dry_run_engine() -> ExecutionLifecycleEngine:
    cfg = ExecutionLifecycleConfig(mode=ExecutionMode.DRY_RUN)
    return ExecutionLifecycleEngine(cfg)


# ---------------------------------------------------------------------------
# Gate validation
# ---------------------------------------------------------------------------


class TestGateValidation:
    def test_unsupported_symbol_rejected(self) -> None:
        engine = _paper_engine()
        req = _request(symbol="XYZUSDT")
        result = engine.process(req)
        assert not result.approved
        assert result.rejection_reason == RejectionReason.INVALID_SYMBOL

    def test_zero_size_rejected(self) -> None:
        engine = _paper_engine()
        req = _request(size=0.0)
        result = engine.process(req)
        assert not result.approved
        assert result.rejection_reason == RejectionReason.ZERO_SIZE

    def test_negative_size_rejected(self) -> None:
        engine = _paper_engine()
        req = _request(size=-0.01)
        result = engine.process(req)
        assert not result.approved
        assert result.rejection_reason == RejectionReason.ZERO_SIZE

    def test_risk_not_approved_rejected(self) -> None:
        engine = _paper_engine()
        req = _request(risk=_risk_rejected())
        result = engine.process(req)
        assert not result.approved
        assert result.rejection_reason == RejectionReason.RISK_NOT_APPROVED

    def test_defensive_system_state_rejected(self) -> None:
        engine = _paper_engine()
        req = _request(risk=_risk_approved(system_state=SystemState.DEFENSIVE))
        result = engine.process(req)
        assert not result.approved
        assert result.rejection_reason == RejectionReason.SYSTEM_STATE_DEFENSIVE

    def test_emergency_system_state_rejected(self) -> None:
        engine = _paper_engine()
        req = _request(risk=_risk_approved(system_state=SystemState.HALT))
        result = engine.process(req)
        assert not result.approved
        assert result.rejection_reason == RejectionReason.SYSTEM_STATE_DEFENSIVE

    def test_gate_rejection_has_no_fill_events(self) -> None:
        engine = _paper_engine()
        req = _request(symbol="UNKNOWN")
        result = engine.process(req)
        assert len(result.fill_events) == 0
        assert result.total_filled_quantity == 0.0

    def test_gate_rejection_order_in_terminal_state(self) -> None:
        engine = _paper_engine()
        req = _request(symbol="UNKNOWN")
        result = engine.process(req)
        assert result.order.is_terminal or str(result.order.state) == OrderState.REJECTED


# ---------------------------------------------------------------------------
# DRY_RUN path
# ---------------------------------------------------------------------------


class TestDryRunPath:
    def test_dry_run_is_approved(self) -> None:
        engine = _dry_run_engine()
        result = engine.process(_request())
        assert result.approved is True

    def test_dry_run_no_fill_events(self) -> None:
        engine = _dry_run_engine()
        result = engine.process(_request())
        assert len(result.fill_events) == 0

    def test_dry_run_order_in_validated_state(self) -> None:
        engine = _dry_run_engine()
        result = engine.process(_request())
        assert str(result.order.state) == OrderState.VALIDATED

    def test_dry_run_total_filled_quantity_is_zero(self) -> None:
        engine = _dry_run_engine()
        result = engine.process(_request())
        assert result.total_filled_quantity == pytest.approx(0.0)

    def test_dry_run_rejection_reason_is_none(self) -> None:
        engine = _dry_run_engine()
        result = engine.process(_request())
        assert result.rejection_reason is None

    def test_dry_run_event_history_contains_validated(self) -> None:
        engine = _dry_run_engine()
        result = engine.process(_request())
        event_types = [e.event_type for e in result.order.event_history]
        assert "VALIDATED" in event_types


# ---------------------------------------------------------------------------
# PAPER full lifecycle
# ---------------------------------------------------------------------------


class TestPaperFullLifecycle:
    def test_paper_fill_is_approved(self) -> None:
        engine = _paper_engine()
        result = engine.process(_request())
        assert result.approved is True

    def test_paper_fill_events_non_empty(self) -> None:
        engine = _paper_engine()
        result = engine.process(_request())
        assert len(result.fill_events) > 0

    def test_paper_fill_quantity_matches_request(self) -> None:
        engine = _paper_engine()
        result = engine.process(_request(size=0.01))
        assert result.total_filled_quantity == pytest.approx(0.01)

    def test_paper_fill_price_is_above_mid_for_buy(self) -> None:
        engine = _paper_engine()
        result = engine.process(_request(intent=OrderIntent.BUY, price_hint=50000.0))
        assert result.average_fill_price is not None
        assert result.average_fill_price > 50000.0

    def test_paper_order_in_terminal_state(self) -> None:
        engine = _paper_engine()
        result = engine.process(_request())
        assert result.order.is_terminal

    def test_paper_final_state_is_filled(self) -> None:
        engine = _paper_engine()
        result = engine.process(_request(size=0.01))
        assert result.final_state == OrderState.FILLED

    def test_paper_rejection_reason_is_none_on_success(self) -> None:
        engine = _paper_engine()
        result = engine.process(_request())
        assert result.rejection_reason is None

    def test_paper_no_book_degraded_fill(self) -> None:
        engine = _paper_engine(allow_degraded=True)
        req = _request(book=None)
        # Need to pass a request without book — override
        req2 = ExecutionRequest(
            symbol=req.symbol,
            exchange=req.exchange,
            intent=req.intent,
            size=req.size,
            price_hint=req.price_hint,
            risk_evaluation=req.risk_evaluation,
            book=None,
            timestamp_ns=req.timestamp_ns,
        )
        result = engine.process(req2)
        assert result.approved is True
        assert result.total_filled_quantity == pytest.approx(req.size)


# ---------------------------------------------------------------------------
# Partial fill path
# ---------------------------------------------------------------------------


class TestPartialFill:
    def test_partial_fill_when_order_exceeds_depth(self) -> None:
        # max_participation_pct=500, max_slippage_bps=9999 → pricer won't block; depth gate decides partial fill
        engine = _paper_engine(max_spread_bps=200.0, max_participation_pct=500.0, max_slippage_bps=9999.0)
        # Book ask_size=0.5, order=1.0 → partial fill
        book = BookContext(bid_price=49990.0, ask_price=50010.0, bid_size=5.0, ask_size=0.5)
        req = _request(size=1.0, book=book)
        result = engine.process(req)
        assert result.total_filled_quantity == pytest.approx(0.5)
        assert result.final_state == OrderState.CANCELLED  # residual cancelled

    def test_partial_fill_is_not_approved_in_paper(self) -> None:
        """Partial fill still produces fills — approved is True (qty > 0)."""
        engine = _paper_engine(max_spread_bps=200.0, max_participation_pct=500.0, max_slippage_bps=9999.0)
        book = BookContext(bid_price=49990.0, ask_price=50010.0, bid_size=5.0, ask_size=0.5)
        req = _request(size=1.0, book=book)
        result = engine.process(req)
        # Even partial fill → approved because total_filled_quantity > 0
        assert result.approved is True


# ---------------------------------------------------------------------------
# Pricer-level rejection
# ---------------------------------------------------------------------------


class TestPricerRejection:
    def test_rejected_on_excessive_spread(self) -> None:
        engine = _paper_engine(max_spread_bps=3.0)  # book spread 4bps → reject
        result = engine.process(_request())
        assert not result.approved
        assert result.total_filled_quantity == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# to_execution_decision backward compat
# ---------------------------------------------------------------------------


class TestToExecutionDecision:
    def test_approved_maps_to_allowed_true(self) -> None:
        engine = _paper_engine()
        result = engine.process(_request())
        decision = result.to_execution_decision()
        assert decision.allowed is True

    def test_rejected_maps_to_allowed_false(self) -> None:
        engine = _paper_engine()
        result = engine.process(_request(symbol="UNKNOWN"))
        decision = result.to_execution_decision()
        assert decision.allowed is False

    def test_fill_generated_set_on_paper_fill(self) -> None:
        engine = _paper_engine()
        result = engine.process(_request())
        decision = result.to_execution_decision()
        assert decision.fill_generated is True

    def test_fill_price_propagated(self) -> None:
        engine = _paper_engine()
        result = engine.process(_request())
        decision = result.to_execution_decision()
        assert decision.fill_price is not None
        assert decision.fill_price > 0.0

    def test_dry_run_decision_is_allowed(self) -> None:
        engine = _dry_run_engine()
        result = engine.process(_request())
        decision = result.to_execution_decision()
        assert decision.allowed is True
        assert decision.fill_generated is False  # no fills in dry-run


# ---------------------------------------------------------------------------
# cancel() / replace() in-flight
# ---------------------------------------------------------------------------


class TestCancelReplace:
    def test_cancel_unknown_order_id_returns_empty(self) -> None:
        engine = _paper_engine()
        result = engine.cancel("unknown-id", reason="test")
        assert result == []

    def test_replace_unknown_order_id_returns_empty_list(self) -> None:
        engine = _paper_engine()
        events = engine.replace("unknown-id", new_quantity=0.02)
        assert events == []

    def test_cancel_in_flight_dry_run_order(self) -> None:
        """After DRY_RUN, order is in VALIDATED state — not submitted, so cancel returns empty."""
        engine = _dry_run_engine()
        result = engine.process(_request())
        order_id = result.order_id
        cancel_events = engine.cancel(order_id, "test_cancel")
        # VALIDATED → CANCEL_PENDING is not a valid transition (never submitted)
        assert cancel_events == []


# ---------------------------------------------------------------------------
# SyntheticFillFactory.from_fill_event integration
# ---------------------------------------------------------------------------


class TestFillEventBridge:
    def test_from_fill_event_creates_synthetic_fill(self) -> None:
        engine = _paper_engine()
        result = engine.process(_request(size=0.01, intent=OrderIntent.BUY))
        assert len(result.fill_events) > 0
        fill_event = result.fill_events[0]
        synthetic = SyntheticFillFactory.from_fill_event(
            fill_event=fill_event,
            mode=ExecutionMode.PAPER,
            leverage=1.0,
        )
        assert synthetic.quantity * synthetic.fill_price > 0.0
        assert synthetic.intent == OrderIntent.BUY

    def test_from_fill_event_sell_side(self) -> None:
        engine = _paper_engine()
        result = engine.process(_request(size=0.01, intent=OrderIntent.SELL))
        fill_event = result.fill_events[0]
        synthetic = SyntheticFillFactory.from_fill_event(
            fill_event=fill_event,
            mode=ExecutionMode.PAPER,
            leverage=1.0,
        )
        assert synthetic.intent == OrderIntent.SELL

    def test_from_fill_event_rejects_zero_quantity(self) -> None:
        from crypto_core.execution.events import FillEvent

        bad_fill = FillEvent(
            order_id="test-id",
            symbol="BTCUSDT",
            exchange="binance",
            intent=OrderIntent.BUY,
            filled_quantity=0.0,
            fill_price=50000.0,
            timestamp_ns=_now_ns(),
        )
        with pytest.raises(ValueError):
            SyntheticFillFactory.from_fill_event(bad_fill, mode=ExecutionMode.PAPER)

    def test_from_fill_event_rejects_zero_price(self) -> None:
        from crypto_core.execution.events import FillEvent

        bad_fill = FillEvent(
            order_id="test-id",
            symbol="BTCUSDT",
            exchange="binance",
            intent=OrderIntent.BUY,
            filled_quantity=0.01,
            fill_price=0.0,
            timestamp_ns=_now_ns(),
        )
        with pytest.raises(ValueError):
            SyntheticFillFactory.from_fill_event(bad_fill, mode=ExecutionMode.PAPER)


# ---------------------------------------------------------------------------
# Result immutability
# ---------------------------------------------------------------------------


class TestResultImmutability:
    def test_fill_events_is_tuple(self) -> None:
        engine = _paper_engine()
        result = engine.process(_request())
        assert isinstance(result.fill_events, tuple)

    def test_result_is_frozen(self) -> None:
        engine = _paper_engine()
        result = engine.process(_request())
        with pytest.raises((AttributeError, TypeError)):
            result.total_filled_quantity = 999.0  # type: ignore[misc]
