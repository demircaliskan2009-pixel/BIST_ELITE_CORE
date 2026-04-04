import json
import subprocess
import sys
from pathlib import Path


def test_live_test_cli_log_with_meta_file_utf8(tmp_path: Path) -> None:
    root = tmp_path / "live_test"
    meta_file = tmp_path / "meta.json"
    meta_file.write_text(
        json.dumps({"message": "AKBNK için kısa vade senaryo üret", "top_n": 3}, ensure_ascii=False),
        encoding="utf-8",
    )

    cmd = [
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
        "--meta-file",
        str(meta_file),
    ]
    cp = subprocess.run(cmd, capture_output=True, text=True, check=True)
    payload = json.loads(cp.stdout)

    assert payload["ok"] is True
    assert payload["record"]["metadata"]["message"] == "AKBNK için kısa vade senaryo üret"
    assert payload["record"]["metadata"]["top_n"] == 3
