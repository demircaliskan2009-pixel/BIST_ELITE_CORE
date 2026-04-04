"""Strategy engine — converts OHLCVBar sequences into trading decisions.

Uses indicators from the feature layer (SMA, ATR) to detect trend
crossover signals and produce deterministic Decision objects with
entry/stop/target levels.  Pure stdlib, no network.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from bist_core.backtest.backtest_engine import OHLCVBar
from bist_core.features.indicator_library import atr as compute_atr, sma as compute_sma


@dataclass
class Decision:
    symbol: str
    entry: float
    stop: float
    target: float
    side: str
    confidence: float
    reasoning: str
    timestamp: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "entry": self.entry,
            "stop": self.stop,
            "target": self.target,
            "side": self.side,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "timestamp": self.timestamp,
        }


class StrategyEngine:
    """Trend-crossover strategy: SMA20/SMA50 with ATR-based stop/target."""

    def __init__(
        self,
        lookback: int = 50,
        risk_reward: float = 2.0,
    ) -> None:
        self._lookback = lookback
        self._risk_reward = risk_reward

    @property
    def lookback(self) -> int:
        return self._lookback

    @property
    def risk_reward(self) -> float:
        return self._risk_reward

    def compute_indicators(self, bars: Sequence[OHLCVBar]) -> Dict[str, float | None]:
        sma20_vals = compute_sma(bars, 20)
        sma50_vals = compute_sma(bars, 50)
        atr14_vals = compute_atr(bars, 14)

        sma20 = sma20_vals[-1] if sma20_vals and sma20_vals[-1] is not None else None
        sma50 = sma50_vals[-1] if sma50_vals and sma50_vals[-1] is not None else None
        atr_val = atr14_vals[-1] if atr14_vals and atr14_vals[-1] is not None else None

        return {
            "sma20": sma20,
            "sma50": sma50,
            "atr": atr_val,
        }

    def detect_signal(self, bars: Sequence[OHLCVBar]) -> str | None:
        if len(bars) < self._lookback + 1:
            return None

        sma20_vals = compute_sma(bars, 20)
        sma50_vals = compute_sma(bars, 50)

        curr_sma20 = sma20_vals[-1]
        curr_sma50 = sma50_vals[-1]
        prev_sma20 = sma20_vals[-2]
        prev_sma50 = sma50_vals[-2]

        if any(v is None for v in (curr_sma20, curr_sma50, prev_sma20, prev_sma50)):
            return None

        close = bars[-1].close

        if prev_sma20 <= prev_sma50 and curr_sma20 > curr_sma50 and close > curr_sma20:
            return "long"

        if prev_sma20 >= prev_sma50 and curr_sma20 < curr_sma50 and close < curr_sma20:
            return "short"

        return None

    def generate_decision(
        self,
        symbol: str,
        bars: Sequence[OHLCVBar],
    ) -> Decision | None:
        if len(bars) < self._lookback + 1:
            return None

        signal = self.detect_signal(bars)
        if signal is None:
            return None

        indicators = self.compute_indicators(bars)
        sma20 = indicators["sma20"]
        sma50 = indicators["sma50"]
        atr_val = indicators["atr"]

        if sma20 is None or sma50 is None or atr_val is None or atr_val <= 0:
            return None

        entry = bars[-1].close
        timestamp = bars[-1].timestamp

        if signal == "long":
            stop = round(entry - atr_val, 4)
            target = round(entry + atr_val * self._risk_reward, 4)
        else:
            stop = round(entry + atr_val, 4)
            target = round(entry - atr_val * self._risk_reward, 4)

        sma_diff = abs(sma20 - sma50)
        confidence = round(min(sma_diff / atr_val, 3.0), 4)

        trend = "yükseliş" if signal == "long" else "düşüş"
        reasoning = (
            f"{symbol} {trend} sinyali. "
            f"SMA20={sma20:.2f}, SMA50={sma50:.2f}, ATR={atr_val:.2f}. "
            f"Risk/ödül={self._risk_reward:.1f}x."
        )

        return Decision(
            symbol=symbol.upper().strip(),
            entry=round(entry, 4),
            stop=stop,
            target=target,
            side=signal,
            confidence=confidence,
            reasoning=reasoning,
            timestamp=timestamp,
        )

    def batch_generate(
        self,
        symbol_bars: Dict[str, Sequence[OHLCVBar]],
    ) -> List[Decision]:
        decisions: list[Decision] = []
        for symbol in sorted(symbol_bars.keys()):
            bars = symbol_bars[symbol]
            decision = self.generate_decision(symbol, bars)
            if decision is not None:
                decisions.append(decision)
        return decisions
