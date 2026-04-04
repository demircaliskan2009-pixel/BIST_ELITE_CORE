"""BIST-style session phase from Unix timestamp (TRT UTC+3, deterministic)."""

from __future__ import annotations


class SessionEngine:
    def get_phase(self, ts: int) -> str:
        import datetime

        _tz = datetime.timezone(datetime.timedelta(hours=3))
        dt = datetime.datetime.fromtimestamp(int(ts), tz=_tz)
        h = dt.hour
        m = dt.minute

        if h == 9 and m < 55:
            return "pre_open"

        if (h == 9 and m >= 55) or (h == 10 and m < 0):
            return "auction_open"

        if h >= 10 and h < 18:
            return "continuous"

        if h == 18 and m < 5:
            return "auction_close"

        return "closed"


__all__ = ["SessionEngine"]
