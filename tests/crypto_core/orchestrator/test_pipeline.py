"""Integration tests for PipelineOrchestrator v1/v2 (PRD §2)."""

from __future__ import annotations

import pytest

from crypto_core.data.models.events import Exchange, TradeEvent, TradeSide
from crypto_core.orchestrator.models import MarketDataInput, PipelineResult
from crypto_core.orchestrator.pipeline import PipelineConfig, PipelineOrchestrator
from crypto_core.state.models import SignalInputs, SystemState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_T0_NS = 1_000_000_000_000
_NS_PER_S = 1_000_000_000


def _trade(side: TradeSide, qty: float = 1.0) -> TradeEvent:
    return TradeEvent(
        trade_id=f"t{side}{qty}",
        symbol="BTCUSDT",
        exchange=Exchange.BINANCE,
        side=side,
        price=50_000.0,
        qty=qty,
        timestamp_ns=_T0_NS,
        sequence_no=1,
        is_maker=False,
    )


def _healthy_data(n_buys: int = 30, n_sells: int = 10) -> MarketDataInput:
    trades = tuple([_trade(TradeSide.BUY) for _ in range(n_buys)] + [_trade(TradeSide.SELL) for _ in range(n_sells)])
    return MarketDataInput(
        symbol="BTCUSDT",
        exchange="binance",
        timestamp_ns=_T0_NS,
        trades=trades,
        book_last_update_ns=_T0_NS - 100 * 1_000_000,  # 100ms ago
        book_has_snapshot=True,
        book_bid_count=5,
        book_ask_count=5,
        feed_connection_state="connected",
        feed_recovery_state="ready",
    )


def _stale_data() -> MarketDataInput:
    return MarketDataInput(
        symbol="BTCUSDT",
        exchange="binance",
        timestamp_ns=_T0_NS,
        trades=tuple([_trade(TradeSide.BUY) for _ in range(20)]),
        book_last_update_ns=_T0_NS - 30 * _NS_PER_S,  # 30 seconds old
        book_has_snapshot=True,
        book_bid_count=5,
        book_ask_count=5,
        feed_connection_state="connected",
        feed_recovery_state="ready",
    )


def _orchestrator(emit_telemetry: bool = False) -> PipelineOrchestrator:
    cfg = PipelineConfig(emit_telemetry=emit_telemetry)
    return PipelineOrchestrator(config=cfg)


def _healthy_signals() -> SignalInputs:
    return SignalInputs()  # all zeros → SHS = 1.0 → NORMAL


def _defensive_signals() -> SignalInputs:
    # Force SHS to ~0.50 → DEFENSIVE
    return SignalInputs(
        s2_drawdown=0.9,
        s3_cvar=0.9,
        s4_data_feed=0.8,
        s5_execution=0.8,
        s6_liquidity=0.8,
    )


# ---------------------------------------------------------------------------
# Healthy flow
# ---------------------------------------------------------------------------


class TestHealthyFlow:
    def test_healthy_pipeline_produces_approved_result(self) -> None:
        orch = _orchestrator()
        result = orch.process(_healthy_data(), _healthy_signals())
        assert isinstance(result, PipelineResult)
        assert result.approved is True
        assert result.state_snapshot.state == SystemState.NORMAL
        assert result.no_trade_decision.allowed is True
        assert len(result.edge_signals) == 1
        assert result.edge_signals[0].is_valid is True
        assert len(result.risk_evaluations) == 1
        assert result.risk_evaluations[0].approved is True

    def test_result_is_frozen(self) -> None:
        orch = _orchestrator()
        result = orch.process(_healthy_data(), _healthy_signals())
        with pytest.raises((AttributeError, TypeError)):
            result.approved = False  # type: ignore[misc]

    def test_timestamps_ordered(self) -> None:
        orch = _orchestrator()
        result = orch.process(_healthy_data(), _healthy_signals())
        assert result.output_ts_ns >= result.input_ts_ns


# ---------------------------------------------------------------------------
# Stale data block
# ---------------------------------------------------------------------------


class TestStaleDataBlock:
    def test_stale_data_blocks_pipeline(self) -> None:
        orch = _orchestrator()
        result = orch.process(_stale_data(), _healthy_signals())
        assert result.approved is False
        assert result.block_stage == "guard"
        assert "stale" in (result.block_reason or "")


# ---------------------------------------------------------------------------
# State defensive block
# ---------------------------------------------------------------------------


class TestStateDefensiveBlock:
    def test_defensive_state_blocks_pipeline(self) -> None:
        orch = _orchestrator()
        result = orch.process(_healthy_data(), _defensive_signals())
        assert result.approved is False
        # State should be DEFENSIVE
        from crypto_core.state.models import is_at_least

        assert is_at_least(result.state_snapshot.state, SystemState.DEFENSIVE)

    def test_halt_state_blocks_pipeline(self) -> None:
        orch = _orchestrator()
        # S1=1.0 → KS-4 → HALT
        halt_signals = SignalInputs(s1_kill_switch=1.0)
        result = orch.process(_healthy_data(), halt_signals)
        assert result.approved is False
        assert result.state_snapshot.state == SystemState.HALT


# ---------------------------------------------------------------------------
# Invalid edge block
# ---------------------------------------------------------------------------


class TestInvalidEdgeBlock:
    def test_no_trades_produces_invalid_edge(self) -> None:
        orch = _orchestrator()
        data = MarketDataInput(
            symbol="BTCUSDT",
            exchange="binance",
            timestamp_ns=_T0_NS,
            trades=(),  # no trades
            book_last_update_ns=_T0_NS - 100 * 1_000_000,
            book_has_snapshot=True,
            book_bid_count=5,
            book_ask_count=5,
            feed_connection_state="connected",
            feed_recovery_state="ready",
        )
        result = orch.process(data, _healthy_signals())
        assert result.approved is False
        assert len(result.edge_signals) == 1
        assert result.edge_signals[0].is_valid is False


# ---------------------------------------------------------------------------
# Deterministic replay equality
# ---------------------------------------------------------------------------


class TestDeterministicReplay:
    def test_same_inputs_produce_same_outputs(self) -> None:
        """Same inputs → same approval decision, same state, same directions."""
        orch1 = _orchestrator()
        orch2 = _orchestrator()

        data = _healthy_data()
        sigs = _healthy_signals()

        r1 = orch1.process(data, sigs)
        r2 = orch2.process(data, sigs)

        assert r1.approved == r2.approved
        assert r1.state_snapshot.state == r2.state_snapshot.state
        assert abs(r1.state_snapshot.shs - r2.state_snapshot.shs) < 1e-9
        assert len(r1.edge_signals) == len(r2.edge_signals)
        for s1, s2 in zip(r1.edge_signals, r2.edge_signals):
            assert s1.direction == s2.direction
            assert s1.is_valid == s2.is_valid
            assert abs(s1.confidence - s2.confidence) < 1e-9

    def test_pipeline_result_has_full_audit_trail(self) -> None:
        orch = _orchestrator()
        result = orch.process(_healthy_data(), _healthy_signals())
        assert result.state_snapshot is not None
        assert result.no_trade_decision is not None
        assert len(result.edge_signals) > 0
        assert len(result.risk_evaluations) > 0


# ---------------------------------------------------------------------------
# Risk v2 integration — evaluations now routed through evaluate_v2()
# ---------------------------------------------------------------------------


class TestRiskV2Integration:
    """Verify that the pipeline now enforces all v2 risk gates end-to-end."""

    def test_v2_kill_switch_level_present_in_evaluation(self) -> None:
        """Risk evaluations carry kill_switch_level, confirming evaluate_v2 is used."""
        orch = _orchestrator()
        result = orch.process(_healthy_data(), _healthy_signals())
        # evaluate_v2 populates kill_switch_level; v1 evaluate() does not
        assert len(result.risk_evaluations) == 1
        assert result.risk_evaluations[0].kill_switch_level == 0

    def test_ks_level_2_blocks_new_entries_end_to_end(self) -> None:
        """KS level 2 (KS_BLOCK_THRESHOLD) must block all new entries."""
        orch = _orchestrator()
        result = orch.process(_healthy_data(), _healthy_signals(), kill_switch_level=2)
        assert result.approved is False
        assert result.block_stage == "risk"
        assert result.block_reason is not None
        assert "ks_blocked" in (result.block_reason or "")
        # Risk evaluations are present but all blocked
        assert len(result.risk_evaluations) == 1
        assert result.risk_evaluations[0].approved is False
        assert result.risk_evaluations[0].kill_switch_level == 2

    def test_ks_level_3_blocks_end_to_end(self) -> None:
        """KS level 3 (flatten/stop) must also block new entries."""
        orch = _orchestrator()
        result = orch.process(_healthy_data(), _healthy_signals(), kill_switch_level=3)
        assert result.approved is False
        assert result.block_stage == "risk"
        assert result.risk_evaluations[0].kill_switch_level == 3

    def test_ks_level_1_does_not_block(self) -> None:
        """KS level 1 (advisory/reduce) is below the hard block threshold — must pass."""
        orch = _orchestrator()
        result = orch.process(_healthy_data(), _healthy_signals(), kill_switch_level=1)
        assert result.approved is True
        assert result.risk_evaluations[0].kill_switch_level == 1

    def test_ks_level_0_passes_through(self) -> None:
        """Default KS level 0 (normal) must not block on healthy data."""
        orch = _orchestrator()
        result = orch.process(_healthy_data(), _healthy_signals(), kill_switch_level=0)
        assert result.approved is True

    def test_unavailable_optional_gates_skip_not_block(self) -> None:
        """All optional v2 gates (dtl, kelly, cvar, portfolio) are None in the
        orchestrator — they must skip, not block healthy trades."""
        orch = _orchestrator()
        result = orch.process(_healthy_data(), _healthy_signals())
        assert result.approved is True
        # None optional gates leave these fields as None in the evaluation
        assert result.risk_evaluations[0].dtl_pct is None
        assert result.risk_evaluations[0].kelly_fraction is None
        assert result.risk_evaluations[0].portfolio_snapshot is None

    def test_deterministic_replay_with_ks_level(self) -> None:
        """Same inputs + same KS level → identical v2 evaluation outcomes."""
        orch1 = _orchestrator()
        orch2 = _orchestrator()
        data = _healthy_data()
        sigs = _healthy_signals()

        r1 = orch1.process(data, sigs, kill_switch_level=1)
        r2 = orch2.process(data, sigs, kill_switch_level=1)

        assert r1.approved == r2.approved
        assert r1.state_snapshot.state == r2.state_snapshot.state
        for e1, e2 in zip(r1.risk_evaluations, r2.risk_evaluations):
            assert e1.approved == e2.approved
            assert e1.kill_switch_level == e2.kill_switch_level
            assert str(e1.block_reason) == str(e2.block_reason)

    def test_ks_block_audit_evidence_is_present(self) -> None:
        """KS block must populate evidence with the block key."""
        orch = _orchestrator()
        result = orch.process(_healthy_data(), _healthy_signals(), kill_switch_level=2)
        ev = result.risk_evaluations[0].evidence
        assert "block" in ev
        assert "ks_level_2" in str(ev["block"])
