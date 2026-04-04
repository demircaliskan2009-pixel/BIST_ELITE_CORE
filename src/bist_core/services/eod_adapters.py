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


def resolve_snapshots_base(root: Path) -> Path:
    """
    Accept both:
      - snapshots base dir (contains YYYY-MM-DD subfolders)
      - .../eod/snapshots
      - data root -> data/eod/snapshots
    """
    root = Path(root)

    # If root already looks like snapshots base, keep it.
    try:
        if any(p.is_dir() for p in root.glob("????-??-??")):
            return root
    except Exception:
        pass

    # allow passing .../eod/snapshots directly
    if root.name.lower() == "snapshots" and root.parent.name.lower() == "eod":
        return root

    return root / "eod" / "snapshots"


def materialize_snapshots_from_inbox(
    *,
    data_root: Path,
    snapshots_base: Path,
    symbols: list[str] | None,
    end_day: str,
    lookback: int,
) -> None:
    """
    Bootstrap snapshots_base/YYYY-MM-DD/snapshot.csv from data_root/inbox/{SYMBOL}.csv or {SYMBOL}.symbol.csv.

    - Merges into existing snapshot.csv (does NOT overwrite other symbols)
    - Ensures turnover_tl exists; approximates as close*volume when missing.
    """
    import csv
    from datetime import date

    data_root = Path(data_root)
    inbox = data_root / "inbox"
    if not inbox.exists():
        return

    snapshots_base = Path(snapshots_base)
    snapshots_base.mkdir(parents=True, exist_ok=True)

    end = date.fromisoformat(end_day)
    keep_n = max(int(lookback) * 3, int(lookback) + 32)

    def _f(x):
        try:
            if x is None:
                return float("nan")
            s = str(x).strip().replace(",", ".")
            if s == "":
                return float("nan")
            return float(s)
        except Exception:
            return float("nan")

    def _i(x):
        try:
            if x is None:
                return 0
            s = str(x).strip().replace(",", ".")
            if s == "":
                return 0
            return int(float(s))
        except Exception:
            return 0

    def _pick_date(row: dict) -> str:
        for k in ("date", "Date", "DATE", "day", "Day", "DAY"):
            v = row.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
        return ""

    def _read_existing_snapshot(fp):
        out = {}
        if not fp.exists():
            return out
        try:
            with fp.open("r", encoding="utf-8", newline="") as f:
                rdr = csv.DictReader(f)
                for r in rdr:
                    s = (r.get("symbol") or "").strip().upper()
                    if s:
                        out[s] = r
        except Exception:
            return out
        return out

    def _write_snapshot(fp, by_symbol: dict):
        hdr = ["symbol","open","high","low","close","volume","turnover_tl"]
        rows = []
        for s in sorted(by_symbol.keys()):
            r = by_symbol[s]
            rows.append({
                "symbol": s,
                "open": r.get("open",""),
                "high": r.get("high",""),
                "low": r.get("low",""),
                "close": r.get("close",""),
                "volume": r.get("volume",""),
                "turnover_tl": r.get("turnover_tl",""),
            })
        with fp.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=hdr)
            w.writeheader()
            for r in rows:
                w.writerow(r)
    if symbols is None:
        syms = set()
        for fp in inbox.glob("*.csv"):
            stem = fp.stem
            if stem.endswith(".symbol"):
                stem = stem[: -len(".symbol")]
            if stem:
                syms.add(stem.upper())
        symbols_use = sorted(syms)
    else:
        symbols_use = [s.upper() for s in symbols]

    for sym in symbols_use:
        src1 = inbox / f"{sym}.symbol.csv"
        src2 = inbox / f"{sym}.csv"
        src = src1 if src1.exists() else src2
        if not src.exists():
            continue

        rows = []
        with src.open("r", encoding="utf-8", newline="") as f:
            rdr = csv.DictReader(f)
            for row in rdr:
                ds = _pick_date(row)
                if not ds:
                    continue
                try:
                    dd = date.fromisoformat(ds)
                except Exception:
                    continue
                if dd <= end:
                    rows.append((dd, row))

        rows.sort(key=lambda x: x[0])
        rows = rows[-keep_n:]

        for dd, row in rows:
            o = _f(row.get("open") or row.get("Open"))
            h = _f(row.get("high") or row.get("High"))
            low_ = _f(row.get("low") or row.get("Low"))
            c = _f(row.get("close") or row.get("Close"))
            v = _i(row.get("volume") or row.get("Volume") or row.get("vol") or row.get("Vol"))

            t = _i(row.get("turnover_tl") or row.get("turnover") or row.get("Turnover") or row.get("value"))
            if t == 0 and (c == c) and v:
                t = int(round(c * v))

            day_dir = snapshots_base / dd.isoformat()
            day_dir.mkdir(parents=True, exist_ok=True)
            out_fp = day_dir / "snapshot.csv"

            existing = _read_existing_snapshot(out_fp)
            existing[sym] = {
                "open": o,
                "high": h,
                "low": low_,
                "close": c,
                "volume": v,
                "turnover_tl": t,
            }
            _write_snapshot(out_fp, existing)
