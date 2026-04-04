"""Price provider — deterministic price layer (Matriks + iDeal + cache)."""

from __future__ import annotations

import datetime
import json
import os
import time

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[misc, assignment]
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from bist_core.data.ideal_parser import parse_ideal_file

_PRICE_CACHE: Dict[str, Dict] = {}
_MAX_AGE_SEC = 60 * 60 * 24 * 7

_MATRIKS_BAR_CACHE: Dict[str, Dict] = {}
_MATRIKS_BAR_TTL = 5

DEBUG_PRICE = False


def _normalize_symbol(symbol: str) -> list[str]:
    """BIST symbol variants to try (exchange naming realities)."""
    s = str(symbol).upper().strip()
    return [
        s,
        f"{s}.IS",
        f"{s}.E",
        f"IMKBH'{s}",
    ]


def _fetch_matriks(symbol: str) -> dict[str, Any]:
    """
    Matriks HTTP bar fetch — **always** returns a dict, never None.

    Success: payload includes ``data`` (list) and optional ``_matriks_meta`` (HTTP + token usage).
    Failure: ``{"error": "<code>", ...}`` with ``attempts`` / ``reason`` where applicable.
    """
    attempts: list[dict[str, Any]] = []
    token = os.getenv("MATRIKS_TOKEN") or ""
    token_used = bool(token)

    if not token:
        return {
            "error": "NO_TOKEN",
            "token_used": False,
            "attempts": attempts,
        }

    if requests is None:
        return {
            "error": "NO_REQUESTS",
            "reason": "requests_not_installed",
            "token_used": True,
            "attempts": attempts,
        }

    if not isinstance(symbol, str) or not symbol.strip():
        return {
            "error": "INVALID_SYMBOL",
            "token_used": token_used,
            "attempts": attempts,
        }

    urls = [
        "https://api.matriksdata.com/data/bar",
        "https://api.matriksdata.com/v1/data/bar",
    ]

    symbols = _normalize_symbol(symbol)
    last_exc: str | None = None

    for sym in symbols:
        for url in urls:
            try:
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                }
                params = {
                    "symbol": sym,
                    "period": "1d",
                    "limit": 100,
                }
                r = requests.get(url, headers=headers, params=params, timeout=5)
                rec: dict[str, Any] = {
                    "symbol": sym,
                    "url": url,
                    "status_code": r.status_code,
                }
                attempts.append(rec)
                print("MATRİKS DEBUG →", sym, url, r.status_code)

                if r.status_code != 200:
                    continue

                data = r.json()
                if isinstance(data, dict) and data.get("data"):
                    out = dict(data)
                    out["_matriks_meta"] = {
                        "token_used": True,
                        "http": rec,
                        "response_excerpt": (r.text[:500] if isinstance(r.text, str) else ""),
                        "attempts": attempts,
                    }
                    return out

            except Exception as e:
                last_exc = str(e)
                print("MATRİKS ERROR:", str(e))
                attempts.append({"symbol": sym, "url": url, "error": str(e)})
                continue

    return {
        "error": "NO_DATA",
        "reason": last_exc or "no_successful_bar_payload",
        "token_used": True,
        "attempts": attempts,
    }


def _fetch_matriks_bar(
    symbol: str,
    *,
    period: str = "1day",
    start: str | None = None,
    end: str | None = None,
) -> Optional[dict]:
    """
    Fetch Matriks BAR data (production-safe).

    Uses ``Authorization: jwt <token>`` (Matriks expects jwt prefix, not Bearer).
    When start/end are omitted, uses a short recent window (2 calendar days).
    """
    token = os.environ.get("MATRIKS_TOKEN")
    if not token or not isinstance(symbol, str):
        return None

    if requests is None:
        return None

    try:
        today = datetime.date.today()
        start_s = start if start is not None else (today - datetime.timedelta(days=2)).isoformat()
        end_s = end if end is not None else today.isoformat()

        url = (
            "https://apitest.matriksdata.com/dumrul/v1/tick/bar"
            f"?symbol={symbol}"
            f"&period={period}"
            f"&start={start_s}"
            f"&end={end_s}"
        )

        headers = {
            "Authorization": f"jwt {token}",
            "Accept": "application/json",
        }

        resp = None

        # Matriks test env can be unstable — retry up to 3 times.
        for _ in range(3):
            try:
                resp = requests.get(url, headers=headers, timeout=2)
                if resp.status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(0.5)

        if resp is None or resp.status_code != 200:
            return None

        try:
            data = resp.json()
        except Exception:
            return None

        if isinstance(data, dict):
            return data
        if isinstance(data, list):
            return {"data": data}
        return None

    except Exception:
        return None


def _get_matriks_bar_price(symbol: str) -> Optional[float]:
    """
    Matriks **price** endpoint only (latest close). OHLCV bar history for the
    trading engine is loaded from iDeal — not from Matriks.
    """
    now = int(time.time())

    cached = _MATRIKS_BAR_CACHE.get(symbol)
    if isinstance(cached, dict):
        ts = cached.get("ts")
        price = cached.get("price")
        if isinstance(ts, int) and isinstance(price, (int, float)):
            if now - ts <= _MATRIKS_BAR_TTL:
                return float(price)

    data = _fetch_matriks_bar(symbol)
    if not isinstance(data, dict):
        return None

    bars = data.get("data") or data.get("bars") or data.get("result")

    if not isinstance(bars, list) or len(bars) == 0:
        return None

    last_bar = bars[-1]

    if not isinstance(last_bar, dict):
        return None

    close = last_bar.get("close") or last_bar.get("c")

    if not isinstance(close, (int, float)) or close <= 0:
        return None

    _MATRIKS_BAR_CACHE[symbol] = {
        "price": float(close),
        "ts": now,
    }

    return float(close)


def _get_ideal_path(symbol: str) -> str:
    base = r"C:\iDeal\ChartData\IMKBH\G"
    return os.path.join(base, f"IMKBH'{symbol}.G")


def _is_fresh(ts: int) -> bool:
    now = int(time.time())
    return (now - ts) <= _MAX_AGE_SEC


def get_current_price(symbol: str) -> Optional[float]:
    """
    Deterministic price provider with priority:

    1) Matriks API (optional)
    2) iDeal local data
    3) None
    """
    if not isinstance(symbol, str) or not symbol:
        return None

    # --- MATRIKS BAR (priority 1) ---
    matriks_price = _get_matriks_bar_price(symbol)
    if isinstance(matriks_price, (int, float)) and matriks_price > 0:
        if DEBUG_PRICE:
            print("MATRIKS_BAR_USED", symbol)
        return float(matriks_price)

    cached = _PRICE_CACHE.get(symbol)
    if isinstance(cached, dict):
        price = cached.get("price")
        ts = cached.get("ts")
        if isinstance(price, (int, float)) and isinstance(ts, int):
            if _is_fresh(ts):
                if DEBUG_PRICE:
                    print("IDEAL_USED", symbol)
                return float(price)

    path = _get_ideal_path(symbol)

    if not os.path.exists(path):
        return None

    bars = parse_ideal_file(path, symbol)

    if not isinstance(bars, list) or len(bars) == 0:
        return None

    last_bar = bars[-1]

    try:
        price = float(last_bar.close)
        ts = int(last_bar.timestamp)
    except Exception:
        return None

    if price <= 0:
        return None

    if not _is_fresh(ts):
        return None

    _PRICE_CACHE[symbol] = {
        "price": price,
        "ts": ts,
    }

    return price


def test_matriks_endpoint(symbol: str) -> None:
    """
    Isolated Matriks endpoint validator.
    Does NOT affect main system.
    """
    token = os.environ.get("MATRIKS_TOKEN")

    if not token:
        print("❌ ENDPOINT INVALID — NO TOKEN")
        return

    url = f"https://api.matriksdata.com/price/{symbol}"

    start = time.time()

    try:
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {token}"},
        )

        try:
            with urllib.request.urlopen(req, timeout=1) as resp:
                status = getattr(resp, "status", 200)
                raw = resp.read()
        except urllib.error.HTTPError as e:
            status = e.code
            raw = e.read() if hasattr(e, "read") else b""
        except Exception as e:
            print("❌ ENDPOINT INVALID — REQUEST FAILED")
            print("error:", str(e))
            return

        latency_ms = int((time.time() - start) * 1000)

        print("status_code:", status)
        print("latency_ms:", latency_ms)

        body = raw.decode("utf-8", errors="ignore")
        print("raw_response:", body)

        if latency_ms > 1000:
            print("❌ ENDPOINT INVALID — LATENCY TOO HIGH")
            return

        if status == 401:
            print("❌ ENDPOINT INVALID — AUTH FAILED (401)")
            return
        if status == 404:
            print("❌ ENDPOINT INVALID — WRONG ENDPOINT (404)")
            return
        if not body:
            print("❌ ENDPOINT INVALID — EMPTY RESPONSE")
            return

        try:
            data = json.loads(body)
        except Exception:
            print("❌ ENDPOINT INVALID — INVALID JSON")
            return

        price = data.get("price")
        timestamp = data.get("timestamp")

        print("parsed_price:", price)
        print("parsed_timestamp:", timestamp)

        if not isinstance(price, (int, float)):
            print("❌ ENDPOINT INVALID — PRICE MISSING/INVALID")
            return

        if not isinstance(timestamp, int):
            print("❌ ENDPOINT INVALID — TIMESTAMP MISSING/INVALID")
            return

        print("ENDPOINT VALID")

    except Exception as e:
        print("❌ ENDPOINT INVALID — UNEXPECTED ERROR")
        print("error:", str(e))


__all__ = [
    "get_current_price",
    "test_matriks_endpoint",
    "_normalize_symbol",
    "_fetch_matriks",
]


if __name__ == "__main__":
    test_matriks_endpoint("ASELS")
