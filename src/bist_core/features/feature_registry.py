"""Feature registry — maps feature names to indicator functions.

Provides ``register_feature``, ``get_feature``, ``list_features`` and
a pre-populated ``FEATURE_REGISTRY`` with standard BIST indicators.
"""

from __future__ import annotations

from functools import partial
from typing import Any, Callable, Dict, List, Optional, Sequence

from bist_core.backtest.backtest_engine import OHLCVBar
from bist_core.features.indicator_library import atr, ema, momentum_20, returns, rsi, sma

FeatureFn = Callable[[Sequence[OHLCVBar]], List[Optional[float]]]

FEATURE_REGISTRY: Dict[str, FeatureFn] = {}


def _wrap(fn: Callable[..., Any], **kwargs: Any) -> FeatureFn:
    return partial(fn, **kwargs)


def register_feature(name: str, fn: FeatureFn) -> None:
    FEATURE_REGISTRY[name] = fn


def get_feature(name: str) -> FeatureFn:
    if name not in FEATURE_REGISTRY:
        raise KeyError(f"Unknown feature: {name!r}")
    return FEATURE_REGISTRY[name]


def list_features() -> list[str]:
    return sorted(FEATURE_REGISTRY.keys())


# -- Pre-populate standard features ---------------------------------------

register_feature("sma_20", _wrap(sma, period=20))
register_feature("sma_50", _wrap(sma, period=50))
register_feature("ema_20", _wrap(ema, period=20))
register_feature("rsi_14", _wrap(rsi, period=14))
register_feature("atr_14", _wrap(atr, period=14))
register_feature("returns", returns)
register_feature("momentum_20", momentum_20)
