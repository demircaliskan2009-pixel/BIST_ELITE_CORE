"""Backtesting and walk-forward validation engine — PRD §11/§12.

Replays OHLCV bar data through the advisor decision pipeline and
PaperExecutionEngine / OrderStateMachineController.  Computes rich
performance metrics, equity curves, regime summaries, and supports
deterministic walk-forward rolling windows.  Pure stdlib, no network.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from bist_core.execution.order_state_machine import (
    OrderStateMachineController,
    RiskLimits,
    reset_order_counter,
)
from bist_core.execution.paper_engine import (
    PaperExecutionEngine,
    PaperTrade,
    SlippageModel,
)
from bist_core.models.ohlcv import OHLCVBar
from bist_core.analytics.trade_analytics import compute_expectancy

try:
    from bist_core.decision.decision_engine_v2 import DecisionEngineV2
except Exception:  # pragma: no cover
    DecisionEngineV2 = None  # type: ignore[misc, assignment]


class _DecisionEngineDefault:
    """Sentinel: use DecisionEngineV2 when available; explicit ``None`` disables it."""


_DECISION_ENGINE_DEFAULT = _DecisionEngineDefault()


# ---------------------------------------------------------------------------
# Cost model
# ---------------------------------------------------------------------------

@dataclass
class CostModel:
    slippage: SlippageModel = field(default_factory=lambda: SlippageModel(base_slippage_bps=5.0))
    commission_bps: float = 10.0
    exchange_fee_bps: float = 5.0

    @property
    def total_fee_bps(self) -> float:
        return self.commission_bps + self.exchange_fee_bps


# ---------------------------------------------------------------------------
# Decision function protocol
# ---------------------------------------------------------------------------

DecisionFunction = Callable[
    [str, List[OHLCVBar], int],
    Optional[Dict[str, Any]],
]


def _default_decision_fn(
    symbol: str,
    bars: List[OHLCVBar],
    bar_index: int,
) -> Optional[Dict[str, Any]]:
    """Minimal momentum decision: buy when close > open for latest bar."""
    if bar_index < 1 or not bars:
        return None
    bar = bars[bar_index]
    prev = bars[bar_index - 1]
    if bar.close > prev.close:
        entry = bar.close
        stop = round(entry * 0.95, 4)
        target = round(entry * 1.10, 4)
        return {
            "symbol": symbol,
            "entry": entry,
            "stop": stop,
            "target": target,
            "position_size": 10,
        }
    return None


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------

def _compute_metrics(
    trades: List[PaperTrade],
    equity_curve: List[Dict[str, Any]],
    initial_equity: float,
) -> Dict[str, Any]:
    closed = [t for t in trades if t.status == "CLOSED"]

    if not closed:
        equities = [pt["equity"] for pt in equity_curve]
        peak = initial_equity
        max_dd = 0.0
        for e in equities:
            if e > peak:
                peak = e
            dd = (peak - e) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        final_eq = equities[-1] if equities else initial_equity
        total_return = round((final_eq - initial_equity) / initial_equity, 6) if initial_equity > 0 else 0.0
        return {
            "total_return": total_return,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "max_drawdown": round(max_dd, 6),
            "avg_R_multiple": 0.0,
            "sharpe_ratio": 0.0,
            "total_trades": len(trades),
            "open_trades": len(trades) - len(closed),
            "closed_trades": 0,
        }

    wins = [t for t in closed if t.pnl > 0]
    losses = [t for t in closed if t.pnl <= 0]
    total_win = sum(t.pnl for t in wins)
    total_loss = abs(sum(t.pnl for t in losses))

    win_rate = round(len(wins) / len(closed), 4)
    if total_loss > 0:
        profit_factor = round(total_win / total_loss, 4)
    elif total_win > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0
    expectancy = round(sum(t.pnl for t in closed) / len(closed), 4)

    r_multiples = [t.r_multiple for t in closed if t.r_multiple is not None]
    avg_r = round(sum(r_multiples) / len(r_multiples), 4) if r_multiples else 0.0

    equities = [pt["equity"] for pt in equity_curve]
    peak = initial_equity
    max_dd = 0.0
    for e in equities:
        if e > peak:
            peak = e
        dd = (peak - e) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

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
        "total_return": total_return,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "max_drawdown": round(max_dd, 6),
        "avg_R_multiple": avg_r,
        "sharpe_ratio": sharpe,
        "total_trades": len(trades),
        "open_trades": len(trades) - len(closed),
        "closed_trades": len(closed),
    }


# ---------------------------------------------------------------------------
# Regime summary
# ---------------------------------------------------------------------------

def _regime_summary(
    equity_curve: List[Dict[str, Any]],
    trades: List[PaperTrade],
) -> Dict[str, Any]:
    if not equity_curve:
        return {"regime": "unknown", "bars_processed": 0, "trend": "flat"}

    equities = [pt["equity"] for pt in equity_curve]
    start = equities[0] if equities else 0.0
    end = equities[-1] if equities else 0.0
    if start > 0:
        total_pct = ((end - start) / start) * 100.0
    else:
        total_pct = 0.0

    if total_pct > 5.0:
        regime = "bullish"
        trend = "up"
    elif total_pct < -5.0:
        regime = "bearish"
        trend = "down"
    else:
        regime = "sideways"
        trend = "flat"

    return {
        "regime": regime,
        "trend": trend,
        "equity_change_pct": round(total_pct, 4),
        "bars_processed": len(equity_curve),
        "total_trades": len(trades),
    }


# ---------------------------------------------------------------------------
# Backtest engine
# ---------------------------------------------------------------------------

class BacktestEngine:
    """Replays OHLCV bars through a decision function and paper execution engine."""

    def __init__(
        self,
        cost_model: CostModel | None = None,
        risk_limits: RiskLimits | None = None,
        initial_equity: float = 100_000.0,
        decision_fn: DecisionFunction | None = None,
        decision_engine: Any | None = _DECISION_ENGINE_DEFAULT,
    ) -> None:
        self._cost = cost_model or CostModel()
        self._risk = risk_limits or RiskLimits()
        self._initial_equity = initial_equity
        self._decision_fn = decision_fn or _default_decision_fn
        if decision_engine is not _DECISION_ENGINE_DEFAULT:
            self.decision_engine = decision_engine
        elif DecisionEngineV2 is not None:
            self.decision_engine = DecisionEngineV2()
        else:
            self.decision_engine = None

    def _run_dict_rolling_decision(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deterministic backtest: real OHLCV bars, rolling window, DecisionEngineV2 signals.
        """
        trades: list[dict[str, Any]] = []
        bars_processed: int = 0
        open_pos: dict[str, list[dict[str, Any]]] = {}
        last_exit_index_by_sym: dict[str, int] = {}
        min_hold = 3
        max_hold = 20
        equity = 1.0
        equity_curve: list[float] = []
        signal_counter: dict[str, int] = {}
        hold_counter: dict[str, int] = {}

        if self.decision_engine is None:
            return {
                "trades": [],
                "metrics": {
                    "total_trades": 0,
                    "expectancy": 0.0,
                    "stable": False,
                    "equity_final": 1.0,
                },
                "equity_curve": [],
                "regime_summary": {"bars_processed": 0, "regime": "unknown"},
                "signal_stats": {
                    "entry_signals": {},
                    "hold_signals": {},
                },
            }

        for sym, bars_list in sorted(data.items(), key=lambda kv: kv[0]):
            bars = list(bars_list)
            if not isinstance(bars, list) or len(bars) < 21:
                continue

            for i in range(20, len(bars)):
                window = bars[i - 20 : i]

                if len(window) < 20:
                    continue

                last_close = getattr(window[-1], "close", None)
                next_close = getattr(bars[i], "close", None)

                if last_close is None or next_close is None:
                    continue
                if not isinstance(last_close, (int, float)):
                    continue
                if not isinstance(next_close, (int, float)):
                    continue
                if float(last_close) <= 0 or float(next_close) <= 0:
                    continue

                try:
                    decision = self.decision_engine.evaluate_symbol(
                        {
                            "current_price": float(last_close),
                            "bars": list(window),
                            "capital": float(self._initial_equity),
                            "portfolio_exposure": 0.0,
                        }
                    )
                except Exception:
                    decision = {"action": "hold", "score": 0.0, "no_trade": True}

                if not isinstance(decision, dict):
                    decision = {"action": "hold", "score": 0.0, "no_trade": True}

                debug_action = decision.get("action") if isinstance(decision, dict) else None

                if debug_action == "enter":
                    signal_counter[sym] = signal_counter.get(sym, 0) + 1

                if debug_action == "hold":
                    hold_counter[sym] = hold_counter.get(sym, 0) + 1

                action = decision.get("action", "hold")
                if not isinstance(action, str):
                    action = "hold"

                if action == "hold":
                    if decision.get("no_trade") is True:
                        pass
                    else:
                        action = "enter"

                # Cooldown: no new entry on same bar as last exit (1 bar gap) (last_exit_index_by_sym).
                if action in ("enter", "long"):
                    positions = open_pos.get(sym, [])
                    last_exit_index = last_exit_index_by_sym.get(sym)
                    allow_entry = True
                    if last_exit_index is not None:
                        if i - last_exit_index < 1:
                            allow_entry = False

                    if allow_entry and len(positions) < 5:
                        positions.append(
                            {
                                "entry_price": float(last_close),
                                "entry_index": i,
                                "peak_price": float(last_close),
                                "size": 1,
                            }
                        )
                        open_pos[sym] = positions

                # TEMP DEBUG: total open legs across symbols — remove after verification
                count_positions = sum(len(v) for v in open_pos.values())
                assert count_positions >= 0

                if sym in open_pos:
                    new_positions: list[dict[str, Any]] = []
                    for pos in open_pos[sym]:
                        entry_price = float(pos["entry_price"])
                        entry_index = int(pos["entry_index"])
                        held = i - entry_index

                        pos_action = action
                        if held >= 7:
                            if abs((float(last_close) - entry_price) / entry_price) < 0.0008:
                                pos_action = "exit"

                        pos["peak_price"] = max(
                            float(pos.get("peak_price", last_close)),
                            float(last_close),
                        )

                        peak_px = float(pos["peak_price"])
                        profit_from_peak = (
                            (float(last_close) - peak_px) / peak_px if peak_px > 0 else 0.0
                        )

                        should_exit = False
                        if profit_from_peak < -0.003:
                            should_exit = True

                        mtm = (float(last_close) - entry_price) / entry_price
                        peak = float(pos["peak_price"])
                        current = float(last_close)
                        drawdown = (current - peak) / peak if peak > 0 else 0.0
                        (current - entry_price) / entry_price

                        trail_threshold = -0.005
                        try:
                            feat_vol_exit = float(
                                decision.get("debug", {}).get("features", {}).get("volatility", 0.0)
                            )
                            if feat_vol_exit > 0.005:
                                trail_threshold = -0.003
                        except Exception:
                            pass
                        if drawdown < trail_threshold:
                            should_exit = True

                        if mtm > 0.02:
                            should_exit = True

                        if pos_action == "exit" and held >= min_hold:
                            should_exit = True

                        if held >= max_hold:
                            strong_trend = False
                            try:
                                trend_dbg = float(decision.get("debug", {}).get("trend", 0.0))
                                if trend_dbg > 0.003:
                                    strong_trend = True
                            except Exception:
                                pass
                            if not strong_trend:
                                should_exit = True

                        if mtm > 0.01 and held >= 3:
                            should_exit = True
                        if mtm < -0.004:
                            should_exit = True

                        if should_exit and (-0.002 < mtm < 0):
                            if pos.get("skip_exit_bar"):
                                pos["skip_exit_bar"] = False
                            else:
                                pos["skip_exit_bar"] = True
                                should_exit = False

                        if should_exit:
                            raw_pnl = (float(next_close) - entry_price) / entry_price
                            pos_size = int(pos.get("size", 1))
                            pnl = float(raw_pnl) * float(pos_size)

                            if abs(pnl) < 0.0005:
                                pass
                            elif abs(pnl) > 0.0005:
                                trades.append(
                                    {
                                        "symbol": str(sym),
                                        "pnl": float(pnl),
                                        "size": pos_size,
                                    }
                                )
                                equity *= 1.0 + float(pnl)

                            last_exit_index_by_sym[sym] = i
                        else:
                            new_positions.append(pos)

                    if new_positions:
                        open_pos[sym] = new_positions
                    else:
                        del open_pos[sym]

                bars_processed += 1
                equity_curve.append(float(equity))

        valid_trades = [t for t in trades if abs(float(t.get("pnl", 0.0))) > 0.0005]

        mid = len(valid_trades) // 2
        first_half = valid_trades[:mid]
        second_half = valid_trades[mid:]

        exp_1 = compute_expectancy(first_half)
        exp_2 = compute_expectancy(second_half)
        stable = abs(exp_1 - exp_2) < 0.02

        expectancy = compute_expectancy(valid_trades)

        if len(valid_trades) > 10:
            drawdowns = [min(0.0, float(t.get("pnl", 0.0))) for t in valid_trades]
            if sum(drawdowns) < -0.05:
                stable = False

        return {
            "trades": valid_trades,
            "metrics": {
                "total_trades": len(valid_trades),
                "expectancy": float(expectancy),
                "stable": bool(stable),
                "equity_final": float(equity),
            },
            "equity_curve": equity_curve,
            "regime_summary": {
                "bars_processed": bars_processed,
            },
            "signal_stats": {
                "entry_signals": signal_counter,
                "hold_signals": hold_counter,
            },
        }

    def _run_bar_sequence(
        self,
        bars: Sequence[OHLCVBar],
    ) -> Dict[str, Any]:
        """Realistic backtest: next-bar execution, dynamic slippage, partial fills.

        Signal at bar T → queued → filled at bar T+1 open price with:
        - Dynamic slippage (vol + size impact + opening spread)
        - Partial fills (volume-based fill ratio)
        - Order rejection (low liquidity)
        - Tick-rounded prices
        - Missing bar simulation (data realism)
        """
        from bist_core.data.data_realism import (
            opening_spread_penalty_bps,
            simulate_missing_bars,
        )
        from bist_core.execution.execution_realism import (
            _daily_vol,
            _avg_daily_volume,
            apply_slippage,
            compute_fill_ratio,
            compute_slippage_bps,
            compute_total_cost_bps,
            round_decision_prices,
        )

        reset_order_counter()

        # Fail-closed: reject invalid OHLCV bars before processing
        _invalid_count = 0
        valid_bars: list[OHLCVBar] = []
        for b in bars:
            if (
                b.open <= 0
                or b.high <= 0
                or b.low <= 0
                or b.close <= 0
                or b.volume < 0
                or b.high < b.low
                or b.high < max(b.open, b.close)
                or b.low > min(b.open, b.close)
            ):
                _invalid_count += 1
                continue
            valid_bars.append(b)
        bars = valid_bars

        if not bars:
            return {
                "metrics": _compute_metrics([], [], self._initial_equity),
                "equity_curve": [],
                "trades": [],
                "regime_summary": _regime_summary([], []),
                "rejected_bars": _invalid_count,
            }

        # Data realism: simulate missing bars (1.5% dropout)
        _original_bar_count = len(bars)
        bars = simulate_missing_bars(bars)
        _bars_dropped = _original_bar_count - len(bars)

        # Zero slippage in PaperEngine — dynamic slippage is applied
        # externally via apply_slippage() before order submission.
        engine = PaperExecutionEngine(
            slippage=SlippageModel(base_slippage_bps=0.0),
            fee_bps=compute_total_cost_bps(),
        )
        controller = OrderStateMachineController(
            engine=engine,
            risk_limits=self._risk,
            capital=self._initial_equity,
        )

        bars_by_symbol: dict[str, list[OHLCVBar]] = {}
        bar_index_by_symbol: dict[str, int] = {}
        equity = self._initial_equity
        equity_curve: list[dict[str, Any]] = []

        sorted_bars = sorted(bars, key=lambda b: (b.timestamp, b.symbol))

        # Portfolio feedback: detect trade closes and notify decision_fn
        _has_notify = hasattr(self._decision_fn, "notify_trade_closed")
        _has_equity = hasattr(self._decision_fn, "notify_equity")
        _has_fill_failed = hasattr(self._decision_fn, "notify_fill_failed")
        _notified_closed_ids: set[int] = set()  # track by id() to handle out-of-order closes

        # Next-bar execution queue: decisions made at bar T, filled at bar T+1
        # Key: symbol → list of pending decisions from previous bar
        pending_decisions: dict[str, list[Dict[str, Any]]] = {}
        prev_close_by_sym: dict[str, float] = {}  # for opening spread calc
        _rejected_count = 0
        _partial_count = 0

        for bar in sorted_bars:
            sym = bar.symbol.upper().strip()
            if sym not in bars_by_symbol:
                bars_by_symbol[sym] = []
                bar_index_by_symbol[sym] = -1

            bars_by_symbol[sym].append(bar)
            bar_index_by_symbol[sym] += 1
            idx = bar_index_by_symbol[sym]

            # ---- FILL PENDING ORDERS from previous bar (next-bar execution) ----
            if sym in pending_decisions and pending_decisions[sym]:
                closes = [float(b.close) for b in bars_by_symbol[sym]]
                volumes = [float(b.volume) for b in bars_by_symbol[sym]]
                vol = _daily_vol(closes)
                adv = _avg_daily_volume(volumes)

                for pending in pending_decisions[sym]:
                    # Fill price = current bar open (next bar after signal)
                    fill_price = bar.open

                    # Compute dynamic slippage
                    slip_bps = compute_slippage_bps(
                        daily_vol=vol,
                        order_size=pending["position_size"],
                        avg_volume=adv,
                        price=fill_price,
                    )

                    # Add opening spread penalty (BIST auction effect)
                    pc = prev_close_by_sym.get(sym, fill_price)
                    slip_bps += opening_spread_penalty_bps(bar, pc)

                    # Check fill ratio (partial fills / rejection)
                    fill_ratio = compute_fill_ratio(
                        order_size=pending["position_size"],
                        avg_volume=adv,
                        price=fill_price,
                    )

                    if fill_ratio <= 0:
                        _rejected_count += 1
                        if _has_fill_failed:
                            self._decision_fn.notify_fill_failed(pending.get("symbol", sym))
                        continue  # order rejected — insufficient liquidity

                    # Apply partial fill
                    filled_size = max(1, int(pending["position_size"] * fill_ratio))
                    if filled_size < pending["position_size"]:
                        _partial_count += 1
                    pending["position_size"] = filled_size

                    # Apply slippage to fill price
                    slipped_price = apply_slippage(fill_price, slip_bps, "buy")

                    # Override engine slippage model: use our computed price directly
                    order = controller.create_order_from_decision(pending)
                    if not order.sm.is_terminal:
                        controller.submit_order(order, slipped_price, bar.timestamp)
                    elif _has_fill_failed:
                        self._decision_fn.notify_fill_failed(pending.get("symbol", sym))

                pending_decisions[sym] = []

            # ---- GENERATE SIGNAL for current bar (queued for next bar) ----
            decision = self._decision_fn(sym, bars_by_symbol[sym], idx)
            if decision is not None:
                # Tick-round all prices
                round_decision_prices(decision)
                # Queue for next-bar execution
                if sym not in pending_decisions:
                    pending_decisions[sym] = []
                pending_decisions[sym].append(decision)

            # ---- STOP/TARGET CHECKS on open trades ----
            prices = {sym: bar.close}
            controller.tick(prices, bar.timestamp)

            # Detect newly closed trades and notify portfolio wrapper
            # NOTE: closed_trades is ordered by opening time, NOT closure time.
            # Trades can close out of order, so we track by identity (id())
            # instead of a positional counter to avoid missing notifications.
            if _has_notify:
                for ct in engine.journal.closed_trades:
                    ct_id = id(ct)
                    if ct_id not in _notified_closed_ids:
                        _notified_closed_ids.add(ct_id)
                        self._decision_fn.notify_trade_closed(ct.symbol, ct.pnl)

            realized_pnl = sum(
                t.pnl for t in engine.journal.closed_trades
            )
            open_pnl = sum(
                (bar.close - t.entry_price) * t.position_size
                for t in engine.journal.open_trades
                if t.symbol == sym
            )
            equity = self._initial_equity + realized_pnl + open_pnl

            # Notify portfolio wrapper of current equity
            if _has_equity:
                self._decision_fn.notify_equity(equity)

            # Track previous close for opening spread calculation
            prev_close_by_sym[sym] = bar.close

            equity_curve.append({
                "timestamp": bar.timestamp,
                "symbol": sym,
                "equity": round(equity, 4),
                "close": bar.close,
            })

        # Release tracker slots for unfilled pending decisions (end-of-data)
        if _has_fill_failed:
            for sym_key, pending_list in pending_decisions.items():
                for pending in pending_list:
                    self._decision_fn.notify_fill_failed(pending.get("symbol", sym_key))

        all_trades = engine.journal.all_trades
        metrics = _compute_metrics(all_trades, equity_curve, self._initial_equity)
        regime = _regime_summary(equity_curve, all_trades)

        # Execution realism stats
        metrics["rejected_orders"] = _rejected_count
        metrics["partial_fills"] = _partial_count
        metrics["bars_dropped"] = _bars_dropped
        metrics["rejected_bars"] = _invalid_count

        return {
            "metrics": metrics,
            "equity_curve": equity_curve,
            "trades": [t.to_dict() for t in all_trades],
            "regime_summary": regime,
        }

    def run(
        self,
        data: Any,
    ) -> Dict[str, Any]:
        """
        - ``dict[str, list[OHLCVBar]]``: rolling-window loop + :class:`DecisionEngineV2` (no lookahead beyond window end).
        - ``Sequence[OHLCVBar]``: legacy paper-engine replay (decision_fn + execution journal).
        """
        if isinstance(data, dict) and all(
            isinstance(v, (list, tuple)) for v in data.values()
        ):
            return self._run_dict_rolling_decision(data)

        if isinstance(data, (list, tuple)) or (
            hasattr(data, "__iter__") and not isinstance(data, (str, bytes, dict))
        ):
            try:
                seq = list(data)
            except Exception:
                return {
                    "trades": [],
                    "metrics": {"total_trades": 0},
                    "equity_curve": [],
                    "regime_summary": {"bars_processed": 0, "regime": "unknown"},
                }
            if not seq:
                return {
                    "metrics": _compute_metrics([], [], self._initial_equity),
                    "equity_curve": [],
                    "trades": [],
                    "regime_summary": _regime_summary([], []),
                }
            if isinstance(seq[0], OHLCVBar):
                return self._run_bar_sequence(seq)

        return {
            "trades": [],
            "metrics": {"total_trades": 0},
            "equity_curve": [],
            "regime_summary": {"bars_processed": 0, "regime": "unknown"},
        }


# ---------------------------------------------------------------------------
# Walk-forward engine
# ---------------------------------------------------------------------------

def _split_windows(
    timestamps: list[str],
    train_window: int,
    test_window: int,
) -> list[dict[str, Any]]:
    if not timestamps or train_window < 1 or test_window < 1:
        return []
    unique = sorted(set(timestamps))
    total = len(unique)
    windows: list[dict[str, Any]] = []
    start = 0
    while start + train_window + test_window <= total:
        train_start = unique[start]
        train_end = unique[start + train_window - 1]
        test_start = unique[start + train_window]
        test_end = unique[min(start + train_window + test_window - 1, total - 1)]
        windows.append({
            "train_start": train_start,
            "train_end": train_end,
            "test_start": test_start,
            "test_end": test_end,
            "train_size": train_window,
            "test_size": test_window,
        })
        start += test_window
    return windows


class WalkForwardEngine:
    """Rolling walk-forward validation: train_window + test_window splits."""

    def __init__(
        self,
        train_window: int = 90,
        test_window: int = 30,
        cost_model: CostModel | None = None,
        risk_limits: RiskLimits | None = None,
        initial_equity: float = 100_000.0,
        decision_fn: DecisionFunction | None = None,
    ) -> None:
        self._train_window = train_window
        self._test_window = test_window
        self._cost = cost_model or CostModel()
        self._risk = risk_limits or RiskLimits()
        self._initial_equity = initial_equity
        self._decision_fn = decision_fn or _default_decision_fn

    def run(
        self,
        bars: Sequence[OHLCVBar],
    ) -> Dict[str, Any]:
        all_bars = sorted(bars, key=lambda b: (b.timestamp, b.symbol))
        timestamps = [b.timestamp for b in all_bars]
        windows = _split_windows(timestamps, self._train_window, self._test_window)

        if not windows:
            return {
                "windows": [],
                "aggregate_metrics": _compute_metrics([], [], self._initial_equity),
                "num_windows": 0,
            }

        window_results: list[dict[str, Any]] = []
        all_test_trades: list[PaperTrade] = []
        combined_equity: list[dict[str, Any]] = []

        for win in windows:
            test_bars = [
                b for b in all_bars
                if win["test_start"] <= b.timestamp <= win["test_end"]
            ]
            if not test_bars:
                window_results.append({
                    "window": win,
                    "metrics": _compute_metrics([], [], self._initial_equity),
                    "trade_count": 0,
                })
                continue

            bt = BacktestEngine(
                cost_model=self._cost,
                risk_limits=self._risk,
                initial_equity=self._initial_equity,
                decision_fn=self._decision_fn,
                decision_engine=None,
            )
            result = bt.run(test_bars)
            window_results.append({
                "window": win,
                "metrics": result["metrics"],
                "trade_count": result["metrics"]["total_trades"],
            })
            combined_equity.extend(result["equity_curve"])
            for t_dict in result["trades"]:
                trade = PaperTrade(
                    trade_id=t_dict["trade_id"],
                    symbol=t_dict["symbol"],
                    entry_price=t_dict["entry_price"],
                    stop_price=t_dict["stop_price"],
                    target_price=t_dict["target_price"],
                    position_size=t_dict["position_size"],
                    entry_time=t_dict["entry_time"],
                    exit_time=t_dict.get("exit_time"),
                    status=t_dict["status"],
                    pnl=t_dict["pnl"],
                    fees=t_dict["fees"],
                    slippage=t_dict["slippage"],
                )
                all_test_trades.append(trade)

        aggregate = _compute_metrics(all_test_trades, combined_equity, self._initial_equity)

        return {
            "windows": window_results,
            "aggregate_metrics": aggregate,
            "num_windows": len(window_results),
        }
