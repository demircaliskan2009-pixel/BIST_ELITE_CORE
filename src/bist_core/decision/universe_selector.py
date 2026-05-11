"""PRDV3 Universe Selection Engine — dynamic symbol ranking and filtering.

Architecture:

    vendor data → UniverseSelector (rank + filter) → PortfolioDecisionEngine
               → MetaDecisionEngine → BistEdgeV2Decision → BacktestEngine

The universe selector adds SYMBOL INTELLIGENCE to the pipeline:

1. TREND QUALITY (25%): SMA alignment strength with uptrend bonus.
   Our edges are long-biased — trending symbols score higher.

2. VOLATILITY REGIME (25%): sweet-spot daily vol preferred.
   Too low = no moves (waste of capital). Too high = blown stops.
   Sweet spot: 1.5%–3.5% daily return stddev.

3. EFFICIENCY (25%): lag-1 autocorrelation of returns.
   |acf1| > 0 means the symbol has exploitable structure
   (trending or mean-reverting). Zero = random walk = no edge.

4. LIQUIDITY (25%): average daily turnover (close × volume).
   Higher liquidity = better fills, lower slippage, tighter spreads.

Equal weights avoid overfitting to any single factor.
Rebalances every _REBALANCE_DAYS trading days.
During warmup (no symbol has _LOOKBACK bars), all symbols allowed.
All logic is deterministic. No ML, no randomness, no future data.
"""

from __future__ import annotations

import math
from typing import Dict, List, Set, Tuple

# ---------------------------------------------------------------------------
# Constants — structural, not optimized
# ---------------------------------------------------------------------------

_LOOKBACK = 60  # minimum bars for scoring
_SMA_SHORT = 20
_SMA_LONG = 50
_REBALANCE_DAYS = 5  # re-rank every 5 trading days
_DEFAULT_TOP_N = 10  # select top 10 symbols

# Equal weights — avoids overfitting to any single factor
_W_TREND = 0.25
_W_VOLATILITY = 0.25
_W_EFFICIENCY = 0.25
_W_LIQUIDITY = 0.25

# Volatility sweet-spot thresholds (daily return stddev)
_VOL_FLOOR = 0.005  # below this → too quiet
_VOL_SWEET_LO = 0.015  # sweet spot starts
_VOL_SWEET_HI = 0.035  # sweet spot ends
_VOL_CEILING = 0.06  # above this → too dangerous


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sma(values: List[float], period: int) -> float:
    """Simple moving average of last ``period`` values."""
    if len(values) < period or period <= 0:
        return 0.0
    return sum(values[-period:]) / period


# ---------------------------------------------------------------------------
# Scoring components
# ---------------------------------------------------------------------------


def score_trend_quality(closes: List[float]) -> float:
    """Trend strength from SMA alignment. Long-only bias.

    |SMA20 − SMA50| / SMA50 measures divergence.
    Uptrend bonus: our edges are long-biased.
    Returns score in [0, 1]. 0.5 = neutral (insufficient data).
    """
    if len(closes) < _SMA_LONG:
        return 0.5

    sma_s = _sma(closes, _SMA_SHORT)
    sma_l = _sma(closes, _SMA_LONG)

    if sma_l <= 0:
        return 0.0

    divergence = abs(sma_s - sma_l) / sma_l
    score = min(divergence / 0.05, 1.0)  # 5% divergence = max

    # Uptrend bonus (edges are long-only)
    if sma_s > sma_l:
        score = min(score * 1.2, 1.0)

    return round(score, 6)


def score_volatility_regime(closes: List[float]) -> float:
    """Sweet-spot volatility scoring. Moderate daily vol preferred.

    Too low (<0.5%): no moves, waste of capital.
    Sweet spot (1.5%–3.5%): edges work best.
    Too high (>6%): stops blown frequently.
    Returns score in [0, 1]. 0.5 = neutral.
    """
    n = len(closes)
    if n < _SMA_LONG:
        return 0.5

    window = closes[-min(n, _LOOKBACK) :]
    rets: List[float] = []
    for i in range(1, len(window)):
        if window[i - 1] > 0:
            rets.append((window[i] - window[i - 1]) / window[i - 1])

    if len(rets) < 10:
        return 0.5

    mean_r = sum(rets) / len(rets)
    daily_vol = (sum((r - mean_r) ** 2 for r in rets) / len(rets)) ** 0.5

    # Sweet-spot piecewise linear
    if daily_vol < _VOL_FLOOR:
        return 0.2
    if daily_vol < _VOL_SWEET_LO:
        return round(
            0.2 + 0.8 * (daily_vol - _VOL_FLOOR) / (_VOL_SWEET_LO - _VOL_FLOOR),
            6,
        )
    if daily_vol <= _VOL_SWEET_HI:
        return 1.0
    if daily_vol <= _VOL_CEILING:
        return round(
            1.0
            - 0.8 * (daily_vol - _VOL_SWEET_HI) / (_VOL_CEILING - _VOL_SWEET_HI),
            6,
        )
    return 0.2


def score_efficiency(closes: List[float]) -> float:
    """Edge exploitability via lag-1 autocorrelation.

    |acf(1)| measures return predictability:
    - Positive acf → trending (good for trend_pullback).
    - Negative acf → mean-reverting (good for mean_reversion).
    - Zero → random walk → no edge.
    Returns score in [0, 1]. 0.5 = neutral.
    """
    n = len(closes)
    if n < _SMA_LONG:
        return 0.5

    window = closes[-min(n, _LOOKBACK) :]
    rets: List[float] = []
    for i in range(1, len(window)):
        if window[i - 1] > 0:
            rets.append((window[i] - window[i - 1]) / window[i - 1])

    if len(rets) < 10:
        return 0.5

    mean_r = sum(rets) / len(rets)
    var = sum((r - mean_r) ** 2 for r in rets) / len(rets)
    if var <= 0:
        return 0.5

    # Lag-1 autocovariance
    cov = sum(
        (rets[i] - mean_r) * (rets[i - 1] - mean_r) for i in range(1, len(rets))
    ) / (len(rets) - 1)
    acf1 = cov / var

    # |acf1| → higher = more exploitable; 0.3+ = very exploitable
    return round(min(abs(acf1) / 0.3, 1.0), 6)


def score_liquidity(closes: List[float], volumes: List[float]) -> float:
    """Liquidity from average daily turnover (close × volume).

    Log-scale normalization: 10M TRY ≈ 0.33, 100M ≈ 0.67, 1B = 1.0.
    Returns score in [0, 1].
    """
    n = min(len(closes), len(volumes), _SMA_SHORT)
    if n == 0:
        return 0.0

    total = 0.0
    for i in range(n):
        c = closes[-(n - i)]
        v = volumes[-(n - i)]
        if c > 0 and v > 0:
            total += c * v

    turnover = total / n
    if turnover <= 0:
        return 0.0

    log_t = math.log10(turnover)
    # 1M (6) = 0.0, 1B (9) = 1.0
    score = (log_t - 6.0) / 3.0
    return round(max(0.0, min(1.0, score)), 6)


# ---------------------------------------------------------------------------
# Composite scorer
# ---------------------------------------------------------------------------


def score_symbol(
    closes: List[float],
    volumes: List[float],
) -> Dict[str, float]:
    """Composite score for universe selection.

    Returns component scores and weighted composite.
    All components in [0, 1]. Composite in [0, 1].
    """
    trend = score_trend_quality(closes)
    vol = score_volatility_regime(closes)
    eff = score_efficiency(closes)
    liq = score_liquidity(closes, volumes)

    composite = (
        _W_TREND * trend
        + _W_VOLATILITY * vol
        + _W_EFFICIENCY * eff
        + _W_LIQUIDITY * liq
    )

    return {
        "trend_quality": round(trend, 4),
        "volatility_regime": round(vol, 4),
        "efficiency": round(eff, 4),
        "liquidity": round(liq, 4),
        "composite": round(composite, 4),
    }


# ---------------------------------------------------------------------------
# Universe Selector
# ---------------------------------------------------------------------------


class UniverseSelector:
    """Dynamic universe selection — ranks symbols, gates trading.

    Integration point for PortfolioDecisionEngine:
    1. ``update_bar()`` — feed each bar to accumulate history.
    2. ``is_allowed()`` — check if symbol is in current universe.

    Rebalances every ``rebalance_days`` trading days.
    During warmup (no symbol has ``_LOOKBACK`` bars), all symbols allowed.
    Deterministic: same input sequence → same rankings.
    """

    def __init__(
        self,
        top_n: int = _DEFAULT_TOP_N,
        rebalance_days: int = _REBALANCE_DAYS,
    ) -> None:
        self._top_n = top_n
        self._rebalance_days = rebalance_days
        self._closes: Dict[str, List[float]] = {}
        self._volumes: Dict[str, List[float]] = {}
        self._universe: Set[str] = set()
        self._scores: Dict[str, Dict[str, float]] = {}
        self._rankings: List[Tuple[str, Dict[str, float]]] = []
        self._current_ts: int = -1
        self._days_since_rebalance: int = 0

    # -- read-only properties -----------------------------------------------

    @property
    def universe(self) -> Set[str]:
        """Current allowed symbols (empty during warmup)."""
        return set(self._universe)

    @property
    def scores(self) -> Dict[str, Dict[str, float]]:
        """Latest scores per symbol."""
        return dict(self._scores)

    @property
    def rankings(self) -> List[Tuple[str, Dict[str, float]]]:
        """Latest rankings (symbol, scores) sorted by composite desc."""
        return list(self._rankings)

    # -- public API ---------------------------------------------------------

    def update_bar(
        self,
        symbol: str,
        close: float,
        volume: float,
        timestamp: int,
    ) -> None:
        """Feed a bar. Triggers rebalance on schedule.

        Rebalance happens BEFORE adding the current bar so that all
        symbols have T-1 complete data at rebalance time.
        """
        # Detect new day BEFORE adding bar → rebalance uses T-1 data
        if timestamp != self._current_ts:
            self._days_since_rebalance += 1
            self._current_ts = timestamp
            if (
                self._days_since_rebalance >= self._rebalance_days
                or not self._universe
            ):
                self._rebalance()
                self._days_since_rebalance = 0

        # Accumulate
        if symbol not in self._closes:
            self._closes[symbol] = []
            self._volumes[symbol] = []
        self._closes[symbol].append(close)
        self._volumes[symbol].append(volume)

    def is_allowed(self, symbol: str) -> bool:
        """Check if symbol is in current universe.

        During warmup (empty universe), all symbols allowed.
        """
        if not self._universe:
            return True
        return symbol in self._universe

    # -- internal -----------------------------------------------------------

    def _rebalance(self) -> None:
        """Re-score and re-rank all symbols with sufficient history."""
        scored: Dict[str, Dict[str, float]] = {}
        for sym in self._closes:
            if len(self._closes[sym]) < _LOOKBACK:
                continue
            scored[sym] = score_symbol(self._closes[sym], self._volumes[sym])

        if not scored:
            return  # stay in warmup

        # Sort by composite desc, then alphabetical for deterministic tie-break
        ranked = sorted(
            scored.items(),
            key=lambda x: (-x[1]["composite"], x[0]),
        )

        self._universe = {sym for sym, _ in ranked[: self._top_n]}
        self._scores = scored
        self._rankings = [(sym, s) for sym, s in ranked]
