"""BinanceSnapshotFetcher — REST order-book snapshot for recovery.

Fetches the current Binance Futures L2 order book via REST and returns an
OrderBookEvent(event_type=SNAPSHOT) ready for OrderBookManager.apply().

The injectable _http_get parameter allows deterministic unit testing
without any real network activity (CI-safe).

PRD reference: §4.5 Recovery Protocol — snapshot bootstrap / resync.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

import requests

from crypto_core.data.ingestion import binance_adapter
from crypto_core.data.models.events import OrderBookEvent

logger = logging.getLogger(__name__)

_FAPI_DEPTH_URL = "https://fapi.binance.com/fapi/v1/depth"
_DEFAULT_LIMIT = 1000
_DEFAULT_TIMEOUT_S = 10.0


class BinanceSnapshotFetcher:
    """Fetches an L2 order-book snapshot from Binance Futures REST API.

    Constructor args:
        symbol:    Uppercase instrument symbol, e.g. "BTCUSDT".
        limit:     Number of price levels to request (default 1000, max 1000).
        timeout_s: HTTP request timeout in seconds (default 10.0).
        _http_get: Injectable HTTP GET callable for testing.
                   Signature: (url, *, params, timeout) → response-like object
                   Must expose .raise_for_status() and .json() → dict.
                   If None, uses requests.get at call time.
    """

    def __init__(
        self,
        symbol: str,
        limit: int = _DEFAULT_LIMIT,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        _http_get: Callable[..., Any] | None = None,
    ) -> None:
        if not symbol:
            raise ValueError("symbol must be non-empty")
        self._symbol = symbol.upper()
        self._limit = limit
        self._timeout_s = timeout_s
        self._http_get = _http_get  # None → use requests.get at fetch time

    def fetch(self) -> OrderBookEvent:
        """Fetch and parse the current order book snapshot.

        Returns:
            OrderBookEvent with event_type=SNAPSHOT and all price levels.
            timestamp_ns is set to wall-clock time at the moment of the request.

        Raises:
            requests.HTTPError:   on non-2xx HTTP response.
            requests.Timeout:     if the request exceeds timeout_s.
            requests.RequestException: on connection or transport error.
            KeyError:             if the response body is missing expected fields.
        """
        http_get = self._http_get if self._http_get is not None else requests.get
        ts_ns = time.time_ns()
        logger.info(
            "BinanceSnapshotFetcher: fetching snapshot symbol=%s limit=%d",
            self._symbol,
            self._limit,
        )
        resp = http_get(
            _FAPI_DEPTH_URL,
            params={"symbol": self._symbol, "limit": self._limit},
            timeout=self._timeout_s,
        )
        resp.raise_for_status()
        payload: dict[str, Any] = resp.json()
        event = binance_adapter.parse_depth_snapshot(payload, self._symbol, ts_ns)
        logger.info(
            "BinanceSnapshotFetcher: snapshot received symbol=%s lastUpdateId=%d bids=%d asks=%d",
            self._symbol,
            event.last_update_id,
            len(event.bids),
            len(event.asks),
        )
        return event
