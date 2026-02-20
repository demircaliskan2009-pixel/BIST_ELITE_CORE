"""FAZ118-HOTFIX-NODECISION: 1 günlük snapshot -> HOLD + InsufficientHistory."""
from __future__ import annotations

from pathlib import Path

from bist_core.services.advisor import build_advice_for_symbol


def test_faz118_insufficient_history_returns_hold(tmp_path: Path) -> None:
    """Sadece 1 gün snapshot ile build_advice_for_symbol -> decision_raw=PASS (fail-closed), InsufficientHistory."""
    snap_root = tmp_path / "snap"
    (snap_root / "2099-01-15").mkdir(parents=True)
    (snap_root / "2099-01-15" / "snapshot.csv").write_text(
        "symbol,close\nAAA,100.0\n",
        encoding="utf-8",
    )

    advice = build_advice_for_symbol("AAA", "2099-01-15", root=snap_root)

    assert advice.decision_raw == "PASS"
    assert "InsufficientHistory" in advice.text
    assert advice.plan is None
