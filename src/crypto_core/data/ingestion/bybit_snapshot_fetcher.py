"""BybitSnapshotFetcher — REST order-book snapshot for Bybit V5 recovery.

Fetches the current Bybit V5 linear order book via REST and returns an
OrderBookEvent(event_type=SNAPSHOT) ready for DeltaBuffer replay.

The injectable _http_get parameter allows deterministic unit testing
without any real network activity (CI-safe).

Bybit V5 REST order-book endpoint:
    GET https://api.bybit.com/v5/market/orderbook
    params: category=linear, symbol=<SYMBOL>, limit=200 (max for linear)

Response structure:
    {
        "retCode": 0,          # 0 = success; non-zero = API error
        "retMsg": "OK",
        "result": {
            "s":   "BTCUSDT",  # symbol
            "b":   [["price", "qty"], ...],  # bids, best bid first
            "a":   [["price", "qty"], ...],  # asks, best ask first
            "ts":  1672914493826,    # server timestamp (ms)
            "u":   18234961,         # symbol-local update ID
            "seq": 11486752626,      # global cross-symbol sequence number
            "cts": 1672914493816     # create timestamp (ms, optional)
        },
        "retExtInfo": {},
        "time": 1672914493901
    }

Sequence semantics (critical for replay alignment):
    "seq" is the cross-symbol global sequence shared between the REST snapshot
    and the WebSocket delta stream.  After a snapshot with seq=S, replay all
    WS deltas buffered while seq > S.  Bybit deltas use monotonic ordering
    (not strict +1 contiguity) because seq is incremented globally across all
    symbols; legitimate gaps exist.

PRD reference: §4.5 Recovery Protocol — Bybit snapshot bootstrap / resync.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

import requests

from crypto_core.data.ingestion import bybit_adapter
from crypto_core.data.models.events import OrderBookEvent

logger = logging.getLogger(__name__)

_V5_ORDERBOOK_URL = "https://api.bybit.com/v5/market/orderbook"
_DEFAULT_LIMIT = 200  # maximum depth for linear perpetuals
_DEFAULT_TIMEOUT_S = 10.0
_BYBIT_SUCCESS_CODE = 0


class BybitSnapshotFetcher:
    """Fetches an L2 order-book snapshot from Bybit V5 REST API.

    Constructor args:
        symbol:    Uppercase instrument symbol, e.g. "BTCUSDT".
        category:  Bybit market category (default "linear" for perpetual futures).
        limit:     Number of price levels to request (default 200, max 200 for linear).
        timeout_s: HTTP request timeout in seconds (default 10.0).
        _http_get: Injectable HTTP GET callable for testing.
                   Signature: (url, *, params, timeout) → response-like object
                   Must expose .raise_for_status() and .json() → dict.
                   If None, uses requests.get at fetch time.
    """

    def __init__(
        self,
        symbol: str,
        category: str = "linear",
        limit: int = _DEFAULT_LIMIT,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        _http_get: Callable[..., Any] | None = None,
    ) -> None:
        if not symbol:
            raise ValueError("symbol must be non-empty")
        self._symbol = symbol.upper()
        self._category = category
        self._limit = limit
        self._timeout_s = timeout_s
        self._http_get = _http_get  # None → use requests.get at fetch time

    def fetch(self) -> OrderBookEvent:
        """Fetch and parse a Bybit V5 order-book snapshot.

        Returns:
            OrderBookEvent with event_type=SNAPSHOT, first_update_id=last_update_id=seq.

        Raises:
            requests.HTTPError:     HTTP-level error (status 4xx / 5xx).
            requests.Timeout:       Request exceeded timeout_s.
            requests.RequestException: Other network errors.
            RuntimeError:           Bybit API returned retCode != 0 (application error).
            KeyError:               Unexpected response structure (missing required fields).
        """
        http_get = self._http_get if self._http_get is not None else requests.get
        params = {
            "category": self._category,
            "symbol": self._symbol,
            "limit": self._limit,
        }

        logger.debug(
            "BybitSnapshotFetcher.fetch symbol=%s category=%s limit=%d",
            self._symbol,
            self._category,
            self._limit,
        )

        resp = http_get(_V5_ORDERBOOK_URL, params=params, timeout=self._timeout_s)
        resp.raise_for_status()

        payload: dict[str, Any] = resp.json()
        ret_code = int(payload.get("retCode", -1))
        if ret_code != _BYBIT_SUCCESS_CODE:
            ret_msg = payload.get("retMsg", "unknown error")
            raise RuntimeError(f"Bybit API error for symbol={self._symbol}: retCode={ret_code} retMsg={ret_msg!r}")

        result: dict[str, Any] = payload["result"]

        # Capture fetch timestamp before parsing for reproducible timestamp_ns.
        timestamp_ns = time.time_ns()

        event = bybit_adapter.parse_depth_snapshot(result, self._symbol, timestamp_ns)

        logger.info(
            "BybitSnapshotFetcher.fetch OK symbol=%s seq=%d bids=%d asks=%d",
            self._symbol,
            event.last_update_id,
            len(event.bids),
            len(event.asks),
        )
        return event
