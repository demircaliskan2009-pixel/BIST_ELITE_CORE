"""Pipeline Orchestrator v1 — deterministic data → state → guard → edge → risk.

All stages fail-closed: any broken stage blocks all downstream stages.
Same input stream → same outputs (deterministic replay equivalence).
Telemetry is emitted at each stage boundary.

PRD reference: §2 System Orchestration.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from crypto_core.edge.activation import (
    execution_condition_from_runtime,
    liquidity_condition_from_score,
    regime_state_from_trades,
    spread_condition_from_book,
    volatility_condition_from_trades,
)
from crypto_core.edge.engine import EdgeEngine, EdgeEngineConfig
from crypto_core.edge.families.funding import FundingSafetyContext
from crypto_core.edge.models import SignalDirection
from crypto_core.edge_health.models import EdgeHealthSnapshot
from crypto_core.edge_health.tracker import EdgeHealthTracker
from crypto_core.execution.engine import ExecutionConfig, ExecutionEngine
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import BookContext, ExecutionDecision, ExecutionRequest, OrderIntent
from crypto_core.execution.paper_adapter import PaperAdapterConfig
from crypto_core.execution.recovery import RecoveryEvidence
from crypto_core.execution.route_binding import (
    MetadataGatedRouter,
    RouteDecision,
    RouteDecisionOutcome,
)
from crypto_core.execution.tca_loop import ExecutionTCALoop, PriceUpdateResult
from crypto_core.execution.venue_metadata import VenueMetadataSnapshot
from crypto_core.execution.venue_scoring import VenueScoreComponents
from crypto_core.guard.models import (
    EdgeHealthInput,
    MarketRegimeInput,
    NoTradeContext,
    NoTradeDecision,
    NoTradeReason,
    RiskGuardInput,
    TemporalInput,
)
from crypto_core.guard.no_trade_guard import NoTradeConfig, NoTradeGuard
from crypto_core.orchestrator.models import MarketDataInput, PipelineResult
from crypto_core.portfolio.fills import SyntheticFillFactory
from crypto_core.portfolio.tracker import PositionTracker
from crypto_core.regime.models import LiquiditySignal, RegimeSignalInput, RegimeSnapshot
from crypto_core.regime.tracker import MarketRegimeTracker
from crypto_core.risk.contracts import KS_LEVEL_NORMAL, RiskInput
from crypto_core.risk.engine import RiskEngine
from crypto_core.risk.kill_switch import KillSwitchEngine, KillSwitchInput, KillSwitchResult
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.engine import SystemStateEngine
from crypto_core.state.models import SignalInputs, StateSnapshot, SystemState, is_at_least
from crypto_core.telemetry.emitter import TelemetryEmitter
from crypto_core.temporal.models import TemporalSnapshot
from crypto_core.temporal.scheduler import TemporalScheduler

logger = logging.getLogger(__name__)

_NS_PER_HOUR: int = 3600 * 1_000_000_000
_PRICE_HISTORY_MAXLEN: int = 4096


@dataclass(frozen=True)
class _ExecutionRuntimeSample:
    latency_ms: float
    fill_rate_pct: float


@dataclass(frozen=True)
class _ActivationRuntimeContext:
    regime_state: str | None
    liquidity_condition: str | None
    execution_condition: str | None
    spread_condition: str | None
    volatility_condition: str | None
    funding_safety_context: FundingSafetyContext


@dataclass
class PipelineConfig:
    """Configuration bundle for the pipeline orchestrator."""

    guard: NoTradeConfig = None  # type: ignore[assignment]
    edge: EdgeEngineConfig = None  # type: ignore[assignment]
    execution: ExecutionConfig = None  # type: ignore[assignment]
    execution_lifecycle: ExecutionLifecycleConfig = None  # type: ignore[assignment]
    execution_order_size: float = 0.01
    execution_leverage: float = 1.0
    telemetry_log_dir: str = "logs/telemetry"
    emit_telemetry: bool = True

    def __post_init__(self) -> None:
        if self.guard is None:
            self.guard = NoTradeConfig()
        if self.edge is None:
            self.edge = EdgeEngineConfig()
        if self.execution is None:
            self.execution = ExecutionConfig()
        if self.execution_lifecycle is None:
            self.execution_lifecycle = ExecutionLifecycleConfig(
                mode=self.execution.mode,
                paper_adapter=PaperAdapterConfig(fill_pricer=self.execution.fill_pricer),
                fill_pricer=self.execution.fill_pricer,
            )


class PipelineOrchestrator:
    """Deterministic single-process pipeline orchestrator.

    Stages (in order, fail-closed):
      1. State evaluation    — SignalInputs → StateSnapshot
      2. Guard evaluation    — NoTradeContext → NoTradeDecision
      3. Edge evaluation     — trades + state + guard → EdgeSignals
      4. Risk evaluation     — EdgeSignal + state + guard → RiskEvaluation
            5. Execution evaluation — approved risk outputs → execution decisions
            6. Telemetry emission   — per-stage metrics → JSONL

    Architecture note:
      This orchestrator is in-process and synchronous.
      It is designed to expand to event-driven operation later via the
      message bus (crypto-message-bus skill) without API changes.

    Usage::

        orch = PipelineOrchestrator()
        result = orch.process(market_data, signal_inputs)
    """

    def __init__(
        self,
        config: PipelineConfig | None = None,
        state_engine: SystemStateEngine | None = None,
        execution_engine: ExecutionEngine | None = None,
        telemetry_emitter: TelemetryEmitter | None = None,
        position_tracker: PositionTracker | None = None,
        regime_tracker: MarketRegimeTracker | None = None,
        edge_health_tracker: EdgeHealthTracker | None = None,
        temporal_scheduler: TemporalScheduler | None = None,
        lifecycle_engine: ExecutionLifecycleEngine | None = None,
        recovery_evidence: RecoveryEvidence | None = None,
        metadata_gated_router: MetadataGatedRouter | None = None,
        tca_loop: ExecutionTCALoop | None = None,
    ) -> None:
        self._cfg = config or PipelineConfig()
        self._state_engine = state_engine or SystemStateEngine()
        self._guard = NoTradeGuard(self._cfg.guard)
        self._edge_engine = EdgeEngine(self._cfg.edge)
        self._risk_engine = RiskEngine()
        self._execution_engine = execution_engine or ExecutionEngine(self._cfg.execution)
        # Phase 6D: lifecycle engine replaces the raw execute() + SyntheticFillFactory path.
        self._lifecycle_engine = lifecycle_engine or ExecutionLifecycleEngine(self._cfg.execution_lifecycle)
        self._ks_engine = KillSwitchEngine()
        # PositionTracker is optional — None = portfolio gates skip (Phase 5D+ wired)
        self._position_tracker: PositionTracker | None = position_tracker
        # Phase 6C: activation closure depends on real liquidity/regime context,
        # so the crypto pipeline enables the regime tracker by default.
        self._regime_tracker: MarketRegimeTracker | None = regime_tracker or MarketRegimeTracker()
        # Phase 6C: EHS feeds both NT-E and activation; enable tracker by default.
        self._edge_health_tracker: EdgeHealthTracker | None = edge_health_tracker or EdgeHealthTracker()
        # TemporalScheduler is optional — None = temporal family disabled (NT-T skipped)
        self._temporal_scheduler: TemporalScheduler | None = temporal_scheduler
        from pathlib import Path

        self._telemetry = telemetry_emitter or (
            TelemetryEmitter(log_dir=Path(self._cfg.telemetry_log_dir)) if self._cfg.emit_telemetry else None
        )
        self._price_history: dict[tuple[str, str], deque[tuple[int, float]]] = defaultdict(
            lambda: deque(maxlen=_PRICE_HISTORY_MAXLEN)
        )
        self._regime_history: dict[tuple[str, str], deque[tuple[int, str]]] = defaultdict(
            lambda: deque(maxlen=_PRICE_HISTORY_MAXLEN)
        )
        self._execution_runtime: dict[tuple[str, str], _ExecutionRuntimeSample] = {}
        # Phase 6F: recovery evidence for orchestrator visibility
        self._recovery_evidence: RecoveryEvidence | None = recovery_evidence
        if recovery_evidence is not None:
            self._emit_recovery_telemetry(recovery_evidence)

        # Phase 9D: execution intelligence integration
        self._metadata_gated_router: MetadataGatedRouter | None = metadata_gated_router
        self._tca_loop: ExecutionTCALoop | None = tca_loop
        self._venue_metadata: dict[str, VenueMetadataSnapshot] = {}
        self._venue_components: dict[str, VenueScoreComponents] = {}
        self._route_block_count: int = 0
        self._route_abstain_count: int = 0

    # ------------------------------------------------------------------
    # Properties for session-layer access (Phase 7E)
    # ------------------------------------------------------------------

    @property
    def position_tracker(self) -> PositionTracker | None:
        """Current position tracker instance."""
        return self._position_tracker

    @position_tracker.setter
    def position_tracker(self, tracker: PositionTracker | None) -> None:
        """Replace the position tracker (used by session recovery)."""
        self._position_tracker = tracker

    def process(
        self,
        data: MarketDataInput,
        signal_inputs: SignalInputs | None = None,
        kill_switch_level: int = KS_LEVEL_NORMAL,
        ks_input: KillSwitchInput | None = None,
    ) -> PipelineResult:
        """Execute the full pipeline for one market data input.

        Args:
            data: validated market data snapshot.
            signal_inputs: 10-signal SHS inputs. If None, uses zero signals
                           (system stays in or near NORMAL — safe for testing).
            kill_switch_level: DEPRECATED — kept for backward compatibility only.
                               Ignored when ks_input is provided.  When neither
                               is provided, a KillSwitchInput is built from
                               the state snapshot and data health signals.
            ks_input: explicit KillSwitchInput override.  If None, the
                      orchestrator builds one from available runtime signals.

        Returns:
            PipelineResult with full audit trail.
        """
        t_start = time.time_ns()

        try:
            return self._do_process(data, signal_inputs or SignalInputs(), t_start, kill_switch_level, ks_input)
        except Exception:
            logger.exception("PipelineOrchestrator.process raised — fail-closed block")
            ts = time.time_ns()
            # Produce minimal fail-closed result
            dummy_snap = StateSnapshot(
                timestamp_ns=ts,
                state=SystemState.HALT,
                shs=0.0,
                signals=signal_inputs or SignalInputs(),
                trigger_reason="exception_fail_closed",
            )
            no_trade = NoTradeDecision.block(NoTradeReason.SYSTEM_STATE_DEFENSIVE, {"error": "pipeline_exception"})
            return PipelineResult(
                input_ts_ns=data.timestamp_ns,
                output_ts_ns=ts,
                state_snapshot=dummy_snap,
                no_trade_decision=no_trade,
                edge_signals=(),
                risk_evaluations=(),
                block_stage="orchestrator",
                block_reason="exception_fail_closed",
                approved=False,
            )

    # -----------------------------------------------------------------------
    # Internal pipeline
    # -----------------------------------------------------------------------

    def _do_process(
        self,
        data: MarketDataInput,
        signal_inputs: SignalInputs,
        t_start: int,
        kill_switch_level: int,
        ks_input_override: KillSwitchInput | None,
    ) -> PipelineResult:
        ts = data.timestamp_ns

        # ── Stage 1: State ──────────────────────────────────────────────
        stage_t0 = time.time_ns()
        state_snap = self._state_engine.evaluate(signal_inputs, timestamp_ns=ts)
        _state_latency_ms = (time.time_ns() - stage_t0) / 1e6

        self._emit_telemetry_safe(
            "state",
            _state_latency_ms,
            {"shs_value": state_snap.shs, "system_state": str(state_snap.state)},
        )

        # ── Stage 2: Guard ──────────────────────────────────────────────
        stage_t0 = time.time_ns()
        # Build risk guard input — NT-R01 always set; NT-R02–R06 from tracker if available.
        cvar_snapshot = None
        if self._position_tracker is not None:
            mark_price = self._resolve_portfolio_mark_price(data)
            if mark_price is not None:
                self._position_tracker.update_mark(data.symbol, data.exchange, mark_price)
            cvar_snapshot = self._position_tracker.cvar_snapshot(snapshot_ns=ts)
            risk_guard_input = self._position_tracker.to_risk_guard_input(
                kill_switch_level=kill_switch_level,
                snapshot_ns=ts,
                cvar_snapshot=cvar_snapshot,
            )
        else:
            # NT-R01 only — all portfolio fields remain None (explicitly unavailable).
            risk_guard_input = RiskGuardInput(kill_switch_level=kill_switch_level)

        # Build market regime input — real values from tracker when available.
        # When tracker is None, market=None → NT-M family explicitly disabled.
        market_regime_input: MarketRegimeInput | None = None
        if self._regime_tracker is not None:
            spread_bps = None
            if data.book_has_snapshot and data.book_bid_price > 0.0 and data.book_ask_price > data.book_bid_price:
                mid_price = (data.book_bid_price + data.book_ask_price) / 2.0
                spread_bps = (data.book_ask_price - data.book_bid_price) / mid_price * 10_000.0
            liq_signal = LiquiditySignal(
                bid_level_count=data.book_bid_count,
                ask_level_count=data.book_ask_count,
                recent_trade_count=len(data.trades),
                timestamp_ns=ts,
                bid_ask_spread_bps=spread_bps,
            )
            regime_signal = RegimeSignalInput(
                snapshot_ns=ts,
                liquidity=liq_signal,
                leverage_proxy=None,  # unavailable until OI/MC feed integrated
                correlation_score=None,  # unavailable until cross-asset feed integrated
            )
            regime_snap = self._regime_tracker.update(regime_signal)
            market_regime_input = MarketRegimeInput(
                liquidity_score=regime_snap.liquidity_score,
                liquidity_crisis_sustained_ms=regime_snap.liquidity_crisis_sustained_ms,
                oi_mc_ratio=regime_snap.oi_mc_ratio,
                regime_transition_active=regime_snap.regime_transition_active,
                mean_pairwise_correlation=regime_snap.mean_pairwise_correlation,
            )
        else:
            regime_snap = None

        # Build edge health input — uses PREVIOUS cycle's history (deterministic).
        # When tracker is None, edge=None → NT-E family explicitly disabled.
        edge_health_input: EdgeHealthInput | None = None
        family_edge_health: dict[object, EdgeHealthSnapshot] = {}
        if self._edge_health_tracker is not None:
            edge_health_input = self._edge_health_tracker.to_edge_health_input(
                symbol=data.symbol,
                exchange=data.exchange,
                snapshot_ns=ts,
            )
            # edge_health_input may be None if no history yet — that's correct.
            family_edge_health = {
                family: self._edge_health_tracker.snapshot_for_key(
                    family=str(family),
                    symbol=data.symbol,
                    exchange=data.exchange,
                    snapshot_ns=ts,
                )
                for family in self._edge_engine.runtime_families
            }

        # Build temporal input — uses current scheduler state (deterministic).
        # When scheduler is None, temporal=None → NT-T family explicitly disabled.
        temporal_input: TemporalInput | None = None
        temporal_snap: TemporalSnapshot | None = None
        if self._temporal_scheduler is not None:
            temporal_snap = self._temporal_scheduler.snapshot(current_ns=ts)
            temporal_input = self._temporal_scheduler.to_temporal_input(temporal_snap)

        guard_ctx = NoTradeContext(
            symbol=data.symbol,
            exchange=data.exchange,
            current_ns=ts,
            book_last_update_ns=data.book_last_update_ns,
            book_has_snapshot=data.book_has_snapshot,
            book_bid_count=data.book_bid_count,
            book_ask_count=data.book_ask_count,
            feed_connection_state=data.feed_connection_state,
            feed_recovery_state=data.feed_recovery_state,
            system_state=str(state_snap.state),
            risk=risk_guard_input,
            market=market_regime_input,
            edge=edge_health_input,
            temporal=temporal_input,
        )
        no_trade = self._guard.evaluate(guard_ctx)
        guard_latency_ms = (time.time_ns() - stage_t0) / 1e6

        # Regime telemetry — only emit fields that have real values.
        _tele_regime: dict[str, object] = {"market_snapshot_available": regime_snap is not None}
        if regime_snap is not None:
            _tele_regime["regime_evidence_quality"] = str(regime_snap.evidence_quality)
            _tele_regime["regime_transition_active"] = regime_snap.regime_transition_active is True
            if regime_snap.liquidity_score is not None:
                _tele_regime["liquidity_score"] = round(regime_snap.liquidity_score, 4)
            if regime_snap.oi_mc_ratio is not None:
                _tele_regime["leverage_proxy"] = round(regime_snap.oi_mc_ratio, 6)
                _tele_regime["leverage_proxy_available"] = True
            else:
                _tele_regime["leverage_proxy_available"] = False
            if regime_snap.mean_pairwise_correlation is not None:
                _tele_regime["correlation_breakdown_score"] = round(regime_snap.mean_pairwise_correlation, 4)

        # Temporal telemetry — only emit fields when temporal scheduler is active.
        _tele_temporal: dict[str, object] = {"temporal_snapshot_available": temporal_snap is not None}
        if temporal_snap is not None:
            _tele_temporal["startup_warmup_active"] = temporal_snap.startup_warmup_active
            _tele_temporal["ks_cooldown_active"] = temporal_snap.ks_cooldown_active
            _tele_temporal["active_event_count"] = len(temporal_snap.active_events)
            if temporal_snap.active_events:
                _tele_temporal["active_event_window"] = temporal_snap.active_events[0].event_id
            if temporal_snap.cooldown.cooldown_until_ns > 0:
                _tele_temporal["cooldown_until_ns"] = temporal_snap.cooldown.cooldown_until_ns

        self._emit_telemetry_safe(
            "guard",
            guard_latency_ms,
            {"allowed": no_trade.allowed, "reason": str(no_trade.reason), **_tele_regime, **_tele_temporal},
        )

        activation_runtime = self._build_activation_runtime_context(
            data=data,
            state_snap=state_snap,
            regime_snap=regime_snap,
        )

        # ── Stage 3: Edge ───────────────────────────────────────────────
        stage_t0 = time.time_ns()
        edge_signals = self._edge_engine.evaluate(
            trades=list(data.trades),
            symbol=data.symbol,
            exchange=data.exchange,
            no_trade=no_trade,
            system_state=state_snap.state,
            timestamp_ns=ts,
            mark_price_event=data.mark_price_event,
            liquidation_events=data.liquidation_events,
            feed_connection_state=data.feed_connection_state,
            feed_recovery_state=data.feed_recovery_state,
            regime_state=activation_runtime.regime_state,
            liquidity_condition=activation_runtime.liquidity_condition,
            execution_condition=activation_runtime.execution_condition,
            spread_condition=activation_runtime.spread_condition,
            volatility_condition=activation_runtime.volatility_condition,
            funding_safety_context=activation_runtime.funding_safety_context,
            market_regime=regime_snap,
            family_edge_health=family_edge_health,
        )
        edge_latency_ms = (time.time_ns() - stage_t0) / 1e6

        valid_count = sum(1 for s in edge_signals if s.is_valid)

        # ── Stage 3-post: Edge health update ───────────────────────────
        # Record this cycle's signals into the edge health tracker so that
        # the NEXT cycle's guard stage gets real upstream NT-E values.
        if self._edge_health_tracker is not None:
            self._edge_health_tracker.record_signals(edge_signals)
            ehs_snap = self._edge_health_tracker.tracker_snapshot(snapshot_ns=ts)
        else:
            ehs_snap = None

        # Edge telemetry — include edge health metrics when available.
        _tele_edge: dict[str, object] = {
            "active_edges": valid_count,
            "total_edges": len(edge_signals),
            "edge_health_snapshot_available": ehs_snap is not None,
            "activation_regime_state": activation_runtime.regime_state or "unavailable",
            "activation_execution_condition": activation_runtime.execution_condition or "unavailable",
        }
        if ehs_snap is not None:
            _tele_edge["valid_edge_count"] = ehs_snap.valid_edge_count if ehs_snap.valid_edge_count is not None else 0
            _tele_edge["disabled_edge_count"] = ehs_snap.disabled_edge_count
            _tele_edge["warning_edge_count"] = ehs_snap.warning_edge_count
            _tele_edge["quarantine_edge_count"] = ehs_snap.quarantine_edge_count
            _tele_edge["capacity_red_count"] = ehs_snap.capacity_red_count
            if ehs_snap.min_ehs is not None:
                _tele_edge["minimum_ehs"] = round(ehs_snap.min_ehs, 4)
            if ehs_snap.max_ehs is not None:
                _tele_edge["maximum_ehs"] = round(ehs_snap.max_ehs, 4)

        self._emit_telemetry_safe(
            "edge",
            edge_latency_ms,
            _tele_edge,
        )

        # ── Stage 3.5: Kill-Switch computation ─────────────────────────
        # Build KillSwitchInput from available runtime signals.
        # If caller supplies ks_input_override, use that verbatim.
        # Otherwise derive from state snapshot + data health flags.
        if ks_input_override is not None:
            ks_inp = ks_input_override
        else:
            ks_inp = KillSwitchInput(
                system_state=state_snap.state,
                # Data health proxy: non-connected feed state = 1 failure
                data_failure_count=(1 if data.feed_connection_state not in ("connected", "ready") else 0),
                recovery_active=(data.feed_recovery_state == "recovering"),
                # latency_ms not measured here — Phase 5C will supply it
            )
        ks_result: KillSwitchResult = self._ks_engine.compute(ks_inp)
        # Backward-compat floor: if caller supplied a legacy kill_switch_level
        # that exceeds the computed level, honour it (higher always wins).
        computed_ks_level = max(ks_result.level, kill_switch_level)

        # Notify temporal scheduler of this cycle's KS level (for next cycle).
        # This allows NT-T02 (KS cooldown) to fire on the following cycle
        # without the guard needing to know about the current KS result.
        if self._temporal_scheduler is not None:
            self._temporal_scheduler.notify_ks_event(level=computed_ks_level, current_ns=ts)

        # ── Stage 4: Risk (v2) ──────────────────────────────────────────
        # Build portfolio risk snapshot — real values from tracker if available.
        portfolio_risk_snap = (
            self._position_tracker.to_portfolio_risk_snapshot(snapshot_ns=ts)
            if self._position_tracker is not None
            else None
        )
        cvar_input = (
            self._position_tracker.to_cvar_input(snapshot_ns=ts, cvar_snapshot=cvar_snapshot)
            if self._position_tracker is not None
            else None
        )

        stage_t0 = time.time_ns()
        risk_evals: list[RiskEvaluation] = []
        for sig in edge_signals:
            risk_input = RiskInput(
                edge_signal=sig,
                system_state=state_snap.state,
                no_trade=no_trade,
                timestamp_ns=ts,
                shs_snapshot=state_snap.shs,
                kill_switch_level=computed_ks_level,
                dtl=None,  # requires exchange-supplied liquidation price
                kelly=None,  # requires trade history distribution
                cvar=cvar_input,
                portfolio=portfolio_risk_snap,  # real values when tracker available
            )
            risk_eval = self._risk_engine.evaluate_v2(risk_input)
            risk_evals.append(risk_eval)
        risk_latency_ms = (time.time_ns() - stage_t0) / 1e6

        approved_count = sum(1 for r in risk_evals if r.approved)
        # Optional v2 telemetry fields — only include if non-None (schema forbids null)
        _tele_v2: dict[str, object] = {}
        for _r in risk_evals:
            if _r.kelly_fraction is not None:
                _prev = _tele_v2.get("kelly_fraction_min")
                _tele_v2["kelly_fraction_min"] = (
                    min(float(_prev), _r.kelly_fraction) if _prev is not None else _r.kelly_fraction
                )
            if _r.dtl_pct is not None:
                _prev = _tele_v2.get("dtl_pct_min")
                _tele_v2["dtl_pct_min"] = min(float(_prev), _r.dtl_pct) if _prev is not None else _r.dtl_pct
        # Portfolio telemetry — only when tracker is available
        _tele_portfolio: dict[str, object] = {}
        if self._position_tracker is not None:
            _psnap = self._position_tracker.portfolio_snapshot(snapshot_ns=ts)
            _tele_portfolio = {
                "open_positions_count": _psnap.active_position_count,
                "gross_exposure_pct": round(_psnap.gross_exposure_pct, 4),
                "net_exposure_pct": round(_psnap.net_exposure_pct, 4),
                "concentration_max_pct": round(_psnap.concentration_max_pct, 4),
                "daily_realized_pnl_pct": round(_psnap.daily_realized_pnl_pct, 4),
                "dtl_available_count": _psnap.dtl_available_count,
                "cvar_available": cvar_snapshot.available if cvar_snapshot is not None else False,
                "cvar_history_count": cvar_snapshot.history_count if cvar_snapshot is not None else 0,
                **(
                    {"margin_utilization_pct": round(_psnap.margin_used_pct, 4)}
                    if _psnap.margin_used_pct is not None
                    else {}
                ),
            }
            if cvar_snapshot is not None and cvar_snapshot.available:
                _tele_portfolio["cvar99_pct"] = round(float(cvar_snapshot.cvar99_pct), 4)
                _tele_portfolio["var99_pct"] = round(float(cvar_snapshot.var99_pct), 4)
        self._emit_telemetry_safe(
            "risk",
            risk_latency_ms,
            {
                "shs_value": state_snap.shs,
                "kill_switch_level": computed_ks_level,
                "approved_count": approved_count,
                "active_trigger_count": ks_result.evidence.get("active_trigger_count", 0),
                **({"winning_trigger": ks_result.winning_trigger} if ks_result.winning_trigger is not None else {}),
                **_tele_v2,
                **_tele_portfolio,
            },
        )

        # ── Stage 5: Execution (lifecycle-aware + route binding + TCA) ───
        stage_t0 = time.time_ns()
        executable_risk_evals = [
            risk_eval
            for risk_eval in risk_evals
            if risk_eval.approved and risk_eval.edge_signal.direction in (SignalDirection.BUY, SignalDirection.SELL)
        ]
        execution_decisions: list[ExecutionDecision] = []
        lifecycle_results: list = []
        route_decisions: list[RouteDecision] = []
        tca_price_update: PriceUpdateResult | None = None

        # Reference mid-price for TCA arrival/decision and markout advancement.
        # Policy: best-bid/ask mid (primary), last trade (fallback), None (absent).
        ref_mid = self._resolve_portfolio_mark_price(data)

        for risk_eval in executable_risk_evals:
            # Phase 9D: route binding check before execution
            route_decision: RouteDecision | None = None
            if self._metadata_gated_router is not None:
                route_decision = self._evaluate_route(data, risk_eval)
                route_decisions.append(route_decision)
                if not route_decision.is_routable:
                    if route_decision.outcome == RouteDecisionOutcome.BLOCK:
                        self._route_block_count += 1
                    elif route_decision.outcome == RouteDecisionOutcome.ABSTAIN:
                        self._route_abstain_count += 1
                    continue

            request = self._build_execution_request(data, risk_eval)
            # Phase 6D: use lifecycle engine for full order state machine.
            lifecycle_result = self._lifecycle_engine.process(request)
            lifecycle_results.append(lifecycle_result)
            # Apply fills from lifecycle result to position tracker.
            for fill_event in lifecycle_result.fill_events:
                synthetic = SyntheticFillFactory.from_fill_event(
                    fill_event,
                    mode=lifecycle_result.order.mode,
                    leverage=self._cfg.execution_leverage,
                )
                if self._position_tracker is not None:
                    self._position_tracker.apply_fill(synthetic)

                # Phase 9D: register fill in TCA loop for markout tracking.
                if self._tca_loop is not None:
                    self._register_fill_in_tca_loop(
                        fill_event=fill_event,
                        request=request,
                        route_decision=route_decision,
                        ref_mid=ref_mid,
                        regime_state=activation_runtime.regime_state,
                    )

            # Produce backward-compat ExecutionDecision from lifecycle result.
            decision = lifecycle_result.to_execution_decision()
            execution_decisions.append(decision)

        # Phase 9D: advance markout from current price observation.
        # Called every cycle: matures previously registered fills whose
        # horizons have elapsed, and auto-persists completed TCA records.
        if self._tca_loop is not None and ref_mid is not None:
            tca_price_update = self._tca_loop.on_price_update(
                data.symbol,
                data.exchange,
                ref_mid,
                data.timestamp_ns,
            )

        execution_latency_ms = (time.time_ns() - stage_t0) / 1e6
        execution_metrics: dict[str, object] = {
            "execution_decision_count": len(execution_decisions),
            "approved_risk_count": len(executable_risk_evals),
        }
        if execution_decisions:
            allowed_execution_count = sum(1 for decision in execution_decisions if decision.allowed)
            primary_decision = execution_decisions[0]
            execution_metrics["fill_rate_pct"] = allowed_execution_count / len(execution_decisions) * 100.0
            execution_metrics["execution_fill_generated"] = primary_decision.fill_generated
            if primary_decision.fill_price is not None:
                execution_metrics["execution_fill_price"] = round(primary_decision.fill_price, 8)
            if primary_decision.rejection_reason is not None:
                execution_metrics["execution_rejection_reason"] = str(primary_decision.rejection_reason)
            # Reference mid-price for slippage analysis
            if data.book_bid_price > 0.0 and data.book_ask_price > data.book_bid_price:
                execution_metrics["execution_reference_mid"] = round(
                    (data.book_bid_price + data.book_ask_price) / 2.0, 8
                )
        # Fill event realism metrics from primary lifecycle result
        if lifecycle_results and lifecycle_results[0].fill_events:
            primary_fill = lifecycle_results[0].fill_events[0]
            if primary_fill.spread_bps is not None:
                execution_metrics["execution_spread_bps"] = round(primary_fill.spread_bps, 4)
            if primary_fill.slippage_bps is not None:
                execution_metrics["execution_slippage_bps"] = round(primary_fill.slippage_bps, 4)
            if primary_fill.participation_pct is not None:
                execution_metrics["execution_participation_pct"] = round(primary_fill.participation_pct, 6)
        if lifecycle_results:
            primary_lc = lifecycle_results[0]
            execution_metrics["lifecycle_final_state"] = primary_lc.final_state
            execution_metrics["lifecycle_total_filled_qty"] = primary_lc.total_filled_quantity
            execution_metrics["lifecycle_event_count"] = len(primary_lc.order.event_history)
            if primary_lc.average_fill_price is not None:
                execution_metrics["lifecycle_avg_fill_price"] = round(primary_lc.average_fill_price, 8)

        self._update_execution_runtime_sample(
            symbol=data.symbol,
            exchange=data.exchange,
            latency_ms=execution_latency_ms,
            execution_decisions=execution_decisions,
        )

        self._emit_telemetry_safe("execution", execution_latency_ms, execution_metrics)

        # ── Determine overall result ────────────────────────────────────
        is_approved = any(r.approved for r in risk_evals)
        if executable_risk_evals:
            is_approved = any(decision.allowed for decision in execution_decisions)
        block_stage, block_reason = self._find_block(
            state_snap,
            no_trade,
            edge_signals,
            risk_evals,
            execution_decisions,
            route_decisions=tuple(route_decisions),
        )

        t_end = time.time_ns()
        return PipelineResult(
            input_ts_ns=data.timestamp_ns,
            output_ts_ns=t_end,
            state_snapshot=state_snap,
            no_trade_decision=no_trade,
            edge_signals=tuple(edge_signals),
            risk_evaluations=tuple(risk_evals),
            block_stage=block_stage,
            block_reason=block_reason,
            approved=is_approved,
            ks_result=ks_result,
            execution_decisions=tuple(execution_decisions),
            execution_lifecycle_results=tuple(lifecycle_results),
            route_decisions=tuple(route_decisions),
            tca_price_update=tca_price_update,
        )

    @staticmethod
    def _find_block(
        state_snap: StateSnapshot,
        no_trade: NoTradeDecision,
        edge_signals: list,
        risk_evals: list[RiskEvaluation],
        execution_decisions: list[ExecutionDecision],
        route_decisions: tuple = (),
    ) -> tuple[str | None, str | None]:
        """Identify the first blocking stage and reason."""
        if is_at_least(state_snap.state, SystemState.HALT):
            return "state", f"system_state:{state_snap.state}"
        if not no_trade.allowed:
            return "guard", str(no_trade.reason)
        if not edge_signals or all(not s.is_valid for s in edge_signals):
            return "edge", "all_signals_invalid"
        if risk_evals and all(r.decision == RiskDecision.BLOCKED for r in risk_evals):
            reasons = {str(r.block_reason) for r in risk_evals}
            return "risk", ",".join(sorted(reasons))
        approved_directional = any(
            risk_eval.approved and risk_eval.edge_signal.direction in (SignalDirection.BUY, SignalDirection.SELL)
            for risk_eval in risk_evals
        )
        # Phase 9D: route binding blocks
        if approved_directional and route_decisions and all(not rd.is_routable for rd in route_decisions):
            reasons = set()
            for rd in route_decisions:
                if rd.reason:
                    reasons.add(rd.reason)
            return "routing", ",".join(sorted(reasons)) if reasons else "all_routes_blocked"
        if (
            approved_directional
            and execution_decisions
            and all(not decision.allowed for decision in execution_decisions)
        ):
            reasons = {
                str(decision.rejection_reason)
                for decision in execution_decisions
                if decision.rejection_reason is not None
            }
            return "execution", ",".join(sorted(reasons))
        return None, None

    def _build_execution_request(
        self,
        data: MarketDataInput,
        risk_eval: RiskEvaluation,
    ) -> ExecutionRequest:
        """Build a deterministic execution request from one approved risk output."""
        direction = risk_eval.edge_signal.direction
        intent = OrderIntent.BUY if direction == SignalDirection.BUY else OrderIntent.SELL
        book = self._build_book_context(data)
        price_hint = self._resolve_price_hint(data, book)
        return ExecutionRequest(
            symbol=risk_eval.edge_signal.symbol,
            exchange=risk_eval.edge_signal.exchange,
            intent=intent,
            size=self._cfg.execution_order_size,
            price_hint=price_hint,
            risk_evaluation=risk_eval,
            timestamp_ns=data.timestamp_ns,
            book=book,
        )

    @staticmethod
    def _build_book_context(data: MarketDataInput) -> BookContext | None:
        """Return top-of-book context when a valid snapshot is available."""
        if not data.book_has_snapshot:
            return None
        if data.book_bid_price <= 0.0 or data.book_ask_price <= 0.0:
            return None
        return BookContext(
            bid_price=data.book_bid_price,
            ask_price=data.book_ask_price,
            bid_size=data.book_bid_size,
            ask_size=data.book_ask_size,
            bid_level_count=data.book_bid_count,
            ask_level_count=data.book_ask_count,
        )

    @staticmethod
    def _resolve_price_hint(data: MarketDataInput, book: BookContext | None) -> float:
        """Resolve a deterministic reference price for dry-run or degraded paper mode."""
        if book is not None:
            return book.mid_price
        if data.trades:
            return float(data.trades[-1].price)
        return 0.0

    @staticmethod
    def _resolve_portfolio_mark_price(data: MarketDataInput) -> float | None:
        """Resolve the portfolio mark price used for tracked unrealized PnL."""
        if data.book_bid_price > 0.0 and data.book_ask_price > 0.0:
            return (data.book_bid_price + data.book_ask_price) / 2.0
        if data.trades:
            return float(data.trades[-1].price)
        return None

    def _build_activation_runtime_context(
        self,
        data: MarketDataInput,
        state_snap: StateSnapshot,
        regime_snap: RegimeSnapshot | None,
    ) -> _ActivationRuntimeContext:
        key = (data.symbol, data.exchange)
        trade_list = list(data.trades)

        volatility_condition, _ = volatility_condition_from_trades(trade_list)
        regime_state, _ = regime_state_from_trades(
            trade_list,
            str(state_snap.state),
            volatility_condition,
            regime_snap.regime_transition_active if regime_snap is not None else None,
        )
        liquidity_condition, _ = liquidity_condition_from_score(
            regime_snap.liquidity_score if regime_snap is not None else None
        )
        spread_condition, _ = spread_condition_from_book(
            data.book_has_snapshot,
            data.book_bid_price,
            data.book_ask_price,
        )

        prior_execution = self._execution_runtime.get(key)
        execution_condition, _ = execution_condition_from_runtime(
            data.feed_connection_state,
            data.feed_recovery_state,
            data.book_has_snapshot,
            data.book_bid_price,
            data.book_ask_price,
            spread_condition,
            prior_latency_ms=prior_execution.latency_ms if prior_execution is not None else None,
            prior_fill_rate_pct=prior_execution.fill_rate_pct if prior_execution is not None else None,
        )

        current_price = self._resolve_activation_price(data)
        if current_price is not None:
            self._append_price_observation(key, data.timestamp_ns, current_price)
        self._append_regime_observation(key, data.timestamp_ns, regime_state)

        funding_safety_context = FundingSafetyContext(
            regime_state=regime_state,
            regime_trending_recently=self._recently_trending(key, data.timestamp_ns),
            recent_return_4h=self._compute_recent_return(key, data.timestamp_ns, 4 * _NS_PER_HOUR),
            trend_strength=self._compute_trend_strength(key, data.timestamp_ns),
        )

        return _ActivationRuntimeContext(
            regime_state=regime_state,
            liquidity_condition=liquidity_condition,
            execution_condition=execution_condition,
            spread_condition=spread_condition,
            volatility_condition=volatility_condition,
            funding_safety_context=funding_safety_context,
        )

    def _append_price_observation(self, key: tuple[str, str], timestamp_ns: int, price: float) -> None:
        history = self._price_history[key]
        history.append((timestamp_ns, price))
        cutoff = timestamp_ns - 72 * _NS_PER_HOUR
        while history and history[0][0] < cutoff:
            history.popleft()

    def _append_regime_observation(self, key: tuple[str, str], timestamp_ns: int, regime_state: str) -> None:
        history = self._regime_history[key]
        history.append((timestamp_ns, regime_state))
        cutoff = timestamp_ns - 8 * _NS_PER_HOUR
        while history and history[0][0] < cutoff:
            history.popleft()

    def _compute_recent_return(self, key: tuple[str, str], current_ns: int, lookback_ns: int) -> float | None:
        history = self._price_history.get(key)
        if not history:
            return None
        current_price = history[-1][1]
        target_ns = current_ns - lookback_ns
        candidates = [price for (ts, price) in history if ts <= target_ns and price > 0.0]
        if not candidates or current_price <= 0.0:
            return None
        base_price = candidates[-1]
        return current_price / base_price - 1.0

    def _compute_trend_strength(self, key: tuple[str, str], current_ns: int) -> float | None:
        history = self._price_history.get(key)
        if not history:
            return None
        cutoff_48h = current_ns - 48 * _NS_PER_HOUR
        cutoff_24h = current_ns - 24 * _NS_PER_HOUR
        cutoff_12h = current_ns - 12 * _NS_PER_HOUR
        prices_48h = [price for (ts, price) in history if ts >= cutoff_48h and price > 0.0]
        prices_24h = [price for (ts, price) in history if ts >= cutoff_24h and price > 0.0]
        prices_12h = [price for (ts, price) in history if ts >= cutoff_12h and price > 0.0]
        if len(prices_48h) < 8 or len(prices_24h) < 4 or len(prices_12h) < 3:
            return None
        if history[0][0] > cutoff_48h:
            return None

        ema12 = self._ema(prices_12h)
        ema48 = self._ema(prices_48h)
        returns_24h = [
            abs(prices_24h[idx] / prices_24h[idx - 1] - 1.0)
            for idx in range(1, len(prices_24h))
            if prices_24h[idx - 1] > 0.0
        ]
        if len(returns_24h) < 2:
            return None
        atr24 = sum(returns_24h) / len(returns_24h)
        if atr24 <= 0.0 or ema48 <= 0.0:
            return None
        return ((ema12 - ema48) / ema48) / atr24

    def _recently_trending(self, key: tuple[str, str], current_ns: int) -> bool | None:
        history = self._regime_history.get(key)
        if not history:
            return None
        cutoff = current_ns - 4 * _NS_PER_HOUR
        recent = [state for (ts, state) in history if ts >= cutoff]
        if not recent:
            return None
        return any(state == "TRENDING" for state in recent)

    def _update_execution_runtime_sample(
        self,
        symbol: str,
        exchange: str,
        latency_ms: float,
        execution_decisions: list[ExecutionDecision],
    ) -> None:
        if not execution_decisions:
            return
        allowed_count = sum(1 for decision in execution_decisions if decision.allowed)
        fill_rate_pct = allowed_count / len(execution_decisions) * 100.0
        self._execution_runtime[(symbol, exchange)] = _ExecutionRuntimeSample(
            latency_ms=latency_ms,
            fill_rate_pct=fill_rate_pct,
        )

    @staticmethod
    def _resolve_activation_price(data: MarketDataInput) -> float | None:
        if data.mark_price_event is not None and data.mark_price_event.mark_price > 0.0:
            return float(data.mark_price_event.mark_price)
        if data.book_bid_price > 0.0 and data.book_ask_price > data.book_bid_price:
            return (data.book_bid_price + data.book_ask_price) / 2.0
        if data.trades:
            return float(data.trades[-1].price)
        return None

    @staticmethod
    def _ema(values: list[float]) -> float:
        if not values:
            return 0.0
        alpha = 2.0 / (len(values) + 1.0)
        ema = values[0]
        for value in values[1:]:
            ema = alpha * value + (1.0 - alpha) * ema
        return ema

    def _emit_telemetry_safe(self, stage: str, latency_ms: float, extra: dict) -> None:
        """Emit telemetry — never raises."""
        if self._telemetry is None:
            return
        import time as _time

        ts_ms = int(_time.time() * 1000)
        metrics: dict[str, object] = {"stage_latency_ms": latency_ms, **extra}

        # Build stage-specific envelope
        try:
            from crypto_core.telemetry.models import TelemetryEnvelope

            # Map "guard" to "data" stage for telemetry (guard is part of data stage)
            tele_stage = stage if stage in ("data", "edge", "risk", "execution") else "data"
            if tele_stage == "edge":
                # Ensure required edge fields
                if "active_edges" not in metrics:
                    metrics["active_edges"] = 0
            if tele_stage == "risk":
                if "shs_value" not in metrics:
                    metrics["shs_value"] = 0.0
                if "kill_switch_level" not in metrics:
                    metrics["kill_switch_level"] = 0

            env = TelemetryEnvelope(timestamp_ms=ts_ms, stage=tele_stage, metrics=metrics)
            errors = env.validate()
            if not errors:
                self._telemetry.emit_safe(env)
        except Exception:
            logger.exception("Telemetry emission failed in orchestrator")

    def _emit_recovery_telemetry(self, evidence: RecoveryEvidence) -> None:
        """Emit recovery bootstrap telemetry at initialization."""
        self._emit_telemetry_safe(
            "data",
            0.0,
            {
                "recovery_restore_success": evidence.restore_success,
                "recovery_restored_order_count": evidence.restored_order_count,
                "recovery_orphan_count": len(evidence.orphan_order_ids),
                "recovery_reconciled_count": evidence.reconciled_count,
                "recovery_stale_count": evidence.stale_count,
                "recovery_unresolved_count": evidence.unresolved_count,
                "recovery_restored_position_count": evidence.restored_position_count,
            },
        )

    def _emit_recovery_telemetry(self, evidence: RecoveryEvidence) -> None:
        """Emit recovery bootstrap telemetry at initialization."""
        self._emit_telemetry_safe(
            "data",
            0.0,
            {
                "recovery_restore_success": evidence.restore_success,
                "recovery_restored_order_count": evidence.restored_order_count,
                "recovery_orphan_count": len(evidence.orphan_order_ids),
                "recovery_reconciled_count": evidence.reconciled_count,
                "recovery_stale_count": evidence.stale_count,
                "recovery_unresolved_count": evidence.unresolved_count,
                "recovery_restored_position_count": evidence.restored_position_count,
            },
        )

    @property
    def recovery_evidence(self) -> RecoveryEvidence | None:
        """Recovery evidence from the last bootstrap (None if no recovery)."""
        return self._recovery_evidence

    @property
    def has_unresolved_orders(self) -> bool:
        """True if recovery found unresolved orders (execution risk)."""
        if self._recovery_evidence is None:
            return False
        return self._recovery_evidence.unresolved_count > 0

    # ------------------------------------------------------------------
    # Phase 9D: execution intelligence integration
    # ------------------------------------------------------------------

    @property
    def tca_loop(self) -> ExecutionTCALoop | None:
        """Injected TCA loop (None if not configured)."""
        return self._tca_loop

    @property
    def metadata_gated_router(self) -> MetadataGatedRouter | None:
        """Injected metadata-gated router (None if not configured)."""
        return self._metadata_gated_router

    @property
    def route_block_count(self) -> int:
        """Cumulative count of route-blocked execution candidates."""
        return self._route_block_count

    @property
    def route_abstain_count(self) -> int:
        """Cumulative count of route-abstained execution candidates."""
        return self._route_abstain_count

    def update_venue_metadata(self, venue: str, snapshot: VenueMetadataSnapshot) -> None:
        """Set or update venue metadata for routing decisions."""
        self._venue_metadata[venue] = snapshot

    def update_venue_components(self, venue: str, components: VenueScoreComponents) -> None:
        """Set or update venue score components for routing decisions."""
        self._venue_components[venue] = components

    def _evaluate_route(
        self,
        data: MarketDataInput,
        risk_eval: RiskEvaluation,
    ) -> RouteDecision:
        """Evaluate routing via metadata-gated router. Fail-closed on missing metadata."""
        venue = data.exchange
        venue_meta = self._venue_metadata.get(venue)
        venue_comps = self._venue_components.get(venue)

        # Fail-closed: no metadata snapshot → BLOCK
        if venue_meta is None:
            return RouteDecision(
                symbol=data.symbol,
                outcome=RouteDecisionOutcome.BLOCK,
                reason="venue_metadata_unavailable",
                decided_at_ns=data.timestamp_ns,
                evidence={"venue": venue, "cause": "no_metadata_snapshot"},
            )

        # Fail-closed: no score components → BLOCK
        if venue_comps is None:
            return RouteDecision(
                symbol=data.symbol,
                outcome=RouteDecisionOutcome.BLOCK,
                reason="venue_components_unavailable",
                decided_at_ns=data.timestamp_ns,
                evidence={"venue": venue, "cause": "no_score_components"},
            )

        # Compute half-spread from book data
        half_spread_bps = 0.0
        if data.book_bid_price > 0 and data.book_ask_price > data.book_bid_price:
            mid = (data.book_bid_price + data.book_ask_price) / 2.0
            half_spread_bps = (data.book_ask_price - data.book_bid_price) / mid * 5_000.0

        return self._metadata_gated_router.decide(
            symbol=data.symbol,
            venue_metadata={venue: venue_meta},
            venue_components={venue: venue_comps},
            half_spread_by_venue={venue: half_spread_bps},
            expected_impact_bps=1.0,
            is_maker=False,
        )

    def _register_fill_in_tca_loop(
        self,
        *,
        fill_event: object,
        request: ExecutionRequest,
        route_decision: RouteDecision | None,
        ref_mid: float | None,
        regime_state: str | None,
    ) -> None:
        """Register a fill in the TCA loop with available context."""
        if self._tca_loop is None:
            return

        # Extract fee cost from venue metadata if available
        fee_bps: float | None = None
        venue_meta = self._venue_metadata.get(getattr(fill_event, "exchange", ""))
        if venue_meta is not None and venue_meta.fees is not None:
            fee_bps = venue_meta.fees.taker_fee_bps

        # Extract funding cost from venue metadata if available
        funding_bps: float | None = None
        if venue_meta is not None and venue_meta.funding is not None:
            funding_bps = venue_meta.funding.funding_rate_bps

        self._tca_loop.on_fill(
            order_id=getattr(fill_event, "order_id", ""),
            fill_price=getattr(fill_event, "fill_price", 0.0),
            fill_timestamp_ns=getattr(fill_event, "timestamp_ns", 0),
            is_buy=(getattr(fill_event, "intent", None) == OrderIntent.BUY),
            symbol=getattr(fill_event, "symbol", ""),
            exchange=getattr(fill_event, "exchange", ""),
            size=getattr(fill_event, "filled_quantity", 0.0),
            requested_size=request.size,
            decision_price=ref_mid,
            arrival_price=ref_mid,
            expected_slippage_bps=getattr(fill_event, "slippage_bps", None),
            spread_cost_bps=getattr(fill_event, "spread_bps", None),
            fee_cost_bps=fee_bps,
            funding_cost_bps=funding_bps,
            fill_role="taker",
            regime_tag=regime_state or "unknown",
            route_venue=(
                route_decision.selected_venue
                if route_decision is not None and route_decision.selected_venue
                else getattr(fill_event, "exchange", "")
            ),
            route_cost_bps=(route_decision.selected_cost_bps if route_decision is not None else None),
        )
