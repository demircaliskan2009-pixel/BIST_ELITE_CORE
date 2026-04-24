"""Event Scorer — score events with price + volume confirmation.

event_score = sentiment_score * importance_weight * price_confirmation * volume_confirmation

All confirmations are derived from OHLCV data at or before the event timestamp.
No lookahead. Deterministic.

Price confirmation: Was there already directional price movement aligned with
                    the event sentiment? (momentum confirmation)
Volume confirmation: Is volume elevated vs recent average? (market attention)
"""

from __future__ import annotations

from typing import Final, Sequence

from bist_core.events.event_types import ClassifiedEvent, Sentiment
from bist_core.models.ohlcv import OHLCVBar

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VOL_LOOKBACK: Final[int] = 20       # bars for average volume
_PRICE_LOOKBACK: Final[int] = 5      # bars for price return
_VOL_CONFIRM_THRESHOLD: Final[float] = 1.2  # volume must be 1.2x avg
_PRICE_CONFIRM_PCT: Final[float] = 0.005    # 0.5% move in sentiment direction


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------


def _volume_confirmation(bars: Sequence[OHLCVBar]) -> float:
    """Compute volume confirmation factor (0.5 - 1.5).

    1.5 if current volume >> average (strong market attention)
    0.5 if volume below average (low attention)
    1.0 if around average
    """
    if len(bars) < _VOL_LOOKBACK + 1:
        return 1.0  # neutral if insufficient data

    avg_vol = sum(float(b.volume) for b in bars[-_VOL_LOOKBACK - 1:-1]) / _VOL_LOOKBACK
    if avg_vol <= 0:
        return 1.0

    current_vol = float(bars[-1].volume)
    ratio = current_vol / avg_vol

    if ratio >= 2.0:
        return 1.5
    elif ratio >= _VOL_CONFIRM_THRESHOLD:
        return 1.0 + (ratio - _VOL_CONFIRM_THRESHOLD) * 0.625  # linear 1.0-1.5
    elif ratio >= 0.5:
        return 0.5 + ratio  # linear 0.5-1.0
    else:
        return 0.5


def _price_confirmation(bars: Sequence[OHLCVBar], sentiment: Sentiment) -> float:
    """Compute price confirmation factor (0.5 - 1.5).

    Checks if recent price action aligns with event sentiment.
    Positive event + rising price → higher confirmation.
    Positive event + falling price → lower confirmation.
    """
    if len(bars) < _PRICE_LOOKBACK + 1:
        return 1.0

    recent_close = float(bars[-1].close)
    past_close = float(bars[-_PRICE_LOOKBACK - 1].close)
    if past_close <= 0:
        return 1.0

    ret = (recent_close - past_close) / past_close

    if sentiment == Sentiment.POSITIVE:
        if ret > _PRICE_CONFIRM_PCT:
            return min(1.5, 1.0 + ret * 20)  # scale up
        elif ret < -_PRICE_CONFIRM_PCT:
            return max(0.5, 1.0 + ret * 10)  # slight penalty
        return 1.0
    elif sentiment == Sentiment.NEGATIVE:
        if ret < -_PRICE_CONFIRM_PCT:
            return min(1.5, 1.0 + abs(ret) * 20)  # negative price confirms negative event
        elif ret > _PRICE_CONFIRM_PCT:
            return max(0.5, 1.0 - ret * 10)
        return 1.0
    else:
        return 1.0


def score_event(
    classified: ClassifiedEvent,
    bars: Sequence[OHLCVBar],
) -> float:
    """Compute final event score with price + volume confirmation.

    Returns: Score in range [-1.5, +1.5].
             Magnitude indicates strength, sign indicates direction.
    """
    if not bars:
        # No price data → return unconfirmed composite
        return classified.composite_score

    vol_conf = _volume_confirmation(bars)
    price_conf = _price_confirmation(bars, classified.sentiment)

    # event_score = sentiment_score * importance_weight * price_confirmation * volume_confirmation
    score = (
        classified.sentiment_score
        * classified.impact_weight
        * price_conf
        * vol_conf
    )

    return round(score, 4)


def score_events(
    classified_events: Sequence[ClassifiedEvent],
    bars_by_symbol: dict[str, Sequence[OHLCVBar]],
) -> list[tuple[ClassifiedEvent, float]]:
    """Score a batch of classified events.

    Args:
        classified_events: Events to score.
        bars_by_symbol: Recent bars (up to event time) per symbol.

    Returns:
        List of (classified_event, score) tuples.
    """
    results: list[tuple[ClassifiedEvent, float]] = []
    for cev in classified_events:
        bars = bars_by_symbol.get(cev.event.symbol, [])
        score = score_event(cev, bars)
        results.append((cev, score))
    return results


__all__ = [
    "score_event",
    "score_events",
]
