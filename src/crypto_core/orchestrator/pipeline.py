"""Pipeline Orchestrator v1 — deterministic data → state → guard → edge → risk.

All stages fail-closed: any broken stage blocks all downstream stages.
Same input stream → same outputs (deterministic replay equivalence).
Telemetry is emitted at each stage boundary.

PRD reference: §2 System Orchestration.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from crypto_core.edge.engine import EdgeEngine, EdgeEngineConfig
from crypto_core.guard.models import NoTradeContext, NoTradeDecision, NoTradeReason
from crypto_core.guard.no_trade_guard import NoTradeConfig, NoTradeGuard
from crypto_core.orchestrator.models import MarketDataInput, PipelineResult
from crypto_core.risk.engine import RiskEngine
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.engine import SystemStateEngine
from crypto_core.state.models import SignalInputs, StateSnapshot, SystemState, is_at_least
from crypto_core.telemetry.emitter import TelemetryEmitter

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration bundle for the pipeline orchestrator."""

    guard: NoTradeConfig = None  # type: ignore[assignment]
    edge: EdgeEngineConfig = None  # type: ignore[assignment]
    telemetry_log_dir: str = "logs/telemetry"
    emit_telemetry: bool = True

    def __post_init__(self) -> None:
        if self.guard is None:
            self.guard = NoTradeConfig()
        if self.edge is None:
            self.edge = EdgeEngineConfig()


class PipelineOrchestrator:
    """Deterministic single-process pipeline orchestrator.

    Stages (in order, fail-closed):
      1. State evaluation    — SignalInputs → StateSnapshot
      2. Guard evaluation    — NoTradeContext → NoTradeDecision
      3. Edge evaluation     — trades + state + guard → EdgeSignals
      4. Risk evaluation     — EdgeSignal + state + guard → RiskEvaluation
      5. Telemetry emission  — per-stage metrics → JSONL

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
        telemetry_emitter: TelemetryEmitter | None = None,
    ) -> None:
        self._cfg = config or PipelineConfig()
        self._state_engine = state_engine or SystemStateEngine()
        self._guard = NoTradeGuard(self._cfg.guard)
        self._edge_engine = EdgeEngine(self._cfg.edge)
        self._risk_engine = RiskEngine()
        from pathlib import Path

        self._telemetry = telemetry_emitter or (
            TelemetryEmitter(log_dir=Path(self._cfg.telemetry_log_dir)) if self._cfg.emit_telemetry else None
        )

    def process(
        self,
        data: MarketDataInput,
        signal_inputs: SignalInputs | None = None,
    ) -> PipelineResult:
        """Execute the full pipeline for one market data input.

        Args:
            data: validated market data snapshot.
            signal_inputs: 10-signal SHS inputs. If None, uses zero signals
                           (system stays in or near NORMAL — safe for testing).

        Returns:
            PipelineResult with full audit trail.
        """
        t_start = time.time_ns()

        try:
            return self._do_process(data, signal_inputs or SignalInputs(), t_start)
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
        )
        no_trade = self._guard.evaluate(guard_ctx)
        guard_latency_ms = (time.time_ns() - stage_t0) / 1e6

        self._emit_telemetry_safe(
            "guard",
            guard_latency_ms,
            {"allowed": no_trade.allowed, "reason": str(no_trade.reason)},
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
        )
        edge_latency_ms = (time.time_ns() - stage_t0) / 1e6

        valid_count = sum(1 for s in edge_signals if s.is_valid)
        self._emit_telemetry_safe(
            "edge",
            edge_latency_ms,
            {"active_edges": valid_count, "total_edges": len(edge_signals)},
        )

        # ── Stage 4: Risk ───────────────────────────────────────────────
        stage_t0 = time.time_ns()
        risk_evals: list[RiskEvaluation] = []
        for sig in edge_signals:
            risk_eval = self._risk_engine.evaluate(
                edge_signal=sig,
                system_state=state_snap.state,
                no_trade=no_trade,
                timestamp_ns=ts,
                shs_snapshot=state_snap.shs,
            )
            risk_evals.append(risk_eval)
        risk_latency_ms = (time.time_ns() - stage_t0) / 1e6

        approved_count = sum(1 for r in risk_evals if r.approved)
        self._emit_telemetry_safe(
            "risk",
            risk_latency_ms,
            {
                "shs_value": state_snap.shs,
                "kill_switch_level": 0,  # placeholder until KS engine
                "approved_count": approved_count,
            },
        )

        # ── Determine overall result ────────────────────────────────────
        is_approved = any(r.approved for r in risk_evals)
        block_stage, block_reason = self._find_block(state_snap, no_trade, edge_signals, risk_evals)

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
        )

    @staticmethod
    def _find_block(
        state_snap: StateSnapshot,
        no_trade: NoTradeDecision,
        edge_signals: list,
        risk_evals: list[RiskEvaluation],
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
        return None, None

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
