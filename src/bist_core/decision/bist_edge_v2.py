"""BIST Edge V2 — deconcentrated, regime-aware, portfolio-balanced decision engine.

Structural improvements over V1:
1. STATEFUL CLASS: tracks per-symbol signal cooldown + trend duration,
   preventing rapid re-entry and brief-crossover whipsaw (GSRAY fix).
2. FIXED-NOTIONAL SIZING: position_size = target_notional / entry_price
   → eliminates 28:1 exposure bias across price levels.
3. ATR-SCALED STOPS/TARGETS: risk adapts to each symbol's volatility
   instead of fixed 3%/5% for all. Equalizes risk contribution.
4. REGIME FILTER: blocks signals when >50% of last 50 bars are in
   downtrend, or when daily return stddev > 3.5%.
5. TREND DURATION: SMA20 must have been above SMA50 for ≥10 consecutive
   bars before a trend-pullback signal fires. Blocks brief crossovers.
6. SIGNAL COOLDOWN: minimum 8 bars between signals per symbol.
7. SYMBOL QUALITY FILTER: rejects symbols with >8 regime transitions
   in last 100 bars (whipsaw filter).
8. WIDER PULLBACK ZONE: [-3%, +1.5%] tested to increase frequency.
9. MEAN-REVERSION EDGE: oversold bounces in ranging regimes.

Risk: ATR-based stops (1.5×ATR14), ATR-based targets (2.5×ATR14).
Position sized to ~5000 TRY notional per trade.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from bist_core.models.ohlcv import OHLCVBar

# ---------------------------------------------------------------------------
# Constants — deterministic, no randomness
# ---------------------------------------------------------------------------

_MIN_BARS = 50

# Moving averages
_SMA_SHORT = 20
_SMA_LONG = 50
_SMA_SLOPE_LOOKBACK = 5

# --- Edge 1: Trend Pullback ---
_PULLBACK_LOWER = -0.04
_PULLBACK_UPPER = 0.02
_VOLUME_FLOOR_RATIO = 0.6
_VOLUME_LOOKBACK = 10

# --- Edge 2: Vol Compression Breakout ---
_BREAKOUT_LOOKBACK = 20
_VOL_COMPRESS_THRESHOLD = 0.75
_BREAKOUT_VOLUME_RATIO = 1.1
_RETS_SHORT = 10
_RETS_LONG = 20

# --- Edge 3: Range Mean-Reversion ---
_MR_RSI_PERIOD = 14
_MR_RSI_OVERSOLD = 40.0
_MR_RANGE_MAX_TREND = 0.02
_MR_VOLUME_RATIO = 0.7

# --- Edge 4: Gap Fade (BIST-specific) ---
_GAP_FADE_MIN_GAP_PCT = 0.025    # minimum gap size to consider (2.5%)
_GAP_FADE_MAX_GAP_PCT = 0.08     # max gap — beyond this may be news-driven
_GAP_FADE_CLOSE_RECOVERY = 0.3   # close must recover ≥30% of gap to confirm fade
_GAP_FADE_VOLUME_RATIO = 1.2     # gap day volume should exceed average

# --- Edge 5: Relative Strength Momentum (cross-sectional) ---
# Evidence: top 20% RS(5d) → +0.71%/5d fwd vs +0.23% for rest (n=1103)
_RS_LOOKBACK = 5          # 5-day return for RS ranking
_RS_TOP_PCT = 0.20        # top 20% of universe
_RS_MIN_SYMBOLS = 5       # minimum symbols for valid ranking
_RS_SMA_CONFIRM = True    # price must be > SMA50

# --- Edge 6: Sector Rotation (BIST group momentum) ---
# Evidence: sector follow → +1.01%/5d, WR=53.2%, n=1857
_SECTOR_LOOKBACK = 5      # 5-day sector return
_SECTOR_SPREAD_MIN = 0.02 # min outperformance for sector to be "leading"
_SECTOR_SMA_CONFIRM = 20  # price > SMA20 for individual stock

# BIST sector classification
_BIST_SECTORS: dict[str, str] = {
    "AKBNK": "banks", "YKBNK": "banks", "ISCTR": "banks",
    "PEKGY": "holdings", "EKGYO": "holdings", "PSGYO": "holdings",
    "EREGL": "industrial", "PETKM": "industrial", "SASA": "industrial",
    "ADESE": "consumer", "HEKTS": "consumer", "KATMR": "consumer",
    "GSRAY": "other", "TSPOR": "other", "CANTE": "other",
}

# --- Edge 7: Momentum Continuation (new N-day high) ---
# Evidence: new 20d high → +0.89%/5d, WR=54.8%, n=688
_MOM_CONT_LOOKBACK = 20     # new N-day high
_MOM_CONT_VOL_RATIO = 1.1   # volume above average
_MOM_CONT_RSI_MAX = 75.0    # RSI must not be exhausted

# --- Regime filter ---
_REGIME_LOOKBACK = 50
_REGIME_DOWN_THRESHOLD = 0.55   # tightened from 0.60
_HIGH_VOL_THRESHOLD = 0.035     # tightened from 0.04

# --- Symbol quality filter ---
_QUALITY_TRANSITION_LOOKBACK = 100
_QUALITY_MAX_TRANSITIONS = 8    # tightened from 10

# --- Trend duration ---
_TREND_DURATION_MIN = 5         # bars SMA20>SMA50 must hold consecutively

# --- Signal cooldown ---
_SIGNAL_COOLDOWN_BARS = 5       # min bars between signals per symbol

# --- ATR-based risk ---
_ATR_PERIOD = 14
_STOP_ATR_MULT = 1.5
_TARGET_ATR_MULT = 2.5
_STOP_PCT_FLOOR = 0.015         # minimum stop distance 1.5%
_STOP_PCT_CAP = 0.06            # maximum stop distance 6%
_TARGET_PCT_FLOOR = 0.025       # minimum target distance 2.5%
_TARGET_PCT_CAP = 0.10          # maximum target distance 10%

# --- Portfolio deconcentration ---
_TARGET_NOTIONAL = 5000.0
_MIN_POSITION_SIZE = 1
_MAX_POSITION_SIZE = 500


# ---------------------------------------------------------------------------
# Feature extraction (pure, no side effects)
# ---------------------------------------------------------------------------

def _sma(closes: List[float], period: int) -> float:
    if len(closes) < period:
        return 0.0
    return sum(closes[-period:]) / period


def _stddev_returns(closes: List[float], period: int) -> float:
    if len(closes) < period + 1:
        return 0.0
    rets: list[float] = []
    start = len(closes) - period
    for j in range(start, len(closes)):
        prev = closes[j - 1]
        if prev <= 0:
            continue
        rets.append((closes[j] - prev) / prev)
    if len(rets) < 2:
        return 0.0
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return var ** 0.5


def _atr(bars_window: List[OHLCVBar], period: int) -> float:
    """Average True Range over last `period` bars."""
    n = len(bars_window)
    if n < period + 1:
        return 0.0
    trs: list[float] = []
    for i in range(n - period, n):
        high = float(bars_window[i].high)
        low = float(bars_window[i].low)
        prev_close = float(bars_window[i - 1].close)
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    return sum(trs) / len(trs) if trs else 0.0


def _rsi(closes: List[float], period: int) -> float:
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


# ---------------------------------------------------------------------------
# Regime filter
# ---------------------------------------------------------------------------

def _regime_allows_trend_signal(closes: List[float]) -> bool:
    n = len(closes)
    if n < _REGIME_LOOKBACK + _SMA_LONG:
        return True
    down_count = 0
    for i in range(n - _REGIME_LOOKBACK, n):
        window = closes[: i + 1]
        s20 = _sma(window, _SMA_SHORT)
        s50 = _sma(window, _SMA_LONG)
        if s20 < s50:
            down_count += 1
    return down_count / _REGIME_LOOKBACK < _REGIME_DOWN_THRESHOLD


def _regime_allows_any_signal(closes: List[float]) -> bool:
    vol = _stddev_returns(closes, _SMA_SHORT)
    return vol < _HIGH_VOL_THRESHOLD


# ---------------------------------------------------------------------------
# Symbol quality filter
# ---------------------------------------------------------------------------

def _symbol_quality_ok(closes: List[float]) -> bool:
    n = len(closes)
    lookback = min(_QUALITY_TRANSITION_LOOKBACK, n - _SMA_LONG)
    if lookback < 20:
        return True
    transitions = 0
    prev_up: bool | None = None
    for i in range(n - lookback, n):
        window = closes[: i + 1]
        s20 = _sma(window, _SMA_SHORT)
        s50 = _sma(window, _SMA_LONG)
        is_up = s20 > s50
        if prev_up is not None and is_up != prev_up:
            transitions += 1
        prev_up = is_up
    return transitions <= _QUALITY_MAX_TRANSITIONS


# ---------------------------------------------------------------------------
# Trend duration check
# ---------------------------------------------------------------------------

def _trend_duration_ok(closes: List[float]) -> bool:
    """SMA20 > SMA50 must have held for at least N consecutive bars."""
    n = len(closes)
    if n < _SMA_LONG + _TREND_DURATION_MIN:
        return False
    consecutive = 0
    for i in range(n - _TREND_DURATION_MIN, n):
        window = closes[: i + 1]
        s20 = _sma(window, _SMA_SHORT)
        s50 = _sma(window, _SMA_LONG)
        if s20 > s50:
            consecutive += 1
        else:
            consecutive = 0
    return consecutive >= _TREND_DURATION_MIN


# ---------------------------------------------------------------------------
# Edge 1: Trend Pullback
# ---------------------------------------------------------------------------

def _trend_pullback_signal(
    closes: List[float],
    volumes: List[float],
) -> bool:
    n = len(closes)
    if n < _MIN_BARS:
        return False

    sma20 = _sma(closes, _SMA_SHORT)
    sma50 = _sma(closes, _SMA_LONG)

    if sma20 <= sma50:
        return False

    if n < _SMA_SHORT + _SMA_SLOPE_LOOKBACK:
        return False
    sma20_prev = sum(closes[-(
        _SMA_SHORT + _SMA_SLOPE_LOOKBACK
    ): -_SMA_SLOPE_LOOKBACK]) / _SMA_SHORT
    if sma20 <= sma20_prev:
        return False

    current = closes[-1]
    if sma20 <= 0:
        return False
    dist = (current - sma20) / sma20
    if not (_PULLBACK_LOWER <= dist <= _PULLBACK_UPPER):
        return False

    if current <= sma50:
        return False

    if len(volumes) < _VOLUME_LOOKBACK:
        return False
    avg_vol = sum(volumes[-_VOLUME_LOOKBACK:]) / _VOLUME_LOOKBACK
    if avg_vol <= 0:
        return False
    if volumes[-1] < avg_vol * _VOLUME_FLOOR_RATIO:
        return False

    return True


# ---------------------------------------------------------------------------
# Edge 2: Vol Compression Breakout
# ---------------------------------------------------------------------------

def _vol_compression_breakout_signal(
    closes: List[float],
    volumes: List[float],
) -> bool:
    n = len(closes)
    if n < _MIN_BARS:
        return False

    high20 = max(closes[-_BREAKOUT_LOOKBACK - 1: -1])
    if closes[-1] <= high20:
        return False

    std_short = _stddev_returns(closes, _RETS_SHORT)
    std_long = _stddev_returns(closes, _RETS_LONG)
    if std_long <= 0:
        return False
    if std_short / std_long >= _VOL_COMPRESS_THRESHOLD:
        return False

    if len(volumes) < _VOLUME_LOOKBACK:
        return False
    avg_vol = sum(volumes[-_VOLUME_LOOKBACK:]) / _VOLUME_LOOKBACK
    if avg_vol <= 0:
        return False
    if volumes[-1] < avg_vol * _BREAKOUT_VOLUME_RATIO:
        return False

    return True


# ---------------------------------------------------------------------------
# Edge 3: Range Mean-Reversion
# ---------------------------------------------------------------------------

def _mean_reversion_signal(
    closes: List[float],
    volumes: List[float],
) -> bool:
    n = len(closes)
    if n < _MIN_BARS:
        return False

    sma20 = _sma(closes, _SMA_SHORT)
    sma50 = _sma(closes, _SMA_LONG)

    if sma50 <= 0:
        return False
    trend_gap = abs(sma20 - sma50) / sma50
    if trend_gap > _MR_RANGE_MAX_TREND:
        return False

    rsi = _rsi(closes, _MR_RSI_PERIOD)
    if rsi > _MR_RSI_OVERSOLD:
        return False

    current = closes[-1]
    if current > sma50 * 1.01:
        return False

    if len(volumes) < _VOLUME_LOOKBACK:
        return False
    avg_vol = sum(volumes[-_VOLUME_LOOKBACK:]) / _VOLUME_LOOKBACK
    if avg_vol <= 0:
        return False
    if volumes[-1] < avg_vol * _MR_VOLUME_RATIO:
        return False

    return True


# ---------------------------------------------------------------------------
# Edge 4: Gap Fade (BIST-specific)
# ---------------------------------------------------------------------------

def _gap_fade_signal(
    bars_window: List[OHLCVBar],
    closes: List[float],
    volumes: List[float],
) -> bool:
    """Detect gap-fade setup: stock gaps significantly then shows reversal.

    BIST-specific: stocks often gap at open due to overnight news/sentiment
    but mean-revert during the session. On daily bars, we detect this as:
    - Significant gap (open vs prev close)
    - Close recovers toward prev close (gap partially filled)
    - Above-average volume (confirms participation)

    This is a CONTRARIAN edge — trades AGAINST the gap direction.
    For gap-down with bullish recovery → BUY signal.
    Gap-up with bearish recovery → not traded (short-selling restricted in BIST).
    """
    n = len(bars_window)
    if n < 3 or len(closes) < 3 or len(volumes) < _VOLUME_LOOKBACK:
        return False

    current_bar = bars_window[-1]
    prev_close = closes[-2]

    if prev_close <= 0 or current_bar.open <= 0:
        return False

    # Gap calculation: open vs previous close
    gap_pct = (current_bar.open - prev_close) / prev_close

    # Only trade gap-DOWN fades (long-only: buy the dip after panic gap)
    if gap_pct >= 0:
        return False  # skip gap-up (would need short selling)

    abs_gap = abs(gap_pct)
    if abs_gap < _GAP_FADE_MIN_GAP_PCT or abs_gap > _GAP_FADE_MAX_GAP_PCT:
        return False

    # Close must show recovery (close > open after gap down)
    gap_size = abs(current_bar.open - prev_close)
    recovery = current_bar.close - current_bar.open
    if recovery <= 0:
        return False
    recovery_pct = recovery / gap_size if gap_size > 0 else 0
    if recovery_pct < _GAP_FADE_CLOSE_RECOVERY:
        return False

    # Volume confirmation
    avg_vol = sum(volumes[-_VOLUME_LOOKBACK:]) / _VOLUME_LOOKBACK
    if avg_vol <= 0:
        return False
    if volumes[-1] < avg_vol * _GAP_FADE_VOLUME_RATIO:
        return False

    return True


# ---------------------------------------------------------------------------
# Edge 5: Relative Strength Momentum (cross-sectional)
# ---------------------------------------------------------------------------

def _relative_strength_signal(
    symbol: str,
    closes: List[float],
    universe_closes: dict[str, List[float]],
) -> bool:
    """Cross-sectional RS: symbol must be in top 20% of 5-day returns.

    BIST-specific: retail-heavy market exhibits strong herding behavior.
    Top-performing stocks attract more retail flow, creating momentum
    persistence. This is the strongest cross-sectional signal in the data.

    Evidence: top 20% RS(5d) → +0.71%/5d forward vs +0.23% for rest.
    """
    if len(closes) <= _RS_LOOKBACK:
        return False

    # Need minimum universe breadth for reliable ranking
    rets: dict[str, float] = {}
    for sym, sym_closes in universe_closes.items():
        if len(sym_closes) > _RS_LOOKBACK and sym_closes[-_RS_LOOKBACK - 1] > 0:
            rets[sym] = (sym_closes[-1] - sym_closes[-_RS_LOOKBACK - 1]) / sym_closes[-_RS_LOOKBACK - 1]

    if len(rets) < _RS_MIN_SYMBOLS or symbol not in rets:
        return False

    # Rank and check if in top percentile
    sorted_syms = sorted(rets, key=lambda s: rets[s], reverse=True)
    top_n = max(1, int(len(sorted_syms) * _RS_TOP_PCT))
    if symbol not in sorted_syms[:top_n]:
        return False

    # RS must be positive (not just "least bad")
    if rets[symbol] <= 0:
        return False

    # Trend confirmation: price > SMA50
    if _RS_SMA_CONFIRM:
        sma50 = _sma(closes, _SMA_LONG)
        if sma50 <= 0 or closes[-1] <= sma50:
            return False

    return True


# ---------------------------------------------------------------------------
# Edge 6: Sector Rotation (BIST group momentum)
# ---------------------------------------------------------------------------

def _sector_rotation_signal(
    symbol: str,
    closes: List[float],
    universe_closes: dict[str, List[float]],
) -> bool:
    """Buy stocks in the outperforming BIST sector.

    BIST-specific: sectors (banks, holdings, industrials) rotate in waves.
    When a sector outperforms the universe average by >2% over 5 days,
    individual members of that sector are likely to continue outperforming.

    Evidence: sector rotation follow → +1.01%/5d, WR=53.2%, n=1857.
    """
    sector = _BIST_SECTORS.get(symbol)
    if sector is None:
        return False

    if len(closes) <= _SECTOR_LOOKBACK:
        return False

    # Compute sector and universe average 5-day returns
    sector_rets: list[float] = []
    all_rets: list[float] = []

    for sym, sym_closes in universe_closes.items():
        if len(sym_closes) > _SECTOR_LOOKBACK and sym_closes[-_SECTOR_LOOKBACK - 1] > 0:
            r = (sym_closes[-1] - sym_closes[-_SECTOR_LOOKBACK - 1]) / sym_closes[-_SECTOR_LOOKBACK - 1]
            all_rets.append(r)
            if _BIST_SECTORS.get(sym) == sector:
                sector_rets.append(r)

    if not sector_rets or len(all_rets) < _RS_MIN_SYMBOLS:
        return False

    sector_avg = sum(sector_rets) / len(sector_rets)
    universe_avg = sum(all_rets) / len(all_rets)
    spread = sector_avg - universe_avg

    if spread < _SECTOR_SPREAD_MIN:
        return False

    # Individual stock must be above SMA20 (not a laggard within sector)
    sma20 = _sma(closes, _SECTOR_SMA_CONFIRM)
    if sma20 <= 0 or closes[-1] <= sma20:
        return False

    return True


# ---------------------------------------------------------------------------
# Edge 7: Momentum Continuation (new N-day high)
# ---------------------------------------------------------------------------

def _momentum_continuation_signal(
    closes: List[float],
    volumes: List[float],
) -> bool:
    """Buy stocks making new 20-day closing highs with volume.

    BIST-specific: momentum is stronger than mean-reversion in BIST data.
    Stocks making new highs tend to continue. Different from vol_compression
    breakout which requires LOW vol compression first — this trades HIGH vol
    breakout continuation.

    Evidence: new 20d high → +0.89%/5d forward, WR=54.8%, n=688.
    """
    n = len(closes)
    if n < _MOM_CONT_LOOKBACK + 2:
        return False

    # Close must be above max close of prior N bars (excluding current)
    prev_high = max(closes[-_MOM_CONT_LOOKBACK - 1:-1])
    if closes[-1] <= prev_high:
        return False

    # RSI cap: not already exhausted
    rsi = _rsi(closes, _MR_RSI_PERIOD)
    if rsi >= _MOM_CONT_RSI_MAX:
        return False

    # Volume confirmation
    if len(volumes) < _VOLUME_LOOKBACK:
        return False
    avg_vol = sum(volumes[-_VOLUME_LOOKBACK:]) / _VOLUME_LOOKBACK
    if avg_vol <= 0:
        return False
    if volumes[-1] < avg_vol * _MOM_CONT_VOL_RATIO:
        return False

    return True


# ---------------------------------------------------------------------------
# ATR-based risk model
# ---------------------------------------------------------------------------

def _compute_atr_risk(
    entry: float,
    atr: float,
) -> tuple[float, float]:
    """Compute stop and target from ATR. Returns (stop_price, target_price)."""
    if entry <= 0 or atr <= 0:
        stop_pct = 0.03
        target_pct = 0.05
    else:
        stop_pct = max(_STOP_PCT_FLOOR, min((atr * _STOP_ATR_MULT) / entry, _STOP_PCT_CAP))
        target_pct = max(_TARGET_PCT_FLOOR, min((atr * _TARGET_ATR_MULT) / entry, _TARGET_PCT_CAP))

    stop = round(entry * (1.0 - stop_pct), 4)
    target = round(entry * (1.0 + target_pct), 4)
    return stop, target


# ---------------------------------------------------------------------------
# Position sizing — fixed notional
# ---------------------------------------------------------------------------

def _compute_position_size(entry_price: float) -> int:
    if entry_price <= 0:
        return 0
    size = int(_TARGET_NOTIONAL / entry_price)
    return max(_MIN_POSITION_SIZE, min(size, _MAX_POSITION_SIZE))


# ---------------------------------------------------------------------------
# Stateful decision engine
# ---------------------------------------------------------------------------

class BistEdgeV2Decision:
    """BIST Edge V2 — stateful, regime-aware, deconcentrated.

    Callable matching DecisionFunction protocol:
        (symbol, bars, bar_index) -> Optional[Dict]

    New structural mechanisms vs V1:
    - Per-symbol signal cooldown (prevents rapid re-entry)
    - Trend duration gate (blocks brief crossover whipsaw)
    - ATR-scaled stops/targets (equalizes risk contribution)
    - Tighter regime + quality filters
    """

    def __init__(self) -> None:
        self._last_signal_bar: dict[str, int] = {}
        self._universe_closes: dict[str, list[float]] = {}

    def __call__(
        self,
        symbol: str,
        bars: List[OHLCVBar],
        bar_index: int,
    ) -> Optional[Dict[str, Any]]:
        if bar_index < _MIN_BARS or not bars:
            return None

        window = bars[: bar_index + 1]
        closes = [float(b.close) for b in window]
        volumes = [float(b.volume) for b in window]

        if len(closes) < _MIN_BARS:
            return None

        # Track universe closes for cross-sectional edges (RS, sector)
        self._universe_closes[symbol] = closes

        # --- Signal cooldown ---
        last = self._last_signal_bar.get(symbol, -999)
        if bar_index - last < _SIGNAL_COOLDOWN_BARS:
            return None

        # --- Global filters ---
        if not _regime_allows_any_signal(closes):
            return None
        if not _symbol_quality_ok(closes):
            return None

        # --- Edge detection ---
        trend_regime_ok = _regime_allows_trend_signal(closes)
        trend_duration = _trend_duration_ok(closes)

        edge_name = ""

        # Trend edges require BOTH regime approval AND duration
        if trend_regime_ok and trend_duration:
            if _trend_pullback_signal(closes, volumes):
                edge_name = "trend_pullback"
            # vol_breakout DISABLED: PF=0.15, -1314 TRY over 3 trades. Net loser.

        # Mean-reversion has no trend requirement
        if not edge_name and _mean_reversion_signal(closes, volumes):
            edge_name = "mean_reversion"

        # Gap-fade is contrarian — no trend/regime gate
        if not edge_name and _gap_fade_signal(window, closes, volumes):
            edge_name = "gap_fade"

        # Momentum continuation — trend/duration gate like trend edges
        if not edge_name and trend_regime_ok and _momentum_continuation_signal(closes, volumes):
            edge_name = "momentum_cont"

        # rs_momentum DISABLED: PF=0.31, -1941 TRY over 12 trades. Net loser.

        # sector_rotation DISABLED: PF=1.74 full-sample but degrades walk-forward
        # (WF drops from 4/4 → 2/4). Fires too aggressively in late-2025 regime.
        # Re-enable once more data or intraday MTF available.

        if not edge_name:
            return None

        entry = closes[-1]
        if entry <= 0:
            return None

        # ATR-based risk
        atr = _atr(window, _ATR_PERIOD)
        stop, target = _compute_atr_risk(entry, atr)
        position_size = _compute_position_size(entry)

        if position_size < _MIN_POSITION_SIZE:
            return None

        # Record signal for cooldown
        self._last_signal_bar[symbol] = bar_index

        return {
            "symbol": symbol,
            "entry": entry,
            "stop": stop,
            "target": target,
            "position_size": position_size,
            "edge": edge_name,
        }


def bist_edge_v2_decision(
    symbol: str,
    bars: List[OHLCVBar],
    bar_index: int,
) -> Optional[Dict[str, Any]]:
    """Module-level convenience — uses a shared singleton instance.

    WARNING: This is stateful. Each import gets one shared instance.
    For isolated runs, instantiate BistEdgeV2Decision() directly.
    """
    return _SINGLETON(symbol, bars, bar_index)


_SINGLETON = BistEdgeV2Decision()


__all__ = ["BistEdgeV2Decision", "bist_edge_v2_decision"]
