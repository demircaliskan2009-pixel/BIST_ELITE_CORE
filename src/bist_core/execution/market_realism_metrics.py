"""Deterministic aggregates for paper fill quality (no RNG)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List


@dataclass
class MarketRealismMetrics:
    """Fill success, slippage distribution, missed trades, execution delay."""

    attempts: int = 0
    fills_ok: int = 0
    missed_trades: int = 0
    slippage_fractions: List[float] = field(default_factory=list)
    execution_delay_ms: List[float] = field(default_factory=list)

    def record_attempt(self) -> None:
        self.attempts += 1

    def record_fill(
        self,
        *,
        slippage_fraction: float,
        delay_ms: float,
    ) -> None:
        self.fills_ok += 1
        self.slippage_fractions.append(float(slippage_fraction))
        self.execution_delay_ms.append(float(delay_ms))

    def record_miss(self) -> None:
        self.missed_trades += 1

    def fill_success_rate(self) -> float:
        if self.attempts <= 0:
            return 0.0
        return self.fills_ok / float(self.attempts)

    def avg_slippage(self) -> float:
        if not self.slippage_fractions:
            return 0.0
        return sum(self.slippage_fractions) / len(self.slippage_fractions)

    def avg_execution_delay_ms(self) -> float:
        if not self.execution_delay_ms:
            return 0.0
        return sum(self.execution_delay_ms) / len(self.execution_delay_ms)

    def summary(self) -> dict[str, Any]:
        return {
            "fill_attempts": int(self.attempts),
            "fills_ok": int(self.fills_ok),
            "fill_success_rate": round(self.fill_success_rate(), 6),
            "missed_trades": int(self.missed_trades),
            "avg_slippage_fraction": round(self.avg_slippage(), 8),
            "slippage_samples": len(self.slippage_fractions),
            "avg_execution_delay_ms": round(self.avg_execution_delay_ms(), 4),
        }


__all__ = ["MarketRealismMetrics"]
