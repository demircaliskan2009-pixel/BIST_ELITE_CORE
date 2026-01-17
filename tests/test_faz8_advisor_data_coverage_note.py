from __future__ import annotations

from pathlib import Path

from bist_core.services.advisor import build_advice_for_symbol


def test_advisor_data_coverage_note(tmp_path: Path) -> None:
    snapshots_dir = tmp_path / "snapshots"
    day_dir = snapshots_dir / "2099-01-01"
    day_dir.mkdir(parents=True)
    snapshot_path = day_dir / "snapshot.csv"
    snapshot_path.write_text("symbol,close\nTEST,100.0\n", encoding="utf-8")

    advice = build_advice_for_symbol("TEST", "2099-01-01", root=snapshots_dir)
    assert advice.decision_raw == "PASS"
    assert "eksik veri" in advice.text.lower()
    assert "hacim/turnover" in advice.text.lower()
