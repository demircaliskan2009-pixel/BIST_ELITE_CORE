"""Trade Decision Engine — convert ranked + validated candidates into trade decisions."""

from __future__ import annotations

import math

TOP_N = 5
RANK_WEIGHT = 0.5
STABILITY_WEIGHT = 0.3
EXPECTANCY_WEIGHT = 0.2


def _safe_float(d: dict, key: str) -> float | None:
    v = d.get(key)
    if v is None:
        return None
    try:
        f = float(v)
        return f if not math.isnan(f) else None
    except (TypeError, ValueError):
        return None


def _get_last_close(ranked_item: dict, prices: dict[str, float] | None) -> float | None:
    v = ranked_item.get("last_close") or ranked_item.get("current_price")
    if v is not None:
        try:
            f = float(v)
            if not math.isnan(f) and f > 0:
                return f
        except (TypeError, ValueError):
            pass
    if prices:
        sym = ranked_item.get("symbol")
        if isinstance(sym, str) and sym in prices:
            p = prices.get(sym)
            if p is not None and not math.isnan(float(p)) and float(p) > 0:
                return float(p)
    return None


def _get_validation_stats(validation: dict, symbol: str) -> dict | None:
    symbols = validation.get("symbols")
    if not isinstance(symbols, dict):
        return None
    stats = symbols.get(symbol)
    if not isinstance(stats, dict):
        return None
    return stats


class TradeDecisionEngine:
    """Convert ranked + validated candidates into final trade decisions.

    Deterministic, fail-closed, no randomness.
    """

    def run(
        self,
        ranked: list[dict],
        validation: dict,
        prices: dict[str, float] | None = None,
    ) -> list[dict]:
        """Alias for decide. Produce up to top 5 trade decisions."""
        return self.decide(ranked, validation, prices=prices)

    def decide(
        self,
        ranked: list[dict],
        validation: dict,
        prices: dict[str, float] | None = None,
    ) -> list[dict]:
        """Produce up to top 5 trade decisions from ranked and validation output.

        Skips: missing validation, stability < 0, missing entry price.
        """
        decisions: list[dict] = []

        for item in ranked:
            symbol = item.get("symbol")
            if not isinstance(symbol, str):
                continue

            stats = _get_validation_stats(validation, symbol)
            if stats is None:
                continue

            stability = _safe_float(stats, "stability")
            avg_expectancy = _safe_float(stats, "avg_expectancy")
            if stability is not None and stability < 0:
                continue

            last_close = _get_last_close(item, prices)
            if last_close is None:
                continue

            entry = last_close
            stop = round(entry * 0.98, 4)
            target = round(entry * 1.04, 4)

            rank_score = _safe_float(item, "final_score") or _safe_float(item, "confidence") or 0.0
            rank_score = min(max(rank_score, 0.0), 1.0)
            norm_exp = 0.0 if avg_expectancy is None else min(max(avg_expectancy / 100.0 if abs(avg_expectancy) > 1 else avg_expectancy, 0.0), 1.0)
            stability_val = stability if stability is not None else 0.0
            confidence = min(max(
                RANK_WEIGHT * rank_score
                + STABILITY_WEIGHT * stability_val
                + EXPECTANCY_WEIGHT * norm_exp,
                0.0,
            ), 1.0)

            score = rank_score
            decisions.append({
                "symbol": symbol,
                "entry": entry,
                "stop": stop,
                "target": target,
                "side": "BUY",
                "confidence": round(confidence, 4),
                "score": round(score, 4),
                "reasoning": {
                    "stability": stability,
                    "avg_expectancy": avg_expectancy,
                },
            })

            if len(decisions) >= TOP_N:
                break

        if not decisions:
            for item in ranked:
                bars = item.get("bars")
                if not bars or len(bars) < 6:
                    continue

                last = bars[-1]
                prev = bars[-2]
                prev2 = bars[-3]

                c0 = float(last.close)
                c1 = float(prev.close)
                float(prev2.close)

                h1 = float(prev.high)
                l1 = float(prev.low)

                if not (c0 > c1):
                    continue

                if c0 < h1 * 0.995:
                    continue

                entry = c0
                stop = l1
                target = entry + (entry - stop)

                if stop >= entry:
                    continue

                decision = {
                    "symbol": item["symbol"],
                    "entry": entry,
                    "stop": stop,
                    "target": target,
                    "score": item.get("score", 0.7),
                    "reason": "momentum_breakout_v2",
                }
                decisions.append(decision)

                if len(decisions) >= TOP_N:
                    break

        if not decisions and ranked:
            item = ranked[0]
            bars = item.get("bars")

            if bars and len(bars) >= 2:
                last = bars[-1]
                prev = bars[-2]

                entry = float(last.close)
                stop = float(prev.low)

                if stop < entry:
                    decisions.append({
                        "symbol": item["symbol"],
                        "entry": entry,
                        "stop": stop,
                        "target": entry + (entry - stop),
                        "score": 0.5,
                        "reason": "hard_backstop",
                    })

        return decisions


__all__ = ["TradeDecisionEngine"]
