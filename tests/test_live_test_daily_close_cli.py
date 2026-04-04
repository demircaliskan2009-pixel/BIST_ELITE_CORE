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


def test_live_test_daily_close_cli(tmp_path: Path) -> None:
    live_root = tmp_path / "live_test"
    snap_root = tmp_path / "snapshots"
    live_root.mkdir(parents=True, exist_ok=True)

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

    meta_file = tmp_path / "meta.json"
    meta_file.write_text(
        json.dumps({"message": "AKBNK için kısa vade senaryo üret"}, ensure_ascii=False),
        encoding="utf-8",
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
        "--meta-file",
        str(meta_file),
    ]
    subprocess.run(log_cmd, capture_output=True, text=True, check=True)

    close_cmd = [
        sys.executable,
        "-m",
        "bist_core.live_test.daily_close",
        "--root",
        str(live_root),
        "--snapshot-root",
        str(snap_root),
        "--max-holding-days",
        "5",
    ]
    cp = subprocess.run(close_cmd, capture_output=True, text=True, check=True)
    payload = json.loads(cp.stdout)

    assert payload["ok"] is True
    assert payload["evaluate"]["closed_count"] == 1
    assert payload["report"]["closed_count"] == 1
    assert Path(payload["json_out"]).exists()
    assert Path(payload["csv_out"]).exists()
