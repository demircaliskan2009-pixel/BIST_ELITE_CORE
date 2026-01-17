from __future__ import annotations

from datetime import date as Date
import math
from typing import Dict, List, Optional

from bist_core.models import EODBar, PriceBand
from bist_core.repositories import local_csv as repo
from bist_core.services.marketdata import MarketData


def build_bar_for_symbol_day(
    symbol: str,
    day: str,
    md: MarketData,
) -> Optional[EODBar]:
    try:
        day_date = Date.fromisoformat(day)
    except ValueError:
        return None

    try:
        close_map = md.close_map(day)
    except Exception:
        return None

    close_val = close_map.get(symbol)
    if close_val is None or (isinstance(close_val, float) and math.isnan(close_val)):
        return None

    close = float(close_val)
    caps = _capabilities(md)

    if caps.get("ohlcv"):
        ohlcv_map = getattr(md, "ohlcv_map")(day)
        row = ohlcv_map.get(symbol, {})
        high = float(row.get("high", close))
        low = float(row.get("low", close))
        volume = int(row.get("volume", 0))
        turnover_tl = int(row.get("turnover_tl", 0))
    else:
        high = close
        low = close
        volume = 0
        turnover_tl = 0

    return EODBar(
        symbol=symbol,
        date=day_date,
        close=close,
        high=high,
        low=low,
        volume=volume,
        turnover_tl=turnover_tl,
    )


def build_bars_for_day(day: str, md: MarketData) -> List[EODBar]:
    """
    Snapshot verisinden EODBar listesi üretir.
    Veri eksikse fail-closed olarak boş liste döner.
    """
    try:
        symbols = md.symbols(day)
    except Exception:
        return []

    if not symbols:
        return []

    bars: List[EODBar] = []

    for sym in symbols:
        bar = build_bar_for_symbol_day(sym, day, md)
        if bar is not None:
            bars.append(bar)

    return bars


def build_bands_for_day(day: str, md: MarketData, cfg) -> List[PriceBand]:
    """
    Repo içinde mevcut bant kuralı varsa onu kullanır.
    Belirsizlikte fail-closed olarak boş liste döner.
    """
    try:
        return repo.price_bands()
    except Exception:
        return []


def _capabilities(md: MarketData) -> Dict[str, bool]:
    return {
        "ohlcv": hasattr(md, "ohlcv_map"),
    }
