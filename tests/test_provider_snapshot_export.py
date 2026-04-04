from pathlib import Path

from bist_core.providers.market_data.datastore_file_provider import DatastoreFileMarketDataProvider
from bist_core.providers.snapshot_export import export_market_data_provider_to_snapshot_root


def test_snapshot_export_from_provider(tmp_path: Path) -> None:
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
    out_root = tmp_path / "snapshots"

    summary = export_market_data_provider_to_snapshot_root(provider, out_root)

    assert summary["ok"] is True
    assert summary["days_count"] == 2
    assert summary["last_day"] == "2026-02-27"
    assert (out_root / "2026-02-26" / "snapshot.csv").exists()
    assert (out_root / "2026-02-27" / "snapshot.csv").exists()
