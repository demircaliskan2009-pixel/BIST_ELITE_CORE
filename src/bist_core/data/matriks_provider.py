"""Optional Matriks quote fetch — network disabled unless MATRIKS_ENABLED is set."""

from __future__ import annotations

import os
import time
from typing import Any, Optional

from bist_core.models.ohlcv import OHLCVBar

_matriks_operational_announced: bool = False


def _matriks_network_enabled() -> bool:
    return os.environ.get("MATRIKS_ENABLED", "").strip().lower() in ("1", "true", "yes")


def _parse_positive_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        p = float(v)
        if p > 0.0 and p == p:  # not NaN
            return p
    except (TypeError, ValueError):
        pass
    return None


def _extract_price_from_json(data: Any) -> Optional[float]:
    """Try common Matriks / REST shapes for last trade price."""
    if data is None:
        return None
    if isinstance(data, list) and len(data) > 0:
        p = _extract_price_from_json(data[0])
        if p is not None:
            return p
    if not isinstance(data, dict):
        return None
    for key in (
        "last",
        "price",
        "close",
        "Last",
        "Close",
        "Price",
        "lastPrice",
        "LastPrice",
    ):
        p = _parse_positive_float(data.get(key))
        if p is not None:
            return p
    for wrap in ("data", "result", "content", "payload", "response", "Result"):
        nested = data.get(wrap)
        if isinstance(nested, dict):
            p = _extract_price_from_json(nested)
            if p is not None:
                return p
            for key in ("last", "price", "close", "Last", "Close"):
                p = _parse_positive_float(nested.get(key))
                if p is not None:
                    return p
    return None


def _default_quote_hosts(sym: str) -> list[str]:
    return [
        f"https://api.matriksdata.com/quote/{sym}",
        f"https://api.matriksdata.com/api/quote/{sym}",
        f"https://api.matriksdata.com/stock/{sym}",
        f"https://apitest.matriksdata.com/quote/{sym}",
    ]


def _quote_urls(symbol: str) -> list[str]:
    sym = str(symbol).strip().upper()
    out: list[str] = []
    base = os.environ.get("MATRIKS_QUOTE_BASE_URL", "").strip().rstrip("/")
    if base:
        out.extend(
            [
                f"{base}/quote/{sym}",
                f"{base}/api/quote/{sym}",
                f"{base}/stock/{sym}",
            ]
        )
    out.extend(_default_quote_hosts(sym))
    extra = os.environ.get("MATRIKS_QUOTE_EXTRA_URLS", "").strip()
    if extra:
        for part in extra.split(","):
            p = part.strip()
            if p and "{symbol}" in p:
                out.append(p.replace("{symbol}", sym))
    # Dedupe while preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def _matriks_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _matriks_http_timeout() -> float:
    raw = os.environ.get("MATRIKS_HTTP_TIMEOUT", "").strip()
    if not raw:
        return 2.0
    try:
        t = float(raw)
        return t if t > 0.1 else 2.0
    except ValueError:
        return 2.0


def _retry_sleep_seconds(status_code: int, attempt: int) -> float:
    """503/502/504: backoff; other errors: short pause."""
    if status_code in (502, 503, 504):
        return min(4.0, 0.5 * (2**attempt))
    return 0.2


def _matriks_quote_http(
    symbol: str,
    token: str,
    *,
    timeout: float = 2.0,
    verbose: bool = False,
    log_failures: bool = False,
) -> Optional[float]:
    """
    Try multiple Matriks endpoints; per-URL retry up to 2 times on failure (3 attempts).
    Returns first valid positive price.

    ``verbose`` (typically ``MATRIKS_DEBUG=1``): per-request status/body prints.
    ``log_failures``: if not verbose, print one summary line when all URLs fail (live smoke).
    """
    sym = str(symbol).strip().upper()
    if not sym or not token:
        return None
    try:
        import requests
    except Exception:
        return None

    urls = _quote_urls(sym)
    headers = _matriks_headers(token)
    to = float(timeout)
    last_status: Optional[int] = None
    last_body_snip = ""
    last_err: Optional[str] = None

    for url in urls:
        for attempt in range(3):
            try:
                r = requests.get(url, headers=headers, timeout=to)
                last_status = int(r.status_code)
                last_body_snip = r.text[:200]
                if verbose:
                    print(
                        {
                            "MATRIKS_DEBUG_STATUS": r.status_code,
                            "MATRIKS_DEBUG_TEXT": r.text[:300],
                        }
                    )
                if r.status_code != 200:
                    if verbose:
                        print(
                            {
                                "MATRIKS_ERROR": r.status_code,
                                "BODY": r.text[:200],
                            }
                        )
                    if attempt < 2:
                        time.sleep(_retry_sleep_seconds(r.status_code, attempt))
                        continue
                    break
                try:
                    data = r.json()
                except Exception:
                    last_err = "json_parse"
                    if verbose:
                        print({"MATRIKS_ERROR": "json_parse", "BODY": r.text[:200]})
                    if attempt < 2:
                        time.sleep(0.2)
                        continue
                    break
                px = _extract_price_from_json(data)
                if px is not None:
                    return px
                break
            except Exception as e:
                last_err = "request_exception"
                last_status = None
                last_body_snip = str(e)[:200]
                if verbose:
                    print(
                        {
                            "MATRIKS_ERROR": "request_exception",
                            "BODY": str(e)[:200],
                        }
                    )
                if attempt < 2:
                    time.sleep(0.2)
                    continue
                break
    if log_failures and not verbose:
        msg: dict[str, Any] = {
            "MATRIKS_QUOTE_FAILED": True,
            "symbol": sym,
            "last_http_status": last_status,
            "body_snip": last_body_snip,
            "hint": "503/502 = Matriks upstream; retry later, confirm base URL in docs, or set MATRIKS_QUOTE_BASE_URL.",
        }
        if last_err:
            msg["error"] = last_err
        print(msg)
    return None


def _fetch_matriks_price(symbol: str) -> Optional[float]:
    """
    Live last price from Matriks API (fail-safe).

    - Requires ``MATRIKS_ENABLED`` and ``MATRIKS_TOKEN``.
    - Multiple endpoints + retries; flexible JSON parsing.
    - Prints ``{"matriks_price": <float|None>, "symbol": <str>}``.
    """
    global _matriks_operational_announced
    sym = str(symbol).strip().upper()
    if not sym:
        print({"matriks_price": None, "symbol": ""})
        return None
    if not _matriks_network_enabled():
        print({"matriks_price": None, "symbol": sym})
        return None
    token = os.environ.get("MATRIKS_TOKEN", "").strip()
    if not token:
        print({"matriks_price": None, "symbol": sym})
        return None
    debug = os.environ.get("MATRIKS_DEBUG", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    to = _matriks_http_timeout()
    px = _matriks_quote_http(
        sym,
        token,
        timeout=to,
        verbose=debug,
        log_failures=not debug,
    )
    print({"matriks_price": px, "symbol": sym})
    if px is not None:
        print({"MATRİKS_SUCCESS": float(px), "symbol": sym})
        if not _matriks_operational_announced:
            print("MATRİKS API FULLY OPERATIONAL")
            _matriks_operational_announced = True
    return px


class MatriksProvider:
    """Rate-limited quote cache; HTTP only when MATRIKS_ENABLED=1 and MATRIKS_TOKEN set."""

    def __init__(self) -> None:
        self.cache: dict[str, float] = {}
        self.last_call: dict[str, float] = {}
        self.token = os.environ.get("MATRIKS_TOKEN")

    def get_price(self, symbol: str) -> Optional[float]:
        if not _matriks_network_enabled():
            return None

        sym = str(symbol).strip().upper()
        if not sym:
            return None

        now = time.time()
        last = self.last_call.get(sym, 0.0)

        if now - last < 2.0:
            return self.cache.get(sym)

        price = self._fetch(sym)

        if price is not None and price > 0:
            self.cache[sym] = float(price)
            self.last_call[sym] = now

        return self.cache.get(sym)

    def _fetch(self, symbol: str) -> Optional[float]:
        if not self.token:
            return None
        return _matriks_quote_http(
            str(symbol).strip().upper(),
            self.token.strip(),
            timeout=_matriks_http_timeout(),
            verbose=False,
            log_failures=False,
        )

    def fetch(self, symbol: str, period: str = "1m") -> list[OHLCVBar] | None:
        """
        Fallback OHLCV series when iDeal history is too short.

        When ``MATRIKS_ENABLED`` is off or quote fetch fails, returns ``None`` (fail-closed).
        When enabled, builds a short **flat** 1m series at the last Matriks trade price so
        downstream hardening can validate a consistent window (no mixed corrupt legs).

        ``period`` currently supports ``\"1m\"`` (60-second step, 60 bars).
        """
        if not _matriks_network_enabled():
            return None

        sym = str(symbol).strip().upper()
        if not sym:
            return None

        px = self._fetch(sym)
        if px is None or float(px) <= 0.0:
            return None

        p = float(px)
        step_sec = 60
        if str(period).strip().lower() != "1m":
            step_sec = 60

        n = 60
        now = int(time.time())
        out: list[OHLCVBar] = []
        for i in range(n):
            ts = now - (n - 1 - i) * step_sec
            out.append(
                OHLCVBar(
                    timestamp=int(ts),
                    symbol=sym,
                    open=p,
                    high=p,
                    low=p,
                    close=p,
                    volume=1.0,
                )
            )
        return out


__all__ = [
    "MatriksProvider",
    "_fetch_matriks_price",
    "_matriks_network_enabled",
    "_matriks_quote_http",
    "_extract_price_from_json",
]
