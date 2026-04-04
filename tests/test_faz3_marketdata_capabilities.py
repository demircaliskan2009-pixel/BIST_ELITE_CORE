from __future__ import annotations

from pathlib import Path

from bist_core.services.marketdata import MarketData


def test_marketdata_ohlcv_capabilities(tmp_path: Path) -> None:
    day_close = "2025-01-01"
    day_ohlcv = "2025-01-02"

    close_dir = tmp_path / day_close
    close_dir.mkdir(parents=True)
    (close_dir / "snapshot.csv").write_text(
        "symbol,close\nAAA,10.0\n",
        encoding="utf-8",
    )

    ohlcv_dir = tmp_path / day_ohlcv
    ohlcv_dir.mkdir(parents=True)
    (ohlcv_dir / "snapshot.csv").write_text(
        "symbol,close,open,high,low,volume,turnover\nAAA,10.0,9.5,10.5,9.0,1000,12345\n",
        encoding="utf-8",
    )

    md = MarketData(base=tmp_path)

    assert md.has_ohlcv(day_close) is False
    assert md.has_ohlcv(day_ohlcv) is True

    ohlcv_map = md.ohlcv_map(day_ohlcv)
    row = ohlcv_map["AAA"]
    assert row["open"] == 9.5
    assert row["high"] == 10.5
    assert row["low"] == 9.0
    assert row["close"] == 10.0
    assert row["volume"] == 1000
    assert row["turnover"] == 12345
