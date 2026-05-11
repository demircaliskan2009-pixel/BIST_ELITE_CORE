from __future__ import annotations

import math
from typing import Any

from bist_core.brain.scoring_engine import score_symbol
from bist_core.execution.engine import ExecutionEngine, OrderState
from bist_core.features.feature_engine import RegistryFeatureEngine
from bist_core.models.ohlcv import OHLCVBar
from bist_core.risk.portfolio_state import PortfolioState

SCORE_FEATURES = ['atr_14', 'ema_20', 'momentum_20', 'rsi_14', 'sma_20', 'sma_50']
MIN_TRADES_REQUIRED = 5
MAX_DRAWDOWN_LIMIT = 0.30


def compute_metrics(trades: list[dict[str, Any]], initial_capital: float) -> dict[str, Any]:
    """Compute performance metrics from trade list. Fail-closed on empty."""
    if not trades:
        return {"total_return": 0.0, "win_rate": 0.0, "expectancy": 0.0,
                "max_drawdown": 0.0, "sharpe": 0.0, "profit_factor": 0.0,
                "trades": 0, "valid": False, "reason": "no_trades"}

    pnls = [float(t.get("net_pnl", 0)) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    total = len(pnls)
    win_rate = len(wins) / total if total > 0 else 0.0
    expectancy = sum(pnls) / total if total > 0 else 0.0

    cumulative = initial_capital
    peak = initial_capital
    max_dd = 0.0
    equity = []
    for p in pnls:
        cumulative += p
        equity.append(cumulative)
        if cumulative > peak:
            peak = cumulative
        dd = (peak - cumulative) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    total_return = (cumulative - initial_capital) / initial_capital if initial_capital > 0 else 0.0

    returns = []
    prev = initial_capital
    for e in equity:
        r = (e - prev) / prev if prev > 0 else 0.0
        returns.append(r)
        prev = e
    if len(returns) > 1:
        mean_r = sum(returns) / len(returns)
        variance = sum((r - mean_r) ** 2 for r in returns) / len(returns)
        std_r = math.sqrt(variance) if variance > 0 else 0.0
        sharpe = (mean_r / std_r) * math.sqrt(252) if std_r > 0 else 0.0
    else:
        sharpe = 0.0

    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    valid = (
        total >= MIN_TRADES_REQUIRED
        and expectancy > 0
        and max_dd < MAX_DRAWDOWN_LIMIT
    )
    reason = "ok" if valid else (
        "insufficient_trades" if total < MIN_TRADES_REQUIRED else
        "negative_expectancy" if expectancy <= 0 else
        "drawdown_too_high"
    )

    return {
        "total_return": round(total_return, 6),
        "win_rate": round(win_rate, 6),
        "expectancy": round(expectancy, 4),
        "max_drawdown": round(max_dd, 6),
        "sharpe": round(sharpe, 4),
        "profit_factor": round(profit_factor, 4),
        "trades": total,
        "valid": valid,
        "reason": reason,
    }


def run_backtest(
    symbol: str,
    bars: list[OHLCVBar],
    initial_capital: float = 100_000.0,
    warmup_bars: int = 50,
) -> dict[str, Any]:
    """Run cost-aware backtest on single symbol using ExecutionEngine + PortfolioState.
    Deterministic. No randomness. Fail-closed on invalid input.
    """
    if not bars or len(bars) < warmup_bars + 2:
        return {"valid": False, "reason": "insufficient_bars", "trades": 0}
    if initial_capital <= 0:
        return {"valid": False, "reason": "invalid_capital", "trades": 0}

    fe = RegistryFeatureEngine()
    ps = PortfolioState(capital=initial_capital)
    eng = ExecutionEngine()
    trade_log: list[dict[str, Any]] = []

    for i in range(warmup_bars, len(bars)):
        window = bars[:i + 1]
        current_bar = bars[i]
        current_price = float(current_bar.close)

        # Update open positions
        for sym in list(eng.open_positions().keys()):
            closed = eng.update(sym, current_price)
            if closed and closed.state == OrderState.CLOSED:
                ps.close_position(sym, closed.net_pnl)
                trade_log.append({
                    "symbol": sym,
                    "net_pnl": closed.net_pnl,
                    "exit_price": closed.exit_price,
                    "bar_index": i,
                })
                ps.record_trade(trade_log[-1])

        # Skip if position already open
        if symbol in eng.open_positions():
            continue

        # Score
        try:
            feats = fe.compute_features(window, SCORE_FEATURES)
        except Exception:
            continue

        result = score_symbol(symbol, feats, current_price)
        if result is None or result["score"] < 0.25:
            continue

        # Size and submit
        atr_vals = feats.get("atr_14", [])
        atr = float(atr_vals[-1]) if atr_vals and atr_vals[-1] else current_price * 0.02
        stop = round(current_price - max(atr, current_price * 0.01), 4)
        target = round(current_price + (current_price - stop) * 2, 4)
        if stop >= current_price:
            continue

        can, _ = ps.can_trade()
        if not can:
            continue

        size, size_reason = ps.size_trade(current_price, stop)
        if size <= 0:
            continue

        order = eng.submit(symbol, current_price, stop, target, size)
        if order.state == OrderState.FILLED:
            ps.open_position(symbol, order.fill_price, order.size, stop, target)

    # Force close any remaining
    for sym in list(eng.open_positions().keys()):
        if bars:
            closed = eng.force_close(sym, float(bars[-1].close))
            if closed:
                ps.close_position(sym, closed.net_pnl)
                trade_log.append({"symbol": sym, "net_pnl": closed.net_pnl,
                                   "exit_price": closed.exit_price, "bar_index": len(bars)-1})

    return compute_metrics(trade_log, initial_capital)


def run_walk_forward(
    symbol: str,
    bars: list[OHLCVBar],
    train_size: int = 200,
    test_size: int = 50,
    step_size: int = 50,
    initial_capital: float = 100_000.0,
) -> dict[str, Any]:
    """Walk-forward validation. No leakage. Multiple segments."""
    if len(bars) < train_size + test_size:
        return {"valid": False, "reason": "insufficient_bars_for_wf", "segments": 0}

    segments = []
    start = 0
    while start + train_size + test_size <= len(bars):
        bars[start + train_size: start + train_size + test_size]
        result = run_backtest(symbol, bars[:start + train_size + test_size],
                              initial_capital=initial_capital,
                              warmup_bars=start + train_size)
        segments.append(result)
        start += step_size

    if not segments:
        return {"valid": False, "reason": "no_segments", "segments": 0}

    avg_expectancy = sum(s.get("expectancy", 0) for s in segments) / len(segments)
    avg_drawdown = sum(s.get("max_drawdown", 0) for s in segments) / len(segments)
    total_trades = sum(s.get("trades", 0) for s in segments)
    valid = avg_expectancy > 0 and avg_drawdown < MAX_DRAWDOWN_LIMIT

    return {
        "segments": len(segments),
        "avg_expectancy": round(avg_expectancy, 4),
        "avg_drawdown": round(avg_drawdown, 6),
        "total_trades": total_trades,
        "valid": valid,
        "segment_results": segments,
    }
