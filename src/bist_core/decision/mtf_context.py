"""MTF (Multi-Timeframe) Context Engine — daily → hourly → 5min → 1min cascade.

Produces a deterministic MTFContext at each base-timeframe bar that encodes:
  - daily_regime: BULL / BEAR / RANGE (from .G daily SMA cross + volatility)
  - hourly_trend: UP / DOWN / FLAT (from .60 hourly EMA slope + momentum)
  - m5_setup: boolean setup conditions (from .05 5-min patterns)
  - m1_entry: entry timing context (from .01 1-min microstructure)

NO LOOKAHEAD: every higher-TF value uses only completed bars (timestamp < current bar).
All computations are pure functions over price arrays — no side effects, no randomness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Sequence

from bist_core.models.ohlcv import OHLCVBar

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Daily regime
_REGIME_SMA_SHORT: Final[int] = 20
_REGIME_SMA_LONG: Final[int] = 50
_REGIME_ATR_PERIOD: Final[int] = 14
_REGIME_VOL_THRESHOLD: Final[float] = 0.035  # daily return stddev

# Hourly trend
_TREND_EMA_FAST: Final[int] = 8
_TREND_EMA_SLOW: Final[int] = 21
_TREND_SLOPE_LOOKBACK: Final[int] = 3
_TREND_FLAT_THRESHOLD: Final[float] = 0.001

# 5-min setup
_SETUP_RSI_PERIOD: Final[int] = 14
_SETUP_RSI_OVERSOLD: Final[float] = 35.0
_SETUP_RSI_OVERBOUGHT: Final[float] = 70.0
_SETUP_BB_PERIOD: Final[int] = 20
_SETUP_BB_STD: Final[float] = 2.0

# 1-min entry
_ENTRY_VWAP_LOOKBACK: Final[int] = 60  # rolling VWAP window
_ENTRY_VOL_SPIKE_RATIO: Final[float] = 2.0


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class DailyRegime:
    """Daily market regime classification."""
    regime: str  # "BULL", "BEAR", "RANGE"
    sma_short: float
    sma_long: float
    atr: float
    daily_vol: float
    trend_strength: float  # (sma_short - sma_long) / sma_long


@dataclass(frozen=True, slots=True)
class HourlyTrend:
    """Hourly trend direction."""
    direction: str  # "UP", "DOWN", "FLAT"
    ema_fast: float
    ema_slow: float
    slope: float  # EMA fast slope (normalized)
    momentum: float  # close / ema_slow - 1
    atr: float  # average true range in price units


@dataclass(frozen=True, slots=True)
class M5Setup:
    """5-minute setup conditions."""
    rsi: float
    bb_position: float  # (close - bb_lower) / (bb_upper - bb_lower)
    is_oversold: bool
    is_overbought: bool
    near_bb_lower: bool  # close within 10% of lower band
    near_bb_upper: bool
    volume_ratio: float  # current vol / avg vol


@dataclass(frozen=True, slots=True)
class M1Entry:
    """1-minute entry timing context."""
    vwap: float
    price_vs_vwap: float  # (close - vwap) / vwap
    vol_spike: bool  # volume > 2x average
    bar_range_pct: float  # (high - low) / close
    recent_trend: float  # 5-bar close momentum


@dataclass(frozen=True, slots=True)
class MTFContext:
    """Complete multi-timeframe context at a given bar."""
    timestamp: int
    symbol: str
    daily: DailyRegime | None
    hourly: HourlyTrend | None
    m5: M5Setup | None
    m1: M1Entry | None

    @property
    def regime_allows_long(self) -> bool:
        """Daily regime must not be BEAR to allow long entries."""
        if self.daily is None:
            return False
        return self.daily.regime != "BEAR"

    @property
    def trend_aligned_long(self) -> bool:
        """Hourly trend must be UP for trend-following entries."""
        if self.hourly is None:
            return False
        return self.hourly.direction == "UP"

    @property
    def setup_ready(self) -> bool:
        """At least one 5-min setup condition is active."""
        if self.m5 is None:
            return False
        return self.m5.is_oversold or self.m5.near_bb_lower or self.m5.volume_ratio > 1.5

    @property
    def confidence(self) -> float:
        """Aggregate confidence score 0–1 from all timeframes."""
        score = 0.0
        if self.daily is not None:
            if self.daily.regime == "BULL":
                score += 0.30
            elif self.daily.regime == "RANGE":
                score += 0.15
        if self.hourly is not None:
            if self.hourly.direction == "UP":
                score += 0.30
            elif self.hourly.direction == "FLAT":
                score += 0.10
        if self.m5 is not None:
            if self.m5.is_oversold or self.m5.near_bb_lower:
                score += 0.20
            if self.m5.volume_ratio > 1.3:
                score += 0.10
        if self.m1 is not None:
            if self.m1.price_vs_vwap < 0 and self.m1.vol_spike:
                score += 0.10
        return min(1.0, score)


# ---------------------------------------------------------------------------
# Pure computation helpers
# ---------------------------------------------------------------------------

def _sma(values: Sequence[float], period: int) -> float:
    if len(values) < period:
        return 0.0
    return sum(values[-period:]) / period


def _ema(values: Sequence[float], period: int) -> float:
    if not values:
        return 0.0
    if len(values) < period:
        return sum(values) / len(values)
    k = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
    return ema


def _ema_series(values: Sequence[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2.0 / (period + 1)
    result: list[float] = []
    if len(values) < period:
        s = sum(values) / len(values)
        result = [s] * len(values)
        return result
    ema = sum(values[:period]) / period
    for i in range(period):
        result.append(ema)
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
        result.append(ema)
    return result


def _atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int) -> float:
    n = len(closes)
    if n < period + 1:
        return 0.0
    trs: list[float] = []
    for i in range(n - period, n):
        if i == 0:
            trs.append(highs[i] - lows[i])
        else:
            h, l, pc = highs[i], lows[i], closes[i - 1]
            tr = max(h - l, abs(h - pc), abs(l - pc))
            trs.append(tr)
    return sum(trs) / len(trs) if trs else 0.0


def _rsi(closes: Sequence[float], period: int) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains: list[float] = []
    losses: list[float] = []
    for i in range(len(closes) - period, len(closes)):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(diff))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def _stddev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    return var ** 0.5


def _daily_returns_stddev(closes: Sequence[float], lookback: int) -> float:
    if len(closes) < lookback + 1:
        return 0.0
    rets: list[float] = []
    for i in range(len(closes) - lookback, len(closes)):
        if closes[i - 1] > 0:
            rets.append((closes[i] - closes[i - 1]) / closes[i - 1])
    return _stddev(rets, ) if rets else 0.0


# ---------------------------------------------------------------------------
# Regime / Trend / Setup / Entry builders
# ---------------------------------------------------------------------------

def compute_daily_regime(daily_bars: Sequence[OHLCVBar]) -> DailyRegime | None:
    """Compute daily regime from the last N daily bars (NO LOOKAHEAD)."""
    if len(daily_bars) < _REGIME_SMA_LONG:
        return None

    closes = [float(b.close) for b in daily_bars]
    highs = [float(b.high) for b in daily_bars]
    lows = [float(b.low) for b in daily_bars]

    sma_s = _sma(closes, _REGIME_SMA_SHORT)
    sma_l = _sma(closes, _REGIME_SMA_LONG)
    atr = _atr(highs, lows, closes, _REGIME_ATR_PERIOD)
    d_vol = _daily_returns_stddev(closes, 20)

    if sma_l > 0:
        strength = (sma_s - sma_l) / sma_l
    else:
        strength = 0.0

    if d_vol > _REGIME_VOL_THRESHOLD:
        regime = "RANGE"  # high volatility = uncertain regime
    elif sma_s > sma_l and strength > 0.01:
        regime = "BULL"
    elif sma_s < sma_l and strength < -0.01:
        regime = "BEAR"
    else:
        regime = "RANGE"

    return DailyRegime(
        regime=regime,
        sma_short=round(sma_s, 4),
        sma_long=round(sma_l, 4),
        atr=round(atr, 4),
        daily_vol=round(d_vol, 6),
        trend_strength=round(strength, 6),
    )


def compute_hourly_trend(hourly_bars: Sequence[OHLCVBar]) -> HourlyTrend | None:
    """Compute hourly trend from the last N hourly bars (NO LOOKAHEAD)."""
    if len(hourly_bars) < _TREND_EMA_SLOW:
        return None

    closes = [float(b.close) for b in hourly_bars]
    ema_f = _ema(closes, _TREND_EMA_FAST)
    ema_s = _ema(closes, _TREND_EMA_SLOW)

    # Slope of EMA fast over last N bars
    ema_series = _ema_series(closes, _TREND_EMA_FAST)
    if len(ema_series) >= _TREND_SLOPE_LOOKBACK + 1:
        slope_vals = ema_series[-_TREND_SLOPE_LOOKBACK:]
        if slope_vals[0] > 0:
            slope = (slope_vals[-1] - slope_vals[0]) / slope_vals[0]
        else:
            slope = 0.0
    else:
        slope = 0.0

    current_close = closes[-1]
    if ema_s > 0:
        momentum = (current_close - ema_s) / ema_s
    else:
        momentum = 0.0

    if ema_f > ema_s and slope > _TREND_FLAT_THRESHOLD:
        direction = "UP"
    elif ema_f < ema_s and slope < -_TREND_FLAT_THRESHOLD:
        direction = "DOWN"
    else:
        direction = "FLAT"

    # Hourly ATR
    highs = [float(b.high) for b in hourly_bars]
    lows = [float(b.low) for b in hourly_bars]
    h_atr = _atr(highs, lows, closes, min(14, len(closes) - 1))

    return HourlyTrend(
        direction=direction,
        ema_fast=round(ema_f, 4),
        ema_slow=round(ema_s, 4),
        slope=round(slope, 6),
        momentum=round(momentum, 6),
        atr=round(h_atr, 4),
    )


def compute_m5_setup(m5_bars: Sequence[OHLCVBar]) -> M5Setup | None:
    """Compute 5-min setup from the last N bars (NO LOOKAHEAD)."""
    if len(m5_bars) < _SETUP_BB_PERIOD:
        return None

    closes = [float(b.close) for b in m5_bars]
    volumes = [float(b.volume) for b in m5_bars]

    rsi = _rsi(closes, _SETUP_RSI_PERIOD)

    # Bollinger Bands
    bb_closes = closes[-_SETUP_BB_PERIOD:]
    bb_mean = sum(bb_closes) / len(bb_closes)
    bb_std = _stddev(bb_closes)
    bb_upper = bb_mean + _SETUP_BB_STD * bb_std
    bb_lower = bb_mean - _SETUP_BB_STD * bb_std

    current_close = closes[-1]
    bb_range = bb_upper - bb_lower
    if bb_range > 0:
        bb_pos = (current_close - bb_lower) / bb_range
    else:
        bb_pos = 0.5

    # Volume ratio
    avg_vol = sum(volumes[-20:]) / min(20, len(volumes[-20:])) if volumes else 0
    vol_ratio = volumes[-1] / avg_vol if avg_vol > 0 else 1.0

    return M5Setup(
        rsi=round(rsi, 2),
        bb_position=round(bb_pos, 4),
        is_oversold=rsi < _SETUP_RSI_OVERSOLD,
        is_overbought=rsi > _SETUP_RSI_OVERBOUGHT,
        near_bb_lower=bb_pos < 0.10,
        near_bb_upper=bb_pos > 0.90,
        volume_ratio=round(vol_ratio, 2),
    )


def compute_m1_entry(m1_bars: Sequence[OHLCVBar]) -> M1Entry | None:
    """Compute 1-min entry context from the last N bars (NO LOOKAHEAD)."""
    if len(m1_bars) < _ENTRY_VWAP_LOOKBACK:
        return None

    recent = m1_bars[-_ENTRY_VWAP_LOOKBACK:]
    closes = [float(b.close) for b in recent]
    volumes = [float(b.volume) for b in recent]
    highs = [float(b.high) for b in recent]
    lows = [float(b.low) for b in recent]

    # VWAP
    total_pv = sum(c * v for c, v in zip(closes, volumes))
    total_v = sum(volumes)
    vwap = total_pv / total_v if total_v > 0 else closes[-1]

    current_close = closes[-1]
    price_vs_vwap = (current_close - vwap) / vwap if vwap > 0 else 0.0

    # Volume spike
    avg_vol = sum(volumes) / len(volumes) if volumes else 0
    vol_spike = volumes[-1] > avg_vol * _ENTRY_VOL_SPIKE_RATIO if avg_vol > 0 else False

    # Bar range
    h, l = highs[-1], lows[-1]
    bar_range_pct = (h - l) / current_close if current_close > 0 else 0.0

    # Recent trend (5-bar momentum)
    if len(closes) >= 6 and closes[-6] > 0:
        recent_trend = (closes[-1] - closes[-6]) / closes[-6]
    else:
        recent_trend = 0.0

    return M1Entry(
        vwap=round(vwap, 4),
        price_vs_vwap=round(price_vs_vwap, 6),
        vol_spike=vol_spike,
        bar_range_pct=round(bar_range_pct, 6),
        recent_trend=round(recent_trend, 6),
    )


# ---------------------------------------------------------------------------
# MTF Context builder (main API)
# ---------------------------------------------------------------------------

class MTFContextEngine:
    """Builds MTFContext from pre-aligned multi-timeframe bars.

    Usage:
        engine = MTFContextEngine()
        ctx = engine.build_context(
            symbol="AKBNK",
            timestamp=unix_ts,
            daily_bars=daily_history[:today_index],     # NO LOOKAHEAD
            hourly_bars=hourly_history[:current_hour],   # NO LOOKAHEAD
            m5_bars=m5_history[:current_5min],            # NO LOOKAHEAD
            m1_bars=m1_history[:current_1min],            # NO LOOKAHEAD
        )
    """

    def build_context(
        self,
        symbol: str,
        timestamp: int,
        daily_bars: Sequence[OHLCVBar] | None = None,
        hourly_bars: Sequence[OHLCVBar] | None = None,
        m5_bars: Sequence[OHLCVBar] | None = None,
        m1_bars: Sequence[OHLCVBar] | None = None,
    ) -> MTFContext:
        """Build complete MTF context. Each bar sequence must end BEFORE timestamp."""
        daily = compute_daily_regime(daily_bars) if daily_bars else None
        hourly = compute_hourly_trend(hourly_bars) if hourly_bars else None
        m5 = compute_m5_setup(m5_bars) if m5_bars else None
        m1 = compute_m1_entry(m1_bars) if m1_bars else None

        return MTFContext(
            timestamp=timestamp,
            symbol=symbol,
            daily=daily,
            hourly=hourly,
            m5=m5,
            m1=m1,
        )


__all__ = [
    "DailyRegime",
    "HourlyTrend",
    "M1Entry",
    "M5Setup",
    "MTFContext",
    "MTFContextEngine",
    "compute_daily_regime",
    "compute_hourly_trend",
    "compute_m1_entry",
    "compute_m5_setup",
]
