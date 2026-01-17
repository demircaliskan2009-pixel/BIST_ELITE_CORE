from __future__ import annotations

from datetime import date as Date
import math
from typing import List

from bist_core.models import EODBar, PriceBand
from bist_core.repositories import local_csv as repo
from bist_core.services.marketdata import MarketData


def build_bars_for_day(day: str, md: MarketData) -> List[EODBar]:
    """
    Snapshot verisinden EODBar listesi üretir.
    Veri eksikse fail-closed olarak boş liste döner.
    """
    try:
        day_date = Date.fromisoformat(day)
    except ValueError:
        return []

    try:
        symbols = md.symbols(day)
        close_map = md.close_map(day)
    except Exception:
        return []

    if not symbols and not close_map:
        return []

    bars: List[EODBar] = []
    if not symbols:
        symbols = list(close_map.keys())

    for sym in symbols:
        close_val = close_map.get(sym)
        if close_val is None or (isinstance(close_val, float) and math.isnan(close_val)):
            continue
        close = float(close_val)
        bars.append(
            EODBar(
                symbol=sym,
                date=day_date,
                close=close,
                high=close,
                low=close,
                volume=0,
                turnover_tl=0,
            )
        )

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
