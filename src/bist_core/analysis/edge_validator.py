"""Compare decision-engine outputs on iDeal vs Matriks bar windows (diagnostic)."""

from __future__ import annotations

from typing import Any


class EdgeValidator:
    """Safe, deterministic dual evaluation — never raises."""

    def compare(
        self,
        symbol: str,
        ideal_bars: list[Any],
        matriks_bars: list[Any],
        decision_engine: Any,
    ) -> dict[str, Any]:
        res: dict[str, Any] = {
            "symbol": str(symbol),
            "ideal_decision": None,
            "matriks_decision": None,
        }

        if ideal_bars:
            try:
                last = ideal_bars[-1]
                px = float(getattr(last, "close", 0.0))
                if px > 0.0:
                    res["ideal_decision"] = decision_engine.evaluate_symbol(
                        {
                            "symbol": str(symbol),
                            "bars": ideal_bars,
                            "current_price": px,
                            "capital": 100_000,
                            "portfolio_exposure": 0.0,
                        }
                    )
            except Exception:
                pass

        if matriks_bars:
            try:
                last_m = matriks_bars[-1]
                px_m = float(getattr(last_m, "close", 0.0))
                if px_m > 0.0:
                    res["matriks_decision"] = decision_engine.evaluate_symbol(
                        {
                            "symbol": str(symbol),
                            "bars": matriks_bars,
                            "current_price": px_m,
                            "capital": 100_000,
                            "portfolio_exposure": 0.0,
                        }
                    )
            except Exception:
                pass

        return res


__all__ = ["EdgeValidator"]
