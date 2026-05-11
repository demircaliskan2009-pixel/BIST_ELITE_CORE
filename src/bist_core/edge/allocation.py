from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from bist_core.edge.registry import EdgeDefinition
from bist_core.edge.validation import EdgeValidationResult
from bist_core.features.feature_registry import get_feature
from bist_core.models.ohlcv import OHLCVBar, normalize_timestamp
from bist_core.risk.trade_risk_engine import compute_position_size


@dataclass(frozen=True)
class CapitalAllocationConfig:
    max_risk_per_trade_pct: float = 1.0
    max_exposure_pct: float = 25.0
    atr_stop_multiple: float = 1.0
    volatility_reference_atr_ratio: float = 0.02
    max_drawdown_reference: float = 0.20
    min_stop_distance_pct: float = 0.5


@dataclass(frozen=True)
class CapitalAllocationResult:
    approved: bool
    position_size_pct: float
    risk_amount: float
    share_count: int
    exposure_amount: float
    explanation: str
    blocked_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "position_size_pct": self.position_size_pct,
            "risk_amount": self.risk_amount,
            "share_count": self.share_count,
            "exposure_amount": self.exposure_amount,
            "explanation": self.explanation,
            "blocked_reason": self.blocked_reason,
        }


def _round_value(value: float) -> float:
    return round(float(value), 6)


def _blocked(reason: str) -> CapitalAllocationResult:
    return CapitalAllocationResult(
        approved=False,
        position_size_pct=0.0,
        risk_amount=0.0,
        share_count=0,
        exposure_amount=0.0,
        explanation=f"NO TRADE: {reason}",
        blocked_reason=reason,
    )


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _validate_config(config: CapitalAllocationConfig) -> str | None:
    if config.max_risk_per_trade_pct <= 0.0:
        return "invalid_config:max_risk_per_trade_pct"
    if config.max_exposure_pct <= 0.0 or config.max_exposure_pct > 100.0:
        return "invalid_config:max_exposure_pct"
    if config.atr_stop_multiple <= 0.0:
        return "invalid_config:atr_stop_multiple"
    if config.volatility_reference_atr_ratio <= 0.0:
        return "invalid_config:volatility_reference_atr_ratio"
    if config.max_drawdown_reference <= 0.0:
        return "invalid_config:max_drawdown_reference"
    if config.min_stop_distance_pct <= 0.0:
        return "invalid_config:min_stop_distance_pct"
    return None


def _validate_bars(bars: Sequence[OHLCVBar]) -> str | None:
    if not bars:
        return "invalid_bars:empty"
    previous_timestamp: int | None = None
    symbol = str(bars[0].symbol or "").strip()
    if not symbol:
        return "invalid_bars:empty_symbol"
    for bar in bars:
        timestamp = normalize_timestamp(bar.timestamp)
        if previous_timestamp is not None and timestamp <= previous_timestamp:
            return "invalid_bars:non_monotonic_timestamps"
        previous_timestamp = timestamp
        if str(bar.symbol or "").strip() != symbol:
            return "invalid_bars:mixed_symbols"
        if float(bar.close) <= 0.0 or float(bar.open) <= 0.0 or float(bar.high) <= 0.0 or float(bar.low) <= 0.0:
            return "invalid_bars:non_positive_price"
    return None


def allocate_capital_to_edge(
    selected_edge: EdgeDefinition,
    edge_score: float,
    validation_result: EdgeValidationResult,
    current_equity: float,
    bars: Sequence[OHLCVBar],
    config: CapitalAllocationConfig | None = None,
    edge_state: Any | None = None,
) -> CapitalAllocationResult:
    config = config or CapitalAllocationConfig()
    config_error = _validate_config(config)
    if config_error is not None:
        return _blocked(config_error)

    if not selected_edge.enabled:
        return _blocked("edge_disabled")
    if validation_result.edge_id != selected_edge.edge_id:
        return _blocked("validation_edge_mismatch")
    if validation_result.valid is not True or validation_result.blocked_reason is not None:
        return _blocked("invalid_validation_result")
    if not math.isfinite(float(current_equity)) or float(current_equity) <= 0.0:
        return _blocked("invalid_current_equity")
    if not math.isfinite(float(edge_score)) or float(edge_score) <= 0.0:
        return _blocked("invalid_edge_score")

    bar_error = _validate_bars(bars)
    if bar_error is not None:
        return _blocked(bar_error)

    metrics = validation_result.metrics
    total_trades = int(metrics.get("total_trades", 0))
    if total_trades < 1:
        return _blocked("insufficient_validation_trades")

    max_drawdown = float(metrics.get("max_drawdown", 0.0))
    if not math.isfinite(max_drawdown) or max_drawdown < 0.0:
        return _blocked("invalid_validation_drawdown")

    atr_series = get_feature("atr_14")(bars)
    if not atr_series or atr_series[-1] is None:
        return _blocked("missing_atr_14")
    atr_14 = float(atr_series[-1])
    last_close = float(bars[-1].close)
    if not math.isfinite(atr_14) or atr_14 <= 0.0:
        return _blocked("invalid_atr_14")
    if not math.isfinite(last_close) or last_close <= 0.0:
        return _blocked("invalid_last_close")

    score_factor = _clamp01(edge_score)
    drawdown_factor = _clamp01(1.0 / (1.0 + (max_drawdown / config.max_drawdown_reference)))
    atr_ratio = atr_14 / last_close
    volatility_factor = _clamp01(config.volatility_reference_atr_ratio / max(atr_ratio, 1e-9))
    adjusted_risk_pct = config.max_risk_per_trade_pct * score_factor * drawdown_factor * volatility_factor
    if adjusted_risk_pct <= 0.0:
        return _blocked("adjusted_risk_pct_zero")

    stop_distance = max(atr_14 * config.atr_stop_multiple, last_close * (config.min_stop_distance_pct / 100.0))
    stop_price = max(last_close - stop_distance, 0.01)

    risk_shares = compute_position_size(
        capital=float(current_equity),
        entry=last_close,
        stop=stop_price,
        max_risk_pct=adjusted_risk_pct,
    )
    exposure_cap_shares = int(math.floor((float(current_equity) * (config.max_exposure_pct / 100.0)) / last_close))
    share_count = min(risk_shares, exposure_cap_shares)
    if share_count < 1:
        return _blocked("position_size_zero")

    exposure_amount = _round_value(share_count * last_close)
    position_size_pct = _round_value((exposure_amount / float(current_equity)) * 100.0)
    risk_amount = _round_value(abs(last_close - stop_price) * share_count)
    explanation = (
        f"position_size_pct={position_size_pct:.4f}%; risk_amount={risk_amount:.6f};"
        f" shares={share_count}; edge_score={float(edge_score):.4f};"
        f" score_factor={score_factor:.4f}; drawdown_factor={drawdown_factor:.4f};"
        f" volatility_factor={volatility_factor:.4f}; atr_ratio={atr_ratio:.6f};"
        f" adjusted_risk_pct={adjusted_risk_pct:.6f}; max_exposure_pct={config.max_exposure_pct:.4f}"
    )
    result = CapitalAllocationResult(
        approved=True,
        position_size_pct=position_size_pct,
        risk_amount=risk_amount,
        share_count=share_count,
        exposure_amount=exposure_amount,
        explanation=explanation,
        blocked_reason=None,
    )
    if edge_state is None:
        return result

    from bist_core.edge.self_healing import apply_edge_state_to_allocation

    return apply_edge_state_to_allocation(result, edge_state)


__all__ = ["CapitalAllocationConfig", "CapitalAllocationResult", "allocate_capital_to_edge"]
