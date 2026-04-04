import json
import os
import subprocess
import sys
from pathlib import Path


def test_refresh_snapshots_module(tmp_path: Path) -> None:
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

    out_root = tmp_path / "snapshots"

    env = os.environ.copy()
    env["BIST_MARKET_DATA_PROVIDER"] = "datastore_file"
    env["BIST_DISCLOSURES_PROVIDER"] = "none"
    env["BIST_DATASTORE_NORMALIZED_CSV"] = str(csv_path)

    cmd = [
        sys.executable,
        "-m",
        "bist_core.providers.refresh_snapshots",
        "--out-root",
        str(out_root),
        "--clean",
    ]
    cp = subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
    payload = json.loads(cp.stdout)

    assert payload["ok"] is True
    assert payload["days_count"] == 2
    assert payload["last_day"] == "2026-02-27"
    assert (out_root / "2026-02-26" / "snapshot.csv").exists()
    assert (out_root / "2026-02-27" / "snapshot.csv").exists()
