"""Production-grade ranking by DecisionEngineV2 scores — deterministic, no randomness."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from bist_core.decision.decision_engine_v2 import DecisionEngineV2, run_portfolio_v2_once


class ScoreRanker:
    """Rank symbols using ``DecisionEngineV2.evaluate_symbol`` scores.

    - Sort key: ``(-score, symbol)`` — higher score first, then alphabetical symbol (tie-break).
    - Output rows include ``rank`` (1-based within the returned list), ``score``, ``action``,
      ``reason``, ``risk``, and full ``decision`` dict from the engine.
    - Invalid or non-dict contexts are skipped (fail-closed for that symbol).
    """

    def __init__(self, engine: Optional[DecisionEngineV2] = None) -> None:
        self._engine = engine if engine is not None else DecisionEngineV2()

    def rank(
        self,
        symbol_contexts: Mapping[str, Dict[str, Any]],
        *,
        top_n: Optional[int] = None,
        portfolio_cycle_context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Evaluate each symbol and return sorted ranking rows.

        ``symbol_contexts``: mapping ``symbol -> context`` passed to ``evaluate_symbol``.

        ``top_n``: if set, return only the first *n* rows after sorting (ranks are 1..n).

        ``portfolio_cycle_context``: optional shared dict; after all symbols are evaluated,
        ``run_portfolio_v2_once`` is called once (see ``decision_engine_v2``).
        """
        if portfolio_cycle_context is not None:
            portfolio_cycle_context.pop("_portfolio_v2_ran", None)

        if not symbol_contexts:
            return []

        rows: List[Dict[str, Any]] = []

        for symbol in sorted(symbol_contexts.keys()):
            ctx = symbol_contexts.get(symbol)
            if not isinstance(ctx, dict):
                continue

            try:
                decision = self._engine.evaluate_symbol(ctx)
            except Exception:
                continue

            if not isinstance(decision, dict):
                continue

            raw_sc = decision.get("score")
            if isinstance(raw_sc, (int, float)):
                sc = float(raw_sc)
            else:
                sc = 0.0

            rows.append(
                {
                    "symbol": str(symbol),
                    "score": sc,
                    "action": decision.get("action"),
                    "reason": decision.get("reason"),
                    "risk": decision.get("risk") if isinstance(decision.get("risk"), dict) else {},
                    "decision": decision,
                }
            )

        if portfolio_cycle_context is not None:
            trades = portfolio_cycle_context.get("portfolio_v2_trades")
            if isinstance(trades, list):
                for t in trades:
                    if isinstance(t, dict):
                        t.pop("_v2_scaled", None)
            run_portfolio_v2_once(portfolio_cycle_context)

        rows.sort(key=lambda r: (-r["score"], r["symbol"]))

        if isinstance(top_n, int) and top_n > 0:
            rows = rows[:top_n]

        out: List[Dict[str, Any]] = []
        for i, r in enumerate(rows, start=1):
            entry = dict(r)
            entry["rank"] = i
            out.append(entry)

        return out


__all__ = ["ScoreRanker"]
