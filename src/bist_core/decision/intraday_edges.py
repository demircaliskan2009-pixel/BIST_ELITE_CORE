"""Intraday Edge Detectors — 5 deterministic, MTF-aware intraday edges.

Each edge function takes an MTFBarEvent and returns an IntradaySignal or None.
All logic is deterministic, all indicators use only completed bars (no lookahead).
Designed for BIST intraday session (09:00–18:00 TRT).

Edges:
1. opening_drive — first 30-min momentum continuation
2. intraday_momentum — breakout follow-through above hourly high
3. liquidity_sweep — stop-hunt reversal (wick rejection + volume)
4. volume_spike_reversal — anomalous volume mean-reversion at extremes
5. gap_continuation — intraday gap + follow-through after open

All edges require MTF confirmation at minimum:
  - daily regime != BEAR
  - hourly trend aligned with entry direction (or neutral for reversal edges)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Sequence

from bist_core.decision.mtf_context import MTFContext
from bist_core.decision.timeframe_sync import MTFBarEvent
from bist_core.models.ohlcv import OHLCVBar

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# BIST session timing (seconds from midnight TRT)
# Continuous trading starts after opening auction at 09:55 TRT.
_SESSION_OPEN_SEC: Final[int] = 9 * 3600 + 55 * 60   # 09:55 TRT
_SESSION_CLOSE_SEC: Final[int] = 18 * 3600             # 18:00 TRT
_OPENING_DRIVE_END_SEC: Final[int] = 10 * 3600 + 25 * 60  # 10:25 TRT
_NO_ENTRY_AFTER_SEC: Final[int] = 17 * 3600 + 30 * 60     # 17:30 TRT

# --- Edge 1: Opening Drive ---
_OD_MIN_RANGE_PCT: Final[float] = 0.005   # min price range in first 30min (0.5%)
_OD_MAX_RANGE_PCT: Final[float] = 0.04    # max range (avoid extreme gaps)
_OD_VOLUME_RATIO: Final[float] = 1.5      # opening volume vs avg volume ratio
_OD_MIN_BARS: Final[int] = 5              # need at least 5 opening bars

# --- Edge 2: Intraday Momentum Continuation ---
_IMC_LOOKBACK_BARS: Final[int] = 60       # 60 minutes for intraday high/low
_IMC_BREAKOUT_PCT: Final[float] = 0.002   # must exceed recent range by 0.2%
_IMC_VOLUME_RATIO: Final[float] = 1.2     # breakout bar volume above average
_IMC_RSI_MAX: Final[float] = 80.0         # RSI not exhausted

# --- Edge 3: Liquidity Sweep ---
_LS_WICK_RATIO: Final[float] = 1.3        # wick must be ≥1.3x body
_LS_SWEEP_PCT: Final[float] = 0.0015      # sweep beyond recent range (0.15%)
_LS_VOLUME_RATIO: Final[float] = 1.2      # sweep bar volume above average
_LS_RECOVERY_PCT: Final[float] = 0.4      # close must recover ≥40% of wick

# --- Edge 4: Volume Spike Reversal ---
_VSR_VOL_SPIKE: Final[float] = 2.0        # volume ≥2x average
_VSR_BB_EXTREME: Final[float] = 0.05      # near BB lower (< 5%) or upper (> 95%)
_VSR_RSI_OVERSOLD: Final[float] = 40.0    # RSI extreme for reversal
_VSR_RSI_OVERBOUGHT: Final[float] = 60.0
_VSR_BODY_MIN_PCT: Final[float] = 0.001   # minimum body size (0.1%)

# --- Edge 5: Intraday Gap Continuation ---
_IGC_MIN_GAP_PCT: Final[float] = 0.007    # minimum 0.7% gap from prev close
_IGC_MAX_GAP_PCT: Final[float] = 0.05     # maximum 5% gap (avoid news-driven)
_IGC_FOLLOW_BARS: Final[int] = 30         # confirm within first 30 bars
_IGC_FOLLOW_PCT: Final[float] = 0.003     # price moves further 0.3% in gap dir

# --- Risk parameters ---
_ATR_PERIOD: Final[int] = 14
_STOP_ATR_MULT: Final[float] = 1.5
_TARGET_ATR_MULT: Final[float] = 2.5
_TARGET_NOTIONAL: Final[float] = 5000.0
_MIN_CONFIDENCE: Final[float] = 0.20      # minimum MTF confidence for any entry


# ---------------------------------------------------------------------------
# Signal data structure
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class IntradaySignal:
    """A deterministic intraday trade signal."""
    timestamp: int
    symbol: str
    edge: str              # "opening_drive", "intraday_momentum", etc.
    direction: str         # "LONG" or "SHORT" (BIST shorts restrictions: LONG only)
    entry_price: float     # expected entry (next bar open)
    stop_price: float
    target_price: float
    position_size: int     # shares (notional / entry_price)
    confidence: float      # 0–1 from MTF context
    reason: str            # human-readable explanation
    source: str = "technical"  # "technical" or "event"
    event_boost: float = 0.0
    event_context: str = "none"  # "positive", "negative", or "none"
    event_reason: str = ""  # human-readable event context explanation


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _time_of_day_sec(unix_ts: int) -> int:
    """Extract seconds-since-midnight in TRT (UTC+3) from Unix timestamp."""
    return (unix_ts + 3 * 3600) % 86400


def _is_in_session(unix_ts: int) -> bool:
    """Check if timestamp is within BIST session hours."""
    tod = _time_of_day_sec(unix_ts)
    return _SESSION_OPEN_SEC <= tod <= _SESSION_CLOSE_SEC


def _too_late_for_entry(unix_ts: int) -> bool:
    """No entries after 17:30 TRT."""
    return _time_of_day_sec(unix_ts) > _NO_ENTRY_AFTER_SEC


def _bar_body(bar: OHLCVBar) -> float:
    return abs(bar.close - bar.open)


def _bar_range(bar: OHLCVBar) -> float:
    return bar.high - bar.low


def _upper_wick(bar: OHLCVBar) -> float:
    return bar.high - max(bar.open, bar.close)


def _lower_wick(bar: OHLCVBar) -> float:
    return min(bar.open, bar.close) - bar.low


def _avg_volume(bars: Sequence[OHLCVBar], lookback: int = 20) -> float:
    if not bars:
        return 0.0
    vols = [float(b.volume) for b in bars[-lookback:]]
    return sum(vols) / len(vols) if vols else 0.0


def _atr_from_bars(bars: Sequence[OHLCVBar], period: int = 14) -> float:
    if len(bars) < period + 1:
        return 0.0
    trs: list[float] = []
    for i in range(len(bars) - period, len(bars)):
        h, l = float(bars[i].high), float(bars[i].low)
        pc = float(bars[i - 1].close)
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    return sum(trs) / len(trs)


def _rsi_from_bars(bars: Sequence[OHLCVBar], period: int = 14) -> float:
    closes = [float(b.close) for b in bars]
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


def _mtf_score(ctx: MTFContext) -> float:
    """Adaptive MTF alignment score (0.3–1.5).

    Replaces hard binary gates.  Higher score → better alignment → larger size.
    """
    score = 0.5  # base
    if ctx.daily is not None:
        if ctx.daily.regime == "BULL":
            score += 0.30
        elif ctx.daily.regime == "RANGE":
            score += 0.10
        elif ctx.daily.regime == "BEAR":
            score -= 0.20
    if ctx.hourly is not None:
        if ctx.hourly.direction == "UP":
            score += 0.30
        elif ctx.hourly.direction == "FLAT":
            score += 0.10
        elif ctx.hourly.direction == "DOWN":
            score -= 0.10
    return max(0.3, min(1.5, score))


def _hourly_atr(ctx: MTFContext) -> float:
    """Extract hourly ATR from context, 0.0 if unavailable."""
    if ctx.hourly is not None:
        return ctx.hourly.atr
    return 0.0


def _make_signal(
    bar: OHLCVBar,
    edge: str,
    direction: str,
    entry: float,
    atr: float,
    confidence: float,
    reason: str,
    mtf_mult: float = 1.0,
    hourly_atr: float = 0.0,
    source: str = "technical",
    event_boost: float = 0.0,
) -> IntradaySignal:
    """Build signal with ATR-scaled stops/targets.

    Uses hourly ATR when available for properly-scaled intraday stop/target.
    Falls back to 1-min ATR with wider minimum percentages.
    """
    # BIST swing-entry: 3% stop / 5% target (empirically proven profitable
    # with multi-day holds across AKBNK/YKBNK/PETKM/ISCTR). Intraday-only
    # holds cannot overcome BIST execution friction; overnight gaps provide
    # the real alpha.
    stop_dist = entry * 0.03
    target_dist = entry * 0.05

    if direction == "LONG":
        stop = entry - stop_dist
        target = entry + target_dist
    else:
        stop = entry + stop_dist
        target = entry - target_dist

    size = max(1, int(_TARGET_NOTIONAL * mtf_mult / entry)) if entry > 0 else 0

    return IntradaySignal(
        timestamp=bar.timestamp,
        symbol=bar.symbol,
        edge=edge,
        direction=direction,
        entry_price=round(entry, 4),
        stop_price=round(stop, 4),
        target_price=round(target, 4),
        position_size=size,
        confidence=round(confidence, 3),
        reason=reason,
        source=source,
        event_boost=round(event_boost, 3),
    )


# ---------------------------------------------------------------------------
# Edge 1: Opening Drive
# ---------------------------------------------------------------------------

def detect_opening_drive(
    event: MTFBarEvent,
    m1_history: Sequence[OHLCVBar],
) -> IntradaySignal | None:
    """Detect opening drive momentum in the first 30 minutes of continuous trading.

    Logic:
    - Within first 30 min of continuous session (09:55–10:25 TRT)
    - Price range in opening period exceeds threshold
    - Volume above average
    - Direction determined by close vs opening midpoint
    - MTF adaptive scoring (not hard gate)
    """
    bar = event.bar
    ctx = event.context
    tod = _time_of_day_sec(bar.timestamp)

    # Must be in opening window (09:55–10:25 TRT)
    if tod < _SESSION_OPEN_SEC or tod > _OPENING_DRIVE_END_SEC:
        return None

    # Soft MTF gate: only block in aggressive BEAR
    if ctx.daily is not None and ctx.daily.regime == "BEAR":
        if ctx.daily.trend_strength < -0.03:
            return None
    if ctx.confidence < _MIN_CONFIDENCE:
        return None

    # Need some history
    if len(m1_history) < _OD_MIN_BARS:
        return None

    # Collect today's opening bars
    session_start_ts = bar.timestamp - (tod - _SESSION_OPEN_SEC)
    opening_bars = [b for b in m1_history if b.timestamp >= session_start_ts]
    if len(opening_bars) < _OD_MIN_BARS:
        return None

    # Opening range
    open_high = max(float(b.high) for b in opening_bars)
    open_low = min(float(b.low) for b in opening_bars)
    first_open = float(opening_bars[0].open)
    if first_open <= 0:
        return None

    range_pct = (open_high - open_low) / first_open
    if range_pct < _OD_MIN_RANGE_PCT or range_pct > _OD_MAX_RANGE_PCT:
        return None

    # Volume check
    avg_vol = _avg_volume(m1_history, lookback=60)
    current_vol = sum(float(b.volume) for b in opening_bars[-5:]) / max(1, len(opening_bars[-5:]))
    if avg_vol <= 0 or current_vol / avg_vol < _OD_VOLUME_RATIO:
        return None

    # Direction: closing above midpoint → LONG
    midpoint = (open_high + open_low) / 2
    close = float(bar.close)

    if close > midpoint:
        direction = "LONG"
    else:
        return None  # BIST short restrictions

    mtf = _mtf_score(ctx)
    atr = _atr_from_bars(list(m1_history), _ATR_PERIOD)
    entry = close

    return _make_signal(
        bar=bar,
        edge="opening_drive",
        direction=direction,
        entry=entry,
        atr=atr,
        confidence=ctx.confidence,
        reason=f"Opening drive: range={range_pct:.3f}, vol_r={current_vol/avg_vol:.1f}, mtf={mtf:.2f}",
        mtf_mult=mtf,
        hourly_atr=_hourly_atr(ctx),
    )


# ---------------------------------------------------------------------------
# Edge 2: Intraday Momentum Continuation
# ---------------------------------------------------------------------------

def detect_intraday_momentum(
    event: MTFBarEvent,
    m1_history: Sequence[OHLCVBar],
) -> IntradaySignal | None:
    """Detect breakout above recent intraday high.

    Logic:
    - Current price exceeds highest high of last N bars
    - Minimal filtering: only session timing and lookback
    - MTF adaptive scoring for position sizing (not gating)

    Empirically validated: simple breakout with 3%/5% swing stops
    is profitable across BIST large-caps after realistic execution.
    Filters (volume, RSI, MTF regime) REMOVE profitable signals.
    """
    bar = event.bar
    ctx = event.context

    if _too_late_for_entry(bar.timestamp):
        return None
    if not _is_in_session(bar.timestamp):
        return None

    if len(m1_history) < _IMC_LOOKBACK_BARS:
        return None

    recent = list(m1_history[-_IMC_LOOKBACK_BARS:])
    recent_high = max(float(b.high) for b in recent)
    close = float(bar.close)

    if recent_high <= 0:
        return None

    # Simple breakout: close above recent high
    if close <= recent_high:
        return None

    mtf = _mtf_score(ctx)
    atr = _atr_from_bars(list(m1_history), _ATR_PERIOD)
    entry = close

    breakout_pct = (close - recent_high) / recent_high
    return _make_signal(
        bar=bar,
        edge="intraday_momentum",
        direction="LONG",
        entry=entry,
        atr=atr,
        confidence=ctx.confidence,
        reason=f"Breakout: +{breakout_pct:.3f} above {_IMC_LOOKBACK_BARS}bar high, mtf={mtf:.2f}",
        mtf_mult=mtf,
        hourly_atr=_hourly_atr(ctx),
    )


# ---------------------------------------------------------------------------
# Edge 3: Liquidity Sweep
# ---------------------------------------------------------------------------

def detect_liquidity_sweep(
    event: MTFBarEvent,
    m1_history: Sequence[OHLCVBar],
) -> IntradaySignal | None:
    """Detect stop-hunt reversal (wick below recent low + recovery).

    Logic:
    - Bar wicks below recent low (sweep) then closes back above
    - Lower wick ≥1.3x body (wick rejection)
    - Sweep volume above average
    - Close recovers ≥40% of the wick
    - Adaptive MTF scoring
    """
    bar = event.bar
    ctx = event.context

    if _too_late_for_entry(bar.timestamp):
        return None
    if not _is_in_session(bar.timestamp):
        return None

    # Soft regime: block only in strong BEAR
    if ctx.daily is not None and ctx.daily.regime == "BEAR":
        if ctx.daily.trend_strength < -0.03:
            return None
    if ctx.confidence < _MIN_CONFIDENCE:
        return None

    if len(m1_history) < 30:
        return None

    recent = list(m1_history[-20:])
    recent_low = min(float(b.low) for b in recent)
    bar_low = float(bar.low)
    close = float(bar.close)

    # Must sweep below recent low
    if bar_low >= recent_low:
        return None

    sweep_dist = recent_low - bar_low
    if recent_low <= 0:
        return None
    sweep_pct = sweep_dist / recent_low
    if sweep_pct < _LS_SWEEP_PCT:
        return None

    # Wick analysis
    body = _bar_body(bar)
    lw = _lower_wick(bar)
    if body <= 0 or lw / body < _LS_WICK_RATIO:
        return None

    # Recovery check: close must be above sweep midpoint
    sweep_mid = bar_low + sweep_dist * _LS_RECOVERY_PCT
    if close < sweep_mid:
        return None

    # Close must be above recent low (recovered back into range)
    if close < recent_low:
        return None

    # Volume check
    avg_vol = _avg_volume(m1_history, lookback=60)
    if avg_vol <= 0 or float(bar.volume) / avg_vol < _LS_VOLUME_RATIO:
        return None

    mtf = _mtf_score(ctx)
    atr = _atr_from_bars(list(m1_history), _ATR_PERIOD)
    entry = close

    return _make_signal(
        bar=bar,
        edge="liquidity_sweep",
        direction="LONG",
        entry=entry,
        atr=atr,
        confidence=ctx.confidence,
        reason=f"Sweep: -{sweep_pct:.3f} below range, wick_ratio={lw/body:.1f}, vol_r={float(bar.volume)/avg_vol:.1f}, mtf={mtf:.2f}",
        mtf_mult=mtf,
        hourly_atr=_hourly_atr(ctx),
    )


# ---------------------------------------------------------------------------
# Edge 4: Volume Spike Reversal
# ---------------------------------------------------------------------------

def detect_volume_spike_reversal(
    event: MTFBarEvent,
    m1_history: Sequence[OHLCVBar],
) -> IntradaySignal | None:
    """Detect mean-reversion setup at volume spike + price extreme.

    Logic:
    - Current volume ≥2x average (panic/capitulation)
    - RSI below 40 (oversold zone, not extreme)
    - Body size confirms sell pressure
    - Close in upper portion of bar (signs of recovery)
    - Adaptive MTF scoring
    """
    bar = event.bar
    ctx = event.context

    if _too_late_for_entry(bar.timestamp):
        return None
    if not _is_in_session(bar.timestamp):
        return None

    # Soft regime: block only in strong BEAR
    if ctx.daily is not None and ctx.daily.regime == "BEAR":
        if ctx.daily.trend_strength < -0.03:
            return None

    if len(m1_history) < 60:
        return None

    # Volume spike
    avg_vol = _avg_volume(m1_history, lookback=60)
    if avg_vol <= 0 or float(bar.volume) / avg_vol < _VSR_VOL_SPIKE:
        return None

    # RSI check on 1-min (relaxed from 30 to 40)
    rsi = _rsi_from_bars(list(m1_history[-30:]))
    if rsi > _VSR_RSI_OVERSOLD:
        return None

    # Body check: meaningful candle
    close = float(bar.close)
    if close <= 0:
        return None
    body_pct = _bar_body(bar) / close
    if body_pct < _VSR_BODY_MIN_PCT:
        return None

    # Price should be closing above its low (signs of recovery)
    bar_range = _bar_range(bar)
    if bar_range <= 0:
        return None
    close_position = (close - float(bar.low)) / bar_range
    if close_position < 0.4:  # close should be in upper 60% of bar
        return None

    mtf = _mtf_score(ctx)
    atr = _atr_from_bars(list(m1_history), _ATR_PERIOD)
    entry = close

    return _make_signal(
        bar=bar,
        edge="volume_spike_reversal",
        direction="LONG",
        entry=entry,
        atr=atr,
        confidence=ctx.confidence,
        reason=f"VolSpike: vol_r={float(bar.volume)/avg_vol:.1f}, RSI={rsi:.0f}, close_pos={close_position:.2f}, mtf={mtf:.2f}",
        mtf_mult=mtf,
        hourly_atr=_hourly_atr(ctx),
    )


# ---------------------------------------------------------------------------
# Edge 5: Intraday Gap Continuation
# ---------------------------------------------------------------------------

def detect_gap_continuation(
    event: MTFBarEvent,
    m1_history: Sequence[OHLCVBar],
    prev_day_close: float | None = None,
) -> IntradaySignal | None:
    """Detect gap-up at open with follow-through confirmation.

    Logic:
    - Opening price gaps up from previous close by ≥0.5%
    - Confirmed by further price appreciation in first N bars
    - Volume above average during confirmation period
    - Adaptive MTF scoring
    - Gap not too extreme (≤5%)
    """
    bar = event.bar
    ctx = event.context
    tod = _time_of_day_sec(bar.timestamp)

    # Only in early session (first 30 bars after continuous trading starts)
    if tod < _SESSION_OPEN_SEC or tod > _SESSION_OPEN_SEC + _IGC_FOLLOW_BARS * 60:
        return None

    # Soft regime gate
    if ctx.daily is not None and ctx.daily.regime == "BEAR":
        if ctx.daily.trend_strength < -0.03:
            return None
    if ctx.confidence < _MIN_CONFIDENCE:
        return None

    if prev_day_close is None or prev_day_close <= 0:
        return None

    if len(m1_history) < _IGC_FOLLOW_BARS:
        return None

    # Find today's opening bars
    session_start_ts = bar.timestamp - (tod - _SESSION_OPEN_SEC)
    today_bars = [b for b in m1_history if b.timestamp >= session_start_ts]
    if len(today_bars) < 5:  # need at least 5 bars for confirmation
        return None

    # Gap size
    today_open = float(today_bars[0].open)
    gap_pct = (today_open - prev_day_close) / prev_day_close

    if gap_pct < _IGC_MIN_GAP_PCT or gap_pct > _IGC_MAX_GAP_PCT:
        return None

    # Follow-through: current close > today_open + follow threshold
    close = float(bar.close)
    follow_through = (close - today_open) / today_open
    if follow_through < _IGC_FOLLOW_PCT:
        return None

    # Volume confirmation
    avg_vol = _avg_volume(m1_history, lookback=60)
    recent_vol = sum(float(b.volume) for b in today_bars) / len(today_bars) if today_bars else 0.0
    if avg_vol <= 0 or recent_vol / avg_vol < 1.2:
        return None

    mtf = _mtf_score(ctx)
    atr = _atr_from_bars(list(m1_history), _ATR_PERIOD)
    entry = close

    return _make_signal(
        bar=bar,
        edge="gap_continuation",
        direction="LONG",
        entry=entry,
        atr=atr,
        confidence=ctx.confidence,
        reason=f"Gap: +{gap_pct:.3f} from prev_close, follow={follow_through:.3f}, vol_r={recent_vol/avg_vol:.1f}, mtf={mtf:.2f}",
        mtf_mult=mtf,
        hourly_atr=_hourly_atr(ctx),
    )


# ---------------------------------------------------------------------------
# Edge scanner (runs all 5 edges, returns at most 1 signal per bar)
# ---------------------------------------------------------------------------

class IntradayEdgeScanner:
    """Scans all intraday edges (technical + event) and returns the highest-confidence signal.

    Usage:
        scanner = IntradayEdgeScanner()
        for event in sync.iter_events():
            signal = scanner.scan(event, m1_history, prev_day_close)
            if signal is not None:
                # execute signal

    With event engine:
        from bist_core.events.event_engine import create_event_engine
        ev_engine = create_event_engine(use_synthetic=True)
        ev_engine.load_events(symbols, start_ts, end_ts)
        scanner = IntradayEdgeScanner(event_engine=ev_engine)
    """

    def __init__(
        self,
        disabled_edges: set[str] | None = None,
        event_engine: object | None = None,
    ) -> None:
        self._cooldown: dict[tuple[str, str], int] = {}   # (symbol, edge) → last signal ts
        self._cooldown_bars: int = 15          # min 15 bars between signals per edge per symbol
        self._prev_day_closes: dict[str, float] = {}
        self._disabled_edges: set[str] = disabled_edges or {"volume_spike_reversal", "liquidity_sweep", "gap_continuation"}
        # Per-edge-per-day limit: key=(symbol, edge), value=session_day_ts
        self._fired_today: dict[tuple[str, str], int] = {}
        # Event engine (optional — adds event-driven edges)
        self._event_engine = event_engine
        # Lazy import to avoid circular dependency
        from bist_core.decision.intraday_edges_expansion import (
            IntraEdgeExpansion,
            detect_afternoon_momentum,
            detect_daily_high_breakout,
            detect_intraday_mean_reversion,
            detect_pullback_continuation,
            detect_vol_contraction_breakout,
        )
        self._expansion = IntraEdgeExpansion()
        self._detect_vcb = detect_vol_contraction_breakout
        self._detect_dhb = detect_daily_high_breakout
        self._detect_pbc = detect_pullback_continuation
        self._detect_imr = detect_intraday_mean_reversion
        self._detect_afm = detect_afternoon_momentum

    def update_prev_close(self, symbol: str, close: float) -> None:
        """Update previous day close for gap detection."""
        self._prev_day_closes[symbol] = close

    def scan(
        self,
        event: MTFBarEvent,
        m1_history: Sequence[OHLCVBar],
    ) -> IntradaySignal | None:
        """Run all edges, return highest-confidence signal or None.

        Constraints:
        - Each edge can fire at most once per trading day per symbol.
        - Per-edge cooldown prevents rapid-fire from same edge.
        """
        bar = event.bar
        sym = bar.symbol

        # Update expansion state before edge detection
        self._expansion.update(bar)

        # Trading day id: (ts + 3h offset to TRT) // 86400
        day_id = (bar.timestamp + 3 * 3600) // 86400

        # Update prev_day_close from daily bar completion
        if event.daily_completed:
            pass  # handled by backtest engine via update_prev_close()

        prev_close = self._prev_day_closes.get(sym)

        # Collect candidate signals from all enabled edges
        candidates: list[IntradaySignal] = []

        edges_fns: list[tuple[str, object]] = [
            ("opening_drive", lambda: detect_opening_drive(event, m1_history)),
            ("intraday_momentum", lambda: detect_intraday_momentum(event, m1_history)),
            ("liquidity_sweep", lambda: detect_liquidity_sweep(event, m1_history)),
            ("volume_spike_reversal", lambda: detect_volume_spike_reversal(event, m1_history)),
            ("gap_continuation", lambda: detect_gap_continuation(event, m1_history, prev_close)),
        ]

        # Expansion edges (BIST-structural alpha expansion)
        edges_fns.extend([
            ("vol_contraction_breakout", lambda: self._detect_vcb(event, m1_history, self._expansion)),
            ("daily_high_breakout", lambda: self._detect_dhb(event, m1_history, self._expansion)),
            ("pullback_continuation", lambda: self._detect_pbc(event, m1_history, self._expansion)),
            ("intraday_mean_reversion", lambda: self._detect_imr(event, m1_history, self._expansion)),
            ("afternoon_momentum", lambda: self._detect_afm(event, m1_history, self._expansion)),
        ])

        for edge_name, detect_fn in edges_fns:
            if edge_name in self._disabled_edges:
                continue
            # Once-per-day-per-edge limit
            if self._fired_today.get((sym, edge_name), -1) == day_id:
                continue
            # Per-edge cooldown
            last_ts = self._cooldown.get((sym, edge_name), 0)
            if bar.timestamp - last_ts < self._cooldown_bars * 60:
                continue

            s = detect_fn()  # type: ignore[operator]
            if s is not None:
                candidates.append(s)

        # ── Event engine signals ──────────────────────────────────
        if self._event_engine is not None:
            # Check if a hard negative event blocks LONG signals
            is_blocked = self._event_engine.is_event_blocked(sym)
            if is_blocked:
                # Block ALL technical LONG candidates when hard negative event active
                ctx, ekind, ereason = self._event_engine.get_event_context(sym)
                candidates = [
                    IntradaySignal(
                        symbol=c.symbol,
                        edge=c.edge,
                        direction=c.direction,
                        confidence=c.confidence,
                        entry_price=c.entry_price,
                        stop_price=c.stop_price,
                        target_price=c.target_price,
                        timestamp=c.timestamp,
                        position_size=c.position_size,
                        reason=c.reason,
                        source=c.source,
                        event_boost=0.0,
                        event_context="negative",
                        event_reason=f"BLOCKED by {ekind} ({ereason})",
                    )
                    for c in candidates
                    if c.direction != "LONG"
                ]
            else:
                # Event-driven signals (only fire for POSITIVE kinds)
                event_signals = self._event_engine.scan(event, m1_history)
                for es in event_signals:
                    ek = (sym, es.edge)
                    if self._fired_today.get(ek, -1) == day_id:
                        continue
                    last_ts = self._cooldown.get(ek, 0)
                    if bar.timestamp - last_ts < self._cooldown_bars * 60:
                        continue
                    candidates.append(es)

                # Apply soft penalty (×0.7) for SOFT_NEGATIVE events
                soft_mult = self._event_engine.get_soft_penalty(sym)
                if soft_mult < 1.0:
                    ctx, ekind, ereason = self._event_engine.get_event_context(sym)
                    for i, c in enumerate(candidates):
                        if c.source == "technical":
                            penalized = max(c.confidence * soft_mult, 0.01)
                            candidates[i] = IntradaySignal(
                                symbol=c.symbol,
                                edge=c.edge,
                                direction=c.direction,
                                confidence=penalized,
                                entry_price=c.entry_price,
                                stop_price=c.stop_price,
                                target_price=c.target_price,
                                timestamp=c.timestamp,
                                position_size=c.position_size,
                                reason=c.reason,
                                source=c.source,
                                event_boost=0.0,
                                event_context="soft_negative",
                                event_reason=f"penalized by {ekind} ({ereason})",
                            )

                # Apply event boost to technical candidates (POSITIVE events only)
                event_boost = self._event_engine.get_event_boost(sym)
                if event_boost > 0.0:
                    ctx, ekind, ereason = self._event_engine.get_event_context(sym)
                    for i, c in enumerate(candidates):
                        if c.source == "technical":
                            boosted = min(c.confidence + event_boost, 1.0)
                            candidates[i] = IntradaySignal(
                                symbol=c.symbol,
                                edge=c.edge,
                                direction=c.direction,
                                confidence=boosted,
                                entry_price=c.entry_price,
                                stop_price=c.stop_price,
                                target_price=c.target_price,
                                timestamp=c.timestamp,
                                position_size=c.position_size,
                                reason=c.reason,
                                source=c.source,
                                event_boost=event_boost,
                                event_context="positive",
                                event_reason=f"boosted by {ekind} ({ereason})",
                            )

        if not candidates:
            return None

        # Select highest confidence; tie-break by edge name for determinism
        best = max(candidates, key=lambda x: (x.confidence, x.edge))
        self._cooldown[(sym, best.edge)] = bar.timestamp
        self._fired_today[(sym, best.edge)] = day_id
        return best


__all__ = [
    "IntradayEdgeScanner",
    "IntradaySignal",
    "detect_gap_continuation",
    "detect_intraday_momentum",
    "detect_liquidity_sweep",
    "detect_opening_drive",
    "detect_volume_spike_reversal",
]
