"""Strategy validation engine — PRD §11.

Evaluates backtest / walk-forward / paper trading results against
acceptance gates.  Computes aggregate and per-regime metrics, applies
fail-closed validation rules, and returns a structured verdict.
Pure stdlib, deterministic, no network.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Sequence

# ---------------------------------------------------------------------------
# Validation thresholds
# ---------------------------------------------------------------------------

@dataclass
class ValidationThresholds:
    min_expectancy: float = 0.0
    min_profit_factor: float = 1.2
    max_drawdown_pct: float = 20.0
    min_win_rate: float | None = None
    min_sharpe: float | None = None
    min_avg_r: float | None = None


_DEFAULT_THRESHOLDS = ValidationThresholds()


# ---------------------------------------------------------------------------
# Metric computation helpers
# ---------------------------------------------------------------------------

def compute_metrics_from_trades(
    trades: Sequence[Dict[str, Any]],
    equity_curve: Sequence[Dict[str, Any]] | None = None,
    initial_equity: float = 100_000.0,
) -> Dict[str, Any]:
    closed = [t for t in trades if t.get("status") == "CLOSED"]

    equities = [pt["equity"] for pt in (equity_curve or []) if "equity" in pt]

    peak = initial_equity
    max_dd = 0.0
    for e in equities:
        if e > peak:
            peak = e
        dd = (peak - e) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    if not closed:
        final_eq = equities[-1] if equities else initial_equity
        total_return = round((final_eq - initial_equity) / initial_equity, 6) if initial_equity > 0 else 0.0
        return {
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "win_rate": 0.0,
            "max_drawdown": round(max_dd * 100.0, 4),
            "sharpe_ratio": 0.0,
            "avg_R_multiple": 0.0,
            "total_return": total_return,
            "total_trades": len(trades),
            "closed_trades": 0,
        }

    pnls = [float(t.get("pnl", 0)) for t in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    total_win = sum(wins)
    total_loss = abs(sum(losses))

    win_rate = round(len(wins) / len(closed), 4)
    if total_loss > 0:
        profit_factor = round(total_win / total_loss, 4)
    elif total_win > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    expectancy = round(sum(pnls) / len(closed), 4)

    r_multiples: list[float] = []
    for t in closed:
        r = t.get("r_multiple")
        if r is not None:
            try:
                r_multiples.append(float(r))
            except (TypeError, ValueError):
                pass
    avg_r = round(sum(r_multiples) / len(r_multiples), 4) if r_multiples else 0.0

    returns: list[float] = []
    for i in range(1, len(equities)):
        prev = equities[i - 1]
        if prev > 0:
            returns.append((equities[i] - prev) / prev)
    if len(returns) >= 2:
        mean_ret = sum(returns) / len(returns)
        var = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
        std = math.sqrt(var) if var > 0 else 0.0
        sharpe = round(mean_ret / std, 4) if std > 0 else 0.0
    else:
        sharpe = 0.0

    final_eq = equities[-1] if equities else initial_equity
    total_return = round((final_eq - initial_equity) / initial_equity, 6) if initial_equity > 0 else 0.0

    return {
        "expectancy": expectancy,
        "profit_factor": profit_factor,
        "win_rate": win_rate,
        "max_drawdown": round(max_dd * 100.0, 4),
        "sharpe_ratio": sharpe,
        "avg_R_multiple": avg_r,
        "total_return": total_return,
        "total_trades": len(trades),
        "closed_trades": len(closed),
    }


# ---------------------------------------------------------------------------
# Regime segmentation
# ---------------------------------------------------------------------------

def _classify_regime(equity_change_pct: float) -> str:
    if equity_change_pct > 5.0:
        return "bullish"
    if equity_change_pct < -5.0:
        return "bearish"
    return "sideways"


def segment_by_regime(
    equity_curve: Sequence[Dict[str, Any]],
    trades: Sequence[Dict[str, Any]],
    window_size: int = 20,
) -> Dict[str, Dict[str, Any]]:
    """Segment equity curve into regime windows and compute per-regime metrics."""
    if not equity_curve or window_size < 1:
        return {
            "bullish": _empty_regime_metrics(),
            "bearish": _empty_regime_metrics(),
            "sideways": _empty_regime_metrics(),
        }

    equities = [pt["equity"] for pt in equity_curve if "equity" in pt]
    timestamps = [pt.get("timestamp", "") for pt in equity_curve]

    regime_buckets: dict[str, list[dict[str, Any]]] = {
        "bullish": [],
        "bearish": [],
        "sideways": [],
    }
    regime_equity: dict[str, list[dict[str, Any]]] = {
        "bullish": [],
        "bearish": [],
        "sideways": [],
    }

    i = 0
    while i + window_size <= len(equities):
        start_eq = equities[i]
        end_eq = equities[i + window_size - 1]
        if start_eq > 0:
            change_pct = ((end_eq - start_eq) / start_eq) * 100.0
        else:
            change_pct = 0.0
        regime = _classify_regime(change_pct)

        window_start_ts = timestamps[i] if i < len(timestamps) else ""
        window_end_ts = timestamps[i + window_size - 1] if (i + window_size - 1) < len(timestamps) else ""

        for pt in equity_curve[i : i + window_size]:
            regime_equity[regime].append(pt)

        for t in trades:
            entry_time = str(t.get("entry_time", ""))
            if entry_time and window_start_ts <= entry_time <= window_end_ts:
                regime_buckets[regime].append(t)

        i += window_size

    result: dict[str, dict[str, Any]] = {}
    for regime_name in ("bullish", "bearish", "sideways"):
        bucket_trades = regime_buckets[regime_name]
        bucket_equity = regime_equity[regime_name]
        if bucket_trades or bucket_equity:
            result[regime_name] = compute_metrics_from_trades(
                bucket_trades,
                bucket_equity,
                equities[0] if equities else 100_000.0,
            )
            result[regime_name]["window_count"] = max(1, len(bucket_equity) // window_size)
        else:
            result[regime_name] = _empty_regime_metrics()

    return result


def _empty_regime_metrics() -> Dict[str, Any]:
    return {
        "expectancy": 0.0,
        "profit_factor": 0.0,
        "win_rate": 0.0,
        "max_drawdown": 0.0,
        "sharpe_ratio": 0.0,
        "avg_R_multiple": 0.0,
        "total_return": 0.0,
        "total_trades": 0,
        "closed_trades": 0,
        "window_count": 0,
    }


# ---------------------------------------------------------------------------
# Validation engine
# ---------------------------------------------------------------------------

class ValidationEngine:
    """Evaluate backtest results against acceptance gates."""

    def __init__(
        self,
        thresholds: ValidationThresholds | None = None,
    ) -> None:
        self._thresholds = thresholds or _DEFAULT_THRESHOLDS

    def validate(
        self,
        backtest_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        trades = list(backtest_result.get("trades") or [])
        equity_curve = list(backtest_result.get("equity_curve") or [])
        initial_equity = float(
            backtest_result.get("initial_equity")
            or (equity_curve[0]["equity"] if equity_curve and "equity" in equity_curve[0] else 100_000.0)
        )

        metrics = compute_metrics_from_trades(trades, equity_curve, initial_equity)
        regime_metrics = segment_by_regime(equity_curve, trades)

        warnings: list[str] = []
        valid = True

        if metrics["expectancy"] <= self._thresholds.min_expectancy:
            warnings.append(
                f"expectancy {metrics['expectancy']} <= min {self._thresholds.min_expectancy}"
            )
            valid = False

        pf = metrics["profit_factor"]
        if pf != float("inf") and pf < self._thresholds.min_profit_factor:
            warnings.append(
                f"profit_factor {pf} < min {self._thresholds.min_profit_factor}"
            )
            valid = False

        if metrics["max_drawdown"] > self._thresholds.max_drawdown_pct:
            warnings.append(
                f"max_drawdown {metrics['max_drawdown']}% > max {self._thresholds.max_drawdown_pct}%"
            )
            valid = False

        if self._thresholds.min_win_rate is not None:
            if metrics["win_rate"] < self._thresholds.min_win_rate:
                warnings.append(
                    f"win_rate {metrics['win_rate']} < min {self._thresholds.min_win_rate}"
                )
                valid = False

        if self._thresholds.min_sharpe is not None:
            if metrics["sharpe_ratio"] < self._thresholds.min_sharpe:
                warnings.append(
                    f"sharpe_ratio {metrics['sharpe_ratio']} < min {self._thresholds.min_sharpe}"
                )
                valid = False

        if self._thresholds.min_avg_r is not None:
            if metrics["avg_R_multiple"] < self._thresholds.min_avg_r:
                warnings.append(
                    f"avg_R_multiple {metrics['avg_R_multiple']} < min {self._thresholds.min_avg_r}"
                )
                valid = False

        if metrics["closed_trades"] == 0:
            warnings.append("no_closed_trades")
            valid = False

        return {
            "valid": valid,
            "metrics": metrics,
            "regime_metrics": regime_metrics,
            "warnings": warnings,
        }
