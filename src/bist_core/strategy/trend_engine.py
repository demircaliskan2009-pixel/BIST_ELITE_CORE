"""Deterministic trend classifier for debug logging only."""

from __future__ import annotations


class TrendEngine:
    def detect(self, bars):
        closes = [b.close for b in bars[-50:]]

        if len(closes) < 50:
            return "UNKNOWN"

        sma20 = sum(closes[-20:]) / 20
        sma50 = sum(closes) / 50

        momentum = (closes[-1] - closes[-10]) / closes[-10]

        if sma20 > sma50 and momentum > 0.02:
            return "TRENDING_UP"

        if sma20 < sma50 and momentum < -0.02:
            return "TRENDING_DOWN"

        return "RANGE"
