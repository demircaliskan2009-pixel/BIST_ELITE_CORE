from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from bist_core.providers.base import FailClosedError


_REQUIRED_METRIC_KEYS = frozenset(
    {
        "total_return",
        "max_drawdown",
        "sharpe_ratio",
        "expectancy",
        "win_rate",
        "avg_win",
        "avg_loss",
        "profit_factor",
        "trade_count",
    }
)


def _fail_closed(message: str) -> None:
    raise FailClosedError(message)


def _sequence_to_list(value: Any, field_name: str) -> list[Any]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        _fail_closed(f"invalid_{field_name}:type")
    return list(value)


def _mapping_value(item: Any, field_name: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(field_name)
    return getattr(item, field_name, None)


def _coerce_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        _fail_closed(f"invalid_{field_name}")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise FailClosedError(f"invalid_{field_name}") from exc
    if not math.isfinite(normalized):
        _fail_closed(f"invalid_{field_name}")
    return normalized


def _extract_trade_pnl(trade: Any) -> float:
    pnl_value = _mapping_value(trade, "net_pnl")
    if pnl_value is None:
        pnl_value = _mapping_value(trade, "pnl")
    if pnl_value is None:
        _fail_closed("invalid_trade:pnl")
    return _coerce_float(pnl_value, "trade_pnl")


def _extract_equity_points(equity_curve: Any) -> list[dict[str, float | int]]:
    raw_points = _sequence_to_list(equity_curve, "equity_curve")
    if not raw_points:
        _fail_closed("invalid_equity_curve:empty")

    normalized_points: list[dict[str, float | int]] = []
    previous_timestamp: int | None = None
    for point in raw_points:
        timestamp_value = _mapping_value(point, "timestamp")
        equity_value = _mapping_value(point, "equity")
        if timestamp_value is None:
            _fail_closed("invalid_equity_curve:timestamp")
        if isinstance(timestamp_value, bool):
            _fail_closed("invalid_equity_curve:timestamp")
        try:
            timestamp = int(timestamp_value)
        except (TypeError, ValueError) as exc:
            raise FailClosedError("invalid_equity_curve:timestamp") from exc
        if timestamp < 0:
            _fail_closed("invalid_equity_curve:timestamp")
        if previous_timestamp is not None and timestamp <= previous_timestamp:
            _fail_closed("invalid_equity_curve:non_monotonic_timestamp")
        equity = _coerce_float(equity_value, "equity")
        if equity <= 0.0:
            _fail_closed("invalid_equity_curve:equity")
        normalized_points.append({"timestamp": timestamp, "equity": equity})
        previous_timestamp = timestamp
    return normalized_points


class MetricsEngineV2:
    def compute_metrics(self, trades: Sequence[Any], equity_curve: Sequence[Any]) -> dict[str, float | int]:
        trade_items = _sequence_to_list(trades, "trades")
        if not trade_items:
            _fail_closed("invalid_trades:empty")

        pnl_values = [_extract_trade_pnl(trade) for trade in trade_items]
        equity_points = _extract_equity_points(equity_curve)

        winning_pnls = [pnl for pnl in pnl_values if pnl > 0.0]
        losing_pnls = [pnl for pnl in pnl_values if pnl < 0.0]

        trade_count = len(pnl_values)
        win_count = len(winning_pnls)
        loss_count = trade_count - win_count
        win_rate = win_count / trade_count
        loss_rate = loss_count / trade_count
        avg_win = sum(winning_pnls) / win_count if win_count > 0 else 0.0
        avg_loss = abs(sum(losing_pnls) / len(losing_pnls)) if losing_pnls else 0.0
        expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)

        total_profit = sum(winning_pnls)
        total_loss = abs(sum(losing_pnls))
        if total_loss > 0.0:
            profit_factor = total_profit / total_loss
        elif total_profit > 0.0:
            profit_factor = float("inf")
        else:
            profit_factor = 0.0

        initial_equity = float(equity_points[0]["equity"])
        final_equity = float(equity_points[-1]["equity"])
        total_return = (final_equity / initial_equity) - 1.0

        peak_equity = initial_equity
        max_drawdown = 0.0
        returns: list[float] = []
        for previous_point, current_point in zip(equity_points, equity_points[1:]):
            current_equity = float(current_point["equity"])
            if current_equity > peak_equity:
                peak_equity = current_equity
            drawdown = (peak_equity - current_equity) / peak_equity if peak_equity > 0.0 else 0.0
            if drawdown > max_drawdown:
                max_drawdown = drawdown

            previous_equity = float(previous_point["equity"])
            returns.append((current_equity / previous_equity) - 1.0)

        if len(returns) >= 2:
            mean_return = sum(returns) / len(returns)
            variance = sum((value - mean_return) ** 2 for value in returns) / len(returns)
            std_return = math.sqrt(variance)
            sharpe_ratio = mean_return / std_return if std_return > 0.0 else 0.0
        else:
            sharpe_ratio = 0.0

        return {
            "total_return": round(total_return, 6),
            "max_drawdown": round(max_drawdown, 6),
            "sharpe_ratio": round(sharpe_ratio, 6),
            "expectancy": round(expectancy, 6),
            "win_rate": round(win_rate, 6),
            "avg_win": round(avg_win, 6),
            "avg_loss": round(avg_loss, 6),
            "profit_factor": round(profit_factor, 6) if math.isfinite(profit_factor) else profit_factor,
            "trade_count": trade_count,
        }


def export_metrics_to_json(
    metrics: Mapping[str, Any],
    output_path: str | Path | None = None,
) -> Path:
    if not isinstance(metrics, Mapping):
        _fail_closed("invalid_metrics:type")
    missing_keys = sorted(key for key in _REQUIRED_METRIC_KEYS if key not in metrics)
    if missing_keys:
        _fail_closed(f"invalid_metrics:missing_keys:{','.join(missing_keys)}")

    validated_metrics: dict[str, Any] = {"trade_count": int(metrics["trade_count"])}
    for key in sorted(_REQUIRED_METRIC_KEYS - {"trade_count"}):
        value = metrics[key]
        if value == float("inf"):
            validated_metrics[key] = "inf"
            continue
        validated_metrics[key] = round(_coerce_float(value, key), 6)

    if validated_metrics["trade_count"] < 0:
        _fail_closed("invalid_metrics:trade_count")

    destination = (
        Path(output_path)
        if output_path is not None
        else Path(__file__).resolve().parents[3] / "outputs" / "backtest_metrics.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(validated_metrics, indent=2, sort_keys=True), encoding="utf-8")
    return destination


__all__ = ["MetricsEngineV2", "export_metrics_to_json"]
