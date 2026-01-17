from pathlib import Path

from bist_core.cli.main import _latest_snapshot_day


def test_latest_snapshot_day(tmp_path: Path) -> None:
    (tmp_path / "2025-01-15").mkdir()
    (tmp_path / "2025-01-16").mkdir()
    (tmp_path / "garbage").mkdir()

    assert _latest_snapshot_day(tmp_path) == "2025-01-16"
