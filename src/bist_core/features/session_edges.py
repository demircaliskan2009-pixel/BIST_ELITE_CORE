from datetime import datetime


def in_time_range(ts, start, end):
    t = datetime.fromtimestamp(ts).strftime("%H:%M")
    return start <= t <= end


def opening_drift_edge(bars):
    if len(bars) < 10:
        return 0.0

    ret = (bars[-1]["close"] - bars[-10]["close"]) / bars[-10]["close"]
    return ret


def closing_pressure_edge(bars):
    if len(bars) < 30:
        return 0.0

    ret = (bars[-1]["close"] - bars[-30]["close"]) / bars[-30]["close"]
    return ret


__all__ = [
    "in_time_range",
    "opening_drift_edge",
    "closing_pressure_edge",
]
