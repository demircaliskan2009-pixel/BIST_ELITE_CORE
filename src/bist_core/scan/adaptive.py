"""Adaptive rule engine — filters and score modifiers for scan candidates."""

from __future__ import annotations

from abc import ABC, abstractmethod

from bist_core.models.ohlcv import OHLCVBar


def _avg_volume(bars: list[OHLCVBar]) -> float:
    if not bars:
        return 0.0
    return sum(b.volume for b in bars) / len(bars)


def _avg_volatility(bars: list[OHLCVBar]) -> float:
    if not bars:
        return 0.0
    return sum(b.high - b.low for b in bars) / len(bars)


class AdaptiveRule(ABC):
    """Base class for adaptive rules."""

    @abstractmethod
    def evaluate(self, bars: list[OHLCVBar]) -> tuple[bool, dict]:
        """Evaluate rule. Returns (passed, reasons_dict)."""
        pass


class LiquidityRule(AdaptiveRule):
    """Pass if avg volume > threshold."""

    def __init__(self, threshold: float = 0.0) -> None:
        self.threshold = threshold

    def evaluate(self, bars: list[OHLCVBar]) -> tuple[bool, dict]:
        avg = _avg_volume(bars)
        passed = avg > self.threshold
        return passed, {"liquidity": {"avg_volume": avg, "threshold": self.threshold, "passed": passed}}


class VolatilityRule(AdaptiveRule):
    """Pass if avg(high - low) > threshold."""

    def __init__(self, threshold: float = 0.0) -> None:
        self.threshold = threshold

    def evaluate(self, bars: list[OHLCVBar]) -> tuple[bool, dict]:
        avg = _avg_volatility(bars)
        passed = avg > self.threshold
        return passed, {"volatility": {"avg": avg, "threshold": self.threshold, "passed": passed}}


class BasicSanityRule(AdaptiveRule):
    """Pass if bars length > minimum."""

    def __init__(self, minimum: int = 1) -> None:
        self.minimum = minimum

    def evaluate(self, bars: list[OHLCVBar]) -> tuple[bool, dict]:
        n = len(bars)
        passed = n > self.minimum
        return passed, {"sanity": {"bar_count": n, "minimum": self.minimum, "passed": passed}}


class AdaptiveScanEngine:
    """Applies adaptive rules and returns pass/fail with score modifier and reasons."""

    def __init__(self, rules: list[AdaptiveRule] | None = None) -> None:
        self._rules = list(rules) if rules else []

    def apply(self, symbol: str, bars: list[OHLCVBar]) -> dict:
        """Apply all rules. Return pass, score_modifier, reasons."""
        reasons: dict = {}
        score_modifier = 1.0
        all_passed = True
        for rule in self._rules:
            passed, rule_reasons = rule.evaluate(bars)
            reasons.update(rule_reasons)
            if not passed:
                all_passed = False
                score_modifier *= 0.0
        return {
            "pass": all_passed,
            "score_modifier": score_modifier,
            "reasons": reasons,
        }


__all__ = [
    "AdaptiveRule",
    "AdaptiveScanEngine",
    "BasicSanityRule",
    "LiquidityRule",
    "VolatilityRule",
]
