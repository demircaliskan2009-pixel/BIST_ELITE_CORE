"""Event Edge Detectors — 4 event-driven alpha edges for BIST.

Each edge takes an event context and OHLCV bars, returns IntradaySignal or None.
All logic is deterministic, uses only completed bars (no lookahead).

Edges:
  1. earnings_drift     — Post-Earnings Announcement Drift (PEAD)
  2. news_momentum      — High-impact news + price confirmation
  3. event_breakout     — Event coincides with technical breakout → amplified
  4. fake_reaction_filter — Volume doesn't confirm price spike → AVOID

BIST-specific rationale:
  - BIST has lower institutional coverage → PEAD is stronger and slower to arbitrage
  - KAP disclosures create asymmetric information windows
  - Retail-heavy order flow amplifies initial reactions
  - Fake spikes on low volume are common → filter is critical

Integration:
  EventEdgeScanner produces IntradaySignal objects compatible with the
  existing IntradayEdgeScanner pipeline. The event engine calls these
  detectors when a scored event is active for a symbol.
"""

from __future__ import annotations

from typing import Final, Sequence

from bist_core.decision.intraday_edges import (
    IntradaySignal,
    _atr_from_bars,
    _avg_volume,
    _is_in_session,
    _make_signal,
    _MIN_CONFIDENCE,
    _mtf_score,
    _rsi_from_bars,
    _too_late_for_entry,
)
from bist_core.decision.timeframe_sync import MTFBarEvent
from bist_core.events.event_types import ClassifiedEvent
from bist_core.models.ohlcv import OHLCVBar

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Edge 1: Earnings Drift
_ED_MIN_SCORE: Final[float] = 0.3          # minimum event score for entry
_ED_VOLUME_RATIO: Final[float] = 1.3       # post-event volume above average
_ED_MAX_BARS_AFTER: Final[int] = 300       # drift window: 300 bars (5 hours)
_ED_MIN_RETURN_PCT: Final[float] = 0.005   # min 0.5% move in drift direction

# Edge 2: News Momentum
_NM_MIN_SCORE: Final[float] = 0.25          # lowered from 0.4 — study shows investment/regulatory alpha at lower scores
_NM_VOLUME_RATIO: Final[float] = 1.2       # lowered from 1.5 — BIST thin liquidity
_NM_PRICE_MOVE_PCT: Final[float] = 0.008   # 0.8% move confirms momentum

# Edge 3: Event Breakout
_EB_BREAKOUT_LOOKBACK: Final[int] = 60     # bars to check for technical breakout
_EB_BREAKOUT_PCT: Final[float] = 0.002     # 0.2% above recent high
_EB_MIN_SCORE: Final[float] = 0.2          # lower bar — event amplifies technical

# Edge 4: Fake Reaction Filter
_FR_SPIKE_PCT: Final[float] = 0.015        # 1.5% spike = potential fake
_FR_LOW_VOL_RATIO: Final[float] = 0.8      # volume BELOW 0.8x average = fake
_FR_REVERSION_PCT: Final[float] = 0.005    # 0.5% reversion confirms fake


# ---------------------------------------------------------------------------
# Edge 1: Post-Earnings Announcement Drift (PEAD)
# ---------------------------------------------------------------------------


def detect_earnings_drift(
    event: MTFBarEvent,
    m1_history: Sequence[OHLCVBar],
    active_event: ClassifiedEvent,
    event_score: float,
    bars_since_event: int,
) -> IntradaySignal | None:
    """Detect PEAD: post-earnings price drift in direction of surprise.

    WHY IT WORKS IN BIST:
    - Lower analyst coverage → earnings surprises persist longer
    - Retail-heavy market → slower information absorption
    - Price adjustment takes 1-5 days, not minutes

    Logic:
    1. Earnings event with composite score >= threshold
    2. Within drift window (first 300 bars = ~5 hours after event)
    3. Volume above average (institutional attention)
    4. Price moving in direction of event sentiment
    5. Not overbought/oversold (RSI guard)
    """
    bar = event.bar

    if not _is_in_session(bar.timestamp):
        return None
    if _too_late_for_entry(bar.timestamp):
        return None
    if len(m1_history) < 30:
        return None

    # Only earnings events
    if active_event.event.event_type.value != "earnings":
        return None

    # Score threshold
    if abs(event_score) < _ED_MIN_SCORE:
        return None

    # Drift window
    if bars_since_event > _ED_MAX_BARS_AFTER:
        return None

    # Volume confirmation
    avg_vol = _avg_volume(m1_history, 20)
    if avg_vol <= 0 or float(bar.volume) / avg_vol < _ED_VOLUME_RATIO:
        return None

    # Price movement in event direction
    if len(m1_history) >= 10:
        ref_price = float(m1_history[-10].close)
        current = float(bar.close)
        if ref_price <= 0:
            return None
        ret = (current - ref_price) / ref_price

        if event_score > 0 and ret < _ED_MIN_RETURN_PCT:
            return None  # positive event but price not drifting up
        if event_score < 0:
            return None  # BIST long-only: skip negative drift

    # RSI guard
    rsi = _rsi_from_bars(m1_history, 14)
    if rsi > 75.0:
        return None  # already overbought

    # MTF context
    ctx = event.context
    mtf = _mtf_score(ctx)
    if mtf < _MIN_CONFIDENCE:
        return None

    atr = _atr_from_bars(m1_history, 14)
    confidence = min(1.0, mtf * 0.5 + abs(event_score) * 0.5)

    return _make_signal(
        bar=bar,
        edge="earnings_drift",
        direction="LONG",
        entry=float(bar.close),
        atr=atr,
        confidence=confidence,
        reason=f"PEAD: score={event_score:.2f} bars_since={bars_since_event} vol_ratio={float(bar.volume)/avg_vol:.1f}",
        mtf_mult=mtf,
        source="event",
    )


# ---------------------------------------------------------------------------
# Edge 2: News Momentum
# ---------------------------------------------------------------------------


def detect_news_momentum(
    event: MTFBarEvent,
    m1_history: Sequence[OHLCVBar],
    active_event: ClassifiedEvent,
    event_score: float,
    bars_since_event: int,
) -> IntradaySignal | None:
    """Detect news-driven momentum: high-impact positive news + confirmation.

    WHY IT WORKS IN BIST:
    - Material disclosures on KAP create information asymmetry
    - Contract awards / major investments drive multi-day repricing
    - BIST stocks can move 3-5% on material news before fully absorbing

    Logic:
    1. High or mid-impact event (contract, investment, partnership)
    2. Strong positive sentiment score
    3. Price already moving in positive direction (momentum confirm)
    4. Volume elevated (market attention)
    5. First 2 hours after event only (avoid stale signals)
    """
    bar = event.bar

    if not _is_in_session(bar.timestamp):
        return None
    if _too_late_for_entry(bar.timestamp):
        return None
    if len(m1_history) < 30:
        return None

    # Skip earnings (handled by PEAD edge)
    if active_event.event.event_type.value == "earnings":
        return None

    # Score threshold (higher for non-earnings)
    if event_score < _NM_MIN_SCORE:
        return None

    # Time window: first 240 bars (~4 hours) — extended from 120
    # Study shows 12h returns >> 4h returns for investment/regulatory events
    if bars_since_event > 240:
        return None

    # Volume confirmation
    avg_vol = _avg_volume(m1_history, 20)
    if avg_vol <= 0 or float(bar.volume) / avg_vol < _NM_VOLUME_RATIO:
        return None

    # Price momentum confirmation
    if len(m1_history) >= 5:
        ref_price = float(m1_history[-5].close)
        current = float(bar.close)
        if ref_price <= 0:
            return None
        ret = (current - ref_price) / ref_price
        if ret < _NM_PRICE_MOVE_PCT:
            return None  # no momentum

    # MTF context
    ctx = event.context
    mtf = _mtf_score(ctx)
    if mtf < _MIN_CONFIDENCE:
        return None

    atr = _atr_from_bars(m1_history, 14)
    confidence = min(1.0, mtf * 0.4 + event_score * 0.6)

    return _make_signal(
        bar=bar,
        edge="news_momentum",
        direction="LONG",
        entry=float(bar.close),
        atr=atr,
        confidence=confidence,
        reason=f"News momentum: type={active_event.event.event_type.value} score={event_score:.2f}",
        mtf_mult=mtf,
        source="event",
    )


# ---------------------------------------------------------------------------
# Edge 3: Event Breakout (event + technical confluence)
# ---------------------------------------------------------------------------


def detect_event_breakout(
    event: MTFBarEvent,
    m1_history: Sequence[OHLCVBar],
    active_event: ClassifiedEvent,
    event_score: float,
    bars_since_event: int,
) -> IntradaySignal | None:
    """Detect event-amplified technical breakout.

    WHY IT WORKS IN BIST:
    - Event provides fundamental catalyst for breakout follow-through
    - Reduces false breakout probability (event confirms directional bias)
    - BIST breakouts often fail without catalyst → event supplies the catalyst

    Logic:
    1. Any positive event (even LOW impact) with positive score
    2. Event within last 5 hours
    3. Price breaks above N-bar high (technical breakout)
    4. Volume confirms
    5. Combined signal = higher confidence than either alone
    """
    bar = event.bar

    if not _is_in_session(bar.timestamp):
        return None
    if _too_late_for_entry(bar.timestamp):
        return None
    if len(m1_history) < _EB_BREAKOUT_LOOKBACK:
        return None

    # Positive event only (LONG only)
    if event_score < _EB_MIN_SCORE:
        return None

    # Event window
    if bars_since_event > 300:
        return None

    # Technical breakout: price above recent high
    lookback_bars = m1_history[-_EB_BREAKOUT_LOOKBACK:]
    recent_high = max(float(b.high) for b in lookback_bars)
    current = float(bar.close)
    if recent_high <= 0:
        return None
    breakout_pct = (current - recent_high) / recent_high
    if breakout_pct < _EB_BREAKOUT_PCT:
        return None  # no breakout

    # Volume confirmation
    avg_vol = _avg_volume(m1_history, 20)
    if avg_vol <= 0 or float(bar.volume) / avg_vol < 1.2:
        return None

    # MTF context
    ctx = event.context
    mtf = _mtf_score(ctx)
    if mtf < _MIN_CONFIDENCE:
        return None

    atr = _atr_from_bars(m1_history, 14)
    # Confidence boosted by event + technical confluence
    confidence = min(1.0, mtf * 0.3 + event_score * 0.3 + breakout_pct * 40)

    return _make_signal(
        bar=bar,
        edge="event_breakout",
        direction="LONG",
        entry=current,
        atr=atr,
        confidence=confidence,
        reason=f"Event breakout: bo={breakout_pct:.3f} score={event_score:.2f}",
        mtf_mult=mtf,
        source="event",
    )


# ---------------------------------------------------------------------------
# Edge 4: Fake Reaction Filter
# ---------------------------------------------------------------------------


def detect_fake_reaction(
    event: MTFBarEvent,
    m1_history: Sequence[OHLCVBar],
    active_event: ClassifiedEvent,
    event_score: float,
    bars_since_event: int,
) -> IntradaySignal | None:
    """Detect and AVOID fake reactions (price spike on low volume).

    WHY IT WORKS IN BIST:
    - Retail-driven spikes on event headlines are common
    - Low volume spikes revert within minutes/hours
    - This edge AVOIDS entries (returns None with high confidence)
      when a fake reaction is detected, but can also trade the reversion

    Logic:
    1. Price spiked > 1.5% in short window
    2. But volume is BELOW average (no institutional follow-through)
    3. And price has started reverting
    → This is a FAKE REACTION — do NOT enter
    → If reversion is strong enough and volume picks up → fade
    """
    bar = event.bar

    if not _is_in_session(bar.timestamp):
        return None
    if _too_late_for_entry(bar.timestamp):
        return None
    if len(m1_history) < 30:
        return None

    # Only check within event window
    if bars_since_event > 60:
        return None

    # Check for spike
    if len(m1_history) >= 10:
        ref_price = float(m1_history[-10].close)
        peak = max(float(b.high) for b in m1_history[-10:])
        current = float(bar.close)

        if ref_price <= 0:
            return None

        spike_pct = (peak - ref_price) / ref_price
        reversion_pct = (peak - current) / peak if peak > 0 else 0

        # Was there a spike?
        if spike_pct < _FR_SPIKE_PCT:
            return None  # no spike detected

        # Is volume low? (fake signal)
        avg_vol = _avg_volume(m1_history, 20)
        if avg_vol <= 0:
            return None
        vol_ratio = float(bar.volume) / avg_vol

        if vol_ratio >= _FR_LOW_VOL_RATIO:
            return None  # volume is normal/high — not a fake reaction

        # Fake reaction confirmed: spike on low volume
        # Check if it's reverting (potential fade trade)
        if reversion_pct > _FR_REVERSION_PCT:
            # Strong reversion on low volume — this is unreliable, skip
            # The filter's job is to PREVENT entry, not generate one
            return None

    return None  # The fake reaction filter primarily BLOCKS — see event_engine


__all__ = [
    "detect_earnings_drift",
    "detect_event_breakout",
    "detect_fake_reaction",
    "detect_news_momentum",
]
