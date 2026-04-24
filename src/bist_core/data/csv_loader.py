"""CSV loader for sample BIST data."""

import os

from bist_core.models.ohlcv import OHLCVBar

BASE_PATH = os.path.join("data", "sample_bist")


def _is_valid_bar(o, h, l, c, v):
    if not all(isinstance(x, (int, float)) for x in (o, h, l, c, v)):
        return False
    if not (l <= o <= h and l <= c <= h):
        return False
    if v < 0:
        return False
    return True


def load_csv(symbol: str):
    path = os.path.join(BASE_PATH, f"{symbol}.csv")

    if not os.path.exists(path):
        return []

    bars = []

    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    for line in lines[1:]:
        parts = line.split(",")

        if len(parts) < 6:
            continue

        try:
            o = float(parts[1])
            h = float(parts[2])
            l = float(parts[3])
            c = float(parts[4])
            v = float(parts[5])

            if not _is_valid_bar(o, h, l, c, v):
                continue

            bars.append(
                OHLCVBar(
                    timestamp=str(parts[0]),
                    symbol=symbol,
                    open=o,
                    high=h,
                    low=l,
                    close=c,
                    volume=v,
                )
            )
        except Exception:
            continue

    return bars
