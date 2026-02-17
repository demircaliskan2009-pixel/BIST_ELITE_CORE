"""FAZ550: Snapshot invalid rows report — JSON format, non-zero exit when invalid."""
from __future__ import annotations

from pathlib import Path

from bist_core.services.snapshot_integrity import validate_snapshot


def test_faz550_snapshot_invalid_report_format(tmp_path: Path) -> None:
    """Report has schema_version, invalid_count, invalid_rows with line_no and reason."""
    csv_path = tmp_path / "snapshot.csv"
    csv_path.write_text(
        "symbol,close\n"
        ",50.0\n",
        encoding="utf-8",
    )
    exit_code, report = validate_snapshot(csv_path)
    assert "schema_version" in report
    assert report["schema_version"] == 1
    assert report["invalid_count"] == 1
    assert "invalid_rows" in report
    rows = report["invalid_rows"]
    assert len(rows) == 1
    assert rows[0]["line_no"] == 2
    assert rows[0]["reason"] == "missing_symbol"


def test_faz550_snapshot_invalid_exit_code(tmp_path: Path) -> None:
    """Invalid snapshot -> exit 1; valid -> exit 0."""
    invalid_path = tmp_path / "bad.csv"
    invalid_path.write_text("symbol,close\n,1.0\n", encoding="utf-8")
    exit_invalid, _ = validate_snapshot(invalid_path)
    assert exit_invalid == 1

    valid_path = tmp_path / "good.csv"
    valid_path.write_text("symbol,close\nAAA,100.0\n", encoding="utf-8")
    exit_valid, _ = validate_snapshot(valid_path)
    assert exit_valid == 0
