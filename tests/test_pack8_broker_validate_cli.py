from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_broker_validate_config_cli_smoke() -> None:
    root = _repo_root()
    cfg = root / "configs" / "broker_config.stub.example.json"
    assert cfg.is_file()

    cmd = [
        sys.executable,
        "-m",
        "bist_core.cli",
        "broker",
        "validate-config",
        "--config",
        str(cfg),
        "--schema",
        str(root / "configs" / "broker_config.schema.json"),
    ]
    r = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)

    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert "OK" in (r.stdout or "")
