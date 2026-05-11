"""Execution Engine — dry-run / paper mode (PRD §7).

Phase 6A upgrades:
  - PAPER mode now runs the fill pricing pipeline (spread, slippage, impact gate).
  - DRY_RUN mode retains abstract-approval behavior (price_hint only).
  - New rejection paths for book validity, spread, slippage, and liquidity.
  - ExecutionDecision carries full paper fill pricing evidence.
  - SyntheticFillFactory (in portfolio.fills) bridges decision → portfolio tracker.

Hard constraints:
  - LIVE mode is NOT implemented.
  - Accepts ONLY risk-approved inputs.
  - Fails closed on invalid symbol, incomplete payload, or unsafe state.
  - Emits telemetry for the execution stage.

PRD reference: §7.1–§7.8 Execution Engine.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass

from crypto_core.execution.fill_pricer import FillPricer, FillPricerConfig
from crypto_core.execution.models import (
    ExecutionDecision,
    ExecutionMode,
    ExecutionRequest,
    RejectionReason,
    SlippageResult,
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
    fill_pricer: FillPricerConfig | None = None  # None = use FillPricerConfig() defaults

    def __post_init__(self) -> None:
        if self.mode is None:
            self.mode = ExecutionMode.DRY_RUN
        if self.supported_symbols is None:
            self.supported_symbols = _SUPPORTED_SYMBOLS


class ExecutionEngine:
    """Execution engine operating in DRY_RUN or PAPER mode.

    DRY_RUN: abstract approval only — no fill pricing.  Uses price_hint.
    PAPER:   full fill pricing pipeline for realistic simulation.
             If book context provided: spread + slippage + impact gates run.
             If book context absent:   falls back to price_hint (degraded mode).

    Validation gates (fail-closed, in order):
      1. mode != LIVE (not implemented)
      2. symbol is in supported set
      3. size > 0
      4. risk_evaluation.approved == True
      5. system_state < DEFENSIVE
      6. [PAPER only] book validity gates (spread, slippage, impact)

    On pass: generates a UUID order_id and returns allowed=True.
    On any exception: returns rejected with EXCEPTION_FAIL_CLOSED.

    Usage::

        engine = ExecutionEngine(ExecutionConfig(mode=ExecutionMode.PAPER))
        decision = engine.execute(request)
        if decision.allowed:
            fill = SyntheticFillFactory.from_decision(decision, request)
            tracker.apply_fill(fill)
    """

    def __init__(self, config: ExecutionConfig | None = None) -> None:
        self._cfg = config or ExecutionConfig()
        pricer_cfg = self._cfg.fill_pricer if self._cfg.fill_pricer is not None else FillPricerConfig()
        self._fill_pricer = FillPricer(pricer_cfg)

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

        # ── Approved — generate order_id ────────────────────────────────
        order_id = str(uuid.uuid4())

        # ── Gate 5 (PAPER only): fill pricing pipeline ──────────────────
        if cfg.mode == ExecutionMode.PAPER:
            return self._paper_fill(req, order_id, evidence, ts)

        # DRY_RUN: abstract approval, no fill pricing
        logger.info(
            "[DRY_RUN] order accepted: %s %s %s @ ~%.2f  id=%s",
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

    def _paper_fill(
        self,
        req: ExecutionRequest,
        order_id: str,
        base_evidence: dict[str, object],
        ts: int,
    ) -> ExecutionDecision:
        """PAPER mode: run fill pricing pipeline; fall back to price_hint if no book."""
        cfg = self._cfg

        # No book context → check config
        if req.book is None:
            if cfg.fill_pricer is not None and cfg.fill_pricer.require_book_for_paper:
                return self._reject(
                    RejectionReason.BOOK_UNAVAILABLE,
                    {**base_evidence, "book": "none"},
                    cfg.mode,
                    ts,
                )
            # Degraded: use price_hint as fill_price (no slippage applied)
            logger.info(
                "[PAPER] order accepted (degraded — no book): %s %s %s @ ~%.2f  id=%s",
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
                evidence={
                    **base_evidence,
                    "order_id": order_id,
                    "fill_mode": "degraded_price_hint",
                },
                timestamp_ns=ts,
                fill_price=req.price_hint,
            )

        # Full fill pricing pipeline
        pricing = self._fill_pricer.price_fill(
            intent=req.intent,
            size=req.size,
            book=req.book,
        )

        if isinstance(pricing, RejectionReason):
            return self._reject(
                pricing,
                {**base_evidence, "fill_pricing_rejection": str(pricing)},
                cfg.mode,
                ts,
            )

        assert isinstance(pricing, SlippageResult)
        logger.info(
            "[PAPER] order accepted: %s %s %s fill=%.8f spread=%.2fbps slip=%.2fbps  id=%s",
            req.symbol,
            str(req.intent).upper(),
            req.size,
            pricing.fill_price,
            pricing.spread_bps,
            pricing.slippage_bps,
            order_id,
        )
        return ExecutionDecision(
            allowed=True,
            rejection_reason=None,
            mode=cfg.mode,
            order_id=order_id,
            evidence={
                **base_evidence,
                "order_id": order_id,
                "fill_mode": "paper_realistic",
                **pricing.evidence,
            },
            timestamp_ns=ts,
            ref_mid_price=pricing.base_price,
            ref_bid_price=req.book.bid_price,
            ref_ask_price=req.book.ask_price,
            fill_price=pricing.fill_price,
            spread_bps=pricing.spread_bps,
            slippage_bps=pricing.slippage_bps,
            participation_pct=pricing.participation_pct,
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
