from pathlib import Path

from bist_core.providers.market_data.datastore_file_provider import DatastoreFileMarketDataProvider


def test_datastore_file_provider_reads_and_filters(tmp_path: Path) -> None:
    csv_path = tmp_path / "normalized.csv"
    csv_path.write_text(
        "\n".join(
            [
                "date,symbol,open,high,low,close,volume,turnover_tl",
                "2026-02-26,AKBNK,22.1,22.5,21.8,22.3,100,2200",
                "2026-02-27,AKBNK,22.4,22.9,22.2,22.7,120,2600",
                "2026-02-27,THYAO,310.0,315.0,308.0,314.0,90,28000",
            ]
        ),
        encoding="utf-8",
    )

    provider = DatastoreFileMarketDataProvider(csv_path)

    assert provider.latest_trading_day() == "2026-02-27"
    assert provider.universe_on_day("2026-02-27") == ["AKBNK", "THYAO"]

    out = provider.get_eod_range(start_date="2026-02-27", symbols=["akbnk"])
    assert len(out) == 1
    assert out.iloc[0]["symbol"] == "AKBNK"
    assert out.iloc[0]["date"] == "2026-02-27"
