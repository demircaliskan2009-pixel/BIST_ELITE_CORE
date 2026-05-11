"""Deterministic historical CVaR models.

PRD reference: §1.18 Portfolio-Level Risk: CVaR / Expected Shortfall.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ReturnObservation:
    """One signed portfolio return sample in percentage points.

    return_pct uses percentage-point units, e.g. -2.5 means -2.5% return.
    nav_usd is captured for auditability and validation.
    """

    timestamp_ns: int
    return_pct: float
    nav_usd: float

    def __post_init__(self) -> None:
        if self.timestamp_ns <= 0:
            raise ValueError(f"timestamp_ns must be > 0; got {self.timestamp_ns}")
        if not math.isfinite(self.return_pct):
            raise ValueError(f"return_pct must be finite; got {self.return_pct!r}")
        if not math.isfinite(self.nav_usd) or self.nav_usd <= 0.0:
            raise ValueError(f"nav_usd must be finite and > 0; got {self.nav_usd!r}")


@dataclass(frozen=True)
class CVaRConfig:
    """Historical CVaR configuration.

    confidence_level is expressed on [0, 1), e.g. 0.99 for CVaR99.
    rolling_window bounds retained history. min_history controls when the
    engine transitions from unavailable to available.
    """

    confidence_level: float = 0.99
    rolling_window: int = 252
    min_history: int = 252

    def __post_init__(self) -> None:
        if not 0.0 < self.confidence_level < 1.0:
            raise ValueError(f"confidence_level must be in (0, 1); got {self.confidence_level}")
        if self.rolling_window <= 0:
            raise ValueError(f"rolling_window must be > 0; got {self.rolling_window}")
        if self.min_history <= 0:
            raise ValueError(f"min_history must be > 0; got {self.min_history}")
        if self.min_history > self.rolling_window:
            raise ValueError(
                "min_history must be <= rolling_window; "
                f"got min_history={self.min_history}, rolling_window={self.rolling_window}"
            )


@dataclass(frozen=True)
class CVaREvidence:
    """Audit payload for the latest CVaR snapshot."""

    reason: str | None
    required_history: int
    tail_count: int
    threshold_return_pct: float | None
    worst_return_pct: float | None
    best_return_pct: float | None
    last_return_pct: float | None
    window_start_ns: int | None
    window_end_ns: int | None


@dataclass(frozen=True)
class CVaRSnapshot:
    """Immutable current CVaR engine view."""

    timestamp_ns: int
    confidence_level: float
    history_count: int
    rolling_window: int
    available: bool
    var99_pct: float | None
    cvar99_pct: float | None
    evidence: CVaREvidence
