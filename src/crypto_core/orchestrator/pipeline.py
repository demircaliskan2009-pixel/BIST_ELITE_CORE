"""Pipeline Orchestrator v1 — deterministic data → state → guard → edge → risk.

All stages fail-closed: any broken stage blocks all downstream stages.
Same input stream → same outputs (deterministic replay equivalence).
Telemetry is emitted at each stage boundary.

PRD reference: §2 System Orchestration.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace

from crypto_core.edge.engine import EdgeEngine, EdgeEngineConfig
from crypto_core.edge.models import SignalDirection
from crypto_core.edge_health.models import EdgeHealthSnapshot
from crypto_core.edge_health.tracker import EdgeHealthTracker
from crypto_core.execution.engine import ExecutionConfig, ExecutionEngine
from crypto_core.execution.models import BookContext, ExecutionDecision, ExecutionRequest, OrderIntent
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
from crypto_core.regime.models import LiquiditySignal, RegimeSignalInput
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


@dataclass
class PipelineConfig:
    """Configuration bundle for the pipeline orchestrator."""

    guard: NoTradeConfig = None  # type: ignore[assignment]
    edge: EdgeEngineConfig = None  # type: ignore[assignment]
    execution: ExecutionConfig = None  # type: ignore[assignment]
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
    ) -> None:
        self._cfg = config or PipelineConfig()
        self._state_engine = state_engine or SystemStateEngine()
        self._guard = NoTradeGuard(self._cfg.guard)
        self._edge_engine = EdgeEngine(self._cfg.edge)
        self._risk_engine = RiskEngine()
        self._execution_engine = execution_engine or ExecutionEngine(self._cfg.execution)
        self._ks_engine = KillSwitchEngine()
        # PositionTracker is optional — None = portfolio gates skip (Phase 5D+ wired)
        self._position_tracker: PositionTracker | None = position_tracker
        # MarketRegimeTracker is optional — None = market family disabled (NT-M skipped)
        self._regime_tracker: MarketRegimeTracker | None = regime_tracker
        # EdgeHealthTracker is optional — None = edge family disabled (NT-E skipped)
        self._edge_health_tracker: EdgeHealthTracker | None = edge_health_tracker
        # TemporalScheduler is optional — None = temporal family disabled (NT-T skipped)
        self._temporal_scheduler: TemporalScheduler | None = temporal_scheduler
        from pathlib import Path

        self._telemetry = telemetry_emitter or (
            TelemetryEmitter(log_dir=Path(self._cfg.telemetry_log_dir)) if self._cfg.emit_telemetry else None
        )

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
            liq_signal = LiquiditySignal(
                bid_level_count=data.book_bid_count,
                ask_level_count=data.book_ask_count,
                recent_trade_count=len(data.trades),
                timestamp_ns=ts,
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
            feed_connection_state=data.feed_connection_state,
            feed_recovery_state=data.feed_recovery_state,
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
        }
        if ehs_snap is not None:
            _tele_edge["valid_edge_count"] = ehs_snap.valid_edge_count if ehs_snap.valid_edge_count is not None else 0
            _tele_edge["disabled_edge_count"] = ehs_snap.disabled_edge_count
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

        # ── Stage 5: Execution ─────────────────────────────────────────
        stage_t0 = time.time_ns()
        executable_risk_evals = [
            risk_eval
            for risk_eval in risk_evals
            if risk_eval.approved and risk_eval.edge_signal.direction in (SignalDirection.BUY, SignalDirection.SELL)
        ]
        execution_decisions: list[ExecutionDecision] = []

        for risk_eval in executable_risk_evals:
            request = self._build_execution_request(data, risk_eval)
            decision = self._execution_engine.execute(request)
            if decision.allowed:
                fill = SyntheticFillFactory.from_decision(
                    decision,
                    request,
                    leverage=self._cfg.execution_leverage,
                )
                if self._position_tracker is not None:
                    self._position_tracker.apply_fill(fill)
                decision = replace(decision, fill_generated=True)
            execution_decisions.append(decision)

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
            if primary_decision.ref_mid_price is not None:
                execution_metrics["execution_reference_mid"] = round(primary_decision.ref_mid_price, 8)
            if primary_decision.fill_price is not None:
                execution_metrics["execution_fill_price"] = round(primary_decision.fill_price, 8)
            if primary_decision.spread_bps is not None:
                execution_metrics["execution_spread_bps"] = round(primary_decision.spread_bps, 4)
            if primary_decision.slippage_bps is not None:
                execution_metrics["execution_slippage_bps"] = round(primary_decision.slippage_bps, 4)
            if primary_decision.participation_pct is not None:
                execution_metrics["execution_participation_pct"] = round(primary_decision.participation_pct, 4)
            if primary_decision.rejection_reason is not None:
                execution_metrics["execution_rejection_reason"] = str(primary_decision.rejection_reason)

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
        )

    @staticmethod
    def _find_block(
        state_snap: StateSnapshot,
        no_trade: NoTradeDecision,
        edge_signals: list,
        risk_evals: list[RiskEvaluation],
        execution_decisions: list[ExecutionDecision],
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
