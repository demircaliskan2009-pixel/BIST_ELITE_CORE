from __future__ import annotations

from datetime import date as Date
import math
from pathlib import Path
from typing import Dict, List, Optional

from bist_core.models import EODBar, PriceBand
from bist_core.repositories import local_csv as repo
from bist_core.services.marketdata import MarketData


def _bar_from_maps(
    symbol: str,
    day: str,
    close_map: Dict[str, float],
    ohlcv_map: Optional[Dict[str, Dict]] = None,
) -> Optional[EODBar]:
    """Build EODBar from preloaded close_map and optional ohlcv_map."""
    try:
        day_date = Date.fromisoformat(day)
    except ValueError:
        return None

    close_val = close_map.get(symbol)
    if close_val is None or (isinstance(close_val, float) and math.isnan(close_val)):
        return None

    close = float(close_val)
    if ohlcv_map and symbol in ohlcv_map:
        row = ohlcv_map[symbol]
        high = float(row.get("high", close))
        low = float(row.get("low", close))
        volume = int(row.get("volume", 0))
        turnover_val = row.get("turnover_tl", row.get("turnover", 0))
        turnover_tl = int(turnover_val)
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
    close_map ve ohlcv_map dosyayı tek kez okur (verimsizlik giderildi).
    Veri eksikse fail-closed olarak boş liste döner.
    """
    try:
        symbols = md.symbols(day)
    except Exception:
        return []

    if not symbols:
        return []

    try:
        close_map = md.close_map(day)
    except Exception:
        return []

    ohlcv_map: Optional[Dict[str, Dict]] = None
    if _supports_ohlcv(md, day):
        try:
            ohlcv_map = md.ohlcv_map(day)
        except Exception:
            pass

    bars: List[EODBar] = []
    for sym in sorted(symbols):
        bar = _bar_from_maps(sym, day, close_map, ohlcv_map)
        if bar is not None:
            bars.append(bar)

    return bars


def build_bars_window(
    end_day: str,
    md: MarketData,
    base_dir: Path,
    lookback_days: int,
) -> List[EODBar]:
    """
    end_day dahil geriye doğru en fazla lookback_days gün snapshot'larından bar üretir.
    base_dir/YYYY-MM-DD/snapshot.csv klasörlerini tarar.
    Fail-closed: hiç gün bulunamazsa [] döner.
    Deterministik: günler ve semboller sıralı.
    """
    base = Path(base_dir)
    if not base.is_dir():
        return []

    days_found: List[str] = []
    for sub in sorted(base.iterdir()):
        if not sub.is_dir():
            continue
        day_str = sub.name
        if not _is_valid_date(day_str):
            continue
        if (sub / "snapshot.csv").is_file():
            days_found.append(day_str)

    days_found.sort()
    # Fail-closed: end_day must exist
    if end_day not in days_found:
        return []

    # Filter to <= end_day, take last lookback_days
    candidates = [d for d in days_found if d <= end_day]
    window_days = candidates[-lookback_days:]
    bars: List[EODBar] = []

    for day_str in window_days:
        try:
            close_map = md.close_map(day_str)
        except Exception:
            continue

        ohlcv_map: Optional[Dict[str, Dict]] = None
        if _supports_ohlcv(md, day_str):
            try:
                ohlcv_map = md.ohlcv_map(day_str)
            except Exception:
                pass

        symbols = list(close_map.keys()) if close_map else []
        for sym in sorted(symbols):
            bar = _bar_from_maps(sym, day_str, close_map, ohlcv_map)
            if bar is not None:
                bars.append(bar)

    return bars


def _is_valid_date(s: str) -> bool:
    try:
        Date.fromisoformat(s)
        return True
    except ValueError:
        return False


def build_bands_for_day(day: str, md: MarketData, cfg) -> List[PriceBand]:
    """
    Repo içinde mevcut bant kuralı varsa onu kullanır.
    Belirsizlikte fail-closed olarak boş liste döner.
    """
    try:
        return repo.price_bands()
    except Exception:
        return []


def _supports_ohlcv(md: MarketData, day: str) -> bool:
    if hasattr(md, "has_ohlcv"):
        try:
            return md.has_ohlcv(day)
        except Exception:
            return False
    return hasattr(md, "ohlcv_map")
