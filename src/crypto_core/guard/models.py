"""No-Trade Guard typed models.

All blocking decisions are immutable and fully traceable.

PRD reference: §1.21 — No-Trade Conditions (NT-D, NT-R, NT-M, NT-E, NT-X, NT-T).

Rule families:
  NT-D  — Data integrity (5 rules)
  NT-R  — Risk limits     (6 rules)
  NT-M  — Market/regime   (4 rules)
  NT-E  — Edge health     (4 rules)
  NT-X  — Execution       (3 rules)
  NT-T  — Temporal        (3 rules)
  Total: 25 rules (23 PRD + 2 guard-internal)

Unavailable inputs:
  Optional fields on input dataclasses default to None.
  None = "upstream component not yet available — check explicitly skipped".
  This is NOT a safe default; the guard documents all skipped checks in evidence.
  Callers MUST pass an explicit value or None — magic booleans are forbidden.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class NoTradeReason(str):
    """Canonical reason codes for no-trade blocks.

    NT-D = data-feed tier (feed health, book state, snapshot).
    NT-R = risk limits (kill-switch, P&L, exposure, CVaR, margin).
    NT-M = market/regime conditions (liquidity, leverage, regime, correlation).
    NT-E = edge health (EHS score, FSM state, capacity, valid count).
    NT-X = execution quality (latency, system state, telemetry).
    NT-T = temporal restrictions (startup, KS cooldown, macro events).
    """

    pass


# ── NT-D codes (data-feed tier) ────────────────────────────────────────────
NoTradeReason.STALE_DATA = NoTradeReason("NT-D01_stale_data")
NoTradeReason.INVALID_BOOK = NoTradeReason("NT-D02_invalid_book")
NoTradeReason.MISSING_SNAPSHOT = NoTradeReason("NT-D03_missing_snapshot")
NoTradeReason.UNSUPPORTED_SYMBOL = NoTradeReason("NT-D04_unsupported_symbol")
NoTradeReason.RECOVERY_ACTIVE = NoTradeReason("NT-D05_recovery_active")

# ── NT-R codes (risk limits) ───────────────────────────────────────────────
NoTradeReason.KS_ACTIVE = NoTradeReason("NT-R01_ks_active")
NoTradeReason.DAILY_LOSS_LIMIT = NoTradeReason("NT-R02_daily_loss_limit")
NoTradeReason.OPEN_RISK_CAP = NoTradeReason("NT-R03_open_risk_cap")
NoTradeReason.POSITION_CONCENTRATION = NoTradeReason("NT-R04_position_concentration")
NoTradeReason.CVAR_BUDGET_EXHAUSTED = NoTradeReason("NT-R05_cvar_budget_exhausted")
NoTradeReason.MARGIN_UTILIZATION = NoTradeReason("NT-R06_margin_utilization")

# ── NT-M codes (market/regime) ─────────────────────────────────────────────
NoTradeReason.LIQUIDITY_CRISIS = NoTradeReason("NT-M01_liquidity_crisis")
NoTradeReason.LEVERAGE_EXTREME = NoTradeReason("NT-M02_leverage_extreme")
NoTradeReason.REGIME_TRANSITION = NoTradeReason("NT-M03_regime_transition")
NoTradeReason.CORRELATION_BREAKDOWN = NoTradeReason("NT-M04_correlation_breakdown")

# ── NT-E codes (edge health) ───────────────────────────────────────────────
NoTradeReason.EDGE_HEALTH_LOW = NoTradeReason("NT-E01_edge_health_low")
NoTradeReason.EDGE_DISABLED = NoTradeReason("NT-E02_edge_disabled")
NoTradeReason.EDGE_CAPACITY_RED = NoTradeReason("NT-E03_edge_capacity_red")
NoTradeReason.NO_VALID_EDGE = NoTradeReason("NT-E04_no_valid_edge")

# ── NT-X codes (execution/system tier) ─────────────────────────────────────
NoTradeReason.SYSTEM_STATE_DEFENSIVE = NoTradeReason("NT-X01_system_state_defensive")
NoTradeReason.LATENCY_BUDGET_BREACH = NoTradeReason("NT-X02_latency_budget_breach")
NoTradeReason.TELEMETRY_UNAVAILABLE = NoTradeReason("NT-X03_telemetry_unavailable")

# ── NT-T codes (temporal) ─────────────────────────────────────────────────
NoTradeReason.STARTUP_WARMUP = NoTradeReason("NT-T01_startup_warmup")
NoTradeReason.KS_COOLDOWN = NoTradeReason("NT-T02_ks_cooldown")
NoTradeReason.HIGH_IMPACT_EVENT = NoTradeReason("NT-T03_high_impact_event")


class BlockSeverity(str):
    """Severity of a no-trade block."""

    pass


BlockSeverity.SOFT = BlockSeverity("soft")  # transient, self-clears
BlockSeverity.HARD = BlockSeverity("hard")  # requires human review
BlockSeverity.CRITICAL = BlockSeverity("critical")  # system-level, escalates state

#: Maps each reason to its severity.
REASON_SEVERITY: dict[str, BlockSeverity] = {
    # NT-D
    NoTradeReason.STALE_DATA: BlockSeverity.SOFT,
    NoTradeReason.INVALID_BOOK: BlockSeverity.HARD,
    NoTradeReason.MISSING_SNAPSHOT: BlockSeverity.HARD,
    NoTradeReason.UNSUPPORTED_SYMBOL: BlockSeverity.HARD,
    NoTradeReason.RECOVERY_ACTIVE: BlockSeverity.SOFT,
    # NT-R
    NoTradeReason.KS_ACTIVE: BlockSeverity.CRITICAL,
    NoTradeReason.DAILY_LOSS_LIMIT: BlockSeverity.HARD,
    NoTradeReason.OPEN_RISK_CAP: BlockSeverity.HARD,
    NoTradeReason.POSITION_CONCENTRATION: BlockSeverity.HARD,
    NoTradeReason.CVAR_BUDGET_EXHAUSTED: BlockSeverity.HARD,
    NoTradeReason.MARGIN_UTILIZATION: BlockSeverity.HARD,
    # NT-M
    NoTradeReason.LIQUIDITY_CRISIS: BlockSeverity.HARD,
    NoTradeReason.LEVERAGE_EXTREME: BlockSeverity.HARD,
    NoTradeReason.REGIME_TRANSITION: BlockSeverity.SOFT,
    NoTradeReason.CORRELATION_BREAKDOWN: BlockSeverity.HARD,
    # NT-E
    NoTradeReason.EDGE_HEALTH_LOW: BlockSeverity.SOFT,
    NoTradeReason.EDGE_DISABLED: BlockSeverity.HARD,
    NoTradeReason.EDGE_CAPACITY_RED: BlockSeverity.SOFT,
    NoTradeReason.NO_VALID_EDGE: BlockSeverity.HARD,
    # NT-X
    NoTradeReason.SYSTEM_STATE_DEFENSIVE: BlockSeverity.CRITICAL,
    NoTradeReason.LATENCY_BUDGET_BREACH: BlockSeverity.SOFT,
    NoTradeReason.TELEMETRY_UNAVAILABLE: BlockSeverity.HARD,
    # NT-T
    NoTradeReason.STARTUP_WARMUP: BlockSeverity.SOFT,
    NoTradeReason.KS_COOLDOWN: BlockSeverity.SOFT,
    NoTradeReason.HIGH_IMPACT_EVENT: BlockSeverity.SOFT,
}

#: All NT-D reason codes (used for fraction calculation by state engine S4).
NT_D_CODES: frozenset[str] = frozenset(
    {
        NoTradeReason.STALE_DATA,
        NoTradeReason.INVALID_BOOK,
        NoTradeReason.MISSING_SNAPSHOT,
        NoTradeReason.UNSUPPORTED_SYMBOL,
        NoTradeReason.RECOVERY_ACTIVE,
    }
)

#: All NT-R reason codes.
NT_R_CODES: frozenset[str] = frozenset(
    {
        NoTradeReason.KS_ACTIVE,
        NoTradeReason.DAILY_LOSS_LIMIT,
        NoTradeReason.OPEN_RISK_CAP,
        NoTradeReason.POSITION_CONCENTRATION,
        NoTradeReason.CVAR_BUDGET_EXHAUSTED,
        NoTradeReason.MARGIN_UTILIZATION,
    }
)

#: All NT-M reason codes.
NT_M_CODES: frozenset[str] = frozenset(
    {
        NoTradeReason.LIQUIDITY_CRISIS,
        NoTradeReason.LEVERAGE_EXTREME,
        NoTradeReason.REGIME_TRANSITION,
        NoTradeReason.CORRELATION_BREAKDOWN,
    }
)

#: All NT-E reason codes.
NT_E_CODES: frozenset[str] = frozenset(
    {
        NoTradeReason.EDGE_HEALTH_LOW,
        NoTradeReason.EDGE_DISABLED,
        NoTradeReason.EDGE_CAPACITY_RED,
        NoTradeReason.NO_VALID_EDGE,
    }
)

#: All NT-T reason codes.
NT_T_CODES: frozenset[str] = frozenset(
    {
        NoTradeReason.STARTUP_WARMUP,
        NoTradeReason.KS_COOLDOWN,
        NoTradeReason.HIGH_IMPACT_EVENT,
    }
)


# ---------------------------------------------------------------------------
# Typed input contracts for new rule families
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RiskGuardInput:
    """Inputs for NT-R risk-limit family rules.

    All portfolio/position fields default to None = "upstream component not
    yet available".  When None, that specific sub-check is explicitly skipped
    and documented in the guard evidence.  The guard NEVER silently treats
    None as "safe".

    NT-R01 (kill_switch_level) is always available — callers must supply it.
    All other fields require a live position tracker (Phase 5C+).
    """

    # NT-R01: caller-supplied KS level (from KS engine or legacy param)
    kill_switch_level: int = 0

    # NT-R02: intraday PnL as signed % of NAV (negative = loss); None = unavailable
    daily_pnl_pct: float | None = None

    # NT-R03: sum of all position risks / equity %; None = unavailable
    open_risk_pct: float | None = None

    # NT-R04: largest single position / NAV %; None = unavailable
    max_single_position_pct: float | None = None

    # NT-R05: portfolio CVaR₉₉ / NAV %; None = unavailable
    portfolio_cvar99_pct: float | None = None

    # NT-R06: used_margin / available_margin %; None = unavailable
    margin_used_pct: float | None = None


@dataclass(frozen=True)
class MarketRegimeInput:
    """Inputs for NT-M market/regime family rules.

    All fields default to None = "upstream component not yet available".
    When None, that sub-check is explicitly skipped.

    NT-M01 requires the liquidity regime tracker (Phase 5C+).
    NT-M02 requires OI/MC data from the exchange (Phase 5C+).
    NT-M03 requires the regime hysteresis tracker (Phase 5C+).
    NT-M04 requires the cross-asset correlation engine (Phase 5C+).
    """

    # NT-M01: current liquidity score [0, 1]; None = unavailable
    liquidity_score: float | None = None
    # NT-M01: how long liquidity has been below crisis threshold, ms; None = unavailable
    liquidity_crisis_sustained_ms: float | None = None

    # NT-M02: open interest / market cap ratio; None = unavailable
    oi_mc_ratio: float | None = None

    # NT-M03: True if any regime dimension is in a hysteresis window; None = unavailable
    regime_transition_active: bool | None = None

    # NT-M04: mean pairwise correlation across portfolio [−1, 1]; None = unavailable
    mean_pairwise_correlation: float | None = None


@dataclass(frozen=True)
class EdgeHealthInput:
    """Inputs for NT-E edge-health family rules.

    All fields default to None = "upstream component not yet available".
    When None, that sub-check is explicitly skipped.

    Requires the Edge Health Score (EHS) tracker and edge FSM state
    (available once EdgeEngine v2 is wired — Phase 5D+).
    """

    # NT-E01: current EHS for the relevant edge [0, 1]; None = unavailable
    edge_health_score: float | None = None

    # NT-E02: edge FSM state string (e.g. "ACTIVE", "DISABLED"); None = unavailable
    edge_fsm_state: str | None = None

    # NT-E03: edge utilization as % of K_max [0, 100]; None = unavailable
    edge_utilization_pct: float | None = None

    # NT-E04: count of valid edges (EHS > threshold) for this asset; None = unavailable
    valid_edge_count: int | None = None


@dataclass(frozen=True)
class TemporalInput:
    """Inputs for NT-T temporal restriction family rules.

    engine_start_ns = 0 disables the startup warmup check (safe default for
    systems that do not track start time).  All other fields default to None
    = "upstream component not yet available" → skip that check.
    """

    # NT-T01: engine start timestamp in ns; 0 = startup check disabled
    engine_start_ns: int = 0

    # NT-T02: True if the system is within a post-kill-switch cool-down window; None = skip
    ks_cooldown_active: bool | None = None

    # NT-T03: True if currently inside a high-impact macro event window; None = skip
    high_impact_event_window_active: bool | None = None


# ---------------------------------------------------------------------------
# Core context and decision types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NoTradeContext:
    """All inputs needed by the guard to make a blocking decision.

    This context is built by the caller (pipeline orchestrator) from
    live data layer state and system state.

    New family inputs (risk, market, edge, temporal) are optional.
    Passing None for a family disables all checks in that family.
    Passing a struct with None fields disables those individual sub-checks.
    The guard documents every skipped check in decision evidence.
    """

    symbol: str
    exchange: str
    current_ns: int  # wall-clock in nanoseconds

    # Data-feed tier
    book_last_update_ns: int = 0  # 0 = never updated
    book_has_snapshot: bool = False
    book_bid_count: int = 0
    book_ask_count: int = 0
    feed_connection_state: str = ""  # ConnectionState.value or empty
    feed_recovery_state: str = ""  # RecoveryState.value or empty
    supported_symbols: frozenset[str] = field(default_factory=frozenset)

    # Execution/system tier
    system_state: str = "NORMAL"  # SystemState value
    latency_ms: float = 0.0
    telemetry_last_emit_ns: int = 0  # 0 = never emitted

    # ── New family inputs (None = family checks disabled) ────────────────
    risk: RiskGuardInput | None = None
    market: MarketRegimeInput | None = None
    edge: EdgeHealthInput | None = None
    temporal: TemporalInput | None = None


@dataclass(frozen=True)
class NoTradeDecision:
    """Immutable result of one guard evaluation.

    If allowed=True: reason, severity, and evidence are informational only.
    If allowed=False: reason and severity are required.
    """

    allowed: bool
    reason: NoTradeReason | None  # None iff allowed=True
    severity: BlockSeverity | None  # None iff allowed=True
    evidence: dict[str, object]

    @classmethod
    def allow(cls, evidence: dict[str, object] | None = None) -> NoTradeDecision:
        return cls(allowed=True, reason=None, severity=None, evidence=evidence or {})

    @classmethod
    def block(cls, reason: NoTradeReason, evidence: dict[str, object] | None = None) -> NoTradeDecision:
        severity = REASON_SEVERITY.get(str(reason), BlockSeverity.HARD)
        return cls(allowed=False, reason=reason, severity=severity, evidence=evidence or {})
