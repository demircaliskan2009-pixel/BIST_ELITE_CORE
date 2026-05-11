"""DeterministicClock — injectable wall clock for fully deterministic tests.

Usage:
    clock = DeterministicClock(start_ns=1_700_000_000_000_000_000)
    validator = DataValidator(wall_clock=clock)
    clock.advance(1_000_000_000)   # advance 1 second
    assert clock() == 1_700_000_001_000_000_000

The DeterministicClock is callable (implements WallClockProvider protocol).
"""

from __future__ import annotations


class DeterministicClock:
    """Deterministic injectable clock returning nanoseconds since epoch.

    The clock is frozen at start_ns and only advances when advance() is called.
    No real wall-clock time is consulted.

    Usage as WallClockProvider (callable returning int):
        clock = DeterministicClock(start_ns=1_700_000_000_000_000_000)
        clock()      # → 1_700_000_000_000_000_000
        clock.advance(5_000_000_000)  # advance 5 seconds
        clock()      # → 1_700_000_005_000_000_000
    """

    def __init__(self, start_ns: int = 1_700_000_000_000_000_000) -> None:
        self._current_ns: int = start_ns

    def __call__(self) -> int:
        """Return current clock value as nanoseconds since epoch (UTC)."""
        return self._current_ns

    def advance(self, delta_ns: int) -> None:
        """Advance the clock by delta_ns nanoseconds.

        Raises ValueError if delta_ns <= 0 (clocks do not go backward).
        """
        if delta_ns <= 0:
            raise ValueError(f"DeterministicClock.advance requires delta_ns > 0, got {delta_ns}")
        self._current_ns += delta_ns

    def set(self, absolute_ns: int) -> None:
        """Set the clock to an absolute value.

        Raises ValueError if absolute_ns < current (no time travel backward).
        """
        if absolute_ns < self._current_ns:
            raise ValueError(
                f"DeterministicClock.set: cannot go backward. current={self._current_ns}, requested={absolute_ns}"
            )
        self._current_ns = absolute_ns

    @property
    def now_ns(self) -> int:
        """Current clock value (same as calling the instance)."""
        return self._current_ns
