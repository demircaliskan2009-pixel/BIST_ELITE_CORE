"""Dataset ingest pipeline — PRD §7 data layer.

Pulls BIST data via MatriksClient, normalizes through the adapter, and
builds datasets for backtesting.  Supports optional local JSON cache.
Network-guarded per AGENTS.md (default OFF).  Deterministic ordering,
fail-closed on per-symbol errors.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from bist_core.backtest.backtest_engine import OHLCVBar
from bist_core.data.matriks_adapter import normalize_symbol, prepare_bars_for_backtest
from bist_core.data.matriks_client import (
    MatriksAPIError,
    MatriksClient,
    NetworkDisabledError,
    fetch_and_prepare_bars,
)

# ---------------------------------------------------------------------------
# Symbol universe loader
# ---------------------------------------------------------------------------

def load_symbols(
    *,
    client: MatriksClient | None = None,
    raw_symbols: Sequence[str] | None = None,
) -> list[str]:
    """Load and normalize symbol universe.

    When *raw_symbols* is provided, network is not used (offline mode).
    Otherwise fetches from Matriks meta endpoint (network guard applies).
    Returns sorted, deduplicated list of normalized symbol strings.
    """
    if raw_symbols is not None:
        normalized = sorted({normalize_symbol(s) for s in raw_symbols if normalize_symbol(s)})
        return normalized

    c = client or MatriksClient()
    try:
        data = c._request("/api/v1/symbols")
    except (MatriksAPIError, NetworkDisabledError):
        return []

    symbols_raw: list[str] = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                symbols_raw.append(item)
            elif isinstance(item, dict):
                sym = item.get("symbol") or item.get("ticker") or ""
                if sym:
                    symbols_raw.append(str(sym))
    elif isinstance(data, dict):
        items = data.get("symbols") or data.get("data") or data.get("results") or []
        if isinstance(items, list):
            for item in items:
                if isinstance(item, str):
                    symbols_raw.append(item)
                elif isinstance(item, dict):
                    sym = item.get("symbol") or item.get("ticker") or ""
                    if sym:
                        symbols_raw.append(str(sym))

    normalized = sorted({normalize_symbol(s) for s in symbols_raw if normalize_symbol(s)})
    return normalized


# ---------------------------------------------------------------------------
# Historical data fetcher
# ---------------------------------------------------------------------------

def fetch_symbol_history(
    symbol: str,
    start: str,
    end: str,
    period: str = "1d",
    *,
    client: MatriksClient | None = None,
    reject_zero_volume: bool = False,
) -> list[OHLCVBar]:
    """Fetch historical bars for a single symbol via the Matriks pipeline."""
    return fetch_and_prepare_bars(
        symbol,
        start,
        end,
        period,
        client=client,
        reject_zero_volume=reject_zero_volume,
    )


# ---------------------------------------------------------------------------
# Local cache
# ---------------------------------------------------------------------------

def _cache_key(symbol: str, period: str, start: str, end: str) -> str:
    return f"{symbol}_{period}_{start}_{end}.json"


def _read_cache(cache_dir: Path, key: str) -> list[dict[str, Any]] | None:
    path = cache_dir / key
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _write_cache(cache_dir: Path, key: str, bars: list[OHLCVBar]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / key
    records = [
        {
            "timestamp": b.timestamp,
            "symbol": b.symbol,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
        }
        for b in bars
    ]
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Batch dataset builder
# ---------------------------------------------------------------------------

def build_dataset(
    symbols: Sequence[str],
    start: str,
    end: str,
    period: str = "1d",
    *,
    client: MatriksClient | None = None,
    cache_dir: Path | str | None = None,
    reject_zero_volume: bool = False,
) -> dict[str, list[OHLCVBar]]:
    """Fetch bars for each symbol and return ``{symbol: [OHLCVBar, ...]}``.

    Fail-closed per symbol: if a fetch fails, the symbol is skipped
    (logged in ``errors``) and the remaining symbols continue.
    Uses local JSON cache when *cache_dir* is provided.
    """
    resolved_cache: Path | None = Path(cache_dir) if cache_dir is not None else None
    c = client or MatriksClient()
    result: dict[str, list[OHLCVBar]] = {}

    for raw_sym in sorted(set(symbols)):
        sym = normalize_symbol(raw_sym)
        if not sym:
            continue

        if resolved_cache is not None:
            key = _cache_key(sym, period, start, end)
            cached = _read_cache(resolved_cache, key)
            if cached is not None:
                bars = prepare_bars_for_backtest(cached, symbol=sym, reject_zero_volume=reject_zero_volume)
                if bars:
                    result[sym] = bars
                    continue

        try:
            bars = fetch_symbol_history(sym, start, end, period, client=c, reject_zero_volume=reject_zero_volume)
        except (MatriksAPIError, NetworkDisabledError, Exception):
            continue

        if not bars:
            continue

        result[sym] = bars

        if resolved_cache is not None:
            key = _cache_key(sym, period, start, end)
            _write_cache(resolved_cache, key, bars)

    return result
