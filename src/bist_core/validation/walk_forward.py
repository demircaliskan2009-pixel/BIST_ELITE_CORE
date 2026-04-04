"""Walk-Forward Validation Engine — evaluate strategy robustness across time."""

from __future__ import annotations

import math
from typing import Any

from bist_core.backtest.backtest_engine import BacktestEngine
from bist_core.data.quality import InvalidDataError, basic_checks
from bist_core.models.ohlcv import OHLCVBar


def _has_nan(bar: OHLCVBar) -> bool:
    return (
        math.isnan(bar.open)
        or math.isnan(bar.high)
        or math.isnan(bar.low)
        or math.isnan(bar.close)
        or math.isnan(bar.volume)
    )


def _is_valid(bars: list[OHLCVBar], min_len: int) -> bool:
    if len(bars) < min_len:
        return False
    if any(_has_nan(b) for b in bars):
        return False
    try:
        basic_checks(bars)
    except InvalidDataError:
        return False
    return True


def _variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((x - mean) ** 2 for x in values) / len(values)


class WalkForwardValidator:
    """Evaluate strategy robustness across time via walk-forward windows.

    Deterministic, fail-closed, no randomness.
    """

    def __init__(
        self,
        train_size: int,
        test_size: int,
        step_size: int,
        backtest_engine: BacktestEngine | None = None,
    ) -> None:
        self._train_size = train_size
        self._test_size = test_size
        self._step_size = step_size
        self._bt = backtest_engine or BacktestEngine()

    def validate(self, data: dict[str, list[OHLCVBar]]) -> dict[str, Any]:
        """Run walk-forward validation per symbol.

        Returns symbols dict with windows, avg_expectancy, avg_drawdown, stability.
        Skips symbols with insufficient data or invalid bars.
        """
        min_bars = self._train_size + self._test_size
        result: dict[str, Any] = {"symbols": {}}

        for symbol in sorted(data.keys()):
            bars = data[symbol]
            if not _is_valid(bars, min_bars):
                continue

            sorted_bars = sorted(bars, key=lambda b: b.timestamp)
            windows: list[dict[str, Any]] = []
            test_expectancies: list[float] = []

            i = 0
            while i + self._train_size + self._test_size <= len(sorted_bars):
                train = sorted_bars[i : i + self._train_size]
                test = sorted_bars[
                    i + self._train_size : i + self._train_size + self._test_size
                ]

                train_result = self._bt.run(train)
                test_result = self._bt.run(test)

                train_metrics = train_result["metrics"]
                test_metrics = test_result["metrics"]

                windows.append({
                    "train_start": train[0].timestamp,
                    "train_end": train[-1].timestamp,
                    "test_start": test[0].timestamp,
                    "test_end": test[-1].timestamp,
                    "train_metrics": train_metrics,
                    "test_metrics": test_metrics,
                })
                test_expectancies.append(test_metrics["expectancy"])

                i += self._step_size

            if not windows:
                continue

            var = _variance(test_expectancies)
            stability = 1.0 / (1.0 + var)
            avg_expectancy = sum(test_expectancies) / len(test_expectancies)
            avg_drawdown = sum(
                w["test_metrics"]["max_drawdown"] for w in windows
            ) / len(windows)

            result["symbols"][symbol] = {
                "windows": windows,
                "avg_expectancy": round(avg_expectancy, 6),
                "avg_drawdown": round(avg_drawdown, 6),
                "stability": round(stability, 6),
            }

        return result
