"""Backtest engine — bar walk with DecisionEngineV2 (parity with paper trader actions)."""

from __future__ import annotations

from typing import Any, Optional

from bist_core.models.ohlcv import OHLCVBar

from bist_core.decision.decision_engine_v2 import DecisionEngineV2
from bist_core.execution.execution_model import ExecutionModel

from .metrics import compute_metrics


MIN_BARS = 3
DEFAULT_EXECUTION_MODEL = ExecutionModel(slippage_bps=5.0, spread_bps=10.0, commission_bps=2.0)
INITIAL_CAPITAL = 100_000.0


class BacktestEngine:
    """Runs time-series backtest: DecisionEngineV2 on bars[:i+1] at each bar (no lookahead).

    One active position per symbol; enter / hold / exit aligned with live paper_trader semantics.
    Closed trades record fractional return in ``pnl``: (exit - entry) / entry.
    """

    def __init__(
        self,
        *,
        threshold: float = 1.0,
        weights: dict | None = None,
        initial_capital: float = INITIAL_CAPITAL,
        execution_model: ExecutionModel | None = None,
        edges: Optional[dict[tuple[Any, ...], dict[str, Any]]] = None,
        edges_by_tf: Optional[dict[str, dict[tuple[Any, ...], dict[str, Any]]]] = None,
    ) -> None:
        self._threshold = float(threshold)
        self._weights = weights or {}
        self._initial_capital = float(initial_capital)
        self._exec_model = execution_model or DEFAULT_EXECUTION_MODEL
        self.decision_engine = DecisionEngineV2(edges=edges, edges_by_tf=edges_by_tf)

    def run(self, symbol_data: dict[str, list[OHLCVBar]]) -> dict:
        """Walk each symbol bar-by-bar; collect closed exits as trades."""
        trades: list[dict] = []

        for symbol, bars in sorted(symbol_data.items(), key=lambda kv: kv[0]):
            if not isinstance(bars, list) or len(bars) < 1:
                continue

            position: dict | None = None

            for i in range(len(bars)):
                try:
                    bar = bars[i]
                    price = getattr(bar, "close", None)
                    if not isinstance(price, (int, float)) or price <= 0:
                        continue

                    pos_ex = 0.0
                    if position is not None:
                        ep = float(position.get("entry_price", 0.0))
                        if self._initial_capital > 0 and ep > 0:
                            pos_ex = min(0.99, ep / self._initial_capital)

                    context = {
                        "symbol": symbol,
                        "current_price": float(price),
                        "bars": bars[: i + 1],
                        "capital": float(self._initial_capital),
                        "portfolio_exposure": pos_ex,
                    }

                    decision = None
                    try:
                        decision = self.decision_engine.evaluate_symbol(context)
                    except Exception:
                        decision = None

                    if not isinstance(decision, dict):
                        continue

                    action = decision.get("action")

                    if action not in ("enter", "hold", "exit"):
                        continue

                    # --- EXECUTION RULES (PARITY WITH PAPER TRADER) ---

                    if action == "enter":
                        if position is not None:
                            continue

                        position = {
                            "entry_price": float(price),
                            "entry_index": i,
                        }

                    elif action == "exit":
                        if position is None:
                            continue

                        entry_price = position.get("entry_price", price)
                        entry_index = position.get("entry_index")

                        pnl = (
                            (float(price) - float(entry_price)) / float(entry_price)
                            if isinstance(entry_price, (int, float)) and entry_price > 0
                            else 0.0
                        )

                        trades.append(
                            {
                                "symbol": symbol,
                                "action": "exit",
                                "entry": float(entry_price),
                                "exit": float(price),
                                "pnl": float(pnl),
                                "decision_bar": entry_index,
                            }
                        )

                        position = None

                    elif action == "hold":
                        continue

                except Exception:
                    continue

            # --- FORCE CLOSE ---
            if position is not None:
                try:
                    last_price = getattr(bars[-1], "close", None)

                    if isinstance(last_price, (int, float)) and last_price > 0:
                        entry_price = position.get("entry_price", last_price)

                        pnl = (
                            (float(last_price) - float(entry_price)) / float(entry_price)
                            if isinstance(entry_price, (int, float)) and entry_price > 0
                            else 0.0
                        )

                        trades.append(
                            {
                                "symbol": symbol,
                                "action": "exit",
                                "entry": float(entry_price),
                                "exit": float(last_price),
                                "pnl": float(pnl),
                                "decision_bar": position.get("entry_index"),
                            }
                        )
                except Exception:
                    pass

        metrics = compute_metrics(trades)
        return {"trades": trades, "metrics": metrics, "equity": self._initial_capital}


__all__ = ["BacktestEngine"]
