"""Expansion Intraday Edges — 5 BIST-structural alpha edges.

Complements existing edges (opening_drive, intraday_momentum) by covering
different market conditions and entry styles:

  6. vol_contraction_breakout — volatility squeeze into range expansion
  7. daily_high_breakout — multi-day high breakout (higher timeframe signal)
  8. pullback_continuation — buy dips in confirmed m1 uptrends
  9. intraday_mean_reversion — oversold bounce within session
 10. afternoon_momentum — late session institutional flow breakout

All edges:
- BIST-specific structural hypotheses (not curve-fit)
- Use only completed bars (no lookahead)
- Deterministic logic
- Use _make_signal with 3%/5% fixed stops (same as existing edges)
- Respect BIST session hours (09:55–18:00 TRT)
- Soft MTF gating (block only strong BEAR, not hard binary gates)

IntraEdgeExpansion maintains rolling session/daily state that cannot
be derived from the 200-bar m1 buffer alone (session high, multi-day
highs, morning range statistics).
"""

from __future__ import annotations

from typing import Final, Sequence

from bist_core.decision.intraday_edges import (
    IntradaySignal,
    _atr_from_bars,
    _avg_volume,
    _bar_range,
    _hourly_atr,
    _is_in_session,
    _make_signal,
    _MIN_CONFIDENCE,
    _mtf_score,
    _rsi_from_bars,
    _SESSION_OPEN_SEC,
    _time_of_day_sec,
    _too_late_for_entry,
)
from bist_core.decision.timeframe_sync import MTFBarEvent
from bist_core.models.ohlcv import OHLCVBar

# ---------------------------------------------------------------------------
# Constants — Expansion edges
# ---------------------------------------------------------------------------

# --- Edge 6: Volatility Contraction Breakout ---
_VCB_ATR_SHORT: Final[int] = 30
_VCB_ATR_LONG: Final[int] = 120
_VCB_CONTRACTION: Final[float] = 0.65
_VCB_BREAKOUT_BARS: Final[int] = 60
_VCB_VOLUME_RATIO: Final[float] = 1.3
_VCB_MIN_AFTER_OPEN: Final[int] = 35 * 60  # 35 min after open → 10:30 TRT

# --- Edge 7: Daily High Breakout ---
_DHB_MIN_AFTER_OPEN: Final[int] = 35 * 60
_DHB_VOLUME_RATIO: Final[float] = 1.2

# --- Edge 8: Pullback Continuation ---
_PBC_SMA_SHORT: Final[int] = 10
_PBC_SMA_LONG: Final[int] = 40
_PBC_VOLUME_FLOOR: Final[float] = 0.8

# --- Edge 9: Intraday Mean Reversion ---
_IMR_DECLINE_PCT: Final[float] = 0.015
_IMR_RSI_THRESHOLD: Final[float] = 35.0
_IMR_CLOSE_POSITION: Final[float] = 0.6
_IMR_VOLUME_RATIO: Final[float] = 1.2

# --- Edge 10: Afternoon Momentum ---
_AFM_AFTER_SEC: Final[int] = 14 * 3600  # 14:00 TRT
_AFM_VOLUME_RATIO: Final[float] = 1.2


# ---------------------------------------------------------------------------
# Expansion state tracker
# ---------------------------------------------------------------------------


class IntraEdgeExpansion:
    """Rolling state for expansion edges that exceed 200-bar buffer scope.

    Tracks per-symbol session-level and multi-day statistics needed by
    daily_high_breakout, intraday_mean_reversion, and afternoon_momentum.

    Call update(bar) BEFORE edge detection at each bar.
    """

    def __init__(self) -> None:
        self._session_high: dict[str, float] = {}
        self._session_low: dict[str, float] = {}
        self._session_open: dict[str, float] = {}
        self._session_day: dict[str, int] = {}

        # Morning range (before 14:00 TRT)
        self._morning_high: dict[str, float] = {}
        self._morning_vol_sum: dict[str, float] = {}
        self._morning_bar_count: dict[str, int] = {}

        # Multi-day rolling highs (for daily_high_breakout)
        self._daily_highs: dict[str, list[float]] = {}

    def update(self, bar: OHLCVBar) -> None:
        """Update state with new bar. Call BEFORE edge detection."""
        sym = bar.symbol
        day_id = (bar.timestamp + 3 * 3600) // 86400
        tod = (bar.timestamp + 3 * 3600) % 86400

        h = float(bar.high)
        l = float(bar.low)
        o = float(bar.open)
        v = float(bar.volume)

        if self._session_day.get(sym) != day_id:
            # New session: archive yesterday's high, reset
            if sym in self._session_high:
                self._daily_highs.setdefault(sym, []).append(
                    self._session_high[sym]
                )
                if len(self._daily_highs[sym]) > 10:
                    self._daily_highs[sym] = self._daily_highs[sym][-10:]

            self._session_high[sym] = h
            self._session_low[sym] = l
            self._session_open[sym] = o
            self._session_day[sym] = day_id
            self._morning_high[sym] = 0.0
            self._morning_vol_sum[sym] = 0.0
            self._morning_bar_count[sym] = 0
        else:
            self._session_high[sym] = max(self._session_high[sym], h)
            self._session_low[sym] = min(self._session_low[sym], l)

        # Morning stats (before 14:00 TRT)
        if tod < _AFM_AFTER_SEC:
            self._morning_high[sym] = max(
                self._morning_high.get(sym, 0.0), h
            )
            self._morning_vol_sum[sym] = (
                self._morning_vol_sum.get(sym, 0.0) + v
            )
            self._morning_bar_count[sym] = (
                self._morning_bar_count.get(sym, 0) + 1
            )

    def get_multi_day_high(self, sym: str, n_days: int = 5) -> float:
        """Highest high of last N complete sessions."""
        highs = self._daily_highs.get(sym, [])
        if not highs:
            return 0.0
        return max(highs[-n_days:])

    def get_session_high(self, sym: str) -> float:
        return self._session_high.get(sym, 0.0)

    def get_session_open(self, sym: str) -> float:
        return self._session_open.get(sym, 0.0)

    def get_morning_high(self, sym: str) -> float:
        return self._morning_high.get(sym, 0.0)

    def get_morning_avg_vol(self, sym: str) -> float:
        count = self._morning_bar_count.get(sym, 0)
        if count == 0:
            return 0.0
        return self._morning_vol_sum.get(sym, 0.0) / count


# ---------------------------------------------------------------------------
# Edge 6: Volatility Contraction Breakout
# ---------------------------------------------------------------------------


def detect_vol_contraction_breakout(
    event: MTFBarEvent,
    m1_history: Sequence[OHLCVBar],
    expansion: IntraEdgeExpansion,
) -> IntradaySignal | None:
    """Volatility squeeze into range expansion breakout.

    Hypothesis: After compressed volatility, the first breakout signals
    a regime change. Institutional accumulation during compression creates
    order-flow imbalance on expansion.

    Target symbols: cyclical/industrial names (EREGL, SISE, TUPRS) that
    alternate between compression and directional moves.
    """
    bar = event.bar
    ctx = event.context
    tod = _time_of_day_sec(bar.timestamp)

    if tod < _SESSION_OPEN_SEC + _VCB_MIN_AFTER_OPEN:
        return None
    if _too_late_for_entry(bar.timestamp):
        return None
    if not _is_in_session(bar.timestamp):
        return None

    if ctx.daily is not None and ctx.daily.regime == "BEAR":
        if ctx.daily.trend_strength < -0.03:
            return None
    if ctx.confidence < _MIN_CONFIDENCE:
        return None

    if len(m1_history) < _VCB_ATR_LONG + 5:
        return None

    # ATR contraction: short ATR < 65% of long ATR
    atr_short = _atr_from_bars(
        list(m1_history[-(_VCB_ATR_SHORT + 5) :]), period=_VCB_ATR_SHORT
    )
    atr_long = _atr_from_bars(
        list(m1_history[-(_VCB_ATR_LONG + 5) :]), period=_VCB_ATR_LONG
    )

    if atr_long <= 0 or atr_short / atr_long >= _VCB_CONTRACTION:
        return None

    # Breakout above 60-bar high
    recent = m1_history[-_VCB_BREAKOUT_BARS:]
    recent_high = max(float(b.high) for b in recent)
    close = float(bar.close)

    if close <= recent_high:
        return None

    # Volume confirmation
    avg_vol = _avg_volume(m1_history, lookback=60)
    bar_vol = float(bar.volume)
    if avg_vol <= 0 or bar_vol / avg_vol < _VCB_VOLUME_RATIO:
        return None

    mtf = _mtf_score(ctx)
    atr = _atr_from_bars(list(m1_history[-20:]), 14)

    contraction = atr_short / atr_long
    return _make_signal(
        bar=bar,
        edge="vol_contraction_breakout",
        direction="LONG",
        entry=close,
        atr=atr,
        confidence=ctx.confidence,
        reason=(
            f"VCB: contraction={contraction:.2f}, "
            f"vol_r={bar_vol / avg_vol:.1f}, mtf={mtf:.2f}"
        ),
        mtf_mult=mtf,
        hourly_atr=_hourly_atr(ctx),
    )


# ---------------------------------------------------------------------------
# Edge 7: Daily High Breakout
# ---------------------------------------------------------------------------


def detect_daily_high_breakout(
    event: MTFBarEvent,
    m1_history: Sequence[OHLCVBar],
    expansion: IntraEdgeExpansion,
) -> IntradaySignal | None:
    """Multi-day high breakout — higher timeframe significance.

    Hypothesis: Breaking above a 5-day high is more meaningful than a
    60-bar (1-hour) high. Multi-day breakouts signal sustained demand
    that persists through overnight gaps.

    Uses expansion state for multi-day high tracking (avoids needing
    2400+ bar buffer).
    """
    bar = event.bar
    ctx = event.context
    sym = bar.symbol
    tod = _time_of_day_sec(bar.timestamp)

    if tod < _SESSION_OPEN_SEC + _DHB_MIN_AFTER_OPEN:
        return None
    if _too_late_for_entry(bar.timestamp):
        return None
    if not _is_in_session(bar.timestamp):
        return None

    if ctx.daily is not None and ctx.daily.regime == "BEAR":
        if ctx.daily.trend_strength < -0.03:
            return None
    if ctx.confidence < _MIN_CONFIDENCE:
        return None

    five_day_high = expansion.get_multi_day_high(sym, n_days=5)
    if five_day_high <= 0:
        return None

    close = float(bar.close)
    if close <= five_day_high:
        return None

    # Volume confirmation
    avg_vol = _avg_volume(m1_history, lookback=60)
    bar_vol = float(bar.volume)
    if avg_vol <= 0 or bar_vol / avg_vol < _DHB_VOLUME_RATIO:
        return None

    mtf = _mtf_score(ctx)
    atr = _atr_from_bars(list(m1_history[-20:]), 14)

    breakout_pct = (close - five_day_high) / five_day_high
    return _make_signal(
        bar=bar,
        edge="daily_high_breakout",
        direction="LONG",
        entry=close,
        atr=atr,
        confidence=ctx.confidence,
        reason=(
            f"DHB: +{breakout_pct:.3f} above 5d high={five_day_high:.2f}, "
            f"vol_r={bar_vol / avg_vol:.1f}, mtf={mtf:.2f}"
        ),
        mtf_mult=mtf,
        hourly_atr=_hourly_atr(ctx),
    )


# ---------------------------------------------------------------------------
# Edge 8: Pullback Continuation
# ---------------------------------------------------------------------------


def detect_pullback_continuation(
    event: MTFBarEvent,
    m1_history: Sequence[OHLCVBar],
    expansion: IntraEdgeExpansion,
) -> IntradaySignal | None:
    """Trend pullback entry — buy dips in m1 uptrends.

    Hypothesis: In a confirmed uptrend (rising SMAs), buying a pullback
    provides a better entry price than chasing breakouts. The 3% stop
    is less likely to trigger when entering at a support-tested level.

    Target symbols: cyclical stocks where breakout entries fail because
    price is already extended by the time the breakout triggers.
    """
    bar = event.bar
    ctx = event.context

    if _too_late_for_entry(bar.timestamp):
        return None
    if not _is_in_session(bar.timestamp):
        return None

    # Block only strong BEAR (same as existing edges)
    if ctx.daily is not None and ctx.daily.regime == "BEAR":
        if ctx.daily.trend_strength < -0.03:
            return None
    if ctx.confidence < _MIN_CONFIDENCE:
        return None

    if len(m1_history) < _PBC_SMA_LONG + 5:
        return None

    # Compute SMAs from prior bars
    closes = [float(b.close) for b in m1_history[-_PBC_SMA_LONG:]]
    sma_short = sum(closes[-_PBC_SMA_SHORT:]) / _PBC_SMA_SHORT
    sma_long = sum(closes) / _PBC_SMA_LONG

    # Uptrend: short SMA above long SMA
    if sma_short <= sma_long:
        return None

    close = float(bar.close)
    bar_low = float(bar.low)
    bar_open = float(bar.open)

    # Pullback: bar low dipped below short SMA
    if bar_low >= sma_short:
        return None

    # Recovery: close back above short SMA
    if close <= sma_short:
        return None

    # Bullish close
    if close <= bar_open:
        return None

    # Volume not collapsed
    avg_vol = _avg_volume(m1_history, lookback=60)
    bar_vol = float(bar.volume)
    if avg_vol <= 0 or bar_vol / avg_vol < _PBC_VOLUME_FLOOR:
        return None

    mtf = _mtf_score(ctx)
    atr = _atr_from_bars(list(m1_history[-20:]), 14)

    pullback_pct = (sma_short - bar_low) / sma_short if sma_short > 0 else 0
    return _make_signal(
        bar=bar,
        edge="pullback_continuation",
        direction="LONG",
        entry=close,
        atr=atr,
        confidence=ctx.confidence,
        reason=(
            f"PBC: pullback={pullback_pct:.3f}, "
            f"sma_s={sma_short:.2f}>sma_l={sma_long:.2f}, mtf={mtf:.2f}"
        ),
        mtf_mult=mtf,
        hourly_atr=_hourly_atr(ctx),
    )


# ---------------------------------------------------------------------------
# Edge 9: Intraday Mean Reversion
# ---------------------------------------------------------------------------


def detect_intraday_mean_reversion(
    event: MTFBarEvent,
    m1_history: Sequence[OHLCVBar],
    expansion: IntraEdgeExpansion,
) -> IntradaySignal | None:
    """Oversold bounce — mean reversion for cyclical/commodity stocks.

    Hypothesis: After sharp intraday declines in non-BEAR markets,
    BIST stocks tend to revert. Buying the bounce captures institutional
    dip-buying, especially on liquid commodity-linked names.

    Target symbols: EREGL, SISE, PETKM, TUPRS — cyclical/industrial
    names where breakout strategies fail but reversal entries succeed.
    """
    bar = event.bar
    ctx = event.context
    sym = bar.symbol

    if _too_late_for_entry(bar.timestamp):
        return None
    if not _is_in_session(bar.timestamp):
        return None

    # Block in BEAR (mean reversion fails in downtrends)
    if ctx.daily is not None and ctx.daily.regime == "BEAR":
        return None
    if ctx.confidence < _MIN_CONFIDENCE:
        return None

    if len(m1_history) < 30:
        return None

    # Session high from expansion state
    session_high = expansion.get_session_high(sym)
    if session_high <= 0:
        return None

    close = float(bar.close)

    # Decline from session high exceeds threshold
    decline_pct = (session_high - close) / session_high
    if decline_pct < _IMR_DECLINE_PCT:
        return None

    # RSI oversold
    rsi = _rsi_from_bars(list(m1_history[-30:]))
    if rsi > _IMR_RSI_THRESHOLD:
        return None

    # Bullish recovery bar
    bar_rng = _bar_range(bar)
    if bar_rng <= 0:
        return None
    close_position = (close - float(bar.low)) / bar_rng
    if close_position < _IMR_CLOSE_POSITION:
        return None
    if close <= float(bar.open):
        return None

    # Volume on bounce
    avg_vol = _avg_volume(m1_history, lookback=60)
    bar_vol = float(bar.volume)
    if avg_vol <= 0 or bar_vol / avg_vol < _IMR_VOLUME_RATIO:
        return None

    mtf = _mtf_score(ctx)
    atr = _atr_from_bars(list(m1_history[-20:]), 14)

    return _make_signal(
        bar=bar,
        edge="intraday_mean_reversion",
        direction="LONG",
        entry=close,
        atr=atr,
        confidence=ctx.confidence,
        reason=(
            f"IMR: decline={decline_pct:.3f}, RSI={rsi:.0f}, "
            f"close_pos={close_position:.2f}, mtf={mtf:.2f}"
        ),
        mtf_mult=mtf,
        hourly_atr=_hourly_atr(ctx),
    )


# ---------------------------------------------------------------------------
# Edge 10: Afternoon Momentum
# ---------------------------------------------------------------------------


def detect_afternoon_momentum(
    event: MTFBarEvent,
    m1_history: Sequence[OHLCVBar],
    expansion: IntraEdgeExpansion,
) -> IntradaySignal | None:
    """Afternoon session breakout — institutional closing flow.

    Hypothesis: BIST afternoon session has lower noise. Breakouts above
    morning range on volume signal late institutional positioning for
    close/next-day settlement, often followed by overnight gap.

    Structural basis: Foreign fund order flow concentrates in afternoon
    for next-day settlement; closing auction creates momentum.
    """
    bar = event.bar
    ctx = event.context
    sym = bar.symbol
    tod = _time_of_day_sec(bar.timestamp)

    # Must be afternoon (after 14:00 TRT)
    if tod < _AFM_AFTER_SEC:
        return None
    if _too_late_for_entry(bar.timestamp):
        return None
    if not _is_in_session(bar.timestamp):
        return None

    if ctx.daily is not None and ctx.daily.regime == "BEAR":
        if ctx.daily.trend_strength < -0.03:
            return None
    if ctx.confidence < _MIN_CONFIDENCE:
        return None

    # Breakout above morning high
    morning_high = expansion.get_morning_high(sym)
    if morning_high <= 0:
        return None

    close = float(bar.close)
    if close <= morning_high:
        return None

    # Volume above morning average
    morning_avg = expansion.get_morning_avg_vol(sym)
    bar_vol = float(bar.volume)
    if morning_avg <= 0 or bar_vol / morning_avg < _AFM_VOLUME_RATIO:
        return None

    # Close above session open (positive day)
    session_open = expansion.get_session_open(sym)
    if session_open > 0 and close <= session_open:
        return None

    mtf = _mtf_score(ctx)
    atr = _atr_from_bars(list(m1_history[-20:]), 14)

    breakout_pct = (close - morning_high) / morning_high
    return _make_signal(
        bar=bar,
        edge="afternoon_momentum",
        direction="LONG",
        entry=close,
        atr=atr,
        confidence=ctx.confidence,
        reason=(
            f"AFM: +{breakout_pct:.3f} above morning high, "
            f"vol_r={bar_vol / morning_avg:.1f}, mtf={mtf:.2f}"
        ),
        mtf_mult=mtf,
        hourly_atr=_hourly_atr(ctx),
    )


__all__ = [
    "IntraEdgeExpansion",
    "detect_afternoon_momentum",
    "detect_daily_high_breakout",
    "detect_intraday_mean_reversion",
    "detect_pullback_continuation",
    "detect_vol_contraction_breakout",
]
