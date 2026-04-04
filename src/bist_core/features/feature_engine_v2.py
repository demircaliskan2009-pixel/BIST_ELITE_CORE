"""Feature engine v2 — extra scalars for regime edge models (numpy where noted)."""

from __future__ import annotations

from typing import Any, Dict, List

from bist_core.features.feature_engine import FeatureEngine


def compute_rsi(closes: List[float], period: int = 14) -> Any:
    """Wilder RSI series (same length as ``closes``); leading values are ``nan``."""
    import numpy as np

    c = np.asarray(closes, dtype=float)
    n = int(c.size)
    rsi = np.full(n, np.nan, dtype=float)
    if n < period + 1:
        return rsi
    delta = np.diff(c)
    gains = np.clip(delta, 0.0, None)
    losses = np.clip(-delta, 0.0, None)
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))
    idx = period
    if avg_loss == 0.0:
        rsi[idx] = 100.0 if avg_gain > 0.0 else 0.0
    else:
        rs = avg_gain / avg_loss
        rsi[idx] = 100.0 - (100.0 / (1.0 + rs))
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        idx = i + 1
        if avg_loss == 0.0:
            rsi[idx] = 100.0 if avg_gain > 0.0 else 0.0
        else:
            rs = avg_gain / avg_loss
            rsi[idx] = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def compute_rsi_zscore(closes: List[float]) -> float:
    import numpy as np

    rsi = compute_rsi(closes)
    if np.all(np.isnan(rsi)):
        return 0.0
    m = float(np.nanmean(rsi))
    s = float(np.nanstd(rsi)) + 1e-6
    last = rsi[-1]
    if np.isnan(last):
        return 0.0
    return float((float(last) - m) / s)


def bollinger_distance(closes: List[float]) -> float:
    import numpy as np

    if len(closes) < 20:
        return 0.0
    w = np.asarray(closes[-20:], dtype=float)
    ma = float(np.mean(w))
    std = float(np.std(w))
    last = float(closes[-1])
    return float((last - ma) / (std + 1e-6))


def ema_slope(closes: List[float]) -> float:
    import numpy as np

    if len(closes) < 30:
        return 0.0
    w10 = np.asarray(closes[-10:], dtype=float)
    w30 = np.asarray(closes[-30:], dtype=float)
    ema_fast = float(np.mean(w10))
    ema_slow = float(np.mean(w30))
    return float((ema_fast - ema_slow) / (ema_slow + 1e-6))


def higher_highs(closes: List[float]) -> float:
    if len(closes) < 6:
        return 0.0
    return float(closes[-1] > max(closes[-5:-1]))


def volume_spike(volumes: List[float]) -> float:
    import numpy as np

    if len(volumes) < 20:
        return 0.0
    v = np.asarray(volumes[-20:], dtype=float)
    return float(volumes[-1] > float(np.mean(v)))


def inject_edge_model_features(
    features: Dict[str, Any],
    closes: List[float],
    volumes: List[float],
) -> None:
    features.update(
        {
            "rsi_zscore": compute_rsi_zscore(closes),
            "bollinger_distance": bollinger_distance(closes),
            "ema_slope": ema_slope(closes),
            "higher_highs": higher_highs(closes),
            "volume_spike": volume_spike(volumes),
        }
    )


class FeatureEngineV2(FeatureEngine):
    """Extends :class:`FeatureEngine` with edge-model feature keys."""

    def _full_closes_volumes(self, bars: List[Any]) -> tuple[List[float], List[float]]:
        closes: List[float] = []
        volumes: List[float] = []
        for b in bars:
            try:
                c = getattr(b, "close", None)
                if isinstance(c, (int, float)) and float(c) > 0:
                    closes.append(float(c))
                    vv = getattr(b, "volume", None)
                    volumes.append(
                        float(vv)
                        if isinstance(vv, (int, float)) and float(vv) >= 0
                        else 0.0
                    )
            except Exception:
                continue
        return closes, volumes

    def extract(self, bars: List[Any], *, lookback: int = 20) -> Dict[str, float]:
        out: Dict[str, float] = super().extract(bars, lookback=lookback)
        closes, volumes = self._full_closes_volumes(bars)
        n_need = max(60, int(lookback), 30)
        if len(closes) > n_need:
            closes = closes[-n_need:]
            volumes = volumes[-n_need:]
        inject_edge_model_features(out, closes, volumes)
        return out


__all__ = [
    "FeatureEngineV2",
    "compute_rsi",
    "compute_rsi_zscore",
    "bollinger_distance",
    "ema_slope",
    "higher_highs",
    "volume_spike",
    "inject_edge_model_features",
]
