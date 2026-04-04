from __future__ import annotations

from typing import Sequence

import pandas as pd

from ..base import FailClosedError
from .base import MarketDataProvider


class DeferredMarketDataProvider(MarketDataProvider):
    def __init__(self, provider_name: str, reason: str | None = None) -> None:
        self.provider_name = provider_name
        self.reason = reason or "Provider wiring is not complete yet."

    def latest_trading_day(self) -> str:
        raise FailClosedError(
            f"Market data provider {self.provider_name!r} is not ready. {self.reason}"
        )

    def get_eod_range(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        symbols: Sequence[str] | None = None,
    ) -> pd.DataFrame:
        raise FailClosedError(
            f"Market data provider {self.provider_name!r} is not ready. {self.reason}"
        )
