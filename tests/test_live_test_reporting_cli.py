import json
import subprocess
import sys
from pathlib import Path


def test_live_test_cli_report_json_and_csv(tmp_path: Path) -> None:
    root = tmp_path / "live_test"

    log_cmd = [
        sys.executable,
        "-m",
        "bist_core.live_test.cli",
        "--root",
        str(root),
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
        "91.05",
        "--stop",
        "88.35",
        "--target",
        "92.85",
    ]
    log_cp = subprocess.run(log_cmd, capture_output=True, text=True, check=True)
    rec_id = json.loads(log_cp.stdout)["recommendation_id"]

    close_cmd = [
        sys.executable,
        "-m",
        "bist_core.live_test.cli",
        "--root",
        str(root),
        "close",
        "--id",
        rec_id,
        "--outcome-label",
        "win",
        "--realized-return-r",
        "1.0",
        "--realized-return-pct",
        "2.5",
        "--note",
        "t1 hit",
    ]
    subprocess.run(close_cmd, capture_output=True, text=True, check=True)

    report_json_cmd = [
        sys.executable,
        "-m",
        "bist_core.live_test.cli",
        "--root",
        str(root),
        "report",
        "--format",
        "json",
    ]
    report_json_cp = subprocess.run(report_json_cmd, capture_output=True, text=True, check=True)
    report_json_payload = json.loads(report_json_cp.stdout)
    assert report_json_payload["ok"] is True
    assert report_json_payload["report"]["closed_count"] == 1
    assert report_json_payload["report"]["outcome_counts"]["win"] == 1

    csv_path = root / "report_records.csv"
    report_csv_cmd = [
        sys.executable,
        "-m",
        "bist_core.live_test.cli",
        "--root",
        str(root),
        "report",
        "--format",
        "csv",
        "--out",
        str(csv_path),
    ]
    report_csv_cp = subprocess.run(report_csv_cmd, capture_output=True, text=True, check=True)
    report_csv_payload = json.loads(report_csv_cp.stdout)
    assert report_csv_payload["ok"] is True
    assert Path(report_csv_payload["out"]).exists()
    csv_text = csv_path.read_text(encoding="utf-8-sig")
    assert "AKBNK" in csv_text
