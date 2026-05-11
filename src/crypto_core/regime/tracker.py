"""Market regime tracker engine — Phase 5E.

Deterministic, bounded-memory tracker that derives a regime snapshot from
available runtime evidence.

V1 evidence sources (pipeline-available now):
  - Order-book level counts   (bid_level_count, ask_level_count)
  - Recent trade count        (recent_trade_count)
  - Optional: bid/ask depth USD, spread BPS (future depth provider)
  - Externally supplied leverage proxy (when OI/MC feed is integrated)
  - Externally supplied correlation score (when cross-asset feed integrated)

For every unavailable input the tracker sets the corresponding output field
to None — it never fabricates a value.

Rolling history:
  Buffer size  : configurable, default _DEFAULT_HISTORY_SIZE = 20
  Window       : _TRANSITION_WINDOW_NS = 5 minutes (300 seconds)
  Transition   : >= _INSTABILITY_CHANGES_THRESHOLD (3) level changes → active

Fail-closed:
  Malformed input → raises ValueError immediately.
  All exceptions in update() propagate to the caller (pipeline should catch).

PRD reference: §1.21 NT-M family (NT-M01–NT-M04).
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass

from crypto_core.regime.models import (
    LiquidityLevel,
    LiquiditySignal,
    RegimeEvidenceQuality,
    RegimeSignalInput,
    RegimeSnapshot,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

#: Score at or above this → HEALTHY level.
_HEALTHY_SCORE_THRESHOLD: float = 0.50

#: Score below this → CRISIS level (matches NoTradeConfig.liquidity_crisis_threshold).
_CRISIS_SCORE_THRESHOLD: float = 0.15

#: Number of book levels per side that maps to a score of 1.0 in level-count proxy.
_HEALTHY_LEVEL_COUNT: int = 10

#: Total bid+ask USD depth that maps to a score of 1.0 in depth-based mode.
_HEALTHY_DEPTH_USD: float = 500_000.0

#: Spread in BPS that completely negates the liquidity score (linear penalty).
_SPREAD_PENALTY_MAX_BPS: float = 500.0

#: Nanoseconds in the rolling window for regime transition detection (5 min).
_TRANSITION_WINDOW_NS: int = 300 * 1_000_000_000

#: Minimum level changes within the window to classify as "transitioning".
_INSTABILITY_CHANGES_THRESHOLD: int = 3

#: Default maximum number of history observations retained.
_DEFAULT_HISTORY_SIZE: int = 20

#: Nanoseconds per millisecond.
_NS_PER_MS: float = 1_000_000.0


# ---------------------------------------------------------------------------
# Private types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _HistoryItem:
    """One observation in the rolling regime history buffer.

    ns    — observation wall-clock (nanoseconds).
    level — categorical liquidity level at this point.
    score — raw numeric score [0, 1] at this point.
    """

    ns: int
    level: LiquidityLevel
    score: float


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------


class MarketRegimeTracker:
    """Deterministic market regime tracker.

    Maintains bounded rolling history to detect regime level transitions.
    All state mutations go through update(); history is bounded to
    `history_size` items.

    Thread safety: NOT thread-safe. Use one instance per pipeline thread.

    Usage::

        tracker = MarketRegimeTracker()
        snapshot = tracker.update(signal)
        market_input = MarketRegimeInput(
            liquidity_score=snapshot.liquidity_score,
            ...
        )
    """

    def __init__(self, history_size: int = _DEFAULT_HISTORY_SIZE) -> None:
        if history_size < 2:
            raise ValueError(f"history_size must be >= 2, got {history_size}")
        self._history_size = history_size
        self._history: deque[_HistoryItem] = deque(maxlen=history_size)
        # ns when liquidity score first dropped below CRISIS threshold.
        # Reset to None whenever score recovers to >= _CRISIS_SCORE_THRESHOLD.
        self._crisis_first_seen_ns: int | None = None

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def update(self, signal: RegimeSignalInput) -> RegimeSnapshot:
        """Process one signal observation and return an immutable regime snapshot.

        Raises:
            ValueError: if any signal field is invalid (fail-closed).
        """
        errors = _validate_signal(signal)
        if errors:
            raise ValueError("; ".join(errors))

        # ── Liquidity ───────────────────────────────────────────────────
        score: float | None = None
        level: LiquidityLevel | None = None
        if signal.liquidity is not None:
            score = self._compute_liquidity_score(signal.liquidity)
            level = _classify_level(score)

        # ── Update crisis tracking ──────────────────────────────────────
        self._update_crisis_tracking(score, signal.snapshot_ns)

        # ── Append history ─────────────────────────────────────────────
        if level is not None and score is not None:
            self._history.append(_HistoryItem(ns=signal.snapshot_ns, level=level, score=score))

        # ── Regime transition detection ─────────────────────────────────
        transition: bool | None = self._detect_transition(signal.snapshot_ns)

        # ── Crisis sustained duration ───────────────────────────────────
        sustained_ms: float | None = self._compute_sustained_ms(signal.snapshot_ns)

        # ── Evidence quality ────────────────────────────────────────────
        quality = _assess_evidence_quality(signal, score)

        return RegimeSnapshot(
            snapshot_ns=signal.snapshot_ns,
            evidence_quality=quality,
            liquidity_score=score,
            liquidity_crisis_sustained_ms=sustained_ms,
            oi_mc_ratio=signal.leverage_proxy,  # forwarded; None = unavailable
            regime_transition_active=transition,
            mean_pairwise_correlation=signal.correlation_score,  # forwarded; None = unavailable
            liquidity_level=level,
            crisis_first_seen_ns=self._crisis_first_seen_ns,
        )

    def reset(self) -> None:
        """Clear all history and reset crisis tracking.

        Use this between independent test cases to guarantee isolation.
        """
        self._history.clear()
        self._crisis_first_seen_ns = None

    @property
    def history_size(self) -> int:
        """Configured maximum history buffer size."""
        return self._history_size

    @property
    def observation_count(self) -> int:
        """Current number of items in the history buffer."""
        return len(self._history)

    # -----------------------------------------------------------------------
    # Private computation helpers
    # -----------------------------------------------------------------------

    def _compute_liquidity_score(self, sig: LiquiditySignal) -> float:
        """Compute normalised liquidity score [0, 1].

        Priority:
          1. Depth-based (bid_depth_usd + ask_depth_usd) — most accurate.
          2. Level-count proxy — v1 pipeline fallback.

        Spread penalty applied whenever bid_ask_spread_bps is available.
        Score is clamped to [0, 1].
        """
        min_levels = min(sig.bid_level_count, sig.ask_level_count)

        if min_levels <= 0:
            # Zero levels on either side = liquidity crisis by definition.
            return 0.0

        if sig.bid_depth_usd is not None and sig.ask_depth_usd is not None:
            total_depth = sig.bid_depth_usd + sig.ask_depth_usd
            base_score = min(1.0, total_depth / _HEALTHY_DEPTH_USD)
        else:
            # Level-count proxy: v1 pipeline default.
            base_score = min(1.0, min_levels / _HEALTHY_LEVEL_COUNT)

        # Optional spread penalty: linear interpolation from 0 BPS (no penalty)
        # to _SPREAD_PENALTY_MAX_BPS BPS (full penalty → score → 0).
        if sig.bid_ask_spread_bps is not None and sig.bid_ask_spread_bps > 0:
            penalty = min(1.0, sig.bid_ask_spread_bps / _SPREAD_PENALTY_MAX_BPS)
            base_score *= 1.0 - penalty

        return max(0.0, base_score)

    def _update_crisis_tracking(self, score: float | None, snapshot_ns: int) -> None:
        """Update the crisis first-seen timestamp.

        When score drops below _CRISIS_SCORE_THRESHOLD for the first time in
        an episode, record the timestamp.  When score recovers, clear it.
        score=None is treated as "no data" — crisis state is unchanged.
        """
        if score is None:
            return
        if score < _CRISIS_SCORE_THRESHOLD:
            if self._crisis_first_seen_ns is None:
                self._crisis_first_seen_ns = snapshot_ns
        else:
            # Recovery — reset crisis episode.
            self._crisis_first_seen_ns = None

    def _compute_sustained_ms(self, snapshot_ns: int) -> float | None:
        """Duration of the current crisis episode in milliseconds.

        Returns None if not currently in a crisis episode.
        """
        if self._crisis_first_seen_ns is None:
            return None
        elapsed_ns = snapshot_ns - self._crisis_first_seen_ns
        return elapsed_ns / _NS_PER_MS

    def _detect_transition(self, snapshot_ns: int) -> bool | None:
        """Detect whether the regime is actively transitioning.

        Returns:
            True  — >= _INSTABILITY_CHANGES_THRESHOLD level changes in window.
            False — < _INSTABILITY_CHANGES_THRESHOLD changes and >= 2 observations.
            None  — fewer than 2 total observations (insufficient history).

        Algorithm (deterministic, auditable):
          1. Filter history to items within _TRANSITION_WINDOW_NS.
          2. Count consecutive pairs where level differs.
          3. Compare against threshold.

        Rationale for returning None (not False) on insufficient history:
          The guard treats None as "unavailable → skip check", which is
          conservative but correct.  We cannot claim "not transitioning"
          without evidence.
        """
        if len(self._history) < 2:
            return None

        cutoff_ns = snapshot_ns - _TRANSITION_WINDOW_NS
        recent = [item for item in self._history if item.ns >= cutoff_ns]

        if len(recent) < 2:
            # All history is stale relative to this window.
            return None

        changes = sum(1 for i in range(1, len(recent)) if recent[i].level != recent[i - 1].level)
        return changes >= _INSTABILITY_CHANGES_THRESHOLD


# ---------------------------------------------------------------------------
# Module-level helpers (stateless, pure functions)
# ---------------------------------------------------------------------------


def _classify_level(score: float) -> LiquidityLevel:
    """Map a continuous score to a categorical LiquidityLevel."""
    if score < _CRISIS_SCORE_THRESHOLD:
        return LiquidityLevel.CRISIS
    if score < _HEALTHY_SCORE_THRESHOLD:
        return LiquidityLevel.DEGRADED
    return LiquidityLevel.HEALTHY


def _assess_evidence_quality(
    signal: RegimeSignalInput,
    score: float | None,
) -> RegimeEvidenceQuality:
    """Classify overall evidence quality for the snapshot.

    FULL        — depth + spread both available.
    PARTIAL     — depth OR spread available.
    MINIMAL     — only level counts (v1 pipeline default).
    UNAVAILABLE — no liquidity signal at all.
    """
    if signal.liquidity is None:
        return RegimeEvidenceQuality.UNAVAILABLE

    liq = signal.liquidity
    has_depth = liq.bid_depth_usd is not None and liq.ask_depth_usd is not None
    has_spread = liq.bid_ask_spread_bps is not None

    if has_depth and has_spread:
        return RegimeEvidenceQuality.FULL
    if has_depth or has_spread:
        return RegimeEvidenceQuality.PARTIAL
    if score is not None:
        return RegimeEvidenceQuality.MINIMAL
    return RegimeEvidenceQuality.UNAVAILABLE


def _validate_signal(signal: RegimeSignalInput) -> list[str]:
    """Return a list of validation error messages (empty = valid).

    All errors are collected before returning so the caller sees a full
    picture in one exception.
    """
    errors: list[str] = []

    if signal.liquidity is not None:
        liq = signal.liquidity
        if liq.bid_level_count < 0:
            errors.append("bid_level_count must be >= 0")
        if liq.ask_level_count < 0:
            errors.append("ask_level_count must be >= 0")
        if liq.recent_trade_count < 0:
            errors.append("recent_trade_count must be >= 0")
        if liq.bid_depth_usd is not None and liq.bid_depth_usd < 0:
            errors.append("bid_depth_usd must be >= 0")
        if liq.ask_depth_usd is not None and liq.ask_depth_usd < 0:
            errors.append("ask_depth_usd must be >= 0")
        if liq.bid_ask_spread_bps is not None and liq.bid_ask_spread_bps < 0:
            errors.append("bid_ask_spread_bps must be >= 0")

    if signal.leverage_proxy is not None and signal.leverage_proxy < 0:
        errors.append("leverage_proxy must be >= 0")

    if signal.correlation_score is not None and not (-1.0 <= signal.correlation_score <= 1.0):
        errors.append(f"correlation_score must be in [-1, 1], got {signal.correlation_score}")

    return errors
