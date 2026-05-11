"""Matriks REST API data fetcher — real OHLCV bars from bar.gz endpoint.

Uses requests, JWT auth, gzip decompression. Fail-closed: invalid data → raise.
Network guarded by BIST_CORE_NETWORK_ENABLED=1.
"""

from __future__ import annotations

import gzip
import json
import os
from datetime import datetime, timedelta, timezone

import requests

from bist_core.data.matriks_adapter import convert_bars
from bist_core.models.ohlcv import OHLCVBar

_URL = "https://apitest.matriksdata.com/dumrul/v1/tick/bar.gz"
_TOKEN_ENV = "MATRIKS_API_TOKEN"
_NETWORK_ENV = "BIST_CORE_NETWORK_ENABLED"
_TIMEOUT = 30


def fetch_bars(
    symbol: str,
    start: str | None = None,
    end: str | None = None,
) -> list[OHLCVBar]:
    """Fetch OHLCV bars for symbol from Matriks REST API.

    Args:
        symbol: BIST symbol (e.g. GARAN, ASELS).
        start: Start date YYYY-MM-DD. Default: 90 days before end.
        end: End date YYYY-MM-DD. Default: today UTC.

    Returns:
        Sorted list of OHLCVBar. Fail-closed on invalid data.
    """
    if os.environ.get(_NETWORK_ENV, "").strip() != "1":
        raise Exception("MATRİKS DATA FETCH FAILED — STOP")

    token = os.environ.get(_TOKEN_ENV, "").strip()
    if not token:
        raise Exception("MATRİKS DATA FETCH FAILED — STOP (MATRIKS_API_TOKEN not set)")

    now = datetime.now(timezone.utc)
    end_date = end or now.strftime("%Y-%m-%d")
    start_date = start or (now - timedelta(days=90)).strftime("%Y-%m-%d")

    headers = {
        "Authorization": "jwt " + token,
        "Accept": "application/json",
    }
    params = {
        "symbol": symbol.upper().strip(),
        "start": start_date,
        "end": end_date,
        "period": "1day",
    }

    try:
        response = requests.get(_URL, headers=headers, params=params, timeout=_TIMEOUT)
    except requests.RequestException as e:
        raise Exception(f"MATRİKS ERROR: {e}") from e

    if response.status_code != 200:
        raise Exception("MATRİKS ERROR: " + (response.text or str(response.status_code)))

    raw = response.content
    if not raw:
        raise Exception("MATRİKS ERROR: empty response")

    try:
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        data = json.loads(raw.decode("utf-8"))
    except (gzip.BadGzipFile, json.JSONDecodeError, UnicodeDecodeError) as e:
        raise Exception(f"MATRİKS ERROR: invalid response — {e}") from e

    if isinstance(data, list):
        raw_bars = data
    elif isinstance(data, dict):
        raw_bars = data.get("bars") or data.get("data") or data.get("results")
        if not isinstance(raw_bars, list):
            raise Exception("MATRİKS ERROR: response has no bar list")
    else:
        raise Exception("MATRİKS ERROR: unexpected response type")

    bars = convert_bars(raw_bars, default_symbol=symbol, reject_zero_volume=False)
    if not bars:
        raise Exception("MATRİKS ERROR: no valid bars after conversion")

    return bars


__all__ = ["fetch_bars"]
