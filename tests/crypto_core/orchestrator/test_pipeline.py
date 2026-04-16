"""Integration tests for PipelineOrchestrator v1/v2 (PRD §2)."""

from __future__ import annotations

import dataclasses
import json

import pytest

from crypto_core.data.models.events import Exchange, MarkPriceEvent, TradeEvent, TradeSide
from crypto_core.edge.models import EdgeFamily, SignalDirection
from crypto_core.execution.engine import ExecutionConfig
from crypto_core.execution.fill_pricer import FillPricerConfig
from crypto_core.execution.models import ExecutionMode, RejectionReason
from crypto_core.orchestrator.models import MarketDataInput, PipelineResult
from crypto_core.orchestrator.pipeline import PipelineConfig, PipelineOrchestrator
from crypto_core.regime.tracker import MarketRegimeTracker
from crypto_core.state.models import SignalInputs, SystemState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_T0_NS = 1_000_000_000_000
_NS_PER_S = 1_000_000_000


def _trade(
    side: TradeSide,
    qty: float = 1.0,
    price: float = 50_000.0,
    timestamp_ns: int = _T0_NS,
) -> TradeEvent:
    return TradeEvent(
        trade_id=f"t{side}{qty}",
        symbol="BTCUSDT",
        exchange=Exchange.BINANCE,
        side=side,
        price=price,
        qty=qty,
        timestamp_ns=timestamp_ns,
        sequence_no=1,
        is_maker=False,
    )


def _mark_price_event(funding_rate: float = 0.0001, timestamp_ns: int = _T0_NS) -> MarkPriceEvent:
    return MarkPriceEvent(
        symbol="BTCUSDT",
        exchange=Exchange.BINANCE,
        mark_price=50_000.0,
        index_price=50_000.0,
        funding_rate=funding_rate,
        next_funding_time_ns=timestamp_ns + 8 * 3600 * 1_000_000_000,
        timestamp_ns=timestamp_ns,
    )


def _signal_map(signals) -> dict[EdgeFamily, object]:
    return {signal.family: signal for signal in signals}


def _healthy_data(n_buys: int = 30, n_sells: int = 10) -> MarketDataInput:
    trades = tuple(
        [_trade(TradeSide.BUY, price=50_250.0 if idx % 2 == 0 else 49_750.0) for idx in range(n_buys)]
        + [_trade(TradeSide.SELL, price=49_750.0 if idx % 2 == 0 else 50_250.0) for idx in range(n_sells)]
    )
    return MarketDataInput(
        symbol="BTCUSDT",
        exchange="binance",
        timestamp_ns=_T0_NS,
        trades=trades,
        book_last_update_ns=_T0_NS - 100 * 1_000_000,  # 100ms ago
        book_has_snapshot=True,
        book_bid_count=6,
        book_ask_count=6,
        feed_connection_state="connected",
        feed_recovery_state="ready",
        book_bid_price=49_900.0,
        book_ask_price=50_100.0,
        book_bid_size=1.0,
        book_ask_size=1.0,
        liquidation_events=(),
        mark_price_event=_mark_price_event(),
    )


def _healthy_data_at(price: float, timestamp_ns: int) -> MarketDataInput:
    trades = tuple(
        [
            _trade(
                TradeSide.BUY,
                price=price * (1.005 if idx % 2 == 0 else 0.995),
                timestamp_ns=timestamp_ns,
            )
            for idx in range(30)
        ]
        + [
            _trade(
                TradeSide.SELL,
                price=price * (0.995 if idx % 2 == 0 else 1.005),
                timestamp_ns=timestamp_ns,
            )
            for idx in range(10)
        ]
    )
    return MarketDataInput(
        symbol="BTCUSDT",
        exchange="binance",
        timestamp_ns=timestamp_ns,
        trades=trades,
        book_last_update_ns=timestamp_ns - 100 * 1_000_000,
        book_has_snapshot=True,
        book_bid_count=6,
        book_ask_count=6,
        feed_connection_state="connected",
        feed_recovery_state="ready",
        book_bid_price=price - 100.0,
        book_ask_price=price + 100.0,
        book_bid_size=1.0,
        book_ask_size=1.0,
        liquidation_events=(),
        mark_price_event=_mark_price_event(timestamp_ns=timestamp_ns),
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
        book_bid_price=49_900.0,
        book_ask_price=50_100.0,
        book_bid_size=1.0,
        book_ask_size=1.0,
        liquidation_events=(),
        mark_price_event=_mark_price_event(),
    )


def _low_liquidity_data() -> MarketDataInput:
    data = _healthy_data()
    return dataclasses.replace(data, book_bid_count=1, book_ask_count=1)


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
        by_family = _signal_map(result.edge_signals)
        assert isinstance(result, PipelineResult)
        assert result.approved is True
        assert result.state_snapshot.state == SystemState.NORMAL
        assert result.no_trade_decision.allowed is True
        # Phase 6B: 4 runtime families (A, B, C, D)
        assert len(result.edge_signals) == 4
        assert set(by_family) == {
            EdgeFamily.ORDER_FLOW_IMBALANCE,
            EdgeFamily.FUNDING_RATE,
            EdgeFamily.VOLATILITY_TRANSITION,
            EdgeFamily.LIQUIDATION_SIGNAL,
        }
        assert by_family[EdgeFamily.ORDER_FLOW_IMBALANCE].is_valid is True
        assert by_family[EdgeFamily.FUNDING_RATE].is_valid is True
        assert by_family[EdgeFamily.FUNDING_RATE].direction == SignalDirection.NEUTRAL
        assert by_family[EdgeFamily.VOLATILITY_TRANSITION].is_valid is False
        assert by_family[EdgeFamily.VOLATILITY_TRANSITION].block_reason == (
            "activation_blocked:activation_input_unavailable:regime_transition_active"
        )
        assert by_family[EdgeFamily.LIQUIDATION_SIGNAL].is_valid is False
        assert by_family[EdgeFamily.LIQUIDATION_SIGNAL].block_reason == "activation_blocked:regime_disallowed"
        assert len(result.risk_evaluations) == 4
        assert result.risk_evaluations[0].approved is True  # OFI (Family A)

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
            book_bid_price=49_900.0,
            book_ask_price=50_100.0,
            book_bid_size=1.0,
            book_ask_size=1.0,
        )
        result = orch.process(data, _healthy_signals())
        assert result.approved is False
        # Phase 6B: 4 runtime families — all invalid with no trades
        assert len(result.edge_signals) == 4
        assert all(not s.is_valid for s in result.edge_signals)


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


class TestActivationIntegration:
    def test_pipeline_blocks_funding_without_mark_price(self) -> None:
        orch = _orchestrator()
        data = dataclasses.replace(_healthy_data(), mark_price_event=None)
        result = orch.process(data, _healthy_signals())
        funding = _signal_map(result.edge_signals)[EdgeFamily.FUNDING_RATE]
        assert funding.is_valid is False
        assert funding.block_reason == "activation_blocked:funding_feed_unavailable"
        assert funding.evidence["activation_state"] == "blocked"

    def test_pipeline_liquidity_activation_blocks_ofi_and_volatility(self) -> None:
        orch = PipelineOrchestrator(
            config=PipelineConfig(emit_telemetry=False),
            regime_tracker=MarketRegimeTracker(),
        )
        result = orch.process(_low_liquidity_data(), _healthy_signals())
        by_family = _signal_map(result.edge_signals)
        assert by_family[EdgeFamily.ORDER_FLOW_IMBALANCE].is_valid is False
        assert by_family[EdgeFamily.ORDER_FLOW_IMBALANCE].block_reason == "activation_blocked:liquidity_dry_blocked"
        assert by_family[EdgeFamily.VOLATILITY_TRANSITION].is_valid is False
        assert by_family[EdgeFamily.VOLATILITY_TRANSITION].block_reason == (
            "activation_blocked:activation_input_unavailable:regime_transition_active"
        )
        assert by_family[EdgeFamily.FUNDING_RATE].block_reason == "activation_blocked:liquidity_dry_blocked"
        assert by_family[EdgeFamily.LIQUIDATION_SIGNAL].block_reason == "activation_blocked:liquidity_dry_blocked"

    def test_pipeline_exposes_activation_audit_fields(self) -> None:
        orch = _orchestrator()
        result = orch.process(_healthy_data(), _healthy_signals())
        ofi = _signal_map(result.edge_signals)[EdgeFamily.ORDER_FLOW_IMBALANCE]
        assert "activation_reason" in ofi.evidence
        assert "evaluation_state" in ofi.evidence
        assert "prd_family_code" in ofi.evidence

    def test_pipeline_deterministic_replay_for_runtime_families(self) -> None:
        orch1 = PipelineOrchestrator(
            config=PipelineConfig(emit_telemetry=False),
            regime_tracker=MarketRegimeTracker(),
        )
        orch2 = PipelineOrchestrator(
            config=PipelineConfig(emit_telemetry=False),
            regime_tracker=MarketRegimeTracker(),
        )
        data = _healthy_data()
        r1 = orch1.process(data, _healthy_signals())
        r2 = orch2.process(data, _healthy_signals())
        for s1, s2 in zip(r1.edge_signals, r2.edge_signals):
            assert s1.family == s2.family
            assert s1.direction == s2.direction
            assert s1.is_valid == s2.is_valid
            assert s1.evidence["activation_reason"] == s2.evidence["activation_reason"]


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
        # Phase 6B: 4 runtime families produce 4 risk evaluations
        assert len(result.risk_evaluations) == 4
        assert result.risk_evaluations[0].kill_switch_level == 0  # OFI (Family A)

    def test_ks_level_2_blocks_new_entries_end_to_end(self) -> None:
        """KS level 2 (KS_BLOCK_THRESHOLD) must block all new entries.

        With Phase 5C NT-R01 in the guard, KS level ≥ 2 blocks at the guard
        stage (before risk).  Risk stage still runs and propagates the KS
        level, but the pipeline is first blocked at 'guard'.
        """
        orch = _orchestrator()
        result = orch.process(_healthy_data(), _healthy_signals(), kill_switch_level=2)
        assert result.approved is False
        # NT-R01 fires in the guard — block_stage is now 'guard'
        assert result.block_stage == "guard"
        assert result.block_reason is not None
        assert "NT-R01" in (result.block_reason or "")
        # Risk evaluations are present because the pipeline always runs all stages;
        # the edge engine emits an invalid signal when the guard blocks, and the
        # risk engine evaluates it — KS level is preserved on the evaluation.
        # Phase 6B: 4 runtime families produce 4 risk evaluations.
        assert len(result.risk_evaluations) == 4
        assert result.risk_evaluations[0].approved is False  # OFI (Family A)
        assert result.risk_evaluations[0].kill_switch_level == 2

    def test_ks_level_3_blocks_end_to_end(self) -> None:
        """KS level 3 (flatten/stop) must also block new entries.

        NT-R01 fires at guard stage for level >= ks_block_threshold (2).
        """
        orch = _orchestrator()
        result = orch.process(_healthy_data(), _healthy_signals(), kill_switch_level=3)
        assert result.approved is False
        assert result.block_stage == "guard"
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
        """KS block (NT-R01) must populate evidence in the guard decision.

        With Phase 5C NT-R01 in the guard, the KS block evidence is now on
        result.no_trade_decision.evidence (not the risk evaluation).
        """
        orch = _orchestrator()
        result = orch.process(_healthy_data(), _healthy_signals(), kill_switch_level=2)
        # Guard decision carries NT-R01 evidence
        ev = result.no_trade_decision.evidence
        assert ev.get("ks_level") == 2
        assert ev.get("rule") == "NT-R01"


# ---------------------------------------------------------------------------
# Phase 5B — Kill-switch engine integration
# ---------------------------------------------------------------------------


def _disconnected_data() -> MarketDataInput:
    """Data with feed_connection_state != 'connected' → data_failure_count=1 in KS engine."""
    import dataclasses

    return dataclasses.replace(_healthy_data(), feed_connection_state="disconnected")


def _recovering_data() -> MarketDataInput:
    """Data with feed_recovery_state == 'recovering' → recovery_active=True in KS engine."""
    import dataclasses

    return dataclasses.replace(_healthy_data(), feed_recovery_state="recovering")


class TestKillSwitchEngineIntegration:
    """Verify KillSwitchEngine is wired into the pipeline (Phase 5B)."""

    def test_ks_result_present_on_healthy_run(self) -> None:
        """PipelineResult must carry a non-None ks_result after Phase 5B."""
        orch = _orchestrator()
        result = orch.process(_healthy_data(), _healthy_signals())
        assert result.ks_result is not None
        assert result.ks_result.level == 0
        assert result.ks_result.active_triggers == ()

    def test_ks_result_present_on_blocked_run(self) -> None:
        """ks_result must be populated even when pipeline is blocked."""
        from crypto_core.risk.kill_switch import KillSwitchInput

        orch = _orchestrator()
        ks_inp = KillSwitchInput(manual_override=True)
        result = orch.process(_healthy_data(), _healthy_signals(), ks_input=ks_inp)
        assert result.ks_result is not None
        assert result.ks_result.level == 4

    def test_ks_computed_from_halt_state(self) -> None:
        """HALT system state must produce ks_result.level == 4 without manual override."""
        from crypto_core.risk.contracts import KS_LEVEL_HALT
        from crypto_core.risk.kill_switch import TRIGGER_SYSTEM_HALT, KillSwitchInput

        orch = _orchestrator()
        ks_inp = KillSwitchInput(system_state=SystemState.HALT)
        result = orch.process(_healthy_data(), _healthy_signals(), ks_input=ks_inp)
        assert result.ks_result is not None
        assert result.ks_result.level == KS_LEVEL_HALT
        assert TRIGGER_SYSTEM_HALT in result.ks_result.active_triggers
        # Pipeline must block at risk stage
        assert result.approved is False

    def test_ks_computed_from_feed_disconnected(self) -> None:
        """Disconnected feed → data_failure_count=1 → KS block (level 2)."""
        from crypto_core.risk.contracts import KS_LEVEL_BLOCK
        from crypto_core.risk.kill_switch import TRIGGER_DATA_FAILURE_SINGLE

        orch = _orchestrator()
        result = orch.process(_disconnected_data(), _healthy_signals())
        assert result.ks_result is not None
        assert result.ks_result.level >= KS_LEVEL_BLOCK
        assert TRIGGER_DATA_FAILURE_SINGLE in result.ks_result.active_triggers
        assert result.approved is False

    def test_ks_computed_from_feed_recovering(self) -> None:
        """Recovering feed → recovery_active=True → KS reduce (level 1) minimum."""
        from crypto_core.risk.contracts import KS_LEVEL_REDUCE
        from crypto_core.risk.kill_switch import TRIGGER_RECOVERY_ACTIVE

        orch = _orchestrator()
        result = orch.process(_recovering_data(), _healthy_signals())
        assert result.ks_result is not None
        assert result.ks_result.level >= KS_LEVEL_REDUCE
        assert TRIGGER_RECOVERY_ACTIVE in result.ks_result.active_triggers

    def test_ks_input_override_respected(self) -> None:
        """Explicit ks_input override must be used verbatim, ignoring data signals."""
        from crypto_core.risk.kill_switch import ExecutionQuality, KillSwitchInput

        orch = _orchestrator()
        # Healthy data but we force execution quality = critical via override
        ks_inp = KillSwitchInput(execution_quality=ExecutionQuality.CRITICAL)
        result = orch.process(_healthy_data(), _healthy_signals(), ks_input=ks_inp)
        assert result.ks_result is not None
        assert result.ks_result.level == 2  # BLOCK
        # Should have blocked new entries
        assert result.approved is False

    def test_legacy_ks_level_floor_respected(self) -> None:
        """Legacy kill_switch_level param acts as a floor over the computed level."""
        orch = _orchestrator()
        # Healthy data → computed KS=0, but legacy param=2 → floor raises to 2
        result = orch.process(_healthy_data(), _healthy_signals(), kill_switch_level=2)
        assert result.approved is False
        assert result.risk_evaluations[0].kill_switch_level == 2

    def test_ks_result_evidence_includes_trigger_count(self) -> None:
        """KS result evidence must include active_trigger_count field."""
        orch = _orchestrator()
        result = orch.process(_healthy_data(), _healthy_signals())
        assert result.ks_result is not None
        assert "active_trigger_count" in result.ks_result.evidence

    def test_deterministic_ks_integration(self) -> None:
        """Same inputs produce identical ks_result across two separate orchestrators."""
        from crypto_core.risk.kill_switch import KillSwitchInput

        orch1 = _orchestrator()
        orch2 = _orchestrator()
        ks_inp = KillSwitchInput(latency_ms=300.0)
        data = _healthy_data()
        sigs = _healthy_signals()

        r1 = orch1.process(data, sigs, ks_input=ks_inp)
        r2 = orch2.process(data, sigs, ks_input=ks_inp)

        assert r1.ks_result is not None
        assert r2.ks_result is not None
        assert r1.ks_result.level == r2.ks_result.level
        assert r1.ks_result.winning_trigger == r2.ks_result.winning_trigger
        assert set(r1.ks_result.active_triggers) == set(r2.ks_result.active_triggers)


# ---------------------------------------------------------------------------
# Phase 5H — live CVaR integration
# ---------------------------------------------------------------------------


class TestCVaRIntegration:
    def _tracker(self):
        from crypto_core.cvar import CVaRConfig
        from crypto_core.execution.models import OrderIntent
        from crypto_core.portfolio.fills import SyntheticFill
        from crypto_core.portfolio.tracker import PositionTracker

        tracker = PositionTracker(
            initial_nav_usd=100_000.0,
            cvar_config=CVaRConfig(rolling_window=3, min_history=3),
        )
        tracker.apply_fill(
            SyntheticFill(
                symbol="BTCUSDT",
                exchange="binance",
                intent=OrderIntent.BUY,
                quantity=3.0,
                fill_price=50_000.0,
                leverage=1.0,
                mode=ExecutionMode.PAPER,
                order_id="seed-long",
                timestamp_ns=_T0_NS,
            )
        )
        return tracker

    def _run_price_path(self, orch: PipelineOrchestrator) -> list[PipelineResult]:
        prices = (50_000.0, 48_000.0, 46_000.0, 44_000.0)
        return [
            orch.process(_healthy_data_at(price, _T0_NS + index * _NS_PER_S), _healthy_signals())
            for index, price in enumerate(prices)
        ]

    def test_live_tracker_cvar_blocks_pipeline_at_guard_stage(self) -> None:
        from crypto_core.guard.no_trade_guard import NoTradeConfig

        tracker = self._tracker()
        cfg = PipelineConfig(
            emit_telemetry=False,
            guard=NoTradeConfig(open_risk_cap_pct=300.0, position_concentration_cap_pct=300.0),
            execution=ExecutionConfig(mode=ExecutionMode.DRY_RUN),
        )
        orch = PipelineOrchestrator(config=cfg, position_tracker=tracker)

        results = self._run_price_path(orch)
        final = results[-1]

        assert final.approved is False
        assert final.block_stage == "guard"
        assert "NT-R05" in (final.block_reason or "")
        assert final.no_trade_decision.allowed is False

    def test_live_tracker_cvar_blocks_pipeline_at_risk_stage(self) -> None:
        from crypto_core.guard.no_trade_guard import NoTradeConfig
        from crypto_core.risk.models import RiskBlockReason

        tracker = self._tracker()
        cfg = PipelineConfig(
            emit_telemetry=False,
            guard=NoTradeConfig(
                open_risk_cap_pct=300.0,
                position_concentration_cap_pct=300.0,
                cvar_budget_pct=10.0,
            ),
            execution=ExecutionConfig(mode=ExecutionMode.DRY_RUN),
        )
        orch = PipelineOrchestrator(config=cfg, position_tracker=tracker)

        results = self._run_price_path(orch)
        final = results[-1]

        assert final.no_trade_decision.allowed is True
        assert final.approved is False
        assert final.block_stage == "risk"
        # Phase 6B: 4 runtime families produce 4 risk evaluations.
        assert len(final.risk_evaluations) == 4
        # OFI (Family A) at index 0 is the directional signal blocked by CVaR.
        assert final.risk_evaluations[0].block_reason == RiskBlockReason.CVAR_LIMIT
        assert final.risk_evaluations[0].evidence["cvar_available"] is True

    def test_risk_telemetry_includes_live_cvar_metrics(self, tmp_path) -> None:
        from crypto_core.guard.no_trade_guard import NoTradeConfig

        tracker = self._tracker()
        cfg = PipelineConfig(
            emit_telemetry=True,
            telemetry_log_dir=str(tmp_path),
            guard=NoTradeConfig(
                open_risk_cap_pct=300.0,
                position_concentration_cap_pct=300.0,
                cvar_budget_pct=10.0,
            ),
            execution=ExecutionConfig(mode=ExecutionMode.DRY_RUN),
        )
        orch = PipelineOrchestrator(config=cfg, position_tracker=tracker)

        self._run_price_path(orch)

        out_files = list(tmp_path.glob("telemetry_*.jsonl"))
        assert len(out_files) == 1
        rows = [json.loads(line) for line in out_files[0].read_text(encoding="utf-8").splitlines() if line.strip()]
        risk_rows = [row for row in rows if row["stage"] == "risk"]
        assert risk_rows
        metrics = risk_rows[-1]["metrics"]
        assert metrics["cvar_available"] is True
        assert metrics["cvar_history_count"] == 3
        assert metrics["cvar99_pct"] > 5.0
        assert metrics["var99_pct"] > 5.0


# ---------------------------------------------------------------------------
# Phase 6A — execution realism integration
# ---------------------------------------------------------------------------


class TestExecutionIntegration:
    def test_paper_execution_updates_tracker_and_result(self) -> None:
        from crypto_core.portfolio.tracker import PositionTracker

        tracker = PositionTracker(initial_nav_usd=100_000.0)
        cfg = PipelineConfig(
            emit_telemetry=False,
            execution=ExecutionConfig(mode=ExecutionMode.PAPER),
        )
        orch = PipelineOrchestrator(config=cfg, position_tracker=tracker)

        result = orch.process(_healthy_data(), _healthy_signals())

        assert result.approved is True
        assert result.block_stage is None
        assert len(result.execution_decisions) == 1
        decision = result.execution_decisions[0]
        assert decision.allowed is True
        assert decision.fill_generated is True
        assert decision.fill_price is not None

        snap = tracker.portfolio_snapshot(snapshot_ns=_T0_NS)
        assert snap.active_position_count == 1
        assert snap.total_notional_usd == pytest.approx(0.01 * decision.fill_price, rel=1e-6)

    def test_execution_rejection_blocks_pipeline_without_mutation(self) -> None:
        from crypto_core.portfolio.tracker import PositionTracker

        tracker = PositionTracker(initial_nav_usd=100_000.0)
        cfg = PipelineConfig(
            emit_telemetry=False,
            execution=ExecutionConfig(
                mode=ExecutionMode.PAPER,
                fill_pricer=FillPricerConfig(max_spread_bps=5.0),
            ),
        )
        orch = PipelineOrchestrator(config=cfg, position_tracker=tracker)

        result = orch.process(_healthy_data(), _healthy_signals())

        assert result.approved is False
        assert result.block_stage == "execution"
        assert len(result.execution_decisions) == 1
        decision = result.execution_decisions[0]
        assert decision.allowed is False
        assert decision.rejection_reason == RejectionReason.EXCESSIVE_SPREAD

        snap = tracker.portfolio_snapshot(snapshot_ns=_T0_NS)
        assert snap.active_position_count == 0

    def test_execution_stage_is_deterministic_for_identical_inputs(self) -> None:
        cfg = PipelineConfig(
            emit_telemetry=False,
            execution=ExecutionConfig(mode=ExecutionMode.PAPER),
        )
        orch1 = PipelineOrchestrator(config=cfg)
        orch2 = PipelineOrchestrator(config=cfg)

        r1 = orch1.process(_healthy_data(), _healthy_signals())
        r2 = orch2.process(_healthy_data(), _healthy_signals())

        assert len(r1.execution_decisions) == 1
        assert len(r2.execution_decisions) == 1
        d1 = r1.execution_decisions[0]
        d2 = r2.execution_decisions[0]
        assert d1.allowed == d2.allowed
        assert d1.fill_price == d2.fill_price
        assert d1.spread_bps == d2.spread_bps
        assert d1.slippage_bps == d2.slippage_bps
        assert d1.participation_pct == d2.participation_pct

    def test_execution_telemetry_contains_realism_fields(self, tmp_path) -> None:
        cfg = PipelineConfig(
            emit_telemetry=True,
            telemetry_log_dir=str(tmp_path),
            execution=ExecutionConfig(mode=ExecutionMode.PAPER),
        )
        orch = PipelineOrchestrator(config=cfg)

        result = orch.process(_healthy_data(), _healthy_signals())
        assert result.approved is True

        out_files = list(tmp_path.glob("telemetry_*.jsonl"))
        assert len(out_files) == 1
        lines = out_files[0].read_text(encoding="utf-8").splitlines()
        telemetry_rows = [json.loads(line) for line in lines if line.strip()]
        execution_rows = [row for row in telemetry_rows if row["stage"] == "execution"]
        assert len(execution_rows) == 1
        metrics = execution_rows[0]["metrics"]
        assert metrics["execution_fill_generated"] is True
        assert metrics["execution_reference_mid"] == pytest.approx(50_000.0)
        assert metrics["execution_fill_price"] > metrics["execution_reference_mid"]
        assert metrics["execution_spread_bps"] == pytest.approx(40.0)
        assert metrics["execution_slippage_bps"] > 0.0
        assert metrics["execution_participation_pct"] == pytest.approx(1.0)
