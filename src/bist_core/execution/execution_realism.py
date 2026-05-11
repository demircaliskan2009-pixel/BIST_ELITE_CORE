"""PRDV3 Execution Realism — dynamic slippage, partial fills, order rejection.

Replaces flat slippage model with realistic BIST execution costs.

Components:
1. DYNAMIC SLIPPAGE: base 20 bps + volatility scaling + volume impact.
2. PARTIAL FILLS: fill ratio 0.3–1.0 based on order size vs ADV.
3. ORDER REJECTION: reject when daily volume too low for position size.
4. TICK ROUNDING: all prices rounded to BIST tick grid.

All logic is deterministic. No randomness.
"""

from __future__ import annotations

from typing import List

from bist_core.execution.tick_size import round_to_tick

# ---------------------------------------------------------------------------
# Constants — structural, calibrated to BIST mid-cap reality
# ---------------------------------------------------------------------------

_BASE_SLIPPAGE_BPS = 20.0  # base slippage (bps) — BIST mid-cap typical
_VOL_SLIPPAGE_MULT = 2.0  # vol multiplier: slippage_bps += daily_vol * mult * 10000
_SIZE_IMPACT_MULT = 0.5  # size impact: slippage_bps += (size_frac ** 0.5) * mult * 10000
_COMMISSION_BPS = 3.0  # broker commission (bps per side, institutional rate)
_EXCHANGE_FEE_BPS = 0.4  # Borsa Istanbul exchange fee (bps per side)
_TAX_BPS = 0.2  # BSMV tax on commissions (~5% of commission)

# Fill ratio parameters
_MIN_FILL_RATIO = 0.3  # minimum partial fill
_MAX_SIZE_PCT_OF_ADV = 0.02  # 2% of ADV → full fill; above → partial
_REJECT_SIZE_PCT_OF_ADV = 0.10  # 10% of ADV → reject order entirely

# ADV estimation
_ADV_LOOKBACK = 20  # bars for average daily volume


# ---------------------------------------------------------------------------
# Volatility estimation
# ---------------------------------------------------------------------------


def _daily_vol(closes: List[float], lookback: int = 20) -> float:
    """Daily return standard deviation from close prices."""
    n = min(len(closes), lookback + 1)
    if n < 3:
        return 0.02  # default conservative estimate

    window = closes[-n:]
    rets: List[float] = []
    for i in range(1, len(window)):
        if window[i - 1] > 0:
            rets.append((window[i] - window[i - 1]) / window[i - 1])

    if len(rets) < 2:
        return 0.02

    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return max(0.005, var**0.5)


def _avg_daily_volume(volumes: List[float], lookback: int = _ADV_LOOKBACK) -> float:
    """Average daily volume from recent bars."""
    n = min(len(volumes), lookback)
    if n == 0:
        return 0.0
    return sum(volumes[-n:]) / n


# ---------------------------------------------------------------------------
# Slippage model
# ---------------------------------------------------------------------------


def compute_slippage_bps(
    daily_vol: float,
    order_size: int,
    avg_volume: float,
    price: float,
) -> float:
    """Dynamic slippage in basis points.

    Components:
    1. Base: 20 bps (BIST mid-cap typical spread)
    2. Volatility: higher vol → wider effective spread
    3. Size impact: larger orders relative to ADV → more market impact

    Returns total one-way slippage in bps.
    """
    # Base
    slip = _BASE_SLIPPAGE_BPS

    # Volatility component: 2% daily vol adds ~40 bps
    # daily_vol is decimal (0.02 = 2%), convert to bps contribution
    slip += daily_vol * _VOL_SLIPPAGE_MULT * 1000.0

    # Size impact: order notional / ADV notional
    if avg_volume > 0 and price > 0:
        adv_notional = avg_volume * price
        order_notional = order_size * price
        size_frac = order_notional / adv_notional if adv_notional > 0 else 1.0
        slip += (size_frac**0.5) * _SIZE_IMPACT_MULT * 100.0

    return max(_BASE_SLIPPAGE_BPS, min(slip, 200.0))  # cap at 200 bps


def compute_total_cost_bps() -> float:
    """Total round-trip fee in bps (commission + exchange + tax, per side)."""
    return _COMMISSION_BPS + _EXCHANGE_FEE_BPS + _TAX_BPS


# ---------------------------------------------------------------------------
# Fill ratio
# ---------------------------------------------------------------------------


def compute_fill_ratio(
    order_size: int,
    avg_volume: float,
    price: float,
) -> float:
    """Fill ratio in [0, 1]. 0 = reject, <1 = partial fill.

    Logic:
    - If order is ≤ 2% of ADV → full fill (1.0)
    - If order is > 10% of ADV → reject (0.0)
    - In between → linear interpolation from 1.0 to MIN_FILL_RATIO
    """
    if avg_volume <= 0 or price <= 0 or order_size <= 0:
        return 0.0

    adv_notional = avg_volume * price
    order_notional = order_size * price
    size_pct = order_notional / adv_notional if adv_notional > 0 else 1.0

    if size_pct <= _MAX_SIZE_PCT_OF_ADV:
        return 1.0
    if size_pct >= _REJECT_SIZE_PCT_OF_ADV:
        return 0.0

    # Linear interpolation
    t = (size_pct - _MAX_SIZE_PCT_OF_ADV) / (
        _REJECT_SIZE_PCT_OF_ADV - _MAX_SIZE_PCT_OF_ADV
    )
    return max(_MIN_FILL_RATIO, 1.0 - t * (1.0 - _MIN_FILL_RATIO))


# ---------------------------------------------------------------------------
# Tick rounding for decision prices
# ---------------------------------------------------------------------------


def round_decision_prices(decision: dict) -> dict:
    """Round entry/stop/target to BIST tick grid. Mutates in place."""
    for key in ("entry", "stop", "target"):
        if key in decision and isinstance(decision[key], (int, float)):
            decision[key] = round_to_tick(float(decision[key]))
    return decision


# ---------------------------------------------------------------------------
# Apply slippage to fill price
# ---------------------------------------------------------------------------


def apply_slippage(price: float, slippage_bps: float, side: str = "buy") -> float:
    """Apply slippage to execution price and round to tick.

    Buy → price goes UP (worse for buyer).
    Sell → price goes DOWN (worse for seller).
    """
    slip_frac = slippage_bps / 10_000.0
    if side == "buy":
        filled = price * (1.0 + slip_frac)
    else:
        filled = price * (1.0 - slip_frac)
    return round_to_tick(filled)
