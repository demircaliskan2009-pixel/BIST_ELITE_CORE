"""Realistic fill + slippage simulation for paper/live path — deterministic (no RNG)."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _deterministic_unit(symbol: str, action: str, price: float, last_price: float) -> float:
    """Stable pseudo-random in [0, 1) from inputs (reproducible across runs)."""
    msg = f"{symbol}|{action}|{float(price):.12g}|{float(last_price):.12g}".encode("utf-8")
    h = hashlib.sha256(msg).digest()
    return int.from_bytes(h[:8], "big") / float(2**64)


class ExecutionEngine:
    """Probabilistic-style fills without randomness; fail-closed when not filled."""

    def __init__(self) -> None:
        self.positions: dict[str, dict[str, Any]] = {}

    def try_fill(
        self,
        symbol: str,
        action: str,
        price: float,
        last_price: float,
        confidence: float,
    ) -> dict[str, Any]:
        if action not in ("enter", "exit"):
            return {"filled": False}

        diff = abs(float(price) - float(last_price)) / max(float(last_price), 1e-9)

        if diff < 0.001:
            fill_prob = 0.9
        elif diff < 0.005:
            fill_prob = 0.6
        else:
            fill_prob = 0.2

        conf = min(1.0, max(0.0, float(confidence)))
        fill_prob *= 0.5 + conf
        fill_prob = min(1.0, max(0.0, fill_prob))

        r = _deterministic_unit(str(symbol), str(action), float(price), float(last_price))
        filled = r < fill_prob

        print(
            json.dumps(
                {
                    "execution_validation": {
                        "symbol": symbol,
                        "diff": diff,
                        "fill_prob": fill_prob,
                        "rand": r,
                        "filled": filled,
                    }
                },
                ensure_ascii=False,
            )
        )

        if not filled:
            print(
                json.dumps(
                    {
                        "execution": {
                            "symbol": symbol,
                            "filled": False,
                            "reason": "prob_miss",
                            "rand": r,
                            "threshold": fill_prob,
                        }
                    },
                    ensure_ascii=False,
                )
            )
            return {"filled": False}

        slip = float(last_price) * 0.0005

        fill_price = (
            float(last_price) + slip
            if action == "enter"
            else float(last_price) - slip
        )

        sym_u = str(symbol).strip().upper()
        self.positions[sym_u] = {
            "fill_price": fill_price,
            "slippage": slip,
            "action": action,
        }

        print(
            json.dumps(
                {
                    "execution": {
                        "symbol": symbol,
                        "filled": True,
                        "fill_price": fill_price,
                        "slippage": slip,
                        "confidence": confidence,
                    }
                },
                ensure_ascii=False,
            )
        )

        return {
            "filled": True,
            "fill_price": fill_price,
            "slippage": slip,
        }


__all__ = ["ExecutionEngine"]
