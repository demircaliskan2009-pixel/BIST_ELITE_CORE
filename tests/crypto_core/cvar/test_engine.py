"""Unit tests for the deterministic historical CVaR engine."""

from __future__ import annotations

import math

import pytest

from crypto_core.cvar import CVaRConfig, CVaREngine, ReturnObservation


def _obs(timestamp_ns: int, return_pct: float, nav_usd: float = 100_000.0) -> ReturnObservation:
    return ReturnObservation(timestamp_ns=timestamp_ns, return_pct=return_pct, nav_usd=nav_usd)


class TestCVaREngine:
    def test_insufficient_history_is_explicit(self) -> None:
        engine = CVaREngine(CVaRConfig(rolling_window=5, min_history=3))
        engine.observe(_obs(1, -1.0))

        snap = engine.snapshot(timestamp_ns=10)

        assert snap.available is False
        assert snap.history_count == 1
        assert snap.var99_pct is None
        assert snap.cvar99_pct is None
        assert snap.evidence.reason == "insufficient_history"
        assert snap.evidence.required_history == 3

    def test_bounded_window_uses_latest_history_only(self) -> None:
        engine = CVaREngine(CVaRConfig(rolling_window=3, min_history=2))
        for timestamp_ns, return_pct in ((1, -1.0), (2, -2.0), (3, -3.0), (4, -4.0)):
            engine.observe(_obs(timestamp_ns, return_pct))

        snap = engine.snapshot(timestamp_ns=20)

        assert snap.available is True
        assert snap.history_count == 3
        assert snap.var99_pct == pytest.approx(4.0)
        assert snap.cvar99_pct == pytest.approx(4.0)
        assert snap.evidence.window_start_ns == 2
        assert snap.evidence.window_end_ns == 4

    def test_duplicate_timestamp_replaces_latest_observation(self) -> None:
        engine = CVaREngine(CVaRConfig(rolling_window=4, min_history=2))
        engine.observe(_obs(1, -1.0))
        engine.observe(_obs(2, -2.0))
        engine.observe(_obs(2, -3.0))

        snap = engine.snapshot(timestamp_ns=30)

        assert snap.history_count == 2
        assert snap.var99_pct == pytest.approx(3.0)
        assert snap.cvar99_pct == pytest.approx(3.0)
        assert snap.evidence.last_return_pct == pytest.approx(-3.0)

    def test_identical_inputs_produce_identical_snapshots(self) -> None:
        cfg = CVaRConfig(rolling_window=5, min_history=3)
        series = (
            _obs(1, -0.5),
            _obs(2, -1.5),
            _obs(3, 0.25),
            _obs(4, -2.0),
        )
        engine_one = CVaREngine(cfg)
        engine_two = CVaREngine(cfg)

        for observation in series:
            engine_one.observe(observation)
            engine_two.observe(observation)

        snap_one = engine_one.snapshot(timestamp_ns=40)
        snap_two = engine_two.snapshot(timestamp_ns=40)

        assert snap_one == snap_two

    def test_malformed_inputs_are_rejected_fail_closed(self) -> None:
        with pytest.raises(ValueError, match="return_pct"):
            _obs(1, math.nan)

        engine = CVaREngine(CVaRConfig(rolling_window=4, min_history=2))
        engine.observe(_obs(2, -1.0))
        with pytest.raises(ValueError, match="monotonic"):
            engine.observe(_obs(1, -2.0))
