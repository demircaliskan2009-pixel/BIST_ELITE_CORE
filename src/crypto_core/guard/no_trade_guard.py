"""No-Trade Guard — fail-closed trade blocking layer (PRD §1.21).

Evaluates 25 NT conditions across 6 families in strict priority order:
  1. Data      (NT-D01–NT-D05) — book/feed health
  2. Risk      (NT-R01–NT-R06) — portfolio risk limits
  3. Market    (NT-M01–NT-M04) — regime / liquidity / leverage / correlation
  4. Edge      (NT-E01–NT-E04) — edge health, FSM state, capacity
  5. Execution (NT-X01–NT-X03) — latency, system state, telemetry
  6. Temporal  (NT-T01–NT-T03) — startup warmup, KS cooldown, macro events

First blocking condition wins — no partial pass.
No signal may proceed to the edge engine without passing this guard.

Unavailable inputs:
  Optional family inputs (risk, market, edge, temporal) in NoTradeContext
  default to None.  None = family disabled.
  Optional sub-fields within each struct default to None.
  None sub-fields are explicitly skipped and documented in evidence.
  The guard NEVER silently treats None as "safe".

PRD reference: §1.21 — No-Trade Conditions v2 (25 rules).
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
DEFAULT_STALE_DATA_THRESHOLD_MS: float = 5_000.0  # 5 seconds

#: Default max latency budget.
DEFAULT_LATENCY_BUDGET_MS: float = 500.0  # 500 ms

#: Default telemetry freshness window.
DEFAULT_TELEMETRY_WINDOW_MS: float = 60_000.0  # 60 seconds

#: Connection states that indicate recovery is active.
_RECOVERY_STATES: frozenset[str] = frozenset({"snapshotting", "replaying", "validating"})

#: Feed connection states that indicate the feed is not ready.
_UNHEALTHY_FEED_STATES: frozenset[str] = frozenset({"reconnecting", "failed", "disconnected", "connecting"})


@dataclass
class NoTradeConfig:
    """Tunable thresholds for the No-Trade Guard.

    All thresholds have safe defaults matching PRD §1.21.
    Override per deployment.
    """

    # ── Data family thresholds ─────────────────────────────────────────
    stale_data_threshold_ms: float = DEFAULT_STALE_DATA_THRESHOLD_MS
    latency_budget_ms: float = DEFAULT_LATENCY_BUDGET_MS
    telemetry_window_ms: float = DEFAULT_TELEMETRY_WINDOW_MS
    min_book_bid_levels: int = 1
    min_book_ask_levels: int = 1
    #: If non-empty, only symbols in this set are tradeable.
    supported_symbols: frozenset[str] = field(default_factory=frozenset)
    #: States at which or above trading is blocked.
    block_at_state: str = SystemState.DEFENSIVE  # type: ignore[assignment]

    # ── Risk family thresholds (NT-R) ──────────────────────────────────
    #: NT-R01: KS level at or above this blocks new entries (PRD §1.19).
    ks_block_threshold: int = 2
    #: NT-R02: daily intraday loss as % of NAV — block if pnl_pct < −limit.
    daily_loss_limit_pct: float = 2.0
    #: NT-R03: max sum of position risks / equity before blocking.
    open_risk_cap_pct: float = 4.0
    #: NT-R04: max single position size as % of NAV before blocking.
    position_concentration_cap_pct: float = 25.0
    #: NT-R05: portfolio CVaR₉₉ limit as % of NAV.
    cvar_budget_pct: float = 5.0
    #: NT-R06: margin utilization cap as % of available margin.
    margin_utilization_cap_pct: float = 80.0

    # ── Market/regime family thresholds (NT-M) ─────────────────────────
    #: NT-M01: liquidity score below this threshold is a crisis.
    liquidity_crisis_threshold: float = 0.15
    #: NT-M01: minimum duration (ms) the score must be below threshold.
    liquidity_crisis_min_duration_ms: float = 1_800_000.0  # 30 minutes
    #: NT-M02: OI/MC ratio above this threshold is extreme leverage.
    oi_mc_extreme_threshold: float = 0.10
    #: NT-M04: mean pairwise correlation above this is a breakdown.
    correlation_crisis_threshold: float = 0.85

    # ── Edge health family thresholds (NT-E) ───────────────────────────
    #: NT-E01: minimum acceptable EHS — below this blocks new entries.
    ehs_min_threshold: float = 0.30
    #: NT-E04: minimum EHS for an edge to be counted as "valid".
    ehs_valid_threshold: float = 0.50
    #: NT-E03: utilization at or above this percentage is RED state.
    edge_utilization_red_threshold: float = 80.0

    # ── Temporal family thresholds (NT-T) ──────────────────────────────
    #: NT-T01: warmup period after engine start (ms).
    startup_warmup_ms: float = 300_000.0  # 5 minutes


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------


class NoTradeGuard:
    """Fail-closed trade blocking layer — PRD §1.21 (25 rules, 6 families).

    Evaluation order per PRD: Data → Risk → Market → Edge → Execution → Temporal.

    Rule mapping:
      NT-D01  stale data
      NT-D02  invalid book
      NT-D03  missing snapshot
      NT-D04  unsupported symbol
      NT-D05  recovery active

      NT-R01  kill-switch active
      NT-R02  daily loss limit
      NT-R03  open risk cap
      NT-R04  position concentration
      NT-R05  CVaR budget exhausted
      NT-R06  margin utilization

      NT-M01  liquidity regime CRISIS
      NT-M02  leverage regime EXTREME
      NT-M03  regime transition in progress
      NT-M04  correlation breakdown

      NT-E01  edge health score too low
      NT-E02  edge in DISABLED state
      NT-E03  edge capacity RED
      NT-E04  no valid edge for asset

      NT-X01  system state >= DEFENSIVE
      NT-X02  latency budget breach
      NT-X03  telemetry unavailable

      NT-T01  system startup warmup
      NT-T02  post-kill-switch cool-down
      NT-T03  high-impact event window

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

    def _do_evaluate(self, ctx: NoTradeContext) -> NoTradeDecision:  # noqa: C901
        cfg = self._cfg
        skipped: list[str] = []  # audit trail for skipped checks

        # ══════════════════════════════════════════════════════════════════
        # FAMILY 1: Data integrity (NT-D01–NT-D05)
        # ══════════════════════════════════════════════════════════════════

        # ── NT-D01: Stale data ──────────────────────────────────────────
        if ctx.book_last_update_ns > 0:
            age_ms = (ctx.current_ns - ctx.book_last_update_ns) / _NS_PER_MS
            if age_ms > cfg.stale_data_threshold_ms:
                return NoTradeDecision.block(
                    NoTradeReason.STALE_DATA,
                    {"rule": "NT-D01", "age_ms": age_ms, "threshold_ms": cfg.stale_data_threshold_ms},
                )
        elif ctx.book_last_update_ns == 0:
            # Never updated — treat as stale
            return NoTradeDecision.block(
                NoTradeReason.STALE_DATA,
                {"rule": "NT-D01", "reason": "book_never_updated"},
            )

        # ── NT-D02: Invalid book ────────────────────────────────────────
        if ctx.book_bid_count < cfg.min_book_bid_levels or ctx.book_ask_count < cfg.min_book_ask_levels:
            return NoTradeDecision.block(
                NoTradeReason.INVALID_BOOK,
                {
                    "rule": "NT-D02",
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
                {"rule": "NT-D03", "symbol": ctx.symbol, "exchange": ctx.exchange},
            )

        # ── NT-D04: Unsupported symbol ──────────────────────────────────
        active_supported = cfg.supported_symbols or ctx.supported_symbols
        if active_supported and ctx.symbol not in active_supported:
            return NoTradeDecision.block(
                NoTradeReason.UNSUPPORTED_SYMBOL,
                {"rule": "NT-D04", "symbol": ctx.symbol, "supported": sorted(active_supported)},
            )

        # ── NT-D05: Recovery active ─────────────────────────────────────
        if ctx.feed_recovery_state in _RECOVERY_STATES:
            return NoTradeDecision.block(
                NoTradeReason.RECOVERY_ACTIVE,
                {"rule": "NT-D05", "recovery_state": ctx.feed_recovery_state},
            )
        if ctx.feed_connection_state in _UNHEALTHY_FEED_STATES:
            return NoTradeDecision.block(
                NoTradeReason.RECOVERY_ACTIVE,
                {"rule": "NT-D05", "connection_state": ctx.feed_connection_state},
            )

        # ══════════════════════════════════════════════════════════════════
        # FAMILY 2: Risk limits (NT-R01–NT-R06)
        # ══════════════════════════════════════════════════════════════════

        if ctx.risk is not None:
            r = ctx.risk

            # ── NT-R01: Kill-switch active ──────────────────────────────
            if r.kill_switch_level >= cfg.ks_block_threshold:
                return NoTradeDecision.block(
                    NoTradeReason.KS_ACTIVE,
                    {
                        "rule": "NT-R01",
                        "ks_level": r.kill_switch_level,
                        "threshold": cfg.ks_block_threshold,
                    },
                )

            # ── NT-R02: Daily loss limit ────────────────────────────────
            if r.daily_pnl_pct is not None:
                if r.daily_pnl_pct < -cfg.daily_loss_limit_pct:
                    return NoTradeDecision.block(
                        NoTradeReason.DAILY_LOSS_LIMIT,
                        {
                            "rule": "NT-R02",
                            "daily_pnl_pct": r.daily_pnl_pct,
                            "limit_pct": cfg.daily_loss_limit_pct,
                        },
                    )
            else:
                skipped.append("NT-R02:daily_pnl_pct=unavailable")

            # ── NT-R03: Open risk cap ───────────────────────────────────
            if r.open_risk_pct is not None:
                if r.open_risk_pct > cfg.open_risk_cap_pct:
                    return NoTradeDecision.block(
                        NoTradeReason.OPEN_RISK_CAP,
                        {
                            "rule": "NT-R03",
                            "open_risk_pct": r.open_risk_pct,
                            "cap_pct": cfg.open_risk_cap_pct,
                        },
                    )
            else:
                skipped.append("NT-R03:open_risk_pct=unavailable")

            # ── NT-R04: Position concentration ─────────────────────────
            if r.max_single_position_pct is not None:
                if r.max_single_position_pct > cfg.position_concentration_cap_pct:
                    return NoTradeDecision.block(
                        NoTradeReason.POSITION_CONCENTRATION,
                        {
                            "rule": "NT-R04",
                            "max_single_pct": r.max_single_position_pct,
                            "cap_pct": cfg.position_concentration_cap_pct,
                        },
                    )
            else:
                skipped.append("NT-R04:max_single_position_pct=unavailable")

            # ── NT-R05: CVaR budget exhausted ───────────────────────────
            if r.portfolio_cvar99_pct is not None:
                if r.portfolio_cvar99_pct >= cfg.cvar_budget_pct:
                    return NoTradeDecision.block(
                        NoTradeReason.CVAR_BUDGET_EXHAUSTED,
                        {
                            "rule": "NT-R05",
                            "cvar99_pct": r.portfolio_cvar99_pct,
                            "budget_pct": cfg.cvar_budget_pct,
                        },
                    )
            else:
                skipped.append("NT-R05:portfolio_cvar99_pct=unavailable")

            # ── NT-R06: Margin utilization ──────────────────────────────
            if r.margin_used_pct is not None:
                if r.margin_used_pct > cfg.margin_utilization_cap_pct:
                    return NoTradeDecision.block(
                        NoTradeReason.MARGIN_UTILIZATION,
                        {
                            "rule": "NT-R06",
                            "margin_used_pct": r.margin_used_pct,
                            "cap_pct": cfg.margin_utilization_cap_pct,
                        },
                    )
            else:
                skipped.append("NT-R06:margin_used_pct=unavailable")

        else:
            skipped.append("NT-R:risk_input=None(family_disabled)")

        # ══════════════════════════════════════════════════════════════════
        # FAMILY 3: Market / regime (NT-M01–NT-M04)
        # ══════════════════════════════════════════════════════════════════

        if ctx.market is not None:
            m = ctx.market

            # ── NT-M01: Liquidity regime CRISIS ─────────────────────────
            if m.liquidity_score is not None:
                if m.liquidity_score < cfg.liquidity_crisis_threshold:
                    # Duration check: if sustained_ms is None → immediate block
                    # (cannot prove crisis NOT sustained → fail-closed)
                    sustained = m.liquidity_crisis_sustained_ms
                    if sustained is None or sustained >= cfg.liquidity_crisis_min_duration_ms:
                        return NoTradeDecision.block(
                            NoTradeReason.LIQUIDITY_CRISIS,
                            {
                                "rule": "NT-M01",
                                "liquidity_score": m.liquidity_score,
                                "threshold": cfg.liquidity_crisis_threshold,
                                "sustained_ms": sustained,
                            },
                        )
            else:
                skipped.append("NT-M01:liquidity_score=unavailable")

            # ── NT-M02: Leverage regime EXTREME ─────────────────────────
            if m.oi_mc_ratio is not None:
                if m.oi_mc_ratio > cfg.oi_mc_extreme_threshold:
                    return NoTradeDecision.block(
                        NoTradeReason.LEVERAGE_EXTREME,
                        {
                            "rule": "NT-M02",
                            "oi_mc_ratio": m.oi_mc_ratio,
                            "threshold": cfg.oi_mc_extreme_threshold,
                        },
                    )
            else:
                skipped.append("NT-M02:oi_mc_ratio=unavailable")

            # ── NT-M03: Regime transition in progress ────────────────────
            if m.regime_transition_active is not None:
                if m.regime_transition_active:
                    return NoTradeDecision.block(
                        NoTradeReason.REGIME_TRANSITION,
                        {"rule": "NT-M03", "regime_transition_active": True},
                    )
            else:
                skipped.append("NT-M03:regime_transition_active=unavailable")

            # ── NT-M04: Correlation breakdown ────────────────────────────
            if m.mean_pairwise_correlation is not None:
                if m.mean_pairwise_correlation > cfg.correlation_crisis_threshold:
                    return NoTradeDecision.block(
                        NoTradeReason.CORRELATION_BREAKDOWN,
                        {
                            "rule": "NT-M04",
                            "mean_correlation": m.mean_pairwise_correlation,
                            "threshold": cfg.correlation_crisis_threshold,
                        },
                    )
            else:
                skipped.append("NT-M04:mean_pairwise_correlation=unavailable")

        else:
            skipped.append("NT-M:market_input=None(family_disabled)")

        # ══════════════════════════════════════════════════════════════════
        # FAMILY 4: Edge health (NT-E01–NT-E04)
        # ══════════════════════════════════════════════════════════════════

        if ctx.edge is not None:
            e = ctx.edge

            # ── NT-E01: Edge health score too low ────────────────────────
            if e.edge_health_score is not None:
                if e.edge_health_score < cfg.ehs_min_threshold:
                    return NoTradeDecision.block(
                        NoTradeReason.EDGE_HEALTH_LOW,
                        {
                            "rule": "NT-E01",
                            "ehs": e.edge_health_score,
                            "min": cfg.ehs_min_threshold,
                        },
                    )
            else:
                skipped.append("NT-E01:edge_health_score=unavailable")

            # ── NT-E02: Edge in DISABLED state ───────────────────────────
            if e.edge_fsm_state is not None:
                if e.edge_fsm_state.upper() == "DISABLED":
                    return NoTradeDecision.block(
                        NoTradeReason.EDGE_DISABLED,
                        {"rule": "NT-E02", "fsm_state": e.edge_fsm_state},
                    )
            else:
                skipped.append("NT-E02:edge_fsm_state=unavailable")

            # ── NT-E03: Edge capacity RED ─────────────────────────────────
            if e.edge_utilization_pct is not None:
                if e.edge_utilization_pct >= cfg.edge_utilization_red_threshold:
                    return NoTradeDecision.block(
                        NoTradeReason.EDGE_CAPACITY_RED,
                        {
                            "rule": "NT-E03",
                            "utilization_pct": e.edge_utilization_pct,
                            "threshold": cfg.edge_utilization_red_threshold,
                        },
                    )
            else:
                skipped.append("NT-E03:edge_utilization_pct=unavailable")

            # ── NT-E04: No valid edge for asset ──────────────────────────
            if e.valid_edge_count is not None:
                if e.valid_edge_count == 0:
                    return NoTradeDecision.block(
                        NoTradeReason.NO_VALID_EDGE,
                        {
                            "rule": "NT-E04",
                            "valid_edge_count": 0,
                            "min_ehs": cfg.ehs_valid_threshold,
                        },
                    )
            else:
                skipped.append("NT-E04:valid_edge_count=unavailable")

        else:
            skipped.append("NT-E:edge_input=None(family_disabled)")

        # ══════════════════════════════════════════════════════════════════
        # FAMILY 5: Execution quality (NT-X01–NT-X03)
        # ══════════════════════════════════════════════════════════════════

        # ── NT-X01: System state too severe ─────────────────────────────
        block_state = SystemState(cfg.block_at_state)
        current_state = SystemState(ctx.system_state)
        if is_at_least(current_state, block_state):
            return NoTradeDecision.block(
                NoTradeReason.SYSTEM_STATE_DEFENSIVE,
                {
                    "rule": "NT-X01",
                    "system_state": ctx.system_state,
                    "block_at": str(cfg.block_at_state),
                    "severity": state_severity(current_state),
                },
            )

        # ── NT-X02: Latency budget breach ───────────────────────────────
        if ctx.latency_ms > cfg.latency_budget_ms:
            return NoTradeDecision.block(
                NoTradeReason.LATENCY_BUDGET_BREACH,
                {"rule": "NT-X02", "latency_ms": ctx.latency_ms, "budget_ms": cfg.latency_budget_ms},
            )

        # ── NT-X03: Telemetry unavailable ───────────────────────────────
        if ctx.telemetry_last_emit_ns > 0:
            age_ms = (ctx.current_ns - ctx.telemetry_last_emit_ns) / _NS_PER_MS
            if age_ms > cfg.telemetry_window_ms:
                return NoTradeDecision.block(
                    NoTradeReason.TELEMETRY_UNAVAILABLE,
                    {"rule": "NT-X03", "age_ms": age_ms, "window_ms": cfg.telemetry_window_ms},
                )
        # telemetry_last_emit_ns == 0 → never emitted.
        # Permissive on first-start — telemetry is observability, not a safety gate.

        # ══════════════════════════════════════════════════════════════════
        # FAMILY 6: Temporal restrictions (NT-T01–NT-T03)
        # ══════════════════════════════════════════════════════════════════

        if ctx.temporal is not None:
            t = ctx.temporal

            # ── NT-T01: System startup warmup ────────────────────────────
            if t.engine_start_ns > 0:
                age_ms = (ctx.current_ns - t.engine_start_ns) / _NS_PER_MS
                if age_ms < cfg.startup_warmup_ms:
                    return NoTradeDecision.block(
                        NoTradeReason.STARTUP_WARMUP,
                        {
                            "rule": "NT-T01",
                            "age_ms": age_ms,
                            "warmup_ms": cfg.startup_warmup_ms,
                        },
                    )
            else:
                skipped.append("NT-T01:engine_start_ns=0(disabled)")

            # ── NT-T02: Post-KS cool-down ─────────────────────────────────
            if t.ks_cooldown_active is not None:
                if t.ks_cooldown_active:
                    return NoTradeDecision.block(
                        NoTradeReason.KS_COOLDOWN,
                        {"rule": "NT-T02", "ks_cooldown_active": True},
                    )
            else:
                skipped.append("NT-T02:ks_cooldown_active=unavailable")

            # ── NT-T03: High-impact event window ─────────────────────────
            if t.high_impact_event_window_active is not None:
                if t.high_impact_event_window_active:
                    return NoTradeDecision.block(
                        NoTradeReason.HIGH_IMPACT_EVENT,
                        {"rule": "NT-T03", "high_impact_event_window_active": True},
                    )
            else:
                skipped.append("NT-T03:high_impact_event_window_active=unavailable")

        else:
            skipped.append("NT-T:temporal_input=None(family_disabled)")

        # ── All checks passed ────────────────────────────────────────────
        evidence: dict[str, object] = {
            "symbol": ctx.symbol,
            "exchange": ctx.exchange,
        }
        if skipped:
            evidence["skipped_checks"] = skipped
        return NoTradeDecision.allow(evidence)
