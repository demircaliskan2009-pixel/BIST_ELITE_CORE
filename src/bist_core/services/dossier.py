from __future__ import annotations

from datetime import date as Date
from pathlib import Path
from typing import List, Optional

from bist_core.services.advisor import build_advice_for_symbol
from bist_core.services.marketdata import MarketData


def build_dossier_for_symbol_day(
    symbol: str,
    day: Date | str,
    root: Optional[Path | str] = None,
) -> dict:
    base = Path(root) if root is not None else Path("data/eod/snapshots")
    day_str = day.isoformat() if isinstance(day, Date) else str(day)

    has_ohlcv, provider = _marketdata_meta(base, day_str)
    provenance = {"snapshot_root": str(base), "provider": provider}

    try:
        advice = build_advice_for_symbol(symbol, day_str, root=base)
        error_marker = None
        if isinstance(advice.text, str) and "Güvenli mod" in advice.text:
            error_marker = "SafeMode"
        return {
            "schema_version": 1,
            "symbol": symbol,
            "day": day_str,
            "decision_raw": advice.decision_raw,
            "score": advice.score,
            "signals": advice.signals,
            "plan": advice.plan,
            "text": advice.text,
            "capabilities": {"ohlcv": bool(has_ohlcv)},
            "provenance": provenance,
            "error_marker": error_marker,
        }
    except Exception as exc:
        err = exc.__class__.__name__
        return {
            "schema_version": 1,
            "symbol": symbol,
            "day": day_str,
            "decision_raw": "PASS",
            "score": 0.0,
            "signals": [],
            "plan": None,
            "text": (
                f"Güvenli mod: {err}. "
                "Veri veya karar üretilemedi; snapshot ve konfigürasyonu kontrol edin."
            ),
            "capabilities": {"ohlcv": False},
            "provenance": provenance,
            "error_marker": err,
        }


def build_dossiers_for_day(
    day: Date | str,
    root: Optional[Path | str] = None,
    symbols: Optional[List[str]] = None,
) -> List[dict]:
    base = Path(root) if root is not None else Path("data/eod/snapshots")
    day_str = day.isoformat() if isinstance(day, Date) else str(day)

    if symbols is None:
        try:
            md = MarketData(base)
            symbols = md.symbols(day_str)
        except Exception:
            symbols = []

    dossiers: List[dict] = []
    for sym in symbols:
        dossiers.append(build_dossier_for_symbol_day(sym, day_str, root=base))
    return dossiers


def _marketdata_meta(base: Path, day_str: str) -> tuple[bool, str | None]:
    provider = None
    has_ohlcv = False
    try:
        md = MarketData(base)
        provider = md._prov.__class__.__name__ if hasattr(md, "_prov") else None
        has_ohlcv = md.has_ohlcv(day_str)
    except Exception:
        has_ohlcv = False
    return has_ohlcv, provider
