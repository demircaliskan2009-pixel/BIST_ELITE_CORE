import json
import subprocess
import sys
from pathlib import Path


def test_live_test_cli_roundtrip(tmp_path: Path) -> None:
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
        "--timeframe",
        "short",
        "--score",
        "1.0",
        "--entry",
        "91.05",
        "--stop",
        "88.35",
        "--target",
        "92.85",
        "--rationale",
        "Momentum pozitif",
        "--invalidation",
        "Ters haber",
    ]
    log_cp = subprocess.run(log_cmd, capture_output=True, text=True, check=True)
    log_payload = json.loads(log_cp.stdout)
    rec_id = log_payload["recommendation_id"]

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

    stats_cmd = [
        sys.executable,
        "-m",
        "bist_core.live_test.cli",
        "--root",
        str(root),
        "stats",
    ]
    stats_cp = subprocess.run(stats_cmd, capture_output=True, text=True, check=True)
    stats_payload = json.loads(stats_cp.stdout)

    assert stats_payload["ok"] is True
    assert stats_payload["stats"]["total_recommendations"] == 1
    assert stats_payload["stats"]["closed_count"] == 1
    assert stats_payload["stats"]["outcome_counts"]["win"] == 1
