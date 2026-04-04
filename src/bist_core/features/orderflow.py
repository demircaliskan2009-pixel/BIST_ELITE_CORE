import numpy as np


def volume_zscore(volumes, window=30):
    vols = np.array(volumes, dtype=float)
    mean = np.mean(vols[-window:])
    std = np.std(vols[-window:]) + 1e-9
    return (vols[-1] - mean) / std


def detect_breakout_vs_exhaustion(bar, vol_z):
    close = bar["close"]
    high = bar["high"]
    low = bar["low"]

    if vol_z > 1.2:
        if abs(close - high) < (high - low) * 0.25:
            signal = "BREAKOUT"
        else:
            signal = "EXHAUSTION"
    else:
        signal = "NONE"

    print({
        "ORDERFLOW_DEBUG_FINAL": {
            "vol_z": float(vol_z),
            "signal": signal
        }
    }, flush=True)

    return signal


def absorption_signal(bar, volume):
    rng = bar["high"] - bar["low"]
    body = abs(bar["close"] - bar["open"])

    if volume > 0 and rng > 0:
        if body / rng < 0.3:
            return True
    return False


def orderflow_edge_adjust(edge, signal):
    if signal == "BREAKOUT":
        return min(1.0, edge * 1.25)
    if signal == "EXHAUSTION":
        return edge * 0.7
    return edge


__all__ = [
    "volume_zscore",
    "detect_breakout_vs_exhaustion",
    "absorption_signal",
    "orderflow_edge_adjust",
]
