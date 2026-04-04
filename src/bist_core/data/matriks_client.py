"""Matriks REST client — PRD §7 data layer.

Fetches bar data from the Matriks API and converts it via the adapter
to internal OHLCVBar format.

**NETWORK GUARD**: Per AGENTS.md, network is forbidden by default.
All HTTP calls require env var ``BIST_CORE_NETWORK_ENABLED=1``.
If the guard is not set, every call raises ``NetworkDisabledError``
without making any outbound request.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from bist_core.backtest.backtest_engine import OHLCVBar
from bist_core.data.matriks_adapter import prepare_bars_for_backtest


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class NetworkDisabledError(RuntimeError):
    """Raised when a network call is attempted but the guard env var is not set."""


class MatriksAPIError(RuntimeError):
    """Raised on non-200 responses, empty payloads, or malformed JSON."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Network guard
# ---------------------------------------------------------------------------

def _network_enabled() -> bool:
    return os.environ.get("BIST_CORE_NETWORK_ENABLED", "").strip() == "1"


def _require_network() -> None:
    if not _network_enabled():
        raise NetworkDisabledError(
            "Network calls are disabled. Set BIST_CORE_NETWORK_ENABLED=1 to enable."
        )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

_DEFAULT_BASE_URL = "https://apitest.matriksdata.com"
_TOKEN_ENV_VAR = "MATRIKS_API_TOKEN"


class MatriksClient:
    """REST client for the Matriks market data API.

    All network calls are guarded by ``BIST_CORE_NETWORK_ENABLED=1``.
    Authentication token is read from ``MATRIKS_API_TOKEN`` env var.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: int = 30,
    ) -> None:
        self._base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        self._token = token or os.environ.get(_TOKEN_ENV_VAR, "")
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        return self._base_url

    def _headers(self) -> Dict[str, str]:
        headers: dict[str, str] = {
            "Accept": "application/json",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _request(self, path: str, params: Dict[str, str] | None = None) -> Any:
        _require_network()

        url = f"{self._base_url}{path}"
        if params:
            qs = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
            url = f"{url}?{qs}"

        req = Request(url, headers=self._headers(), method="GET")

        try:
            with urlopen(req, timeout=self._timeout) as resp:
                status = resp.status
                body = resp.read().decode("utf-8")
        except HTTPError as exc:
            raise MatriksAPIError(
                f"HTTP {exc.code}: {exc.reason}",
                status_code=exc.code,
            ) from exc
        except URLError as exc:
            raise MatriksAPIError(f"URL error: {exc.reason}") from exc

        if status != 200:
            raise MatriksAPIError(f"HTTP {status}", status_code=status)

        if not body or not body.strip():
            raise MatriksAPIError("Empty response body")

        try:
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as exc:
            raise MatriksAPIError(f"Malformed JSON: {exc}") from exc

        return data

    # -- Public API -------------------------------------------------------

    def get_bars(
        self,
        symbol: str,
        start: str,
        end: str,
        period: str = "1d",
    ) -> List[Dict[str, Any]]:
        """Fetch bar data for *symbol* over [start, end] at given period.

        Returns raw JSON list from the API.
        Raises ``NetworkDisabledError`` if guard is off.
        Raises ``MatriksAPIError`` on any API/transport failure.
        """
        params = {
            "symbol": symbol.upper().strip(),
            "start": start,
            "end": end,
            "period": period,
        }
        data = self._request("/api/v1/bars", params)

        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            bars = data.get("bars") or data.get("data") or data.get("results")
            if isinstance(bars, list):
                return bars
            raise MatriksAPIError("Response JSON has no bar list")
        raise MatriksAPIError("Unexpected response type")


# ---------------------------------------------------------------------------
# Integration helper
# ---------------------------------------------------------------------------

def fetch_and_prepare_bars(
    symbol: str,
    start: str,
    end: str,
    period: str = "1d",
    *,
    client: MatriksClient | None = None,
    reject_zero_volume: bool = False,
) -> list[OHLCVBar]:
    """Fetch bars from Matriks API → adapter → list[OHLCVBar].

    Raises ``NetworkDisabledError`` if guard is off.
    """
    c = client or MatriksClient()
    raw_bars = c.get_bars(symbol, start, end, period)
    return prepare_bars_for_backtest(
        raw_bars,
        symbol=symbol,
        reject_zero_volume=reject_zero_volume,
    )
