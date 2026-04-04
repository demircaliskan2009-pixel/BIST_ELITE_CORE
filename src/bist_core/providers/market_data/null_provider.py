from __future__ import annotations

from typing import Sequence

import pandas as pd

from ..base import FailClosedError
from .base import MarketDataProvider


class NullMarketDataProvider(MarketDataProvider):
    provider_name = "none"

    def latest_trading_day(self) -> str:
        raise FailClosedError(
            "Market data provider is disabled (provider=none). Refusing to guess trading day."
        )

    def get_eod_range(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        symbols: Sequence[str] | None = None,
    ) -> pd.DataFrame:
        raise FailClosedError(
            "Market data provider is disabled (provider=none). No data returned."
        )
