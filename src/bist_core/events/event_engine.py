"""Event Engine — orchestrates event data, classification, scoring, and edge detection.

The EventEngine is the main integration point between corporate events and the
existing technical edge scanner. It:
  1. Loads events from registered providers
  2. Classifies impact + sentiment
  3. Scores with price/volume confirmation
  4. Maintains per-symbol active event state
  5. Produces IntradaySignal through event edge detectors
  6. Applies fake reaction filter to block false signals

Integration with IntradayEdgeScanner:
  The EventEngine is called by the scanner on each bar. If an event is active
  for the symbol, event edges are evaluated alongside technical edges.
  The highest-confidence signal (event OR technical) wins.

Thread safety: Not thread-safe. Designed for single-threaded backtest/live loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Sequence

from bist_core.decision.intraday_edges import IntradaySignal
from bist_core.decision.timeframe_sync import MTFBarEvent
from bist_core.events.event_classifier import classify_event
from bist_core.events.event_edges import (
    detect_earnings_drift,
    detect_event_breakout,
    detect_news_momentum,
)
from bist_core.events.event_policy import (
    EventEdgeVerdict,
    POSITIVE_EVENT_BOOST,
    SOFT_NEGATIVE_CONFIDENCE_MULT,
    get_event_verdict,
)
from bist_core.events.event_scorer import score_event
from bist_core.events.event_types import (
    ClassifiedEvent,
    EventRecord,
)
from bist_core.events.provider_base import EventDataProvider, EventProviderRegistry
from bist_core.models.ohlcv import OHLCVBar

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum age of an active event (seconds). After this, the event is expired.
_EVENT_MAX_AGE_SEC: Final[int] = 5 * 86400  # 5 trading days

# Minimum event score to activate event edges
_MIN_ACTIVATION_SCORE: Final[float] = 0.15

# Maximum bar count since event for edge scanning
_MAX_BARS_SINCE_EVENT: Final[int] = 2000  # ~33 hours of trading

# Strong event threshold — overrides technical signals
_STRONG_EVENT_SCORE: Final[float] = 0.6

# Fake reaction detection: minimum spike + low volume = block
_FAKE_SPIKE_PCT: Final[float] = 0.015
_FAKE_LOW_VOL: Final[float] = 0.8

# Event policy: evidence-based kind classification (Phase 2 alpha study)
# Replaces old _BLOCKED_EVENT_TYPES. See event_policy.py for evidence.

# Re-fire cooldown: allow same edge to fire again after N bars
# (replaces absolute single-fire which limited trade count)
_EDGE_REFIRE_COOLDOWN: Final[int] = 120  # bars (~2 hours)


# ---------------------------------------------------------------------------
# Active event tracking
# ---------------------------------------------------------------------------


@dataclass
class ActiveEventState:
    """Tracks an active event for a symbol."""

    classified: ClassifiedEvent
    score: float
    activation_ts: int  # timestamp when event became active
    bars_seen: int = 0  # bars elapsed since activation
    fired_edges: dict[str, int] = field(default_factory=dict)  # edge → bars_seen at last fire


# ---------------------------------------------------------------------------
# Event Engine
# ---------------------------------------------------------------------------


class EventEngine:
    """Orchestrates event-driven alpha detection.

    Usage (backtest):
        engine = EventEngine()
        engine.register_provider(SyntheticBISTEventProvider())
        engine.load_events(symbols, start_ts, end_ts)

        # On each bar:
        signals = engine.scan(mtf_event, m1_history)

    Usage (live):
        engine = EventEngine()
        engine.register_provider(LocalFileEventProvider("data/events"))
        engine.register_provider(KAPScraperProvider())
        engine.load_events(symbols, start_ts, end_ts)
    """

    def __init__(self) -> None:
        self._registry = EventProviderRegistry()
        self._all_events: list[EventRecord] = []
        self._classified: list[ClassifiedEvent] = []
        self._active: dict[str, ActiveEventState] = {}  # symbol → active event
        self._event_index: int = 0  # pointer into sorted events list
        self._disabled_edges: set[str] = set()

    def register_provider(self, provider: EventDataProvider) -> None:
        """Register an event data provider."""
        self._registry.register(provider)

    def load_events(
        self,
        symbols: Sequence[str],
        start_ts: int,
        end_ts: int,
    ) -> int:
        """Load and classify all events for the backtest period.

        Returns number of events loaded.
        """
        self._all_events = self._registry.fetch_all(symbols, start_ts, end_ts)
        self._classified = [classify_event(ev) for ev in self._all_events]
        self._event_index = 0
        self._active.clear()
        return len(self._all_events)

    def disable_edges(self, edges: set[str]) -> None:
        """Disable specific event edges."""
        self._disabled_edges = edges

    @property
    def event_count(self) -> int:
        return len(self._all_events)

    @property
    def active_events(self) -> dict[str, ActiveEventState]:
        return dict(self._active)

    def scan(
        self,
        event: MTFBarEvent,
        m1_history: Sequence[OHLCVBar],
    ) -> list[IntradaySignal]:
        """Scan for event-driven signals on the current bar.

        Called once per bar alongside the technical scanner.
        Returns list of signals (may be empty).
        """
        bar = event.bar
        sym = bar.symbol
        ts = bar.timestamp

        # 1. Activate new events that have become visible
        self._activate_events(sym, ts, m1_history)

        # 2. Check if symbol has an active event
        active = self._active.get(sym)
        if active is None:
            return []

        # 3. Expire old events
        if ts - active.activation_ts > _EVENT_MAX_AGE_SEC:
            del self._active[sym]
            return []

        # 4. Increment bar counter
        active.bars_seen += 1

        # 5. Check minimum score
        if abs(active.score) < _MIN_ACTIVATION_SCORE:
            return []

        # 5b. Apply evidence-based event policy
        etype = active.classified.event.event_type.value
        verdict = get_event_verdict(etype)
        if verdict == EventEdgeVerdict.NEGATIVE:
            # Hard negative: block all event-driven signals
            return []
        if verdict in (EventEdgeVerdict.NEUTRAL, EventEdgeVerdict.SOFT_NEGATIVE):
            # Neutral/soft-negative: no event-driven signals (but technical allowed)
            return []

        # 6. Check max bars
        if active.bars_seen > _MAX_BARS_SINCE_EVENT:
            del self._active[sym]
            return []

        # 7. Fake reaction filter: if spike on low volume, block all signals
        if self._is_fake_reaction(m1_history, active):
            return []

        # 8. Run event edge detectors
        signals: list[IntradaySignal] = []

        edge_fns = [
            ("earnings_drift", detect_earnings_drift),
            ("news_momentum", detect_news_momentum),
            ("event_breakout", detect_event_breakout),
        ]

        for edge_name, detect_fn in edge_fns:
            if edge_name in self._disabled_edges:
                continue
            # Cooldown-based re-fire: allow same edge after N bars
            last_fire_bar = active.fired_edges.get(edge_name, -_EDGE_REFIRE_COOLDOWN - 1)
            if active.bars_seen - last_fire_bar < _EDGE_REFIRE_COOLDOWN:
                continue

            sig = detect_fn(
                event=event,
                m1_history=m1_history,
                active_event=active.classified,
                event_score=active.score,
                bars_since_event=active.bars_seen,
            )
            if sig is not None:
                signals.append(sig)
                active.fired_edges[edge_name] = active.bars_seen

        return signals

    def get_event_boost(self, symbol: str) -> float:
        """Get event-based confidence boost for a symbol.

        Returns POSITIVE_EVENT_BOOST only for POSITIVE-edge event kinds.
        Returns 0.0 for NEGATIVE/NEUTRAL/no event.
        Evidence-based: replaces old generic score-scaled boost.
        """
        active = self._active.get(symbol)
        if active is None:
            return 0.0
        etype = active.classified.event.event_type.value
        verdict = get_event_verdict(etype)
        if verdict == EventEdgeVerdict.POSITIVE:
            return POSITIVE_EVENT_BOOST
        return 0.0

    def get_event_context(self, symbol: str) -> tuple[str, str, str]:
        """Get event context for auditability.

        Returns (verdict, event_kind, reason) for the active event on a symbol.
        If no active event: ("none", "", "no active event")
        """
        active = self._active.get(symbol)
        if active is None:
            return ("none", "", "no active event")
        etype = active.classified.event.event_type.value
        verdict = get_event_verdict(etype)
        reason = f"{etype} event active (score={active.score:.3f})"
        return (verdict.value.lower(), etype, reason)

    def is_event_blocked(self, symbol: str) -> bool:
        """Check if a hard NEGATIVE event is active for this symbol.

        When True, technical LONG signals should be blocked.
        SOFT_NEGATIVE does NOT block — it only reduces confidence.
        """
        active = self._active.get(symbol)
        if active is None:
            return False
        etype = active.classified.event.event_type.value
        return get_event_verdict(etype) == EventEdgeVerdict.NEGATIVE

    def get_soft_penalty(self, symbol: str) -> float:
        """Get confidence multiplier for SOFT_NEGATIVE events.

        Returns SOFT_NEGATIVE_CONFIDENCE_MULT (0.7) when a soft-negative
        event is active, 1.0 otherwise.
        """
        active = self._active.get(symbol)
        if active is None:
            return 1.0
        etype = active.classified.event.event_type.value
        if get_event_verdict(etype) == EventEdgeVerdict.SOFT_NEGATIVE:
            return SOFT_NEGATIVE_CONFIDENCE_MULT
        return 1.0

    def is_strong_event(self, symbol: str) -> bool:
        """Check if a strong event is active (can override technical)."""
        active = self._active.get(symbol)
        if active is None:
            return False
        return abs(active.score) >= _STRONG_EVENT_SCORE

    def _activate_events(
        self,
        symbol: str,
        current_ts: int,
        bars: Sequence[OHLCVBar],
    ) -> None:
        """Activate events that have become visible by current_ts.

        Events are sorted by timestamp. We advance the pointer to
        activate all events up to current_ts (no lookahead).
        """
        while self._event_index < len(self._classified):
            cev = self._classified[self._event_index]
            ev = cev.event

            # Future event — stop
            if ev.timestamp > current_ts:
                break

            self._event_index += 1

            # Only activate for the relevant symbol
            if ev.symbol != symbol:
                # Still advance pointer — events are global
                # But we need a per-symbol approach. Store and check later.
                continue

            # Score with price/volume confirmation
            score = score_event(cev, bars)

            # Only activate if score meets threshold
            if abs(score) >= _MIN_ACTIVATION_SCORE:
                # Replace any existing active event for this symbol
                # (newer event supersedes older one)
                self._active[symbol] = ActiveEventState(
                    classified=cev,
                    score=score,
                    activation_ts=ev.timestamp,
                )

    def _is_fake_reaction(
        self,
        bars: Sequence[OHLCVBar],
        active: ActiveEventState,
    ) -> bool:
        """Detect fake reaction: price spike on low volume.

        Returns True if the current price action looks like a
        fake reaction to the event → block all event signals.
        """
        if len(bars) < 15 or active.bars_seen < 5:
            return False

        # Check recent price spike
        ref_price = float(bars[-10].close)
        peak = max(float(b.high) for b in bars[-10:])
        float(bars[-1].close)

        if ref_price <= 0 or peak <= 0:
            return False

        spike_pct = (peak - ref_price) / ref_price
        if spike_pct < _FAKE_SPIKE_PCT:
            return False  # no spike

        # Check volume
        avg_vol = sum(float(b.volume) for b in bars[-20:-1]) / min(19, len(bars) - 1)
        if avg_vol <= 0:
            return False

        recent_vol = float(bars[-1].volume)
        vol_ratio = recent_vol / avg_vol

        if vol_ratio >= _FAKE_LOW_VOL:
            return False  # volume is fine

        # Low volume spike → fake reaction
        return True


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_event_engine(
    data_dir: str | None = None,
    use_synthetic: bool = True,
) -> EventEngine:
    """Create configured EventEngine with standard providers.

    Args:
        data_dir: Path to local event files (CSV/JSON). None to skip.
        use_synthetic: Include synthetic backtest events (default True).

    Returns:
        Configured EventEngine ready for load_events().
    """
    from pathlib import Path

    engine = EventEngine()

    # Local file provider
    if data_dir is not None:
        from bist_core.events.provider_local import LocalFileEventProvider

        engine.register_provider(LocalFileEventProvider(Path(data_dir)))

    # Synthetic provider (for backtesting)
    if use_synthetic:
        from bist_core.events.provider_synthetic import SyntheticBISTEventProvider

        engine.register_provider(SyntheticBISTEventProvider())

    # KAP stub (OFF by default, guarded by env var)
    from bist_core.events.provider_kap_stub import KAPScraperProvider

    engine.register_provider(KAPScraperProvider())

    return engine


__all__ = [
    "ActiveEventState",
    "EventEngine",
    "create_event_engine",
]
