from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pandas as pd

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


def export_market_data_provider_to_snapshot_root(
    provider,
    out_root: str | Path,
    start_date: str | None = None,
    end_date: str | None = None,
    symbols: Sequence[str] | None = None,
) -> dict[str, object]:
    root = Path(out_root)
    root.mkdir(parents=True, exist_ok=True)

    df = provider.get_eod_range(
        start_date=start_date,
        end_date=end_date,
        symbols=symbols,
    ).copy()

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Provider export missing columns: {missing}")

    work = df[REQUIRED_COLUMNS].copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    work["symbol"] = work["symbol"].astype(str).str.strip().str.upper()
    work = work.dropna(subset=["date", "symbol"]).copy()
    work = work.sort_values(["date", "symbol"]).reset_index(drop=True)

    if work.empty:
        raise ValueError("Provider export dataframe is empty after normalization.")

    days = sorted(work["date"].unique().tolist())
    total_rows = int(len(work))
    total_symbols = int(work["symbol"].nunique())

    for day, group in work.groupby("date", sort=True):
        day_dir = root / str(day)
        day_dir.mkdir(parents=True, exist_ok=True)
        group.to_csv(day_dir / "snapshot.csv", index=False)

    return {
        "ok": True,
        "root": str(root),
        "days_count": len(days),
        "first_day": days[0],
        "last_day": days[-1],
        "rows": total_rows,
        "total_symbols": total_symbols,
    }
