"""Tests for RecoveryBootstrap — Phase 6E.

Covers:
  - Successful recovery from both stores present
  - No execution state (empty store) + valid portfolio
  - No portfolio state → success=False
  - Corrupt execution store → success=False
  - Corrupt portfolio store → success=False
  - Orphan orders surfaced correctly
  - Evidence fields populated correctly on success
  - Evidence fields populated correctly on failure
  - run() never raises
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from crypto_core.execution.events import OrderEvent, OrderEventType
from crypto_core.execution.models import ExecutionMode, OrderIntent
from crypto_core.execution.recovery import RecoveryBootstrap, RecoveryEvidence, RecoveryResult
from crypto_core.execution.state_machine import Order, OrderState
from crypto_core.execution.store import ExecutionStateStore, build_order_meta
from crypto_core.portfolio.store import PortfolioStateStore
from crypto_core.portfolio.tracker import PositionTracker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SNAPSHOT_NS = 1_234_567_890_000


def _exec_store(tmp_path: Path, name: str = "exec.jsonl") -> ExecutionStateStore:
    return ExecutionStateStore(path=tmp_path / name)


def _port_store(tmp_path: Path, name: str = "portfolio.json") -> PortfolioStateStore:
    return PortfolioStateStore(path=tmp_path / name)


def _save_empty_portfolio(store: PortfolioStateStore, nav: float = 10_000.0) -> None:
    tracker = PositionTracker(initial_nav_usd=nav)
    store.save(tracker.to_persistence_dict(_SNAPSHOT_NS))


def _make_order(ts: int | None = None) -> Order:
    ts = ts or time.time_ns()
    return Order.create(
        symbol="BTCUSDT",
        exchange="binance",
        intent=OrderIntent.BUY,
        mode=ExecutionMode.PAPER,
        quantity=0.01,
        timestamp_ns=ts,
    )


def _append_created(store: ExecutionStateStore, order: Order, ts: int) -> None:
    ev = OrderEvent(
        order_id=order.order_id,
        event_type=OrderEventType.CREATED,
        from_state=str(OrderState.CREATED),
        to_state=str(OrderState.CREATED),
        timestamp_ns=ts,
        evidence={},
    )
    store.append_event(ev, order_meta=build_order_meta(order))


# ---------------------------------------------------------------------------
# Success cases
# ---------------------------------------------------------------------------


class TestRecoverySuccess:
    def test_empty_exec_store_and_valid_portfolio(self, tmp_path: Path) -> None:
        es = _exec_store(tmp_path)
        ps = _port_store(tmp_path)
        _save_empty_portfolio(ps)
        # exec store has no events yet
        result = RecoveryBootstrap(es, ps).run()
        assert result.success
        assert result.tracker is not None
        assert result.tracker._nav_usd == pytest.approx(10_000.0)
        assert result.orphan_orders == []
        assert result.evidence.restore_failure_reason is None
        assert result.evidence.execution_store_records == 0
        assert result.evidence.restored_order_count == 0

    def test_one_orphan_order_surfaced(self, tmp_path: Path) -> None:
        es = _exec_store(tmp_path)
        ps = _port_store(tmp_path)
        _save_empty_portfolio(ps)

        ts = 1_000_000_000
        order = _make_order(ts)
        _append_created(es, order, ts)

        result = RecoveryBootstrap(es, ps).run()
        assert result.success
        assert len(result.orphan_orders) == 1
        assert result.orphan_orders[0].order_id == order.order_id
        assert result.evidence.orphan_order_ids == [order.order_id]

    def test_no_orphans_after_terminal_order(self, tmp_path: Path) -> None:
        es = _exec_store(tmp_path)
        ps = _port_store(tmp_path)
        _save_empty_portfolio(ps)

        ts = 2_000_000_000
        order = _make_order(ts)
        _append_created(es, order, ts)
        # Append VALIDATED + REJECTED to reach terminal
        validated = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.VALIDATED,
            from_state=str(OrderState.CREATED),
            to_state=str(OrderState.VALIDATED),
            timestamp_ns=ts + 1,
            evidence={},
        )
        es.append_event(validated)
        rejected = OrderEvent(
            order_id=order.order_id,
            event_type=OrderEventType.REJECTED,
            from_state=str(OrderState.VALIDATED),
            to_state=str(OrderState.REJECTED),
            timestamp_ns=ts + 2,
            reason="test_rejection",
            evidence={},
        )
        es.append_event(rejected)

        result = RecoveryBootstrap(es, ps).run()
        assert result.success
        assert result.orphan_orders == []
        assert result.evidence.orphan_order_ids == []
        assert result.evidence.restored_order_count == 1
        assert result.evidence.execution_store_records == 3

    def test_evidence_snapshot_ns_populated(self, tmp_path: Path) -> None:
        es = _exec_store(tmp_path)
        ps = _port_store(tmp_path)
        _save_empty_portfolio(ps)
        result = RecoveryBootstrap(es, ps).run()
        assert result.evidence.snapshot_ns == _SNAPSHOT_NS

    def test_restored_position_count_correct(self, tmp_path: Path) -> None:
        from crypto_core.execution.events import FillEvent
        from crypto_core.portfolio.fills import SyntheticFillFactory

        ps = _port_store(tmp_path)
        tracker = PositionTracker(initial_nav_usd=10_000.0)
        fill_ev = FillEvent(
            order_id="x",
            symbol="BTCUSDT",
            exchange="binance",
            intent=OrderIntent.BUY,
            filled_quantity=0.01,
            fill_price=50_000.0,
            timestamp_ns=_SNAPSHOT_NS,
        )
        fill = SyntheticFillFactory.from_fill_event(fill_ev, ExecutionMode.PAPER)
        tracker.apply_fill(fill)
        ps.save(tracker.to_persistence_dict(_SNAPSHOT_NS))

        es = _exec_store(tmp_path)
        result = RecoveryBootstrap(es, ps).run()
        assert result.success
        assert result.evidence.restored_position_count == 1


# ---------------------------------------------------------------------------
# Failure cases
# ---------------------------------------------------------------------------


class TestRecoveryFailure:
    def test_missing_portfolio_store_returns_failure(self, tmp_path: Path) -> None:
        es = _exec_store(tmp_path)
        ps = _port_store(tmp_path, "nonexistent.json")
        # portfolio store never written
        result = RecoveryBootstrap(es, ps).run()
        assert not result.success
        assert result.tracker is None
        assert "portfolio_store" in result.evidence.restore_failure_reason

    def test_corrupt_execution_store_returns_failure(self, tmp_path: Path) -> None:
        exec_path = tmp_path / "exec.jsonl"
        exec_path.write_text("not-valid-json\n", encoding="utf-8")
        es = ExecutionStateStore(path=exec_path)
        ps = _port_store(tmp_path)
        _save_empty_portfolio(ps)
        result = RecoveryBootstrap(es, ps).run()
        assert not result.success
        assert result.tracker is None
        assert "execution_store" in result.evidence.restore_failure_reason

    def test_corrupt_portfolio_store_returns_failure(self, tmp_path: Path) -> None:
        es = _exec_store(tmp_path)
        port_path = tmp_path / "portfolio.json"
        port_path.write_text("not-valid-json", encoding="utf-8")
        ps = PortfolioStateStore(path=port_path)
        result = RecoveryBootstrap(es, ps).run()
        assert not result.success
        assert result.tracker is None
        assert "portfolio_store" in result.evidence.restore_failure_reason

    def test_run_never_raises(self, tmp_path: Path) -> None:
        """run() must never propagate exceptions."""
        es = _exec_store(tmp_path)
        ps = _port_store(tmp_path, "nonexistent.json")
        # Should not raise even though portfolio file is missing
        result = RecoveryBootstrap(es, ps).run()
        assert isinstance(result, RecoveryResult)
        assert isinstance(result.evidence, RecoveryEvidence)

    def test_failure_exec_store_has_zero_records_in_evidence(self, tmp_path: Path) -> None:
        exec_path = tmp_path / "exec.jsonl"
        exec_path.write_text('{"broken"}\n', encoding="utf-8")
        es = ExecutionStateStore(path=exec_path)
        ps = _port_store(tmp_path)
        _save_empty_portfolio(ps)
        result = RecoveryBootstrap(es, ps).run()
        assert not result.success
        assert result.evidence.execution_store_records == 0

    def test_failure_preserves_exec_records_in_evidence(self, tmp_path: Path) -> None:
        """When exec store OK but portfolio fails, evidence has exec record count."""
        es = _exec_store(tmp_path)
        ts = 3_000_000_000
        order = _make_order(ts)
        _append_created(es, order, ts)

        port_path = tmp_path / "portfolio.json"
        port_path.write_text("{}", encoding="utf-8")  # missing required fields
        ps = PortfolioStateStore(path=port_path)
        result = RecoveryBootstrap(es, ps).run()
        assert not result.success
        assert result.evidence.execution_store_records == 1
        assert result.evidence.restored_order_count == 1


# ---------------------------------------------------------------------------
# Integration: lifecycle engine + recovery
# ---------------------------------------------------------------------------


class TestLifecycleWithStore:
    """Smoke test: lifecycle engine persists events; bootstrap restores them."""

    def test_paper_fill_persisted_and_restored(self, tmp_path: Path) -> None:
        from crypto_core.edge.models import EdgeFamily, EdgeSignal
        from crypto_core.execution.lifecycle import (
            ExecutionLifecycleConfig,
            ExecutionLifecycleEngine,
        )
        from crypto_core.execution.models import BookContext, ExecutionRequest
        from crypto_core.risk.models import (
            NoTradeDecision,
            RiskDecision,
            RiskEvaluation,
        )
        from crypto_core.state.models import SystemState

        es = ExecutionStateStore(path=tmp_path / "exec.jsonl")
        risk_ok = RiskEvaluation(
            decision=RiskDecision.APPROVED,
            block_reason=None,
            system_state=SystemState.NORMAL,
            edge_signal=EdgeSignal(
                family=EdgeFamily.ORDER_FLOW_IMBALANCE,
                symbol="BTCUSDT",
                exchange="binance",
                direction="buy",
                confidence=0.8,
                score=0.8,
                evidence={},
                timestamp_ns=1_000_000_000,
                is_valid=True,
                block_reason=None,
            ),
            no_trade_decision=NoTradeDecision.allow(),
            evidence={},
            timestamp_ns=1_000_000_000,
        )
        book = BookContext(bid_price=49_900.0, ask_price=50_100.0, bid_size=1.0, ask_size=1.0)
        request = ExecutionRequest(
            symbol="BTCUSDT",
            exchange="binance",
            intent=OrderIntent.BUY,
            size=0.01,
            price_hint=50_000.0,
            risk_evaluation=risk_ok,
            timestamp_ns=1_000_000_000,
            book=book,
        )
        cfg = ExecutionLifecycleConfig(mode=ExecutionMode.PAPER)
        engine = ExecutionLifecycleEngine(config=cfg, store=es)
        result = engine.process(request)
        assert result.approved

        # Restore
        state = es.load()
        assert state.total_records >= 3  # CREATED + VALIDATED + SUBMITTED + FILLED at minimum
        assert len(state.orders) == 1
        restored = state.orders[0]
        assert str(restored.state) == str(OrderState.FILLED)
