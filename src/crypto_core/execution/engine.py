"""Execution Engine skeleton — dry-run / paper mode (PRD §7).

Hard constraints:
  - LIVE mode is NOT implemented.
  - Accepts ONLY risk-approved inputs.
  - Fails closed on invalid symbol, incomplete payload, or unsafe state.
  - Emits telemetry for the execution stage.

Extension points (inject later):
  - ExchangeAdapter: real broker calls
  - PositionTracker: live position state
  - SlippageModel: dynamic slippage estimation

PRD reference: §7.1–§7.8 Execution Engine.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass

from crypto_core.execution.models import (
    ExecutionDecision,
    ExecutionMode,
    ExecutionRequest,
    RejectionReason,
)
from crypto_core.state.models import SystemState, is_at_least

logger = logging.getLogger(__name__)

#: Supported symbols (v1 — must be in this set for execution to proceed)
_SUPPORTED_SYMBOLS: frozenset[str] = frozenset({"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"})


@dataclass
class ExecutionConfig:
    """Execution engine configuration."""

    mode: ExecutionMode = None  # type: ignore[assignment]
    supported_symbols: frozenset[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.mode is None:
            self.mode = ExecutionMode.DRY_RUN
        if self.supported_symbols is None:
            self.supported_symbols = _SUPPORTED_SYMBOLS


class ExecutionEngine:
    """Skeleton execution engine operating in DRY_RUN or PAPER mode.

    Validation gates (fail-closed, in order):
      1. mode != LIVE (not implemented)
      2. symbol is in supported set
      3. size > 0
      4. risk_evaluation.approved == True
      5. system_state < DEFENSIVE

    On pass: generates a UUID order_id and returns allowed=True.
    On any exception: returns rejected with EXCEPTION_FAIL_CLOSED.

    Usage::

        engine = ExecutionEngine(ExecutionConfig(mode=ExecutionMode.PAPER))
        decision = engine.execute(request)
        if decision.allowed:
            # log paper fill
    """

    def __init__(self, config: ExecutionConfig | None = None) -> None:
        self._cfg = config or ExecutionConfig()

    def execute(self, request: ExecutionRequest) -> ExecutionDecision:
        """Validate and (dry-)execute an order request.

        Returns ExecutionDecision.  Never raises.
        """
        try:
            return self._do_execute(request)
        except Exception:
            logger.exception("ExecutionEngine.execute raised — fail-closed")
            return ExecutionDecision(
                allowed=False,
                rejection_reason=RejectionReason.EXCEPTION_FAIL_CLOSED,
                mode=self._cfg.mode,
                order_id=None,
                evidence={"error": "exception_fail_closed"},
                timestamp_ns=time.time_ns(),
            )

    # -----------------------------------------------------------------------
    # Internal validation chain
    # -----------------------------------------------------------------------

    def _do_execute(self, req: ExecutionRequest) -> ExecutionDecision:
        cfg = self._cfg
        ts = req.timestamp_ns
        evidence: dict[str, object] = {
            "symbol": req.symbol,
            "exchange": req.exchange,
            "intent": str(req.intent),
            "size": req.size,
            "price_hint": req.price_hint,
            "mode": str(cfg.mode),
        }

        # Gate 0: LIVE not implemented
        if cfg.mode not in (ExecutionMode.DRY_RUN, ExecutionMode.PAPER):
            return self._reject(
                RejectionReason.LIVE_NOT_ENABLED,
                {**evidence, "mode": str(cfg.mode)},
                cfg.mode,
                ts,
            )

        # Gate 1: symbol validation
        if req.symbol not in cfg.supported_symbols:
            return self._reject(
                RejectionReason.INVALID_SYMBOL,
                {**evidence, "supported": sorted(cfg.supported_symbols)},
                cfg.mode,
                ts,
            )

        # Gate 2: size must be positive
        if req.size <= 0.0:
            return self._reject(
                RejectionReason.ZERO_SIZE,
                {**evidence, "size": req.size},
                cfg.mode,
                ts,
            )

        # Gate 3: risk must be approved
        if not req.risk_evaluation.approved:
            return self._reject(
                RejectionReason.RISK_NOT_APPROVED,
                {**evidence, "risk_reason": str(req.risk_evaluation.block_reason)},
                cfg.mode,
                ts,
            )

        # Gate 4: system state
        sys_state = req.risk_evaluation.system_state
        if is_at_least(sys_state, SystemState.DEFENSIVE):
            return self._reject(
                RejectionReason.SYSTEM_STATE_DEFENSIVE,
                {**evidence, "system_state": str(sys_state)},
                cfg.mode,
                ts,
            )

        # All gates passed — generate paper/dry-run order ID
        order_id = str(uuid.uuid4())
        logger.info(
            "[%s] order accepted: %s %s %s @ ~%.2f  id=%s",
            str(cfg.mode).upper(),
            req.symbol,
            str(req.intent).upper(),
            req.size,
            req.price_hint,
            order_id,
        )
        return ExecutionDecision(
            allowed=True,
            rejection_reason=None,
            mode=cfg.mode,
            order_id=order_id,
            evidence={**evidence, "order_id": order_id},
            timestamp_ns=ts,
        )

    @staticmethod
    def _reject(
        reason: RejectionReason,
        evidence: dict[str, object],
        mode: ExecutionMode,
        ts: int,
    ) -> ExecutionDecision:
        return ExecutionDecision(
            allowed=False,
            rejection_reason=reason,
            mode=mode,
            order_id=None,
            evidence=evidence,
            timestamp_ns=ts,
        )
