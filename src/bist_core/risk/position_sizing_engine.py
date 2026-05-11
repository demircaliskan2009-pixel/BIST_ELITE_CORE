"""Dynamic Position Sizing + Drawdown Control — BIST production risk management.

Position Sizing:
    position_size = f(equity, risk_multiplier, volatility, drawdown)
    Max risk per trade: 0.5% of equity (scaled by aggression engine)
    Total open risk cap: 4% of equity

Drawdown Control:
    Institutional-grade protection with tighter bands:

    DD 0-5%:   normal (1.0x)
    DD 5-8%:   cautious (0.7x)
    DD 8-12%:  defensive (0.4x)
    DD 12-15%: emergency (0.2x, still allows entries)
    DD > 15%:  full stop (0.0x, no entries)

Daily Loss Limit:
    If cumulative intraday PnL exceeds -2% of equity, halt new entries.

Universe Scoring:
    Scores symbols by trend quality, volatility suitability, liquidity,
    and historical edge performance.  Only top-scoring symbols are traded.

All computations deterministic.  No lookahead.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Sequence

from bist_core.models.ohlcv import OHLCVBar

# ---------------------------------------------------------------------------
# Constants — Position Sizing
# ---------------------------------------------------------------------------

_BASE_RISK_PCT: Final[float] = 0.005  # 0.5% of equity risked per trade
_MIN_POSITION_TRY: Final[float] = 1_000.0     # minimum 1K TRY per trade
_MAX_POSITION_PCT: Final[float] = 0.15         # max 15% of equity per trade
_MIN_SHARES: Final[int] = 1
_TOTAL_RISK_CAP: Final[float] = 0.04          # max 4% total open risk
_DAILY_LOSS_LIMIT: Final[float] = 0.02        # 2% daily loss -> halt

# ---------------------------------------------------------------------------
# Constants — Drawdown Control
# ---------------------------------------------------------------------------

_DD_BANDS: Final[list[tuple[float, float, bool]]] = [
    # (dd_threshold, size_multiplier, allow_new_entries)
    (0.05, 1.0, True),     # DD < 5%: normal
    (0.08, 0.70, True),    # DD 5-8%: cautious
    (0.12, 0.40, True),    # DD 8-12%: defensive
    (0.15, 0.20, True),    # DD 12-15%: emergency (still trades)
    (1.00, 0.00, False),   # DD > 15%: STOP TRADING
]

# ---------------------------------------------------------------------------
# Constants — Universe Scoring
# ---------------------------------------------------------------------------

_TREND_LOOKBACK: Final[int] = 20     # 20-day return for trend quality
_VOL_IDEAL_LOW: Final[float] = 0.01  # ideal daily vol range
_VOL_IDEAL_HIGH: Final[float] = 0.03
_MIN_AVG_VOLUME: Final[float] = 500_000.0  # minimum daily volume (TRY)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class SizingResult:
    """Position sizing output."""
    shares: int
    notional: float       # shares * entry_price
    risk_amount: float    # TRY at risk (shares * stop_distance)
    risk_pct: float       # risk_amount / equity
    dd_multiplier: float
    aggression_mult: float
    entries_allowed: bool


@dataclass(frozen=True, slots=True)
class DrawdownState:
    """Current drawdown control state."""
    current_dd: float
    dd_band: str          # "normal", "cautious", "defensive", "emergency", "stopped"
    size_multiplier: float
    entries_allowed: bool


@dataclass(frozen=True, slots=True)
class SymbolScore:
    """Universe selection score for a symbol."""
    symbol: str
    trend_score: float      # [-1, 1] normalized momentum quality
    vol_score: float        # [0, 1] volatility suitability
    liquidity_score: float  # [0, 1]
    composite: float        # weighted total [0, 1]
    tradeable: bool         # passes all minimum thresholds


# ---------------------------------------------------------------------------
# Drawdown Control
# ---------------------------------------------------------------------------

def compute_drawdown_state(
    equity: float,
    peak_equity: float,
) -> DrawdownState:
    """Compute current drawdown band and sizing multiplier.

    Returns:
        DrawdownState with band classification and multiplier.
    """
    if peak_equity <= 0:
        return DrawdownState(0.0, "stopped", 0.0, False)

    dd = (peak_equity - equity) / peak_equity
    dd = max(0.0, dd)

    band_names = ["normal", "cautious", "defensive", "emergency", "stopped"]

    for idx, (threshold, mult, allow) in enumerate(_DD_BANDS):
        if dd < threshold:
            return DrawdownState(
                current_dd=round(dd, 6),
                dd_band=band_names[idx],
                size_multiplier=mult,
                entries_allowed=allow,
            )

    return DrawdownState(
        current_dd=round(dd, 6),
        dd_band="stopped",
        size_multiplier=0.0,
        entries_allowed=False,
    )


# ---------------------------------------------------------------------------
# Position Sizing
# ---------------------------------------------------------------------------

def compute_position_size(
    equity: float,
    entry_price: float,
    stop_price: float,
    risk_multiplier: float,
    dd_state: DrawdownState,
) -> SizingResult:
    """Compute dynamic position size.

    Formula:
        base_risk = equity * _BASE_RISK_PCT
        adjusted_risk = base_risk * risk_multiplier * dd_multiplier
        stop_distance = |entry - stop|
        shares = adjusted_risk / stop_distance

    Clamped by:
        - max 20% of equity per position
        - min 1K TRY
        - dd_state.entries_allowed

    Args:
        equity: current portfolio equity
        entry_price: expected entry price
        stop_price: stop-loss price
        risk_multiplier: from aggression engine in [0.1, 3.0]
        dd_state: from drawdown control

    Returns:
        SizingResult with computed shares and risk metrics.
    """
    if not dd_state.entries_allowed:
        return SizingResult(
            shares=0, notional=0.0, risk_amount=0.0,
            risk_pct=0.0, dd_multiplier=dd_state.size_multiplier,
            aggression_mult=risk_multiplier, entries_allowed=False,
        )

    if entry_price <= 0 or equity <= 0:
        return SizingResult(
            shares=0, notional=0.0, risk_amount=0.0,
            risk_pct=0.0, dd_multiplier=dd_state.size_multiplier,
            aggression_mult=risk_multiplier, entries_allowed=True,
        )

    stop_distance = abs(entry_price - stop_price)
    if stop_distance <= 0:
        return SizingResult(
            shares=0, notional=0.0, risk_amount=0.0,
            risk_pct=0.0, dd_multiplier=dd_state.size_multiplier,
            aggression_mult=risk_multiplier, entries_allowed=True,
        )

    # Compute risk amount
    base_risk = equity * _BASE_RISK_PCT
    dd_mult = dd_state.size_multiplier
    adjusted_risk = base_risk * risk_multiplier * dd_mult

    # Shares from risk
    shares = int(adjusted_risk / stop_distance)

    # Clamp notional to max position size
    max_notional = equity * _MAX_POSITION_PCT
    max_shares = int(max_notional / entry_price) if entry_price > 0 else 0
    shares = min(shares, max_shares)

    # Minimum position size
    min_shares = max(_MIN_SHARES, int(_MIN_POSITION_TRY / entry_price)) if entry_price > 0 else _MIN_SHARES
    if shares < min_shares:
        # Check if minimum position risk is acceptable
        min_risk = min_shares * stop_distance
        if min_risk > base_risk * risk_multiplier * 2.0:
            # Too much risk for minimum position — reject
            shares = 0
        else:
            shares = min_shares

    notional = shares * entry_price
    risk_amount = shares * stop_distance
    risk_pct = risk_amount / equity if equity > 0 else 0.0

    return SizingResult(
        shares=shares,
        notional=round(notional, 2),
        risk_amount=round(risk_amount, 2),
        risk_pct=round(risk_pct, 6),
        dd_multiplier=round(dd_mult, 4),
        aggression_mult=round(risk_multiplier, 4),
        entries_allowed=True,
    )


# ---------------------------------------------------------------------------
# Universe Scoring
# ---------------------------------------------------------------------------

def score_symbol(
    symbol: str,
    daily_bars: Sequence[OHLCVBar],
) -> SymbolScore:
    """Score a symbol for universe selection.

    Uses only completed daily bars.  Scores:
    - trend_score: risk-adjusted momentum (return / vol)
    - vol_score: penalty for too-low or too-high volatility
    - liquidity_score: average daily volume

    Args:
        symbol: ticker
        daily_bars: sorted daily bars

    Returns:
        SymbolScore with composite and tradeable flag.
    """
    if len(daily_bars) < _TREND_LOOKBACK + 5:
        return SymbolScore(symbol, 0.0, 0.0, 0.0, 0.0, False)

    recent = list(daily_bars[-_TREND_LOOKBACK:])

    # Trend quality: return / vol (Sharpe-like)
    returns: list[float] = []
    for i in range(1, len(recent)):
        prev_c = float(recent[i - 1].close)
        curr_c = float(recent[i].close)
        if prev_c > 0:
            returns.append((curr_c - prev_c) / prev_c)

    if not returns:
        return SymbolScore(symbol, 0.0, 0.0, 0.0, 0.0, False)

    mean_ret = sum(returns) / len(returns)
    var_ret = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
    vol = math.sqrt(var_ret) if var_ret > 0 else 0.001
    trend_raw = mean_ret / vol  # Sharpe-like ratio
    trend_score = max(-1.0, min(1.0, trend_raw / 0.5))  # normalize to [-1, 1]

    # Volatility suitability: ideal range [1%, 3%] daily
    vol_score = 1.0
    if vol < _VOL_IDEAL_LOW:
        vol_score = vol / _VOL_IDEAL_LOW  # too boring
    elif vol > _VOL_IDEAL_HIGH:
        vol_score = max(0.0, 1.0 - (vol - _VOL_IDEAL_HIGH) / _VOL_IDEAL_HIGH)

    # Liquidity: average daily volume (in shares * price ~ turnover proxy)
    avg_vol = sum(float(b.volume) * float(b.close) for b in recent) / len(recent)
    liq_raw = avg_vol / _MIN_AVG_VOLUME
    liquidity_score = min(1.0, max(0.0, liq_raw))

    # Composite
    composite = 0.40 * max(0, trend_score) + 0.30 * vol_score + 0.30 * liquidity_score
    tradeable = composite > 0.3 and trend_score > -0.3 and liquidity_score > 0.2

    return SymbolScore(
        symbol=symbol,
        trend_score=round(trend_score, 4),
        vol_score=round(vol_score, 4),
        liquidity_score=round(liquidity_score, 4),
        composite=round(composite, 4),
        tradeable=tradeable,
    )


def rank_universe(
    daily_by_symbol: dict[str, list[OHLCVBar]],
) -> list[SymbolScore]:
    """Score and rank all symbols, return sorted descending by composite.

    Only tradeable symbols are recommended.
    """
    scores = [score_symbol(sym, bars) for sym, bars in daily_by_symbol.items()]
    return sorted(scores, key=lambda s: s.composite, reverse=True)


# ---------------------------------------------------------------------------
# Daily Loss Limit
# ---------------------------------------------------------------------------

def check_daily_loss_limit(
    daily_pnl: float,
    equity_at_day_start: float,
) -> bool:
    """Check if daily loss limit has been breached.

    Returns True if new entries should be BLOCKED.
    """
    if equity_at_day_start <= 0:
        return True
    loss_pct = -daily_pnl / equity_at_day_start if daily_pnl < 0 else 0.0
    return loss_pct >= _DAILY_LOSS_LIMIT


# ---------------------------------------------------------------------------
# Total Risk Cap
# ---------------------------------------------------------------------------

def check_total_risk_cap(
    open_risk_total: float,
    equity: float,
) -> bool:
    """Check if total open risk exceeds cap.

    Returns True if new entries should be BLOCKED.
    """
    if equity <= 0:
        return True
    return (open_risk_total / equity) >= _TOTAL_RISK_CAP


__all__ = [
    "DrawdownState",
    "SizingResult",
    "SymbolScore",
    "check_daily_loss_limit",
    "check_total_risk_cap",
    "compute_drawdown_state",
    "compute_position_size",
    "rank_universe",
    "score_symbol",
    "DAILY_LOSS_LIMIT",
    "TOTAL_RISK_CAP",
]

# Public re-exports of constants for portfolio engine
DAILY_LOSS_LIMIT = _DAILY_LOSS_LIMIT
TOTAL_RISK_CAP = _TOTAL_RISK_CAP
