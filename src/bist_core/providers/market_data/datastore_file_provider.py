from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pandas as pd

from ..base import FailClosedError
from .base import MarketDataProvider

REQUIRED_COLUMNS = [
    "date",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "turnover_tl",
]


class DatastoreFileMarketDataProvider(MarketDataProvider):
    provider_name = "datastore_file"

    def __init__(self, csv_path: str | Path) -> None:
        self.csv_path = Path(csv_path)
        self._cache: pd.DataFrame | None = None

    def _load(self) -> pd.DataFrame:
        if self._cache is not None:
            return self._cache

        if not self.csv_path.exists():
            raise FailClosedError(f"Datastore normalized csv not found: {self.csv_path}")

        df = pd.read_csv(self.csv_path)
        missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing:
            raise FailClosedError(
                f"Datastore normalized csv missing required columns: {missing}"
            )

        work = df[REQUIRED_COLUMNS].copy()
        work["date"] = pd.to_datetime(work["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        work["symbol"] = work["symbol"].astype(str).str.strip().str.upper()
        work = work.dropna(subset=["date", "symbol"]).copy()

        for col in ["open", "high", "low", "close", "volume", "turnover_tl"]:
            work[col] = pd.to_numeric(work[col], errors="coerce")

        work = work.sort_values(["date", "symbol"]).reset_index(drop=True)
        if work.empty:
            raise FailClosedError(f"Datastore normalized csv is empty after parsing: {self.csv_path}")

        self._cache = work
        return self._cache

    def latest_trading_day(self) -> str:
        df = self._load()
        latest = df["date"].max()
        if not isinstance(latest, str) or latest.strip() == "":
            raise FailClosedError("Unable to determine latest trading day from datastore file.")
        return latest

    def get_eod_range(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        symbols: Sequence[str] | None = None,
    ) -> pd.DataFrame:
        df = self._load()
        out = df

        if start_date:
            out = out[out["date"] >= start_date]
        if end_date:
            out = out[out["date"] <= end_date]
        if symbols:
            normalized = {str(sym).strip().upper() for sym in symbols if str(sym).strip()}
            out = out[out["symbol"].isin(normalized)]

        if out.empty:
            raise FailClosedError(
                "Datastore file provider returned empty data for requested range/symbols."
            )

        return out.copy().reset_index(drop=True)

    def universe_on_day(self, day: str) -> list[str]:
        df = self._load()
        out = df.loc[df["date"] == day, "symbol"].astype(str).unique().tolist()
        return sorted(out)
