"""Deterministic bounded historical CVaR engine."""

from __future__ import annotations

import math
from collections import deque
from statistics import fmean

from crypto_core.cvar.models import CVaRConfig, CVaREvidence, CVaRSnapshot, ReturnObservation


class CVaREngine:
    """Bounded historical VaR/CVaR calculator.

    Duplicate timestamps replace the latest observation instead of appending a
    second sample. Older timestamps are rejected as malformed.
    """

    def __init__(self, config: CVaRConfig | None = None) -> None:
        self._config = config or CVaRConfig()
        self._observations: deque[ReturnObservation] = deque(maxlen=self._config.rolling_window)

    @property
    def config(self) -> CVaRConfig:
        return self._config

    @property
    def history_count(self) -> int:
        return len(self._observations)

    def observe(self, observation: ReturnObservation) -> None:
        """Record one return observation.

        Rules:
          - strictly older timestamps are rejected
          - duplicate timestamps replace the most recent sample
          - history is bounded by rolling_window
        """
        if self._observations:
            last_timestamp_ns = self._observations[-1].timestamp_ns
            if observation.timestamp_ns < last_timestamp_ns:
                raise ValueError(
                    "observation timestamps must be monotonic; "
                    f"got {observation.timestamp_ns} after {last_timestamp_ns}"
                )
            if observation.timestamp_ns == last_timestamp_ns:
                self._observations[-1] = observation
                return
        self._observations.append(observation)

    def snapshot(self, timestamp_ns: int) -> CVaRSnapshot:
        """Return the current deterministic historical CVaR snapshot."""
        if timestamp_ns <= 0:
            raise ValueError(f"timestamp_ns must be > 0; got {timestamp_ns}")

        history_count = len(self._observations)
        if history_count < self._config.min_history:
            return CVaRSnapshot(
                timestamp_ns=timestamp_ns,
                confidence_level=self._config.confidence_level,
                history_count=history_count,
                rolling_window=self._config.rolling_window,
                available=False,
                var99_pct=None,
                cvar99_pct=None,
                evidence=CVaREvidence(
                    reason="insufficient_history",
                    required_history=self._config.min_history,
                    tail_count=0,
                    threshold_return_pct=None,
                    worst_return_pct=None,
                    best_return_pct=None,
                    last_return_pct=self._observations[-1].return_pct if self._observations else None,
                    window_start_ns=self._observations[0].timestamp_ns if self._observations else None,
                    window_end_ns=self._observations[-1].timestamp_ns if self._observations else None,
                ),
            )

        sorted_returns = sorted(observation.return_pct for observation in self._observations)
        left_tail_probability = 1.0 - self._config.confidence_level
        tail_index = max(0, math.ceil(left_tail_probability * history_count) - 1)
        threshold_return_pct = sorted_returns[tail_index]
        tail_returns = tuple(ret for ret in sorted_returns if ret <= threshold_return_pct)
        tail_mean = fmean(tail_returns)
        var99_pct = max(0.0, -threshold_return_pct)
        cvar99_pct = max(0.0, -tail_mean)

        return CVaRSnapshot(
            timestamp_ns=timestamp_ns,
            confidence_level=self._config.confidence_level,
            history_count=history_count,
            rolling_window=self._config.rolling_window,
            available=True,
            var99_pct=var99_pct,
            cvar99_pct=cvar99_pct,
            evidence=CVaREvidence(
                reason=None,
                required_history=self._config.min_history,
                tail_count=len(tail_returns),
                threshold_return_pct=threshold_return_pct,
                worst_return_pct=sorted_returns[0],
                best_return_pct=sorted_returns[-1],
                last_return_pct=self._observations[-1].return_pct,
                window_start_ns=self._observations[0].timestamp_ns,
                window_end_ns=self._observations[-1].timestamp_ns,
            ),
        )
