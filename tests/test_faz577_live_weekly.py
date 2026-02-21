"""FAZ577: Weekly live review — scoreboard + performance + journal. Fixtures only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_repo = Path(__file__).resolve().parents[1]
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))
from tools.live_weekly_report import (
    build_weekly_report,
    write_weekly_json,
    write_weekly_csv,
    write_weekly_html,
    _week_to_dates,
    _dates_in_range,
)


def test_week_to_dates() -> None:
    """YYYY-WW parses to (monday, sunday)."""
    m, s = _week_to_dates("2025-W03")
    assert m == "2025-01-13"
    assert s == "2025-01-19"


def test_dates_in_range() -> None:
    """Range inclusive, sorted."""
    days = _dates_in_range("2025-01-13", "2025-01-15")
    assert days == ["2025-01-13", "2025-01-14", "2025-01-15"]


def test_build_weekly_report_empty(tmp_path: Path) -> None:
    """No logs => empty scoreboard/performance, no journal."""
    report = build_weekly_report("2025-W03", tmp_path, None)
    assert report["schema_version"] == 1
    assert report["week"] == "2025-W03"
    assert report["date_from"] == "2025-01-13"
    assert report["date_to"] == "2025-01-19"
    assert report["scoreboard"]["rows"] == []
    assert report["performance"]["aggregated"]["trade_count"] == 0
    assert report["journal"] is None


def test_build_weekly_report_with_fixtures(tmp_path: Path) -> None:
    """Fixture: scoreboard + performance for one day."""
    reports = tmp_path / "reports"
    (reports / "2025-01-15").mkdir(parents=True)
    (reports / "2025-01-15" / "scoreboard.json").write_text(
        json.dumps({
            "schema_version": 1,
            "day": "2025-01-15",
            "horizons": [1, 5, 20],
            "rows": [
                {"symbol": "AAA", "decision_raw": "BUY", "ret_1d": 0.01, "ret_5d": None, "ret_20d": None},
                {"symbol": "BBB", "decision_raw": "HOLD", "ret_1d": None, "ret_5d": None, "ret_20d": None},
            ],
        }),
        encoding="utf-8",
    )
    (reports / "2025-01-15" / "performance.json").write_text(
        json.dumps({
            "schema_version": 1,
            "trade_count": 2,
            "win_count": 1,
            "loss_count": 1,
            "win_rate": 0.5,
            "avg_r": 0.0,
            "total_r": 0.0,
            "max_dd": 0.5,
            "equity_curve": [],
        }),
        encoding="utf-8",
    )

    report = build_weekly_report("2025-W03", tmp_path, None)
    assert len(report["scoreboard"]["rows"]) == 2
    assert report["scoreboard"]["rows"][0]["day"] == "2025-01-15"
    assert report["scoreboard"]["rows"][0]["symbol"] == "AAA"
    assert report["performance"]["aggregated"]["trade_count"] == 2
    assert report["performance"]["aggregated"]["win_rate"] == 0.5


def test_write_weekly_artifacts(tmp_path: Path) -> None:
    """write_weekly_* produces json, csv, html."""
    report = {
        "schema_version": 1,
        "week": "2025-W03",
        "date_from": "2025-01-13",
        "date_to": "2025-01-19",
        "scoreboard": {"days": [], "rows": []},
        "performance": {"aggregated": {"trade_count": 0}, "by_day": []},
        "journal": None,
    }
    out_dir = tmp_path / "2025-W03"
    write_weekly_json(report, out_dir)
    write_weekly_csv(report, out_dir)
    write_weekly_html(report, out_dir)

    assert (out_dir / "weekly.json").is_file()
    assert (out_dir / "weekly.csv").is_file()
    assert (out_dir / "weekly.html").is_file()

    loaded = json.loads((out_dir / "weekly.json").read_text(encoding="utf-8"))
    assert loaded["week"] == "2025-W03"

    html = (out_dir / "weekly.html").read_text(encoding="utf-8")
    assert "2025-W03" in html
    assert "Performance" in html


def test_weekly_deterministic_ordering(tmp_path: Path) -> None:
    """Scoreboard rows sorted by (day, symbol)."""
    reports = tmp_path / "reports"
    for day in ["2025-01-14", "2025-01-13", "2025-01-15"]:
        (reports / day).mkdir(parents=True)
        (reports / day / "scoreboard.json").write_text(
            json.dumps({"rows": [{"symbol": "ZZZ", "decision_raw": "HOLD"}, {"symbol": "AAA", "decision_raw": "BUY"}]}),
            encoding="utf-8",
        )
    report = build_weekly_report("2025-W03", tmp_path, None)
    rows = report["scoreboard"]["rows"]
    assert len(rows) == 6
    days_syms = [(r["day"], r["symbol"]) for r in rows]
    assert days_syms == sorted(days_syms)
