from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence

import pandas as pd


class MarketDataProvider(ABC):
    provider_name: str = "unknown"

    @abstractmethod
    def latest_trading_day(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_eod_range(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        symbols: Sequence[str] | None = None,
    ) -> pd.DataFrame:
        raise NotImplementedError
