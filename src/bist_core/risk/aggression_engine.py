"""Opportunity Detection + Aggression Engine — adaptive risk multiplier for BIST.

Part 2: Opportunity Score
    Computes signal density, breakout clustering, and volume expansion across
    the universe to produce opportunity_score ∈ [0, 1].

Part 3: Aggression Engine
    Maps (regime, opportunity_score, volatility_state) → risk_multiplier ∈ [0.1, 3.0].
    Deterministic lookup with smooth interpolation.

All computations use only completed bars.  No lookahead, no randomness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from bist_core.models.ohlcv import OHLCVBar
from bist_core.regime.market_regime_v2 import RegimeSnapshot

# ---------------------------------------------------------------------------
# Constants — Opportunity
# ---------------------------------------------------------------------------

_BREAKOUT_LOOKBACK: Final[int] = 60    # 60 bars for breakout detection
_VOL_EXPANSION_LOOKBACK: Final[int] = 20
_OPPORTUNITY_EMA_ALPHA: Final[float] = 0.15  # smoothing for opp score

# ---------------------------------------------------------------------------
# Constants — Aggression
# ---------------------------------------------------------------------------

# Base risk multiplier per regime
_REGIME_BASE_MULT: Final[dict[str, float]] = {
    "SUPER_BULL": 1.8,
    "BULL": 1.3,
    "NEUTRAL": 1.0,
    "BEAR": 0.5,
    "CHAOS": 0.2,
}

# Opportunity boost range per regime [min_boost, max_boost]
_REGIME_OPP_BOOST: Final[dict[str, tuple[float, float]]] = {
    "SUPER_BULL": (0.0, 0.2),    # max 2.0x total (1.8 + 0.2)
    "BULL":       (0.0, 0.2),    # max 1.5x total
    "NEUTRAL":    (-0.1, 0.1),   # slight scaling only
    "BEAR":       (-0.2, 0.0),   # opportunity can only reduce
    "CHAOS":      (-0.1, 0.0),   # near-zero, no boost allowed
}

# Vol state damping: high vol reduces multiplier
_VOL_DAMPING_THRESHOLD: Final[float] = 0.025  # vol above this → damp
_VOL_DAMPING_FACTOR: Final[float] = 0.5       # reduce by up to 50%

# Hard floors/ceilings
_MIN_RISK_MULT: Final[float] = 0.1
_MAX_RISK_MULT: Final[float] = 2.0


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class OpportunityState:
    """Current market opportunity assessment."""
    breakout_density: float     # fraction of symbols making N-bar highs
    volume_expansion: float     # avg vol ratio across universe
    strength_clustering: float  # how many symbols break out together
    opportunity_score: float    # composite ∈ [0, 1]


@dataclass(frozen=True, slots=True)
class AggressionState:
    """Current aggression / risk multiplier state."""
    regime: str
    opportunity_score: float
    realized_vol: float
    base_mult: float
    opp_boost: float
    vol_damping: float
    risk_multiplier: float  # final ∈ [0.1, 3.0]


# ---------------------------------------------------------------------------
# Opportunity Score
# ---------------------------------------------------------------------------

def compute_opportunity(
    universe_m1: dict[str, list[OHLCVBar]],
    lookback: int = _BREAKOUT_LOOKBACK,
) -> OpportunityState:
    """Compute opportunity score from current universe state.

    Args:
        universe_m1: symbol → recent 1-min bars (at least `lookback` bars each)
        lookback: bars for breakout detection

    Returns:
        OpportunityState with composite opportunity_score ∈ [0, 1]
    """
    if not universe_m1:
        return OpportunityState(0.0, 0.0, 0.0, 0.0)

    breakout_count = 0
    vol_ratios: list[float] = []
    total = 0

    for sym, bars in universe_m1.items():
        if len(bars) < lookback + 1:
            continue
        total += 1

        recent = bars[-lookback:]
        current = bars[-1]

        # Breakout: current close above recent high
        recent_high = max(float(b.high) for b in recent[:-1]) if len(recent) > 1 else 0.0
        if float(current.close) > recent_high and recent_high > 0:
            breakout_count += 1

        # Volume expansion
        avg_vol = sum(float(b.volume) for b in recent) / len(recent) if recent else 0.0
        curr_vol = float(current.volume)
        if avg_vol > 0:
            vol_ratios.append(curr_vol / avg_vol)

    if total == 0:
        return OpportunityState(0.0, 0.0, 0.0, 0.0)

    breakout_density = breakout_count / total
    avg_vol_expansion = sum(vol_ratios) / len(vol_ratios) if vol_ratios else 1.0
    # Normalize volume expansion: 1.0=normal, >1.5=high
    vol_expansion_norm = min(1.0, max(0.0, (avg_vol_expansion - 0.5) / 2.0))

    # Strength clustering: penalize if only 1 symbol; reward if 3+ break out
    clustering = min(1.0, breakout_count / max(1, total // 2))

    # Composite score (weighted blend)
    raw_score = (
        0.50 * breakout_density +
        0.25 * vol_expansion_norm +
        0.25 * clustering
    )
    opp_score = max(0.0, min(1.0, raw_score))

    return OpportunityState(
        breakout_density=round(breakout_density, 4),
        volume_expansion=round(avg_vol_expansion, 4),
        strength_clustering=round(clustering, 4),
        opportunity_score=round(opp_score, 4),
    )


# ---------------------------------------------------------------------------
# Aggression Engine
# ---------------------------------------------------------------------------

def compute_risk_multiplier(
    regime: RegimeSnapshot | None,
    opportunity: OpportunityState,
    realized_vol: float | None = None,
) -> AggressionState:
    """Compute risk multiplier from regime, opportunity, and volatility.

    Deterministic mapping:
    1. Base multiplier from regime
    2. Opportunity boost (bounded per regime)
    3. Volatility damping (high vol reduces multiplier)
    4. Clamp to [0.1, 3.0]

    Args:
        regime: current market regime (None → NEUTRAL)
        opportunity: current opportunity state
        realized_vol: realized daily volatility (None → no damping)

    Returns:
        AggressionState with final risk_multiplier
    """
    regime_name = regime.regime if regime else "NEUTRAL"
    rvol = realized_vol if realized_vol is not None else (
        regime.realized_vol if regime else 0.0
    )

    # 1. Base multiplier
    base = _REGIME_BASE_MULT.get(regime_name, 1.0)

    # 2. Opportunity boost
    opp_range = _REGIME_OPP_BOOST.get(regime_name, (0.0, 0.0))
    opp_score = opportunity.opportunity_score
    # Linear interpolation: score=0 → min_boost, score=1 → max_boost
    opp_boost = opp_range[0] + (opp_range[1] - opp_range[0]) * opp_score

    # 3. Volatility damping
    vol_damping = 0.0
    if rvol > _VOL_DAMPING_THRESHOLD:
        # Linear damping: at 2x threshold → full damping
        excess = (rvol - _VOL_DAMPING_THRESHOLD) / _VOL_DAMPING_THRESHOLD
        vol_damping = -min(_VOL_DAMPING_FACTOR, excess * _VOL_DAMPING_FACTOR)

    # 4. Combine and clamp
    raw = base + opp_boost + vol_damping
    final = max(_MIN_RISK_MULT, min(_MAX_RISK_MULT, raw))

    return AggressionState(
        regime=regime_name,
        opportunity_score=round(opp_score, 4),
        realized_vol=round(rvol, 6),
        base_mult=round(base, 4),
        opp_boost=round(opp_boost, 4),
        vol_damping=round(vol_damping, 4),
        risk_multiplier=round(final, 4),
    )


__all__ = [
    "AggressionState",
    "OpportunityState",
    "compute_opportunity",
    "compute_risk_multiplier",
]
