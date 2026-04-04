"""FAZ567: Live ops pack — validate, today, journal report. No real market data."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_repo = Path(__file__).resolve().parents[1]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))
from tools.live_validate import validate_snapshot_for_day
from tools.live_journal_report import build_report
from tools.live_snapshot_prepare import prepare_snapshot
from tools.live_publish_summary import publish_summary
from tools.scoreboard_report import build_scoreboard, write_scoreboard


def test_live_validate_missing_snapshot_returns_fail(tmp_path: Path) -> None:
    """live_validate returns ok=False and exit 2 on missing snapshot."""
    # ruff: noqa: E402
    ok, reasons, checked, _ = validate_snapshot_for_day("2025-01-15", tmp_path / "nonexistent")
    assert ok is False
    assert "snapshot_root_missing" in reasons or "day_dir_missing" in reasons


def test_live_validate_empty_dir_returns_fail(tmp_path: Path) -> None:
    """live_validate returns ok=False when day dir exists but no snapshot.csv."""
    (tmp_path / "2025-01-15").mkdir()
    ok, reasons, _, _ = validate_snapshot_for_day("2025-01-15", tmp_path)
    assert ok is False
    assert "snapshot_csv_missing" in reasons


def test_live_validate_invalid_day_format(tmp_path: Path) -> None:
    """live_validate returns ok=False for invalid day format."""
    ok, reasons, _, _ = validate_snapshot_for_day("invalid", tmp_path)
    assert ok is False
    assert "invalid_day_format" in reasons


def test_live_validate_ok_with_valid_snapshot(tmp_path: Path) -> None:
    """live_validate returns ok=True when snapshot is valid."""
    (tmp_path / "2025-01-15").mkdir()
    (tmp_path / "2025-01-15" / "snapshot.csv").write_text(
        "symbol,close\nAAA,100.0\nBBB,99.0\n",
        encoding="utf-8",
    )
    ok, reasons, checked, details = validate_snapshot_for_day("2025-01-15", tmp_path)
    assert ok is True
    assert not reasons
    assert len(checked) >= 1
    assert details.get("symbol_count", 0) >= 1


def test_live_validate_ok_with_bom_prefixed_header(tmp_path: Path) -> None:
    """FAZ593: live_validate returns ok=True when snapshot.csv has UTF-8 BOM prefix."""
    (tmp_path / "2025-01-20").mkdir()
    # Write with BOM (Excel-style); utf-8-sig adds BOM at file start
    (tmp_path / "2025-01-20" / "snapshot.csv").write_text(
        "symbol,close\nAAA,100.0\nBBB,99.0\n",
        encoding="utf-8-sig",
    )
    ok, reasons, checked, details = validate_snapshot_for_day("2025-01-20", tmp_path)
    assert ok is True, f"Expected ok=True, got reasons={reasons}"
    assert not reasons
    assert details.get("symbol_count", 0) >= 1


def test_live_validate_cli_exit_2_on_missing(tmp_path: Path) -> None:
    """live_validate.py exits 2 when snapshot missing."""
    env = {"PYTHONPATH": str(_repo / "src")}
    r = subprocess.run(
        [
            sys.executable,
            str(_repo / "tools" / "live_validate.py"),
            "--day",
            "2099-01-01",
            "--snapshot-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=str(_repo),
    )
    assert r.returncode == 2
    data = json.loads(r.stdout)
    assert data.get("ok") is False


def test_live_today_refuses_when_validate_fails(tmp_path: Path) -> None:
    """live_today logic: validate fails => no live run. Test via validate function."""
    ok, _, _, _ = validate_snapshot_for_day("2099-01-01", tmp_path / "empty")
    assert ok is False
    # When validate returns False, live_today.ps1 would exit 2 without running live_daily


def test_live_journal_report_parses_template(tmp_path: Path) -> None:
    """live_journal_report parses template and produces deterministic output."""
    journal = tmp_path / "journal.csv"
    journal.write_text(
        "day,symbol,side,qty,price,fees_tl,note,source_run_id\n"
        "2025-01-15,ASELS,BUY,100,42.50,0.00,manual,2025-01-15\n"
        "2025-01-20,ASELS,SELL,100,44.00,0.00,manual,2025-01-15\n",
        encoding="utf-8",
    )
    out_root = tmp_path / "log"
    out_root.mkdir()

    report = build_report(journal, out_root, "2025-01-15", "2025-01-20")
    assert report["schema_version"] == 1
    assert report["date_from"] == "2025-01-15"
    assert report["date_to"] == "2025-01-20"
    # PnL: buy 100*42.5=4250, sell 100*44=4400 => 150
    assert report["realized_pnl_tl"] == 150.0
    assert len(report["trades"]) >= 1


def test_live_journal_report_empty_journal(tmp_path: Path) -> None:
    """Empty journal => zero PnL."""
    journal = tmp_path / "empty.csv"
    journal.write_text("day,symbol,side,qty,price,fees_tl,note,source_run_id\n", encoding="utf-8")
    out_root = tmp_path / "log"
    out_root.mkdir()

    report = build_report(journal, out_root, "2025-01-01", "2025-01-31")
    assert report["realized_pnl_tl"] == 0.0
    assert report["trades"] == []


def test_live_snapshot_prepare_valid_fixture_exit_0(tmp_path: Path) -> None:
    """live_snapshot_prepare returns ok=True when snapshot is valid."""
    (tmp_path / "2025-01-15").mkdir()
    (tmp_path / "2025-01-15" / "snapshot.csv").write_text(
        "symbol,close\nAAA,100.0\nBBB,99.0\n",
        encoding="utf-8",
    )
    ok, missing, reasons = prepare_snapshot("2025-01-15", tmp_path)
    assert ok is True
    assert not missing
    assert not reasons


def test_live_snapshot_prepare_missing_snapshot_exit_2(tmp_path: Path) -> None:
    """live_snapshot_prepare returns ok=False when snapshot missing."""
    ok, missing, reasons = prepare_snapshot("2099-01-01", tmp_path / "empty")
    assert ok is False
    assert any("snapshot" in p or "2099" in p for p in missing) or reasons


def test_live_snapshot_prepare_cli_exit_2_on_missing(tmp_path: Path) -> None:
    """live_snapshot_prepare.py exits 2 when snapshot missing."""
    env = {"PYTHONPATH": str(_repo / "src")}
    r = subprocess.run(
        [
            sys.executable,
            str(_repo / "tools" / "live_snapshot_prepare.py"),
            "--day",
            "2099-01-01",
            "--snapshot-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=str(_repo),
    )
    assert r.returncode == 2


def test_live_publish_summary_minimal_workflow(tmp_path: Path) -> None:
    """Minimal fixture => summary.html exists and contains key filenames."""
    day = "2099-01-01"
    out_root = tmp_path / "log"
    (out_root / "daily_scan" / day).mkdir(parents=True)
    (out_root / "ask" / day).mkdir(parents=True)
    (out_root / "reports" / day).mkdir(parents=True)

    (out_root / "daily_scan" / day / "scan.json").write_text(
        '{"day":"2099-01-01","ranked":[{"symbol":"AAA"},{"symbol":"BBB"}]}',
        encoding="utf-8",
    )
    (out_root / "ask" / day / "AAA.json").write_text("{}", encoding="utf-8")
    (out_root / "ask" / day / "BBB.json").write_text("{}", encoding="utf-8")

    summary_path = publish_summary(day, out_root)
    assert summary_path is not None
    assert summary_path.is_file()

    html = summary_path.read_text(encoding="utf-8")
    assert "scan.json" in html
    assert "performance.json" in html
    assert "performance.csv" in html
    assert day in html


def test_scoreboard_minimal_fixture(tmp_path: Path) -> None:
    """Scoreboard with future bars: files exist, deterministic ordering."""
    day = "2099-01-01"
    snap = tmp_path / "snapshots"
    out_root = tmp_path / "log"

    for d, rows in [
        ("2099-01-01", "symbol,close\nAAA,100.0\nBBB,99.0\n"),
        ("2099-01-02", "symbol,close\nAAA,102.0\nBBB,98.0\n"),
        ("2099-01-06", "symbol,close\nAAA,105.0\nBBB,97.0\n"),
        ("2099-01-21", "symbol,close\nAAA,110.0\nBBB,95.0\n"),
    ]:
        (snap / d).mkdir(parents=True)
        (snap / d / "snapshot.csv").write_text(rows, encoding="utf-8")

    (out_root / "daily_scan" / day).mkdir(parents=True)
    (out_root / "daily_scan" / day / "scan.json").write_text(
        '{"day":"2099-01-01","ranked":[{"symbol":"AAA"},{"symbol":"BBB"}]}',
        encoding="utf-8",
    )
    (out_root / "ask" / day).mkdir(parents=True)
    (out_root / "ask" / day / "AAA.json").write_text(
        '{"symbol":"AAA","decision_raw":"BUY"}',
        encoding="utf-8",
    )
    (out_root / "ask" / day / "BBB.json").write_text(
        '{"symbol":"BBB","decision_raw":"HOLD"}',
        encoding="utf-8",
    )

    report = build_scoreboard(day, out_root, snap, [1, 5, 20])
    assert report["schema_version"] == 1
    assert report["day"] == day
    assert len(report["rows"]) == 2
    rows = sorted(report["rows"], key=lambda r: r["symbol"])
    assert rows[0]["symbol"] == "AAA"
    assert rows[0]["decision_raw"] == "BUY"
    assert rows[0]["ret_1d"] == pytest.approx(0.02)
    assert rows[0]["ret_5d"] == pytest.approx(0.05)
    assert rows[0]["ret_20d"] == pytest.approx(0.10)
    assert rows[1]["symbol"] == "BBB"
    assert rows[1]["decision_raw"] == "HOLD"

    write_scoreboard(report, out_root / "reports" / day)
    assert (out_root / "reports" / day / "scoreboard.json").is_file()
    assert (out_root / "reports" / day / "scoreboard.csv").is_file()
