"""FAZ549: Snapshot malformed row detection — invalid numeric, missing symbol; deterministic."""

from __future__ import annotations

from pathlib import Path

from bist_core.services.snapshot_integrity import detect_malformed_snapshot_rows


def test_faz549_snapshot_malformed_detected(tmp_path: Path) -> None:
    """Malformed rows (missing symbol, invalid close) are detected."""
    csv_path = tmp_path / "snapshot.csv"
    csv_path.write_text(
        "symbol,close\nAAA,100.0\n,50.0\nBBB,not_a_number\nCCC,100.0\n",
        encoding="utf-8",
    )
    invalid = detect_malformed_snapshot_rows(csv_path)
    assert len(invalid) == 2
    reasons = {r["reason"] for r in invalid}
    assert "missing_symbol" in reasons
    assert "invalid_close_numeric" in reasons
    line_nos = {r["line_no"] for r in invalid}
    assert 3 in line_nos
    assert 4 in line_nos


def test_faz549_snapshot_valid_rows_pass(tmp_path: Path) -> None:
    """Valid rows produce no invalid entries."""
    csv_path = tmp_path / "snapshot.csv"
    csv_path.write_text(
        "symbol,close\nAAA,100.0\nBBB,50.5\nCCC,0.01\n",
        encoding="utf-8",
    )
    invalid = detect_malformed_snapshot_rows(csv_path)
    assert invalid == []


def test_faz549_snapshot_malformed_deterministic(tmp_path: Path) -> None:
    """Same file -> same detection result (deterministic)."""
    csv_path = tmp_path / "snapshot.csv"
    csv_path.write_text(
        "symbol,close\nX,100\n,99\n",
        encoding="utf-8",
    )
    r1 = detect_malformed_snapshot_rows(csv_path)
    r2 = detect_malformed_snapshot_rows(csv_path)
    assert r1 == r2
    assert len(r1) == 1
    assert r1[0]["reason"] == "missing_symbol"
