"""No-Trade Guard typed models.

All blocking decisions are immutable and fully traceable.

PRD reference: §1.21 — No-Trade Conditions (NT-D and NT-X).
"""

from __future__ import annotations

from dataclasses import dataclass, field


class NoTradeReason(str):
    """Canonical reason codes for no-trade blocks.

    NT-D = data-feed tier (feed health, book state, snapshot).
    NT-X = execution tier (latency, recovery, system state).
    """

    pass


# NT-D codes (data-feed tier)
NoTradeReason.STALE_DATA = NoTradeReason("NT-D01_stale_data")
NoTradeReason.INVALID_BOOK = NoTradeReason("NT-D02_invalid_book")
NoTradeReason.MISSING_SNAPSHOT = NoTradeReason("NT-D03_missing_snapshot")
NoTradeReason.UNSUPPORTED_SYMBOL = NoTradeReason("NT-D04_unsupported_symbol")
NoTradeReason.RECOVERY_ACTIVE = NoTradeReason("NT-D05_recovery_active")

# NT-X codes (execution/system tier)
NoTradeReason.SYSTEM_STATE_DEFENSIVE = NoTradeReason("NT-X01_system_state_defensive")
NoTradeReason.LATENCY_BUDGET_BREACH = NoTradeReason("NT-X02_latency_budget_breach")
NoTradeReason.TELEMETRY_UNAVAILABLE = NoTradeReason("NT-X03_telemetry_unavailable")


class BlockSeverity(str):
    """Severity of a no-trade block."""

    pass


BlockSeverity.SOFT = BlockSeverity("soft")          # transient, self-clears
BlockSeverity.HARD = BlockSeverity("hard")          # requires human review
BlockSeverity.CRITICAL = BlockSeverity("critical")  # system-level, escalates state

#: Maps each reason to its severity.
REASON_SEVERITY: dict[str, BlockSeverity] = {
    NoTradeReason.STALE_DATA: BlockSeverity.SOFT,
    NoTradeReason.INVALID_BOOK: BlockSeverity.HARD,
    NoTradeReason.MISSING_SNAPSHOT: BlockSeverity.HARD,
    NoTradeReason.UNSUPPORTED_SYMBOL: BlockSeverity.HARD,
    NoTradeReason.RECOVERY_ACTIVE: BlockSeverity.SOFT,
    NoTradeReason.SYSTEM_STATE_DEFENSIVE: BlockSeverity.CRITICAL,
    NoTradeReason.LATENCY_BUDGET_BREACH: BlockSeverity.SOFT,
    NoTradeReason.TELEMETRY_UNAVAILABLE: BlockSeverity.HARD,
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


@dataclass(frozen=True)
class NoTradeContext:
    """All inputs needed by the guard to make a blocking decision.

    This context is built by the caller (pipeline orchestrator) from
    live data layer state and system state.
    """

    symbol: str
    exchange: str
    current_ns: int  # wall-clock in nanoseconds

    # Data-feed tier
    book_last_update_ns: int = 0        # 0 = never updated
    book_has_snapshot: bool = False
    book_bid_count: int = 0
    book_ask_count: int = 0
    feed_connection_state: str = ""     # ConnectionState.value or empty
    feed_recovery_state: str = ""       # RecoveryState.value or empty
    supported_symbols: frozenset[str] = field(default_factory=frozenset)

    # Execution/system tier
    system_state: str = "NORMAL"        # SystemState value
    latency_ms: float = 0.0
    telemetry_last_emit_ns: int = 0     # 0 = never emitted


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
    def block(
        cls, reason: NoTradeReason, evidence: dict[str, object] | None = None
    ) -> NoTradeDecision:
        severity = REASON_SEVERITY.get(str(reason), BlockSeverity.HARD)
        return cls(allowed=False, reason=reason, severity=severity, evidence=evidence or {})
