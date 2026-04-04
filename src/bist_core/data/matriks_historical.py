"""Matriks test-env historical bar fetch — chunked daily, fail-closed, deterministic."""

from __future__ import annotations

import math
import os
from datetime import date, datetime, timedelta
from typing import Any, Optional

from bist_core.data.matriks_provider import _matriks_network_enabled
from bist_core.models.ohlcv import OHLCVBar

BASE_URL = "https://apitest.matriksdata.com/dumrul/v1/tick/bar"


def _period_param(period: str) -> int | str:
    """Map canonical TF labels to Matriks ``period`` query param (deterministic)."""
    p = str(period).strip().lower()
    if p in ("1m", "m1"):
        return 1
    if p in ("5m", "m5"):
        return 5
    if p in ("60m", "1h", "h1"):
        return 60
    if p in ("1d", "d1", "day"):
        return "1day"
    return 1


def _parse_date(d: date | str) -> date:
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    s = str(d).strip()
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def _ts_sort_key(ts: int) -> int:
    return int(ts)


class MatriksHistorical:
    """Daily-chunked bar history; network only when ``MATRIKS_ENABLED`` and ``MATRIKS_TOKEN`` set."""

    def __init__(self) -> None:
        self.token = os.getenv("MATRIKS_TOKEN")
        self.cache: dict[tuple[str, str, str, str], list[OHLCVBar]] = {}

    def fetch(
        self,
        symbol: str,
        *,
        start: date | str | None = None,
        end: date | str | None = None,
        period: str = "1m",
    ) -> list[OHLCVBar]:
        """Fetch bars with default **[end−120d, end]** when ``start``/``end`` omitted."""
        end_d = _parse_date(end) if end is not None else date.today()
        start_d = _parse_date(start) if start is not None else end_d - timedelta(days=120)
        return self.fetch_bars(symbol, start_d, end_d, period=period)

    def fetch_bars(
        self,
        symbol: str,
        start: date | str,
        end: date | str,
        *,
        period: str = "1m",
    ) -> list[OHLCVBar]:
        """
        Fetch OHLCV bars for ``[start, end]`` (inclusive), one HTTP request per calendar day.

        ``period``: ``1m`` | ``5m`` | ``60m`` | ``1d`` (mapped to API params).

        Returns ``[]`` if disabled, missing token, any day fails, any row invalid, or final bar count < 200.
        """
        sym = str(symbol).strip().upper()
        if not sym:
            return []

        d0 = _parse_date(start)
        d1 = _parse_date(end)
        if d0 > d1:
            return []

        pkey = str(period).strip().lower()
        key = (sym, d0.isoformat(), d1.isoformat(), pkey)
        if key in self.cache:
            return list(self.cache[key])

        if not _matriks_network_enabled() or not (self.token or "").strip():
            return []

        merged: list[OHLCVBar] = []
        cur = d0
        while cur <= d1:
            day_bars = self._fetch_one_day(sym, cur, period=pkey)
            if day_bars is None:
                return []
            merged.extend(day_bars)
            cur += timedelta(days=1)

        out = self._finalize(merged)
        if len(out) < 200:
            return []

        self.cache[key] = out
        return list(out)

    def _fetch_one_day(self, symbol: str, day: date, *, period: str) -> Optional[list[OHLCVBar]]:
        raw = self._http_get_day(symbol, day, period=period)
        if raw is None:
            return None
        rows = self._extract_rows(raw)
        if rows is None:
            return None
        bars: list[OHLCVBar] = []
        for row in rows:
            if not isinstance(row, dict):
                return None
            b = self._row_to_bar(symbol, row)
            if b is None:
                return None
            bars.append(b)
        return bars

    def _http_get_day(self, symbol: str, day: date, *, period: str = "1m") -> Optional[Any]:
        try:
            import requests
        except Exception:
            return None

        ds = day.isoformat()
        params = {"symbol": symbol, "period": _period_param(period), "start": ds, "end": ds}
        headers = {"Authorization": f"jwt {self.token}"}

        try:
            r = requests.get(BASE_URL, params=params, headers=headers, timeout=60)
        except Exception:
            return None

        if r.status_code != 200:
            return None

        try:
            return r.json()
        except Exception:
            return None

    @staticmethod
    def _extract_rows(payload: Any) -> Optional[list[Any]]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            inner = payload.get("data")
            if isinstance(inner, list):
                return inner
        return None

    @staticmethod
    def _parse_timestamp(t: Any) -> Optional[int]:
        if t is None or isinstance(t, bool):
            return None
        if isinstance(t, int):
            return t
        if isinstance(t, float):
            return int(t)
        try:
            return int(float(str(t).strip()))
        except (TypeError, ValueError):
            return None

    def _row_to_bar(self, symbol: str, row: dict[str, Any]) -> Optional[OHLCVBar]:
        t = self._field(row, "t")
        o = self._field(row, "o")
        h = self._field(row, "h")
        l_ = self._field(row, "l")
        c = self._field(row, "c")
        v = self._field(row, "v")

        if any(x is None for x in (t, o, h, l_, c, v)):
            return None

        ts = self._parse_timestamp(t)
        if ts is None:
            return None

        try:
            open_ = float(o)
            high = float(h)
            low = float(l_)
            close = float(c)
            volume = float(v)
        except (TypeError, ValueError):
            return None

        if any(math.isnan(x) or math.isinf(x) for x in (open_, high, low, close, volume)):
            return None

        if close <= 0 or high < low or volume < 0:
            return None

        return OHLCVBar(
            timestamp=int(ts),
            symbol=symbol,
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume,
        )

    @staticmethod
    def _field(row: dict[str, Any], key: str) -> Any:
        for k in (key, key.upper()):
            if k in row:
                return row[k]
        return None

    def _finalize(self, bars: list[OHLCVBar]) -> list[OHLCVBar]:
        if not bars:
            return []

        sorted_bars = sorted(bars, key=lambda b: _ts_sort_key(b.timestamp))
        seen: dict[int, OHLCVBar] = {}
        for b in sorted_bars:
            seen[b.timestamp] = b
        uniq = sorted(seen.values(), key=lambda x: _ts_sort_key(x.timestamp))
        return list(uniq)


__all__ = ["MatriksHistorical", "BASE_URL", "_period_param"]
