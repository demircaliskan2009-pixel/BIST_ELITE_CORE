import json
import subprocess
import sys
from pathlib import Path


def _write_snapshot_day(root: Path, day: str, rows: list[dict[str, object]]) -> None:
    day_dir = root / day
    day_dir.mkdir(parents=True, exist_ok=True)

    header = "date,symbol,open,high,low,close,volume,turnover_tl"
    lines = [header]
    for row in rows:
        lines.append(
            ",".join(
                [
                    day,
                    str(row["symbol"]),
                    str(row["open"]),
                    str(row["high"]),
                    str(row["low"]),
                    str(row["close"]),
                    "1000",
                    "100000",
                ]
            )
        )
    (day_dir / "snapshot.csv").write_text("\n".join(lines), encoding="utf-8")


def test_live_test_cli_evaluate_open(tmp_path: Path) -> None:
    live_root = tmp_path / "live_test"
    snap_root = tmp_path / "snapshots"

    _write_snapshot_day(
        snap_root,
        "2026-02-27",
        [{"symbol": "AKBNK", "open": 100, "high": 102, "low": 99, "close": 101}],
    )
    _write_snapshot_day(
        snap_root,
        "2026-03-02",
        [{"symbol": "AKBNK", "open": 103, "high": 111, "low": 103, "close": 110}],
    )

    log_cmd = [
        sys.executable,
        "-m",
        "bist_core.live_test.cli",
        "--root",
        str(live_root),
        "log",
        "--source",
        "gateway_chat",
        "--symbol",
        "AKBNK",
        "--day",
        "2026-02-27",
        "--decision",
        "WATCH",
        "--entry",
        "100",
        "--stop",
        "95",
        "--target",
        "110",
    ]
    subprocess.run(log_cmd, capture_output=True, text=True, check=True)

    eval_cmd = [
        sys.executable,
        "-m",
        "bist_core.live_test.cli",
        "--root",
        str(live_root),
        "evaluate-open",
        "--snapshot-root",
        str(snap_root),
        "--max-holding-days",
        "5",
    ]
    eval_cp = subprocess.run(eval_cmd, capture_output=True, text=True, check=True)
    eval_payload = json.loads(eval_cp.stdout)

    assert eval_payload["ok"] is True
    assert eval_payload["closed_count"] == 1
    assert eval_payload["outcome_counts"]["win"] == 1

    stats_cmd = [
        sys.executable,
        "-m",
        "bist_core.live_test.cli",
        "--root",
        str(live_root),
        "stats",
    ]
    stats_cp = subprocess.run(stats_cmd, capture_output=True, text=True, check=True)
    stats_payload = json.loads(stats_cp.stdout)

    assert stats_payload["stats"]["closed_count"] == 1
    assert stats_payload["stats"]["open_count"] == 0
    assert stats_payload["stats"]["outcome_counts"]["win"] == 1
