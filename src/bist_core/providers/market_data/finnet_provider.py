from __future__ import annotations

from typing import Any, Sequence

import pandas as pd

from ..base import FailClosedError
from .base import MarketDataProvider


class FinnetMarketDataProvider(MarketDataProvider):
    provider_name = "finnet"

    def __init__(
        self,
        api_key: str | None,
        base_url: str | None,
        symbol_filter: Sequence[str] | None = None,
    ) -> None:
        self.api_key = None if api_key is None else str(api_key).strip()
        self.base_url = None if base_url is None else str(base_url).strip()
        self.symbol_filter = sorted({str(x).strip().upper() for x in (symbol_filter or []) if str(x).strip()})

    def build_eod_request(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        symbols: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        runtime_symbols = {str(x).strip().upper() for x in (symbols or []) if str(x).strip()}
        merged_symbols = sorted(set(self.symbol_filter).union(runtime_symbols))

        return {
            "provider_name": self.provider_name,
            "ready": bool(self.api_key and self.base_url),
            "base_url": self.base_url,
            "headers": {
                "X-API-Key": "***configured***" if self.api_key else None,
            },
            "params": {
                "start_date": start_date,
                "end_date": end_date,
                "symbols": merged_symbols or None,
            },
        }

    def latest_trading_day(self) -> str:
        raise FailClosedError(
            "Finnet market data provider contract is ready, but live wiring is deferred "
            "until credentials and final endpoint mapping are available."
        )

    def get_eod_range(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        symbols: Sequence[str] | None = None,
    ) -> pd.DataFrame:
        if not self.api_key or not self.base_url:
            raise FailClosedError(
                "Finnet market data provider selected but BIST_FINNET_API_KEY or "
                "BIST_FINNET_BASE_URL is missing."
            )
        raise FailClosedError(
            "Finnet market data provider contract is ready, but live fetch wiring is deferred."
        )
