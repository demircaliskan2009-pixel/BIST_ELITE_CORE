"""No-Trade Guard — fail-closed trade blocking layer (PRD §1.21).

Evaluates NT-D (data-feed tier) and NT-X (system tier) conditions in strict
priority order. First blocking condition wins — no partial pass.

No signal may proceed to the edge engine without passing this guard.

PRD reference: §1.21 — No-Trade Conditions v1 subset.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from crypto_core.guard.models import (
    NoTradeContext,
    NoTradeDecision,
    NoTradeReason,
)
from crypto_core.state.models import SystemState, is_at_least, state_severity

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_NS_PER_MS = 1_000_000
_NS_PER_S = 1_000_000_000

#: Default stale-data threshold: data older than this is considered stale.
DEFAULT_STALE_DATA_THRESHOLD_MS: float = 5_000.0   # 5 seconds

#: Default max latency budget.
DEFAULT_LATENCY_BUDGET_MS: float = 500.0            # 500 ms

#: Default telemetry freshness window.
DEFAULT_TELEMETRY_WINDOW_MS: float = 60_000.0       # 60 seconds

#: Connection states that indicate recovery is active.
_RECOVERY_STATES: frozenset[str] = frozenset(
    {"snapshotting", "replaying", "validating"}
)

#: Feed connection states that indicate the feed is not ready.
_UNHEALTHY_FEED_STATES: frozenset[str] = frozenset(
    {"reconnecting", "failed", "disconnected", "connecting"}
)


@dataclass
class NoTradeConfig:
    """Tunable thresholds for the No-Trade Guard.

    All thresholds have safe defaults.  Override per deployment.
    """

    stale_data_threshold_ms: float = DEFAULT_STALE_DATA_THRESHOLD_MS
    latency_budget_ms: float = DEFAULT_LATENCY_BUDGET_MS
    telemetry_window_ms: float = DEFAULT_TELEMETRY_WINDOW_MS
    min_book_bid_levels: int = 1
    min_book_ask_levels: int = 1
    #: If non-empty, only symbols in this set are tradeable.
    supported_symbols: frozenset[str] = field(default_factory=frozenset)
    #: States at which or above trading is blocked.
    block_at_state: str = SystemState.DEFENSIVE  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------


class NoTradeGuard:
    """Fail-closed trade blocking layer.

    Rules are evaluated in priority order (NT-D before NT-X):
      1. STALE_DATA         — book data is older than threshold
      2. INVALID_BOOK       — book lacks minimum bid/ask levels
      3. MISSING_SNAPSHOT   — book has never received a snapshot
      4. UNSUPPORTED_SYMBOL — symbol not in allowed set
      5. RECOVERY_ACTIVE    — feed is replaying / snapshotting
      6. SYSTEM_STATE       — system state >= DEFENSIVE
      7. LATENCY_BUDGET     — observed latency exceeds budget
      8. TELEMETRY          — telemetry last-emit is stale

    First match blocks; remaining rules are not evaluated.
    On any exception: returns a CRITICAL block (fail-closed).

    Usage::

        guard = NoTradeGuard(config)
        decision = guard.evaluate(ctx)
        if not decision.allowed:
            # halt downstream
    """

    def __init__(self, config: NoTradeConfig | None = None) -> None:
        self._cfg = config or NoTradeConfig()

    def evaluate(self, ctx: NoTradeContext) -> NoTradeDecision:
        """Evaluate all no-trade conditions for the given context.

        Returns NoTradeDecision.  Fail-closed on exception.
        """
        try:
            return self._do_evaluate(ctx)
        except Exception:
            logger.exception("NoTradeGuard.evaluate raised — fail-closed block")
            return NoTradeDecision.block(
                NoTradeReason.SYSTEM_STATE_DEFENSIVE,
                {"error": "guard_evaluation_exception"},
            )

    # -----------------------------------------------------------------------
    # Internal rule chain
    # -----------------------------------------------------------------------

    def _do_evaluate(self, ctx: NoTradeContext) -> NoTradeDecision:
        cfg = self._cfg

        # ── NT-D01: Stale data ──────────────────────────────────────────
        if ctx.book_last_update_ns > 0:
            age_ms = (ctx.current_ns - ctx.book_last_update_ns) / _NS_PER_MS
            if age_ms > cfg.stale_data_threshold_ms:
                return NoTradeDecision.block(
                    NoTradeReason.STALE_DATA,
                    {"age_ms": age_ms, "threshold_ms": cfg.stale_data_threshold_ms},
                )
        elif ctx.book_last_update_ns == 0:
            # Never updated — treat as stale
            return NoTradeDecision.block(
                NoTradeReason.STALE_DATA,
                {"reason": "book_never_updated"},
            )

        # ── NT-D02: Invalid book ────────────────────────────────────────
        if (
            ctx.book_bid_count < cfg.min_book_bid_levels
            or ctx.book_ask_count < cfg.min_book_ask_levels
        ):
            return NoTradeDecision.block(
                NoTradeReason.INVALID_BOOK,
                {
                    "bid_levels": ctx.book_bid_count,
                    "ask_levels": ctx.book_ask_count,
                    "min_bid": cfg.min_book_bid_levels,
                    "min_ask": cfg.min_book_ask_levels,
                },
            )

        # ── NT-D03: Missing snapshot ────────────────────────────────────
        if not ctx.book_has_snapshot:
            return NoTradeDecision.block(
                NoTradeReason.MISSING_SNAPSHOT,
                {"symbol": ctx.symbol, "exchange": ctx.exchange},
            )

        # ── NT-D04: Unsupported symbol ──────────────────────────────────
        active_supported = cfg.supported_symbols or ctx.supported_symbols
        if active_supported and ctx.symbol not in active_supported:
            return NoTradeDecision.block(
                NoTradeReason.UNSUPPORTED_SYMBOL,
                {"symbol": ctx.symbol, "supported": sorted(active_supported)},
            )

        # ── NT-D05: Recovery active ─────────────────────────────────────
        if ctx.feed_recovery_state in _RECOVERY_STATES:
            return NoTradeDecision.block(
                NoTradeReason.RECOVERY_ACTIVE,
                {"recovery_state": ctx.feed_recovery_state},
            )
        if ctx.feed_connection_state in _UNHEALTHY_FEED_STATES:
            return NoTradeDecision.block(
                NoTradeReason.RECOVERY_ACTIVE,
                {"connection_state": ctx.feed_connection_state},
            )

        # ── NT-X01: System state too severe ─────────────────────────────
        block_state = SystemState(cfg.block_at_state)
        current_state = SystemState(ctx.system_state)
        if is_at_least(current_state, block_state):
            return NoTradeDecision.block(
                NoTradeReason.SYSTEM_STATE_DEFENSIVE,
                {
                    "system_state": ctx.system_state,
                    "block_at": str(cfg.block_at_state),
                    "severity": state_severity(current_state),
                },
            )

        # ── NT-X02: Latency budget breach ───────────────────────────────
        if ctx.latency_ms > cfg.latency_budget_ms:
            return NoTradeDecision.block(
                NoTradeReason.LATENCY_BUDGET_BREACH,
                {"latency_ms": ctx.latency_ms, "budget_ms": cfg.latency_budget_ms},
            )

        # ── NT-X03: Telemetry unavailable ───────────────────────────────
        if ctx.telemetry_last_emit_ns > 0:
            age_ms = (ctx.current_ns - ctx.telemetry_last_emit_ns) / _NS_PER_MS
            if age_ms > cfg.telemetry_window_ms:
                return NoTradeDecision.block(
                    NoTradeReason.TELEMETRY_UNAVAILABLE,
                    {"age_ms": age_ms, "window_ms": cfg.telemetry_window_ms},
                )
        # telemetry_last_emit_ns == 0 → never emitted.
        # We allow trading in this state (telemetry is observability, not safety gate)
        # unless explicitly required. Default: permissive on first-start.

        return NoTradeDecision.allow(
            {"symbol": ctx.symbol, "exchange": ctx.exchange}
        )
