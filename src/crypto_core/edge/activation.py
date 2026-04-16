"""Edge Activation Matrix — PRDV4-closer per-family pre-signal gate.

This module keeps the activation decision pure and auditable.
It does two things:

1. Provides deterministic runtime classifiers for the activation dimensions that
   can be computed from currently available crypto runtime inputs.
2. Applies a per-family allow/block matrix with explicit reason codes,
   allocation-scale hints, and evidence for every decision.

The implementation is intentionally conservative:
  - unsupported families remain blocked
  - disconnected / recovering / restricted-state conditions block immediately
  - missing required activation dimensions block the affected family
  - incomplete edge-health history is allowed only in an explicit reduced mode

PRD references: §1.5 Activation Matrix, §1.6 Edge Health Score, §1.9 Funding
Safety, §1.21 No-Trade Conditions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from crypto_core.data.models.events import TradeEvent
from crypto_core.edge.models import EdgeFamily


class RegimeState(str):
    """Activation regime state labels (PRD §1.5)."""

    pass


RegimeState.TRENDING = RegimeState("TRENDING")
RegimeState.RANGE = RegimeState("RANGE")
RegimeState.HIGH_VOL = RegimeState("HIGH_VOL")
RegimeState.CRISIS = RegimeState("CRISIS")
RegimeState.UNKNOWN = RegimeState("UNKNOWN")


class LiquidityCondition(str):
    """Activation liquidity condition labels (PRD §1.5)."""

    pass


LiquidityCondition.DEEP = LiquidityCondition("DEEP")
LiquidityCondition.NORMAL = LiquidityCondition("NORMAL")
LiquidityCondition.THIN = LiquidityCondition("THIN")
LiquidityCondition.DRY = LiquidityCondition("DRY")


class SpreadCondition(str):
    """Activation spread condition labels (runtime proxy for PRD spread stability)."""

    pass


SpreadCondition.STABLE = SpreadCondition("STABLE")
SpreadCondition.WIDENING = SpreadCondition("WIDENING")
SpreadCondition.BLOWN = SpreadCondition("BLOWN")


class ExecutionCondition(str):
    """Activation execution condition labels (PRD §1.5)."""

    pass


ExecutionCondition.OPTIMAL = ExecutionCondition("OPTIMAL")
ExecutionCondition.DEGRADED = ExecutionCondition("DEGRADED")
ExecutionCondition.IMPAIRED = ExecutionCondition("IMPAIRED")
ExecutionCondition.HALTED = ExecutionCondition("HALTED")


class VolatilityCondition(str):
    """Activation volatility bucket labels (PRD §1.5)."""

    pass


VolatilityCondition.LOW = VolatilityCondition("LOW")
VolatilityCondition.MED = VolatilityCondition("MED")
VolatilityCondition.HIGH = VolatilityCondition("HIGH")
VolatilityCondition.EXTREME = VolatilityCondition("EXTREME")


# ---------------------------------------------------------------------------
# Runtime classification constants
# ---------------------------------------------------------------------------

_IMPLEMENTED_FAMILIES: frozenset[str] = frozenset(
    [
        EdgeFamily.ORDER_FLOW_IMBALANCE,
        EdgeFamily.FUNDING_RATE,
        EdgeFamily.VOLATILITY_TRANSITION,
        EdgeFamily.LIQUIDATION_SIGNAL,
    ]
)

_CONNECTED_FEED_STATES: frozenset[str] = frozenset(["connected", "ready"])
_RESTRICTED_SYSTEM_STATES: frozenset[str] = frozenset(["DEFENSIVE", "CRISIS", "HALT"])

_VOLATILITY_MIN_TRADE_COUNT: int = 25
_TRENDING_MIN_TRADE_COUNT: int = 8
_TRENDING_MIN_ABS_RETURN: float = 0.003
_TRENDING_SCORE_THRESHOLD: float = 1.5

_LIQUIDITY_DEEP_MIN: float = 0.85
_LIQUIDITY_NORMAL_MIN: float = 0.50
_LIQUIDITY_THIN_MIN: float = 0.15

_SPREAD_STABLE_MAX_BPS: float = 50.0
_SPREAD_WIDENING_MAX_BPS: float = 150.0

_EDGE_HEALTH_DISABLE_MIN: float = 0.30
_INITIALIZING_ALLOCATION_SCALE: float = 0.25

_FAMILY_ALLOWED_REGIMES: dict[str, frozenset[str]] = {
    EdgeFamily.ORDER_FLOW_IMBALANCE: frozenset([RegimeState.TRENDING, RegimeState.RANGE]),
    EdgeFamily.FUNDING_RATE: frozenset([RegimeState.RANGE, RegimeState.HIGH_VOL]),
    EdgeFamily.LIQUIDATION_SIGNAL: frozenset([RegimeState.HIGH_VOL]),
    EdgeFamily.VOLATILITY_TRANSITION: frozenset([RegimeState.RANGE, RegimeState.TRENDING, RegimeState.HIGH_VOL]),
}

_FAMILY_ALLOWED_VOLATILITY: dict[str, frozenset[str]] = {
    EdgeFamily.ORDER_FLOW_IMBALANCE: frozenset(
        [VolatilityCondition.LOW, VolatilityCondition.MED, VolatilityCondition.HIGH]
    ),
    EdgeFamily.FUNDING_RATE: frozenset([VolatilityCondition.MED, VolatilityCondition.HIGH]),
    EdgeFamily.LIQUIDATION_SIGNAL: frozenset([VolatilityCondition.HIGH, VolatilityCondition.EXTREME]),
    EdgeFamily.VOLATILITY_TRANSITION: frozenset(
        [VolatilityCondition.MED, VolatilityCondition.HIGH, VolatilityCondition.EXTREME]
    ),
}

_FAMILY_ALLOWED_LIQUIDITY: dict[str, frozenset[str]] = {
    EdgeFamily.ORDER_FLOW_IMBALANCE: frozenset([LiquidityCondition.DEEP, LiquidityCondition.NORMAL]),
    EdgeFamily.FUNDING_RATE: frozenset([LiquidityCondition.DEEP, LiquidityCondition.NORMAL, LiquidityCondition.THIN]),
    EdgeFamily.LIQUIDATION_SIGNAL: frozenset([LiquidityCondition.NORMAL, LiquidityCondition.THIN]),
    EdgeFamily.VOLATILITY_TRANSITION: frozenset([LiquidityCondition.DEEP, LiquidityCondition.NORMAL]),
}

_FAMILY_ALLOWED_SPREAD: dict[str, frozenset[str]] = {
    EdgeFamily.ORDER_FLOW_IMBALANCE: frozenset([SpreadCondition.STABLE, SpreadCondition.WIDENING]),
    EdgeFamily.FUNDING_RATE: frozenset([SpreadCondition.STABLE, SpreadCondition.WIDENING]),
    EdgeFamily.LIQUIDATION_SIGNAL: frozenset(),  # any spread condition allowed by PRD
    EdgeFamily.VOLATILITY_TRANSITION: frozenset([SpreadCondition.STABLE]),
}

_FAMILY_ALLOWED_EXECUTION: dict[str, frozenset[str]] = {
    EdgeFamily.ORDER_FLOW_IMBALANCE: frozenset([ExecutionCondition.OPTIMAL, ExecutionCondition.DEGRADED]),
    EdgeFamily.FUNDING_RATE: frozenset([ExecutionCondition.OPTIMAL, ExecutionCondition.DEGRADED]),
    EdgeFamily.LIQUIDATION_SIGNAL: frozenset([ExecutionCondition.OPTIMAL, ExecutionCondition.DEGRADED]),
    EdgeFamily.VOLATILITY_TRANSITION: frozenset([ExecutionCondition.OPTIMAL]),
}

_REQUIRED_FIELDS_BY_FAMILY: dict[str, tuple[str, ...]] = {
    EdgeFamily.ORDER_FLOW_IMBALANCE: (
        "regime_state",
        "liquidity_condition",
        "execution_condition",
        "spread_condition",
        "volatility_condition",
    ),
    EdgeFamily.FUNDING_RATE: (
        "regime_state",
        "liquidity_condition",
        "execution_condition",
        "spread_condition",
        "volatility_condition",
    ),
    EdgeFamily.LIQUIDATION_SIGNAL: (
        "regime_state",
        "liquidity_condition",
        "execution_condition",
        "volatility_condition",
    ),
    EdgeFamily.VOLATILITY_TRANSITION: (
        "regime_state",
        "liquidity_condition",
        "execution_condition",
        "spread_condition",
        "volatility_condition",
        "regime_transition_active",
    ),
}


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def _safe_log_returns(prices: list[float]) -> list[float]:
    returns: list[float] = []
    for idx in range(1, len(prices)):
        prev = prices[idx - 1]
        current = prices[idx]
        if prev > 0.0 and current > 0.0:
            returns.append(math.log(current / prev))
    return returns


def _safe_mid_price(bid_price: float, ask_price: float) -> float | None:
    if bid_price <= 0.0 or ask_price <= bid_price:
        return None
    return (bid_price + ask_price) / 2.0


def liquidity_condition_from_score(score: float | None) -> tuple[LiquidityCondition | None, dict[str, object]]:
    """Map the regime tracker's normalized liquidity score to PRD-like buckets."""
    evidence: dict[str, object] = {
        "source": "regime_liquidity_score_proxy",
        "liquidity_score": score,
    }
    if score is None:
        evidence["reason"] = "liquidity_score_unavailable"
        return None, evidence
    if score >= _LIQUIDITY_DEEP_MIN:
        condition = LiquidityCondition.DEEP
    elif score >= _LIQUIDITY_NORMAL_MIN:
        condition = LiquidityCondition.NORMAL
    elif score >= _LIQUIDITY_THIN_MIN:
        condition = LiquidityCondition.THIN
    else:
        condition = LiquidityCondition.DRY
    evidence["condition"] = condition
    return condition, evidence


def spread_condition_from_book(
    book_has_snapshot: bool,
    bid_price: float,
    ask_price: float,
) -> tuple[SpreadCondition | None, dict[str, object]]:
    """Classify current spread from top-of-book as a conservative runtime proxy."""
    evidence: dict[str, object] = {
        "source": "top_of_book_spread_proxy",
        "book_has_snapshot": book_has_snapshot,
        "bid_price": bid_price,
        "ask_price": ask_price,
    }
    if not book_has_snapshot:
        evidence["reason"] = "book_snapshot_missing"
        return None, evidence
    mid = _safe_mid_price(bid_price, ask_price)
    if mid is None:
        evidence["reason"] = "book_invalid"
        return None, evidence
    spread_bps = (ask_price - bid_price) / mid * 10_000.0
    evidence["spread_bps"] = spread_bps
    if spread_bps <= _SPREAD_STABLE_MAX_BPS:
        condition = SpreadCondition.STABLE
    elif spread_bps <= _SPREAD_WIDENING_MAX_BPS:
        condition = SpreadCondition.WIDENING
    else:
        condition = SpreadCondition.BLOWN
    evidence["condition"] = condition
    return condition, evidence


def volatility_condition_from_trades(
    trades: list[TradeEvent] | tuple[TradeEvent, ...],
) -> tuple[VolatilityCondition | None, dict[str, object]]:
    """Classify trade-return volatility using the PRD bucket thresholds."""
    trade_count = len(trades)
    evidence: dict[str, object] = {
        "source": "trade_return_sigma_proxy",
        "trade_count": trade_count,
    }
    if trade_count < _VOLATILITY_MIN_TRADE_COUNT:
        evidence["reason"] = "insufficient_trades"
        return None, evidence
    prices = [float(trade.price) for trade in trades if trade.price > 0.0]
    returns = _safe_log_returns(prices)
    if len(returns) < 2:
        evidence["reason"] = "insufficient_returns"
        return None, evidence
    sigma = _stddev(returns)
    evidence["sigma_realized"] = sigma
    if sigma < 0.005:
        condition = VolatilityCondition.LOW
    elif sigma < 0.015:
        condition = VolatilityCondition.MED
    elif sigma < 0.035:
        condition = VolatilityCondition.HIGH
    else:
        condition = VolatilityCondition.EXTREME
    evidence["condition"] = condition
    return condition, evidence


def regime_state_from_trades(
    trades: list[TradeEvent] | tuple[TradeEvent, ...],
    system_state: str,
    volatility_condition: VolatilityCondition | None,
    regime_transition_active: bool | None,
) -> tuple[RegimeState, dict[str, object]]:
    """Classify a conservative activation regime state from real runtime inputs."""
    trade_count = len(trades)
    evidence: dict[str, object] = {
        "source": "trade_flow_regime_proxy",
        "trade_count": trade_count,
        "system_state": system_state,
        "volatility_condition": volatility_condition,
        "regime_transition_active": regime_transition_active,
    }
    if system_state in ("CRISIS", "HALT"):
        evidence["reason"] = "system_state_crisis"
        return RegimeState.CRISIS, evidence
    if volatility_condition is None:
        evidence["reason"] = "volatility_condition_unavailable"
        return RegimeState.UNKNOWN, evidence
    if volatility_condition in (VolatilityCondition.HIGH, VolatilityCondition.EXTREME):
        evidence["reason"] = "high_volatility_bucket"
        return RegimeState.HIGH_VOL, evidence
    if trade_count < _TRENDING_MIN_TRADE_COUNT:
        evidence["reason"] = "insufficient_trade_history"
        return RegimeState.UNKNOWN, evidence

    prices = [float(trade.price) for trade in trades if trade.price > 0.0]
    returns = _safe_log_returns(prices)
    if len(prices) < 2 or len(returns) < 2:
        evidence["reason"] = "insufficient_price_series"
        return RegimeState.UNKNOWN, evidence

    abs_return = abs(prices[-1] / prices[0] - 1.0)
    sigma = _stddev(returns)
    trending_score = abs_return / max(sigma, 1e-9)
    evidence["abs_return"] = abs_return
    evidence["sigma_realized"] = sigma
    evidence["trending_score"] = trending_score

    if abs_return >= _TRENDING_MIN_ABS_RETURN and trending_score >= _TRENDING_SCORE_THRESHOLD:
        return RegimeState.TRENDING, evidence
    return RegimeState.RANGE, evidence


def execution_condition_from_runtime(
    feed_connection_state: str,
    feed_recovery_state: str,
    book_has_snapshot: bool,
    bid_price: float,
    ask_price: float,
    spread_condition: SpreadCondition | None,
    prior_latency_ms: float | None = None,
    prior_fill_rate_pct: float | None = None,
) -> tuple[ExecutionCondition | None, dict[str, object]]:
    """Classify execution condition from real runtime evidence.

    When prior execution telemetry is not available yet, the classifier uses a
    conservative book/feed proxy instead of pretending the condition is known.
    """
    evidence: dict[str, object] = {
        "source": "execution_runtime_proxy",
        "feed_connection_state": feed_connection_state,
        "feed_recovery_state": feed_recovery_state,
        "book_has_snapshot": book_has_snapshot,
        "prior_latency_ms": prior_latency_ms,
        "prior_fill_rate_pct": prior_fill_rate_pct,
        "spread_condition": spread_condition,
    }
    if feed_connection_state not in _CONNECTED_FEED_STATES:
        evidence["reason"] = "feed_disconnected"
        return ExecutionCondition.HALTED, evidence
    if feed_recovery_state == "recovering":
        evidence["reason"] = "feed_recovering"
        return ExecutionCondition.HALTED, evidence
    if not book_has_snapshot or _safe_mid_price(bid_price, ask_price) is None:
        evidence["reason"] = "book_unavailable"
        return ExecutionCondition.HALTED, evidence

    if prior_latency_ms is not None and prior_fill_rate_pct is not None:
        if prior_latency_ms > 500.0 or prior_fill_rate_pct < 50.0:
            return ExecutionCondition.HALTED, evidence
        if prior_latency_ms >= 300.0 or prior_fill_rate_pct < 70.0:
            return ExecutionCondition.IMPAIRED, evidence
        if prior_latency_ms >= 100.0 or prior_fill_rate_pct < 90.0:
            return ExecutionCondition.DEGRADED, evidence
        return ExecutionCondition.OPTIMAL, evidence

    evidence["reason"] = "book_feed_proxy"
    if spread_condition == SpreadCondition.BLOWN:
        return ExecutionCondition.IMPAIRED, evidence
    return ExecutionCondition.DEGRADED, evidence


@dataclass(frozen=True)
class ActivationDecision:
    """Immutable result of one activation matrix evaluation."""

    family: EdgeFamily
    allowed: bool
    reason: str
    allocation_scale: float = 1.0
    evidence: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ActivationContext:
    """All activation inputs for a single family evaluation cycle."""

    system_state: str
    feed_connection_state: str
    feed_recovery_state: str
    mark_price_available: bool
    regime_state: str | None = None
    liquidity_condition: str | None = None
    execution_condition: str | None = None
    spread_condition: str | None = None
    volatility_condition: str | None = None
    regime_transition_active: bool | None = None
    edge_health_score: float | None = None
    edge_fsm_state: str | None = None
    edge_allocation_factor: float | None = None


class ActivationMatrix:
    """Deterministic per-family activation matrix."""

    def evaluate(self, family: EdgeFamily, ctx: ActivationContext) -> ActivationDecision:
        base_evidence: dict[str, object] = {
            "family": str(family),
            "system_state": ctx.system_state,
            "feed_connection_state": ctx.feed_connection_state,
            "feed_recovery_state": ctx.feed_recovery_state,
            "mark_price_available": ctx.mark_price_available,
            "regime_state": ctx.regime_state,
            "liquidity_condition": ctx.liquidity_condition,
            "execution_condition": ctx.execution_condition,
            "spread_condition": ctx.spread_condition,
            "volatility_condition": ctx.volatility_condition,
            "regime_transition_active": ctx.regime_transition_active,
            "edge_health_score": ctx.edge_health_score,
            "edge_fsm_state": ctx.edge_fsm_state,
            "edge_allocation_factor": ctx.edge_allocation_factor,
        }

        missing_inputs = [
            field_name
            for field_name in (
                "regime_state",
                "liquidity_condition",
                "execution_condition",
                "spread_condition",
                "volatility_condition",
                "regime_transition_active",
            )
            if getattr(ctx, field_name) is None
        ]

        if family not in _IMPLEMENTED_FAMILIES:
            return ActivationDecision(
                family=family,
                allowed=False,
                reason="family_not_implemented",
                evidence={
                    **base_evidence,
                    "supported_families": sorted(_IMPLEMENTED_FAMILIES),
                    "missing_inputs": missing_inputs,
                },
            )

        if ctx.system_state in _RESTRICTED_SYSTEM_STATES:
            return ActivationDecision(
                family=family,
                allowed=False,
                reason=f"system_state_restricted:{ctx.system_state}",
                evidence={
                    **base_evidence,
                    "restricted_states": sorted(_RESTRICTED_SYSTEM_STATES),
                    "missing_inputs": missing_inputs,
                },
            )

        if ctx.feed_connection_state not in _CONNECTED_FEED_STATES:
            return ActivationDecision(
                family=family,
                allowed=False,
                reason=f"data_disconnected:{ctx.feed_connection_state}",
                evidence={
                    **base_evidence,
                    "required_states": sorted(_CONNECTED_FEED_STATES),
                    "missing_inputs": missing_inputs,
                },
            )

        if ctx.feed_recovery_state == "recovering":
            return ActivationDecision(
                family=family,
                allowed=False,
                reason="data_recovering",
                evidence={**base_evidence, "missing_inputs": missing_inputs},
            )

        required_fields = _REQUIRED_FIELDS_BY_FAMILY.get(family, ())
        for field_name in required_fields:
            if getattr(ctx, field_name) is None:
                return ActivationDecision(
                    family=family,
                    allowed=False,
                    reason=f"activation_input_unavailable:{field_name}",
                    evidence={
                        **base_evidence,
                        "required_fields": required_fields,
                        "missing_inputs": missing_inputs,
                    },
                )

        allocation_scale = 1.0
        allow_tags: list[str] = []

        if ctx.edge_fsm_state is not None:
            edge_state = ctx.edge_fsm_state.upper()
            if edge_state == "QUARANTINE":
                return ActivationDecision(
                    family=family,
                    allowed=False,
                    reason="edge_quarantined",
                    evidence={**base_evidence, "missing_inputs": missing_inputs},
                )
            if edge_state == "DISABLED":
                return ActivationDecision(
                    family=family,
                    allowed=False,
                    reason="edge_disabled",
                    evidence={**base_evidence, "missing_inputs": missing_inputs},
                )
            if edge_state == "WARNING":
                allocation_scale = min(
                    allocation_scale,
                    ctx.edge_allocation_factor if ctx.edge_allocation_factor is not None else 0.50,
                )
                allow_tags.append("warning_health")
        else:
            allocation_scale = min(allocation_scale, _INITIALIZING_ALLOCATION_SCALE)
            allow_tags.append("edge_health_initializing")

        if ctx.edge_health_score is not None and ctx.edge_health_score < _EDGE_HEALTH_DISABLE_MIN:
            return ActivationDecision(
                family=family,
                allowed=False,
                reason="edge_health_low",
                evidence={
                    **base_evidence,
                    "minimum_edge_health_score": _EDGE_HEALTH_DISABLE_MIN,
                    "missing_inputs": missing_inputs,
                },
            )

        if ctx.regime_state == RegimeState.CRISIS:
            return ActivationDecision(
                family=family,
                allowed=False,
                reason="regime_crisis_blocked",
                evidence={**base_evidence, "missing_inputs": missing_inputs},
            )

        if ctx.execution_condition == ExecutionCondition.HALTED:
            return ActivationDecision(
                family=family,
                allowed=False,
                reason="execution_halted",
                evidence={**base_evidence, "missing_inputs": missing_inputs},
            )

        if ctx.liquidity_condition == LiquidityCondition.DRY:
            return ActivationDecision(
                family=family,
                allowed=False,
                reason="liquidity_dry_blocked",
                evidence={**base_evidence, "missing_inputs": missing_inputs},
            )

        if ctx.regime_state == RegimeState.UNKNOWN:
            if family != EdgeFamily.FUNDING_RATE:
                return ActivationDecision(
                    family=family,
                    allowed=False,
                    reason="regime_unknown_family_blocked",
                    evidence={**base_evidence, "missing_inputs": missing_inputs},
                )
            allocation_scale = min(allocation_scale, 0.25)
            allow_tags.append("unknown_regime_reduced")

        if ctx.spread_condition == SpreadCondition.BLOWN:
            if family not in (EdgeFamily.FUNDING_RATE, EdgeFamily.LIQUIDATION_SIGNAL):
                return ActivationDecision(
                    family=family,
                    allowed=False,
                    reason="spread_blown_family_blocked",
                    evidence={**base_evidence, "missing_inputs": missing_inputs},
                )
            allocation_scale = min(allocation_scale, 0.50)
            allow_tags.append("spread_blown_reduced")

        if family == EdgeFamily.FUNDING_RATE and not ctx.mark_price_available:
            return ActivationDecision(
                family=family,
                allowed=False,
                reason="funding_feed_unavailable",
                evidence={
                    **base_evidence,
                    "required": "mark_price_event",
                    "missing_inputs": missing_inputs,
                },
            )

        if family == EdgeFamily.VOLATILITY_TRANSITION and ctx.regime_transition_active is not True:
            return ActivationDecision(
                family=family,
                allowed=False,
                reason="regime_transition_required",
                evidence={**base_evidence, "missing_inputs": missing_inputs},
            )

        if ctx.regime_state not in _FAMILY_ALLOWED_REGIMES[family] and not (
            family == EdgeFamily.FUNDING_RATE and ctx.regime_state == RegimeState.UNKNOWN
        ):
            return ActivationDecision(
                family=family,
                allowed=False,
                reason="regime_disallowed",
                evidence={
                    **base_evidence,
                    "allowed_regimes": sorted(_FAMILY_ALLOWED_REGIMES[family]),
                    "missing_inputs": missing_inputs,
                },
            )

        if ctx.volatility_condition not in _FAMILY_ALLOWED_VOLATILITY[family]:
            return ActivationDecision(
                family=family,
                allowed=False,
                reason="volatility_disallowed",
                evidence={
                    **base_evidence,
                    "allowed_volatility": sorted(_FAMILY_ALLOWED_VOLATILITY[family]),
                    "missing_inputs": missing_inputs,
                },
            )

        if ctx.liquidity_condition not in _FAMILY_ALLOWED_LIQUIDITY[family]:
            return ActivationDecision(
                family=family,
                allowed=False,
                reason="liquidity_disallowed",
                evidence={
                    **base_evidence,
                    "allowed_liquidity": sorted(_FAMILY_ALLOWED_LIQUIDITY[family]),
                    "missing_inputs": missing_inputs,
                },
            )

        allowed_spread = _FAMILY_ALLOWED_SPREAD[family]
        if allowed_spread and ctx.spread_condition not in allowed_spread:
            return ActivationDecision(
                family=family,
                allowed=False,
                reason="spread_disallowed",
                evidence={
                    **base_evidence,
                    "allowed_spread": sorted(allowed_spread),
                    "missing_inputs": missing_inputs,
                },
            )

        if ctx.execution_condition not in _FAMILY_ALLOWED_EXECUTION[family]:
            return ActivationDecision(
                family=family,
                allowed=False,
                reason="execution_disallowed",
                evidence={
                    **base_evidence,
                    "allowed_execution": sorted(_FAMILY_ALLOWED_EXECUTION[family]),
                    "missing_inputs": missing_inputs,
                },
            )

        if ctx.regime_transition_active is True and family == EdgeFamily.ORDER_FLOW_IMBALANCE:
            return ActivationDecision(
                family=family,
                allowed=False,
                reason="regime_transition_blocked",
                evidence={**base_evidence, "missing_inputs": missing_inputs},
            )

        reason = "allowed"
        if allow_tags or allocation_scale < 1.0:
            reason = "allowed_reduced"

        return ActivationDecision(
            family=family,
            allowed=True,
            reason=reason,
            allocation_scale=allocation_scale,
            evidence={
                **base_evidence,
                "allow_tags": allow_tags,
                "missing_inputs": missing_inputs,
                "allocation_scale": allocation_scale,
            },
        )
