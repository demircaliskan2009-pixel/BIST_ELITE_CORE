"""Edge-oriented features — deterministic, live/backtest compatible."""

from __future__ import annotations

from typing import Any

from bist_core.models.ohlcv import OHLCVBar, normalize_timestamp


class FeatureEngineV2:
    """Scalar features for edge bucketing (no numpy, no overfitting hooks)."""

    def returns(self, closes: list[float]) -> list[float]:
        return [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]

    def volatility(self, closes: list[float]) -> float:
        r = self.returns(closes)
        return sum(abs(x) for x in r) / len(r) if r else 0.0

    def trend(self, closes: list[float]) -> float:
        if not closes:
            return 0.0
        c0 = closes[0]
        if c0 <= 0:
            return 0.0
        return (closes[-1] - c0) / c0

    def breakout(self, closes: list[float]) -> int:
        if len(closes) < 2:
            return 0
        prior = closes[-10:-1]
        if not prior:
            return 0
        return int(closes[-1] > max(prior))

    def volume_ratio(self, volumes: list[float]) -> float:
        if len(volumes) < 5:
            return 0.0
        avg = sum(volumes[:-1]) / len(volumes[:-1])
        return volumes[-1] / avg if avg > 0 else 0.0

    def time_bucket(self, ts: int) -> int:
        hour = (ts // 3600) % 24
        return int(hour)

    def extract(self, bars: list[OHLCVBar]) -> dict[str, Any]:
        if not bars:
            return {
                "vol": 0.0,
                "trend": 0.0,
                "breakout": 0,
                "vol_ratio": 0.0,
                "hour": 0,
            }

        closes = [float(b.close) for b in bars]
        volumes = [float(b.volume) for b in bars]
        raw_ts = bars[-1].timestamp
        ts = raw_ts if isinstance(raw_ts, int) else normalize_timestamp(raw_ts)

        return {
            "vol": self.volatility(closes),
            "trend": self.trend(closes),
            "breakout": self.breakout(closes),
            "vol_ratio": self.volume_ratio(volumes),
            "hour": self.time_bucket(int(ts)),
        }


__all__ = ["FeatureEngineV2"]
