"""Scanner — selects candidate symbols based on OHLCV data."""

from __future__ import annotations

from typing import Callable, Protocol

from bist_core.data.quality import InvalidDataError, basic_checks
from bist_core.models.ohlcv import OHLCVBar

from .adaptive import AdaptiveScanEngine
from .schemas import build_candidate


def _compute_momentum(bars: list[OHLCVBar]) -> float:
    """momentum = last_close - first_close"""
    return bars[-1].close - bars[0].close


def _compute_volatility(bars: list[OHLCVBar]) -> float:
    """volatility = average(high - low)"""
    if not bars:
        return 0.0
    total = sum(b.high - b.low for b in bars)
    return total / len(bars)


class RulesEngineProtocol(Protocol):
    """Protocol for rules engine."""

    def apply(self, symbol: str, bars: list[OHLCVBar]) -> dict:
        """Return {pass, score_modifier, reasons}."""
        ...


class Scanner:
    """Selects candidate symbols based on OHLCV data.

    Deterministic, no randomness, fail-closed on invalid data.
    """

    def __init__(
        self,
        data_loader: Callable[[str], list[OHLCVBar]],
        symbols: list[str],
        rules_engine: RulesEngineProtocol | AdaptiveScanEngine,
    ) -> None:
        self._data_loader = data_loader
        self._symbols = list(symbols)
        self._rules_engine = rules_engine

    def scan(self) -> list[dict]:
        """Scan symbols and return list of candidates.

        For each symbol:
        1. Load OHLCV data via data_loader(symbol)
        2. Validate (basic_checks); if invalid → skip
        3. Compute momentum and volatility
        4. Apply adaptive rules; if fail → skip
        5. Build candidate with full schema

        Returns empty list if no valid candidates.
        """
        candidates: list[dict] = []
        for symbol in sorted(self._symbols):
            try:
                bars = self._data_loader(symbol)
            except Exception:
                continue
            if not bars:
                continue
            try:
                basic_checks(bars)
            except InvalidDataError:
                continue
            momentum = _compute_momentum(bars)
            volatility = _compute_volatility(bars)
            result = self._rules_engine.apply(symbol, bars)
            if not result.get("pass", False):
                continue
            score_modifier = result.get("score_modifier", 1.0)
            reasons = result.get("reasons", {})
            candidates.append(build_candidate(
                symbol=symbol,
                momentum=momentum,
                volatility=volatility,
                passed_filters=True,
                score_modifier=score_modifier,
                reasons=reasons,
            ))
        return candidates
