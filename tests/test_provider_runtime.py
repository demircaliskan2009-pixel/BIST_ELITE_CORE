from pathlib import Path

from bist_core.providers.runtime import inspect_runtime


def test_runtime_inspect_datastore_file_ready(tmp_path: Path) -> None:
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

    env = {
        "BIST_MARKET_DATA_PROVIDER": "datastore_file",
        "BIST_DISCLOSURES_PROVIDER": "none",
        "BIST_DATASTORE_NORMALIZED_CSV": str(csv_path),
    }

    status = inspect_runtime(env=env, must_exist=True)
    assert status.market_data_state == "ready"
    assert status.disclosures_state == "disabled"
    assert status.latest_trading_day == "2026-02-27"
    assert status.universe_count_on_latest_day == 2
