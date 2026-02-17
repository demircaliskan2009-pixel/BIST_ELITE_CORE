"""FAZ149: Scan stable ordering — deterministic tie-break for equal scores. Schema, golden, edge tests."""
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
        [sys.executable, "-m", "bist_core.cli", "scan", "--day", day, "--top-n", "10", "--json", *extra_args],
        cwd=str(_repo_root()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=60,
    )
    return r.returncode, r.stdout


def test_faz149_scan_schema_required_keys(tmp_path: Path) -> None:
    """Scan JSON has required schema: schema_version, day, generated_at, ranked with symbol/score/rationale."""
    csv = "symbol,close\nAKBNK,50.0\nGARAN,100.0\n"
    code, out = _run_scan_json(tmp_path, "2025-01-15", csv)
    assert code == 0
    data = json.loads(out)
    assert "schema_version" in data
    assert "day" in data
    assert "generated_at" in data
    assert "ranked" in data
    assert isinstance(data["ranked"], list)
    for item in data["ranked"]:
        assert "symbol" in item
        assert "score" in item
        assert "rationale" in item
        assert isinstance(item["symbol"], str)
        assert isinstance(item["score"], (int, float))
        assert isinstance(item["rationale"], str)


def test_faz149_scan_golden_deterministic(tmp_path: Path) -> None:
    """Same input produces identical ranked order (excluding generated_at). Byte-level determinism for ranked."""
    csv = "symbol,open,high,low,close,volume,turnover_tl\n"
    csv += "XA,50,51,49,50,1000000,50000000\nYB,50,51,49,50,1000000,50000000\nZC,50,51,49,50,1000000,50000000\n"
    code1, out1 = _run_scan_json(tmp_path, "2025-01-20", csv)
    code2, out2 = _run_scan_json(tmp_path, "2025-01-20", csv)
    assert code1 == 0 and code2 == 0
    d1 = json.loads(out1)
    d2 = json.loads(out2)
    assert d1["ranked"] == d2["ranked"], "Ranked must be byte-identical"
    assert d1["day"] == d2["day"]
    assert [r["symbol"] for r in d1["ranked"]] == ["XA", "YB", "ZC"], "Tie-break by symbol ascending"


def test_faz149_scan_equal_scores_tiebreak_ascending(tmp_path: Path) -> None:
    """Equal scores tie-break by symbol ascending (AAA < MMM < ZZZ)."""
    csv = "symbol,open,high,low,close,volume,turnover_tl\n"
    csv += "ZZZ,100,101,99,100,1000000,50000000\nAAA,100,101,99,100,1000000,50000000\nMMM,100,101,99,100,1000000,50000000\n"
    code, out = _run_scan_json(tmp_path, "2025-02-01", csv)
    assert code == 0
    data = json.loads(out)
    symbols = [r["symbol"] for r in data["ranked"]]
    assert symbols == ["AAA", "MMM", "ZZZ"], f"Expected ascending, got {symbols}"


def test_faz149_scan_single_symbol_edge(tmp_path: Path) -> None:
    """Single symbol: ranked has one item, deterministic."""
    csv = "symbol,close\nAKBNK,50.0\n"
    code, out = _run_scan_json(tmp_path, "2025-01-10", csv)
    assert code == 0
    data = json.loads(out)
    assert len(data["ranked"]) == 1
    assert data["ranked"][0]["symbol"] == "AKBNK"
    assert data["ranked"][0]["score"] == 0.0 or isinstance(data["ranked"][0]["score"], (int, float))


def test_faz149_scan_empty_snapshot_edge(tmp_path: Path) -> None:
    """Empty snapshot: ranked is empty list, no crash."""
    csv = "symbol,close\n"
    code, out = _run_scan_json(tmp_path, "2025-01-11", csv)
    assert code == 0
    data = json.loads(out)
    assert data["ranked"] == []
    assert data["day"] == "2025-01-11"
