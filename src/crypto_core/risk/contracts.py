"""Risk Engine v2 — typed input contracts.

These dataclasses form the complete input surface for evaluate_v2().
Each contract is optional in RiskInput; a None value means the
corresponding gate is skipped.

Design rules:
  - All fields are validated at gate-time by RiskEngine, NOT at construction.
  - Callers that lack data set the corresponding contract to None.
  - A gate that receives invalid or missing data BLOCKS (fail-closed).

PRD reference: §1.18 CVaR, §1.19 Kill-Switch, §1.26 Margin, §1.28 Kelly.
"""

from __future__ import annotations

from dataclasses import dataclass

from crypto_core.edge.models import EdgeSignal
from crypto_core.guard.models import NoTradeDecision
from crypto_core.state.models import SystemState

# ---------------------------------------------------------------------------
# Kill-switch level constants
# ---------------------------------------------------------------------------

#: KS0 — normal operation
KS_LEVEL_NORMAL: int = 0
#: KS1 — reduce new position sizes (advisory, not enforced as hard block)
KS_LEVEL_REDUCE: int = 1
#: KS2 — block ALL new entries (hard block begins here)
KS_LEVEL_BLOCK: int = 2
#: KS3 — flatten positions / stop entries (same hard block)
KS_LEVEL_FLATTEN: int = 3
#: KS4 — system HALT, handled upstream by state engine AND risk engine (defense-in-depth)
KS_LEVEL_HALT: int = 4

#: Any kill-switch level >= this value blocks new trade entries
KS_BLOCK_THRESHOLD: int = KS_LEVEL_BLOCK

# ---------------------------------------------------------------------------
# DTL (Distance-to-Liquidation)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DTLInput:
    """Distance-to-Liquidation contract (PRD §1.26).

    Set ``liquidation_price=0.0`` when the liquidation price is unknown
    (e.g. dry-run with no open position). The gate will be skipped with
    an ``"liquidation_price_unavailable"`` note in evidence.

    The risk engine does NOT estimate liquidation prices from first
    principles — that would require exchange-specific margin rules and
    make incorrect assumptions in cross- vs isolated-margin mode.
    Callers must supply the actual liquidation price from the exchange
    or position-tracker layer.

    DTL % = |current_price - liquidation_price| / current_price * 100
    Gate fires when: DTL % < min_safe_distance_pct
    """

    current_price: float
    liquidation_price: float  # 0.0 = data unavailable, gate skipped
    min_safe_distance_pct: float = 5.0  # default: 5% minimum distance


# ---------------------------------------------------------------------------
# Kelly position sizing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KellyInput:
    """Kelly criterion sizing contract (PRD §1.28).

    Uses the exact discrete Kelly formula:
        f* = (p * b - q) / b
    where:
        p = win_rate     (probability of profit per trade)
        q = 1 - p        (probability of loss)
        b = payoff_ratio (average_win / average_loss)

    Gate fires when:
        - win_rate not in (0, 1) exclusive → KELLY_LIMIT
        - payoff_ratio <= 0                → KELLY_LIMIT
        - computed f* <= 0                 → KELLY_NO_EDGE (no mathematical edge)

    Approved fraction = min(f*, max_fraction).
    """

    win_rate: float  # ∈ (0, 1) exclusive
    payoff_ratio: float  # avg_win / avg_loss, must be > 0
    max_fraction: float = 0.25  # hard cap on Kelly fraction (half-Kelly is max_fraction=0.25)


# ---------------------------------------------------------------------------
# CVaR
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CVaRInput:
    """CVaR (Conditional Value-at-Risk) evaluation contract (PRD §1.18).

    cvar99_pct / var99_pct use percentage-point units, e.g. 4.2 means 4.2%.
    history_count captures the number of bounded return observations used.
    available=False or cvar99_pct=None means the gate is explicitly unavailable.

    Gate fires when: cvar99_pct > cvar_limit_pct → CVAR_LIMIT
    """

    cvar99_pct: float | None = None  # 99th percentile CVaR as % of capital; None = skip
    cvar_limit_pct: float = 5.0  # hard block threshold
    var99_pct: float | None = None
    history_count: int = 0
    available: bool = False


# ---------------------------------------------------------------------------
# Portfolio-level risk snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PortfolioRiskSnapshot:
    """Portfolio-level risk state at the time of evaluation.

    This is a snapshot — not a live query. The caller (orchestrator or
    state-store layer) must supply fresh values on each cycle.

    Gates:
      - max_leverage_in_use > 3.0 (system hard cap) → PORTFOLIO_LIMIT
      - total_exposure_usd > max_total_exposure_usd  → PORTFOLIO_LIMIT
      - active_position_count >= max_concurrent_positions → PORTFOLIO_LIMIT
    """

    total_exposure_usd: float  # sum of all open position notional values
    active_position_count: int  # number of open positions
    max_leverage_in_use: float  # highest leverage of any single open position
    max_total_exposure_usd: float = 100_000.0  # USD hard cap (config-driven)
    max_concurrent_positions: int = 10  # concurrent position cap


# ---------------------------------------------------------------------------
# Full v2 risk input contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RiskInput:
    """Complete v2 risk evaluation input.

    Optional gates are skipped when the corresponding field is None.
    This allows partial adoption — callers provide what they have.

    Required fields match the v1 evaluate() signature for drop-in upgrade.
    """

    edge_signal: EdgeSignal
    system_state: SystemState
    no_trade: NoTradeDecision
    timestamp_ns: int

    # Optional v2 gates
    shs_snapshot: float | None = None  # SHS value for telemetry
    kill_switch_level: int = KS_LEVEL_NORMAL  # 0–4
    dtl: DTLInput | None = None  # None = gate skipped
    kelly: KellyInput | None = None  # None = gate skipped
    cvar: CVaRInput | None = None  # None = gate skipped
    portfolio: PortfolioRiskSnapshot | None = None  # None = gate skipped

    @classmethod
    def from_v1(
        cls,
        edge_signal: EdgeSignal,
        system_state: SystemState,
        no_trade: NoTradeDecision,
        timestamp_ns: int,
        shs_snapshot: float | None = None,
    ) -> RiskInput:
        """Construct a v2 RiskInput from v1 evaluate() arguments.

        All v2-only gates will be skipped (None). Useful for migration.
        """
        return cls(
            edge_signal=edge_signal,
            system_state=system_state,
            no_trade=no_trade,
            timestamp_ns=timestamp_ns,
            shs_snapshot=shs_snapshot,
        )
