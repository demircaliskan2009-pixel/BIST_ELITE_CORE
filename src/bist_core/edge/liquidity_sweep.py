from typing import List, Dict, Any


def detect_liquidity_sweep(bars: List[Dict[str, float]]) -> Dict[str, Any]:
    """
    Detects liquidity sweep (stop hunt + rejection)

    bars: list of dict with keys:
        open, high, low, close, volume
    """

    if len(bars) < 50:
        return {"sweep": False}

    last = bars[-1]
    prev = bars[-20:-1]

    prev_high = max(b["high"] for b in prev)
    prev_low = min(b["low"] for b in prev)

    sweep_up = last["high"] > prev_high
    sweep_down = last["low"] < prev_low

    body = abs(last["close"] - last["open"])
    upper_wick = last["high"] - max(last["close"], last["open"])
    lower_wick = min(last["close"], last["open"]) - last["low"]

    # wick ratio
    wick_up_ratio = upper_wick / (body + 1e-6)
    wick_down_ratio = lower_wick / (body + 1e-6)

    # volume spike
    avg_vol = sum(b["volume"] for b in prev) / len(prev)
    vol_spike = last["volume"] > avg_vol * 1.5

    signal = None
    strength = 0.0

    # SHORT setup (sweep up → rejection)
    if sweep_up and wick_up_ratio > 1.5 and vol_spike:
        signal = "sell"
        strength = min(1.0, wick_up_ratio / 3)

    # LONG setup (sweep down → rejection)
    elif sweep_down and wick_down_ratio > 1.5 and vol_spike:
        signal = "buy"
        strength = min(1.0, wick_down_ratio / 3)

    return {
        "sweep": signal is not None,
        "signal": signal,
        "strength": round(strength, 4),
        "sweep_up": sweep_up,
        "sweep_down": sweep_down,
        "vol_spike": vol_spike,
    }
