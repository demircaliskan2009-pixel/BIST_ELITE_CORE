"""Intraday Backtest Engine — event-driven MTF backtest with realistic execution.

Processes bars chronologically, generates MTF contexts, detects signals via
IntradayEdgeScanner, executes with intraday realism (slippage, partial fills,
session timing), and tracks positions to stop/target exits.

Key constraints:
- NEXT-BAR EXECUTION: signal at bar N → fill at bar N+1 open
- NO LOOKAHEAD: all indicators use only completed bars
- Deterministic: no randomness in any path
- Fail-closed: insufficient data → no trade
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from bist_core.data.ideal_intraday_loader import (
    SymbolBundle,
)
from bist_core.decision.intraday_edges import (
    IntradayEdgeScanner,
    IntradaySignal,
)
from bist_core.decision.timeframe_sync import (
    TimeframeSynchronizer,
)
from bist_core.execution.intraday_execution import (
    execute_intraday_signal,
)
from bist_core.models.ohlcv import OHLCVBar

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_INITIAL_EQUITY: float = 100_000.0
_MAX_CONCURRENT_POSITIONS: int = 15
_MAX_POSITION_PCT: float = 0.10  # max 10% of equity per position
_SESSION_OPEN_SEC: int = 9 * 3600 + 55 * 60   # 09:55 TRT
_SESSION_CLOSE_SEC: int = 18 * 3600
_MAX_HOLD_DAYS: int = 999  # effectively unlimited (stop/target handle exit)
_TRAIL_BREAKEVEN_R: float = 999.0  # disabled — too aggressive for BIST noise
_TRAIL_START_R: float = 999.0  # disabled
_TRAIL_DISTANCE_R: float = 1.0  # trail distance = 1R behind high


# ---------------------------------------------------------------------------
# Position tracking
# ---------------------------------------------------------------------------

@dataclass
class IntradayPosition:
    """Tracks an open intraday position."""
    symbol: str
    edge: str
    direction: str
    entry_price: float
    fill_size: int
    stop_price: float
    target_price: float
    entry_timestamp: int
    slippage_bps: float
    total_cost_bps: float
    confidence: float = 0.0
    reason: str = ""
    source: str = "technical"
    event_boost: float = 0.0
    event_context: str = "none"
    event_reason: str = ""

    exit_price: float = 0.0
    exit_timestamp: int = 0
    pnl: float = 0.0
    r_multiple: float = 0.0
    exit_reason: str = ""
    is_closed: bool = False
    trailing_high: float = 0.0
    bars_held: int = 0
    entry_day_id: int = 0  # trading day id for max hold tracking

    def close(self, price: float, timestamp: int, reason: str) -> None:
        """Close position and compute P&L."""
        self.exit_price = price
        self.exit_timestamp = timestamp
        self.exit_reason = reason
        self.is_closed = True

        if self.direction == "LONG":
            raw_pnl = (price - self.entry_price) * self.fill_size
        else:
            raw_pnl = (self.entry_price - price) * self.fill_size

        # Deduct costs (round-trip)
        cost_frac = (self.slippage_bps + self.total_cost_bps) / 10_000.0
        cost = self.entry_price * self.fill_size * cost_frac
        self.pnl = round(raw_pnl - cost, 2)

        # R-multiple
        risk = abs(self.entry_price - self.stop_price) * self.fill_size
        if risk > 0:
            self.r_multiple = round(self.pnl / risk, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "edge": self.edge,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "fill_size": self.fill_size,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "entry_ts": self.entry_timestamp,
            "exit_price": self.exit_price,
            "exit_ts": self.exit_timestamp,
            "pnl": self.pnl,
            "r_multiple": self.r_multiple,
            "exit_reason": self.exit_reason,
            "confidence": self.confidence,
            "reason": self.reason,
            "source": self.source,
            "event_boost": self.event_boost,
            "event_context": self.event_context,
            "event_reason": self.event_reason,
        }


# ---------------------------------------------------------------------------
# Equity curve point
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class EquityPoint:
    timestamp: int
    equity: float
    drawdown: float
    open_positions: int
    bar_symbol: str


# ---------------------------------------------------------------------------
# Backtest results
# ---------------------------------------------------------------------------

@dataclass
class IntradayBacktestResult:
    """Complete intraday backtest result."""
    trades: list[dict[str, Any]] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    signals_generated: int = 0
    signals_executed: int = 0
    signals_rejected: int = 0
    per_edge_stats: dict[str, dict[str, Any]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Core backtest engine
# ---------------------------------------------------------------------------

class IntradayBacktestEngine:
    """Event-driven intraday backtest with MTF context and realistic execution.

    Usage:
        loader = IdealIntradayLoader()
        bundle = loader.load_symbol("AKBNK", ["G", "60", "05", "01"])
        engine = IntradayBacktestEngine(initial_equity=100_000)
        result = engine.run_symbol("AKBNK", bundle, start_ts=..., end_ts=...)
    """

    def __init__(
        self,
        initial_equity: float = _DEFAULT_INITIAL_EQUITY,
        max_positions: int = _MAX_CONCURRENT_POSITIONS,
        event_engine: object | None = None,
    ) -> None:
        self._initial_equity = initial_equity
        self._max_positions = max_positions
        self._event_engine = event_engine

    def run_symbol(
        self,
        symbol: str,
        bundle: SymbolBundle,
        start_ts: int | None = None,
        end_ts: int | None = None,
        edges_enabled: Sequence[str] | None = None,
    ) -> IntradayBacktestResult:
        """Run intraday backtest for a single symbol."""
        sync = TimeframeSynchronizer(
            symbol=symbol,
            bundle=bundle,
            base_tf="01",
            start_ts=start_ts,
            end_ts=end_ts,
        )

        scanner = IntradayEdgeScanner(event_engine=self._event_engine)
        result = IntradayBacktestResult()

        equity = self._initial_equity
        peak_equity = equity
        positions: list[IntradayPosition] = []
        pending_signal: IntradaySignal | None = None
        m1_buffer: list[OHLCVBar] = []
        prev_day_close: float | None = None

        # Build daily close lookup for prev_day_close tracking.
        # Daily bars are sorted chronologically.
        daily_bars = sorted(bundle.get("G", []), key=lambda b: b.timestamp)

        # Load events for this symbol if event engine is active
        if self._event_engine is not None:
            _load_start = start_ts or (daily_bars[0].timestamp if daily_bars else 0)
            _load_end = end_ts or (daily_bars[-1].timestamp if daily_bars else 0)
            if _load_start and _load_end:
                self._event_engine.load_events([symbol], _load_start, _load_end)

        # Initialize prev_day_close from the daily bar before the first
        # base-TF bar.  This ensures gap_continuation has a reference from
        # the very first session bar.
        if daily_bars and start_ts is not None:
            for db in reversed(daily_bars):
                # Daily bars have ts ~03:00 TRT; the one BEFORE start_ts
                # is yesterday's close (no lookahead).
                if db.timestamp < start_ts:
                    prev_day_close = float(db.close)
                    scanner.update_prev_close(symbol, prev_day_close)
                    break
        elif daily_bars:
            # No explicit start — use an early daily bar if available
            if len(daily_bars) > 1:
                prev_day_close = float(daily_bars[-2].close)
                scanner.update_prev_close(symbol, prev_day_close)

        for event in sync.iter_events():
            bar = event.bar
            ts = bar.timestamp

            # Track prev day close — fires when synchronizer detects a new
            # completed daily bar (with lookahead-safe visibility offset).
            if event.daily_completed:
                for db in reversed(daily_bars):
                    if db.timestamp < ts:
                        prev_day_close = float(db.close)
                        scanner.update_prev_close(symbol, prev_day_close)
                        break

            # 1. CHECK STOP/TARGET ON EXISTING POSITIONS
            closed_indices: list[int] = []
            for i, pos in enumerate(positions):
                if pos.is_closed:
                    continue

                price = float(bar.close)
                high = float(bar.high)
                low = float(bar.low)

                # Update tracking
                pos.bars_held += 1
                if pos.direction == "LONG":
                    if pos.trailing_high == 0.0:
                        pos.trailing_high = pos.entry_price
                    pos.trailing_high = max(pos.trailing_high, high)

                # Trailing stop logic (LONG only for BIST)
                if pos.direction == "LONG":
                    initial_risk = pos.entry_price - pos.stop_price
                    if initial_risk > 0:
                        profit_r = (pos.trailing_high - pos.entry_price) / initial_risk
                        if profit_r >= _TRAIL_START_R:
                            # Trail: stop at trailing_high - 1R
                            trail_stop = pos.trailing_high - initial_risk * _TRAIL_DISTANCE_R
                            pos.stop_price = max(pos.stop_price, trail_stop)
                        elif profit_r >= _TRAIL_BREAKEVEN_R:
                            # Move to breakeven
                            pos.stop_price = max(pos.stop_price, pos.entry_price)

                if pos.direction == "LONG":
                    # Gap-aware stop: if bar opens below stop (overnight gap),
                    # fill at bar open, not at stop price.
                    bar_open = float(bar.open)
                    if low <= pos.stop_price:
                        fill_at = min(pos.stop_price, bar_open) if bar_open < pos.stop_price else pos.stop_price
                        reason = "TRAILING_STOP" if pos.stop_price > pos.entry_price else "STOP"
                        pos.close(fill_at, ts, reason)
                        equity += pos.pnl
                        closed_indices.append(i)
                    # Target hit
                    elif high >= pos.target_price:
                        fill_at = max(pos.target_price, bar_open) if bar_open > pos.target_price else pos.target_price
                        pos.close(fill_at, ts, "TARGET")
                        equity += pos.pnl
                        closed_indices.append(i)

                # Max hold days: close at session end on the Nth day
                day_id = (ts + 3 * 3600) // 86400
                days_held = day_id - pos.entry_day_id
                tod = (ts + 3 * 3600) % 86400
                if days_held >= _MAX_HOLD_DAYS and tod >= _SESSION_CLOSE_SEC - 60 and not pos.is_closed:
                    pos.close(price, ts, "MAX_HOLD")
                    equity += pos.pnl
                    closed_indices.append(i)

            # Remove closed positions
            for idx in sorted(closed_indices, reverse=True):
                pos = positions.pop(idx)
                result.trades.append(pos.to_dict())

            # 2. EXECUTE PENDING SIGNAL (next-bar execution)
            if pending_signal is not None:
                open_count = len([p for p in positions if not p.is_closed])
                if open_count < self._max_positions:
                    # Also check position sizing vs equity
                    max_notional = equity * _MAX_POSITION_PCT
                    if pending_signal.entry_price > 0:
                        max_size = int(max_notional / pending_signal.entry_price)
                    else:
                        max_size = 0

                    if max_size > 0:
                        fill = execute_intraday_signal(
                            signal=pending_signal,
                            fill_bar=bar,
                            recent_bars=m1_buffer,
                        )

                        if not fill.rejected:
                            entry_day = (fill.timestamp + 3 * 3600) // 86400
                            pos = IntradayPosition(
                                symbol=fill.symbol,
                                edge=fill.edge,
                                direction=fill.direction,
                                entry_price=fill.fill_price,
                                fill_size=min(fill.fill_size, max_size),
                                stop_price=fill.stop_price,
                                target_price=fill.target_price,
                                entry_timestamp=fill.timestamp,
                                slippage_bps=fill.slippage_bps,
                                total_cost_bps=fill.total_cost_bps,
                                entry_day_id=entry_day,
                                confidence=pending_signal.confidence,
                                reason=pending_signal.reason,
                                source=pending_signal.source,
                                event_boost=pending_signal.event_boost,
                                event_context=getattr(pending_signal, "event_context", "none"),
                                event_reason=getattr(pending_signal, "event_reason", ""),
                            )
                            positions.append(pos)
                            result.signals_executed += 1
                        else:
                            result.signals_rejected += 1
                    else:
                        result.signals_rejected += 1
                else:
                    result.signals_rejected += 1
                pending_signal = None

            # 3. SCAN FOR NEW SIGNALS
            # m1_buffer contains PRIOR bars only (current bar not yet appended)
            # to avoid including current bar in lookback for breakout/sweep detection.
            signal = scanner.scan(event, m1_buffer)
            if signal is not None:
                # Filter by enabled edges
                if edges_enabled is None or signal.edge in edges_enabled:
                    pending_signal = signal
                    result.signals_generated += 1

            # 4. APPEND CURRENT BAR TO HISTORY (after signal scanning)
            m1_buffer.append(bar)
            if len(m1_buffer) > 200:
                m1_buffer = m1_buffer[-200:]

            # 5. UPDATE EQUITY CURVE
            # Mark-to-market open positions
            unrealized = 0.0
            for pos in positions:
                if not pos.is_closed:
                    if pos.direction == "LONG":
                        unrealized += (float(bar.close) - pos.entry_price) * pos.fill_size

            current_equity = equity + unrealized
            if current_equity > peak_equity:
                peak_equity = current_equity
            dd = (peak_equity - current_equity) / peak_equity if peak_equity > 0 else 0.0

            result.equity_curve.append({
                "timestamp": ts,
                "equity": round(current_equity, 2),
                "drawdown": round(dd, 6),
                "open_positions": len([p for p in positions if not p.is_closed]),
                "symbol": symbol,
            })

        # Force-close any remaining open positions at last bar
        if m1_buffer:
            last_bar = m1_buffer[-1]
            for pos in positions:
                if not pos.is_closed:
                    pos.close(float(last_bar.close), last_bar.timestamp, "BACKTEST_END")
                    equity += pos.pnl
                    result.trades.append(pos.to_dict())

        # Compute metrics
        result.metrics = _compute_metrics(
            result.trades, result.equity_curve, self._initial_equity
        )

        # Per-edge stats
        result.per_edge_stats = _compute_per_edge_stats(result.trades)

        return result


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _compute_metrics(
    trades: list[dict[str, Any]],
    equity_curve: list[dict[str, Any]],
    initial_equity: float,
) -> dict[str, Any]:
    """Compute backtest performance metrics."""
    closed = [t for t in trades if t.get("exit_reason", "")]

    if not closed:
        return {
            "total_return": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
            "total_trades": 0,
            "sharpe_ratio": 0.0,
            "avg_r_multiple": 0.0,
        }

    wins = [t for t in closed if t["pnl"] > 0]
    losses = [t for t in closed if t["pnl"] <= 0]
    total_win = sum(t["pnl"] for t in wins)
    total_loss = abs(sum(t["pnl"] for t in losses))

    win_rate = len(wins) / len(closed) if closed else 0.0
    if total_loss > 0:
        profit_factor = total_win / total_loss
    elif total_win > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    # Drawdown from equity curve
    max_dd = 0.0
    if equity_curve:
        max_dd = max(pt["drawdown"] for pt in equity_curve)

    # Return
    final_eq = equity_curve[-1]["equity"] if equity_curve else initial_equity
    total_return = (final_eq - initial_equity) / initial_equity if initial_equity > 0 else 0.0

    # Sharpe from equity curve
    equities = [pt["equity"] for pt in equity_curve]
    returns: list[float] = []
    for i in range(1, len(equities)):
        if equities[i - 1] > 0:
            returns.append((equities[i] - equities[i - 1]) / equities[i - 1])

    if len(returns) >= 2:
        mean_r = sum(returns) / len(returns)
        var_r = sum((r - mean_r) ** 2 for r in returns) / len(returns)
        std_r = math.sqrt(var_r) if var_r > 0 else 0.0
        sharpe = mean_r / std_r if std_r > 0 else 0.0
    else:
        sharpe = 0.0

    # R-multiples
    r_mults = [t["r_multiple"] for t in closed if t.get("r_multiple")]
    avg_r = sum(r_mults) / len(r_mults) if r_mults else 0.0

    return {
        "total_return": round(total_return, 6),
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else 999.0,
        "max_drawdown": round(max_dd, 6),
        "total_trades": len(closed),
        "sharpe_ratio": round(sharpe, 4),
        "avg_r_multiple": round(avg_r, 4),
    }


def _compute_per_edge_stats(trades: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Compute stats broken down by edge type."""
    by_edge: dict[str, list[dict[str, Any]]] = {}
    for t in trades:
        edge = t.get("edge", "unknown")
        by_edge.setdefault(edge, []).append(t)

    stats: dict[str, dict[str, Any]] = {}
    for edge, edge_trades in by_edge.items():
        wins = [t for t in edge_trades if t["pnl"] > 0]
        losses = [t for t in edge_trades if t["pnl"] <= 0]
        total_win = sum(t["pnl"] for t in wins)
        total_loss = abs(sum(t["pnl"] for t in losses))
        n = len(edge_trades)
        wr = len(wins) / n if n > 0 else 0.0
        pf = total_win / total_loss if total_loss > 0 else (999.0 if total_win > 0 else 0.0)
        avg_pnl = sum(t["pnl"] for t in edge_trades) / n if n > 0 else 0.0

        stats[edge] = {
            "trades": n,
            "win_rate": round(wr, 4),
            "profit_factor": round(pf, 4),
            "avg_pnl": round(avg_pnl, 2),
            "total_pnl": round(sum(t["pnl"] for t in edge_trades), 2),
        }

    return stats


# ---------------------------------------------------------------------------
# Walk-forward validation
# ---------------------------------------------------------------------------

def walk_forward_intraday(
    symbol: str,
    bundle: SymbolBundle,
    n_splits: int = 4,
    train_ratio: float = 0.7,
    initial_equity: float = _DEFAULT_INITIAL_EQUITY,
) -> dict[str, Any]:
    """Run walk-forward validation with N splits.

    Each split: train on first 70%, test on last 30%.
    Slides forward by 1/N of total data each split.
    """
    base_bars = sorted(bundle.get("01", []), key=lambda b: b.timestamp)
    if len(base_bars) < 1000:
        return {"error": "INSUFFICIENT_DATA", "splits": []}

    total = len(base_bars)
    split_size = total // n_splits
    results: list[dict[str, Any]] = []

    for i in range(n_splits):
        start_idx = i * (split_size // 2)
        end_idx = min(start_idx + split_size, total)
        if end_idx <= start_idx:
            continue

        train_end = start_idx + int((end_idx - start_idx) * train_ratio)
        test_start_ts = base_bars[train_end].timestamp
        test_end_ts = base_bars[min(end_idx - 1, total - 1)].timestamp

        engine = IntradayBacktestEngine(initial_equity=initial_equity)
        result = engine.run_symbol(
            symbol=symbol,
            bundle=bundle,
            start_ts=test_start_ts,
            end_ts=test_end_ts,
        )

        results.append({
            "split": i + 1,
            "test_bars": end_idx - train_end,
            "metrics": result.metrics,
            "per_edge": result.per_edge_stats,
        })

    # Summary
    profitable_splits = sum(
        1 for r in results
        if r["metrics"].get("total_return", 0) > 0
    )

    return {
        "splits": results,
        "profitable_splits": profitable_splits,
        "total_splits": len(results),
        "pass": profitable_splits >= (n_splits * 3 // 4),
    }


__all__ = [
    "IntradayBacktestEngine",
    "IntradayBacktestResult",
    "IntradayPosition",
    "walk_forward_intraday",
]
