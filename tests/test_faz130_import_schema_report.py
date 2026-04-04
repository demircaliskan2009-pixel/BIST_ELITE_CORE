"""FAZ130: data import --schema-report shows inferred mapping."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_faz130_schema_report(tmp_path: Path) -> None:
    """data import --schema-report prints inferred mapping and exits without writing."""
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(
        "Tarih,Hisse,Kapanış\n01.01.2099,AAA,100\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_project_root() / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "bist_core.cli",
            "data",
            "import",
            "--input",
            str(csv_path),
            "--schema-report",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "columns" in data
    assert "inferred_mapping" in data
    assert "Hisse" in data["columns"]
    assert "date" in data["inferred_mapping"] or "symbol" in data["inferred_mapping"]
    assert not (tmp_path / "snapshots").exists()
