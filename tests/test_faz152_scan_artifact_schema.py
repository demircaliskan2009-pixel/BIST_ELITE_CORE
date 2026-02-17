"""FAZ152: Scan artifact schema — stable JSON schema. Regression guards for backward compatibility."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_scan_json(tmp_path: Path, day: str, csv_content: str, *extra_args: str) -> tuple[int, str]:
    snap_root = tmp_path / "snapshots"
    day_dir = snap_root / day
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "snapshot.csv").write_text(csv_content, encoding="utf-8")
    env = os.environ.copy()
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snap_root)
    env.pop("BIST_CORE_ALLOW_NETWORK", None)
    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "scan", "--day", day, "--json", *extra_args],
        cwd=str(_repo_root()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=60,
    )
    return r.returncode, r.stdout


SCAN_SCHEMA_REQUIRED_TOP = {"schema_version", "generated_at", "day", "ranked"}
RANKED_ITEM_KEYS = {"symbol", "score", "rationale"}


def test_faz152_scan_schema_required_keys(tmp_path: Path) -> None:
    """Scan JSON has required top-level keys (backward compat)."""
    csv = "symbol,close\nAKBNK,50.0\n"
    code, out = _run_scan_json(tmp_path, "2025-01-15", csv)
    assert code == 0
    data = json.loads(out)
    assert set(data.keys()) >= SCAN_SCHEMA_REQUIRED_TOP


def test_faz152_scan_ranked_item_schema(tmp_path: Path) -> None:
    """Each ranked item has symbol, score, rationale (stable schema)."""
    csv = "symbol,close\nAKBNK,50.0\nGARAN,100.0\n"
    code, out = _run_scan_json(tmp_path, "2025-01-15", csv)
    assert code == 0
    data = json.loads(out)
    for item in data["ranked"]:
        assert set(item.keys()) >= RANKED_ITEM_KEYS


def test_faz152_regression_scan_exclusions_still_works(tmp_path: Path) -> None:
    """Regression: scan --exclusions still excludes symbols (faz146)."""
    csv = "symbol,close\nAKBNK,50.0\nGARAN,100.0\nTHYAO,25.0\n"
    code, out = _run_scan_json(tmp_path, "2025-01-15", csv, "--exclusions", "GARAN")
    assert code == 0
    data = json.loads(out)
    symbols = [r["symbol"] for r in data["ranked"]]
    assert "GARAN" not in symbols


def test_faz152_regression_empty_scan_valid(tmp_path: Path) -> None:
    """Regression: empty snapshot yields valid schema (faz388)."""
    csv = "symbol,close\n"
    code, out = _run_scan_json(tmp_path, "2025-01-15", csv)
    assert code == 0
    data = json.loads(out)
    assert data["ranked"] == []
    assert "schema_version" in data
    assert data["day"] == "2025-01-15"
