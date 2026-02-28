"""FAZ552: API deterministic CLI parity — API ask/scan output matches CLI --json."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bist_core.api.app import app, SCAN_ARTIFACT_SCHEMA_VERSION


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def snapshot_fixture(tmp_path: Path) -> Path:
    """Minimal snapshot dir with one day for offline tests."""
    day_dir = tmp_path / "2025-01-15"
    day_dir.mkdir()
    snap = day_dir / "snapshot.csv"
    snap.write_text("symbol,close\nAKBNK,50.0\nGARAN,100.0\n", encoding="utf-8")
    return tmp_path


def _run_cli_ask(snapshot_dir: Path, symbol: str = "AKBNK", day: str = "2025-01-15") -> dict:
    """Run CLI ask --json and return parsed JSON."""
    env = os.environ.copy()
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_dir)
    env.pop("BIST_CORE_ALLOW_NETWORK", None)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "ask", symbol, "--day", day, "--json"],
        cwd=str(_repo_root()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert r.returncode == 0, f"CLI ask failed: {r.stderr}"
    return json.loads(r.stdout)


def _run_cli_scan(snapshot_dir: Path, day: str = "2025-01-15", top_n: int = 5) -> dict:
    """Run CLI scan --json and return parsed JSON."""
    env = os.environ.copy()
    env["BIST_CORE_SNAPSHOT_DIR"] = str(snapshot_dir)
    env.pop("BIST_CORE_ALLOW_NETWORK", None)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    r = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", "scan", "--day", day, "--top-n", str(top_n), "--json"],
        cwd=str(_repo_root()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    assert r.returncode == 0, f"CLI scan failed: {r.stderr}"
    return json.loads(r.stdout)


def test_faz552_api_ask_matches_cli_json(
    client: TestClient, snapshot_fixture: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """API /ask returns same symbol, day, decision_raw, score as CLI ask --json."""
    monkeypatch.delenv("BIST_CORE_ALLOW_NETWORK", raising=False)
    monkeypatch.setenv("BIST_CORE_SNAPSHOT_DIR", str(snapshot_fixture))

    cli_out = _run_cli_ask(snapshot_fixture)
    r = client.post("/ask", json={"symbol": "AKBNK", "day": "2025-01-15"})
    assert r.status_code == 200
    api_out = r.json()

    assert api_out["symbol"] == cli_out["symbol"]
    assert api_out["day"] == cli_out["day"]
    assert api_out["decision_raw"] == cli_out["decision_raw"]
    assert round(api_out["score"], 2) == round(cli_out["score"], 2)


def test_faz552_api_scan_matches_cli_json(
    client: TestClient, snapshot_fixture: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """API /scan returns same schema_version, day, ranked structure as CLI scan --json."""
    monkeypatch.delenv("BIST_CORE_ALLOW_NETWORK", raising=False)
    monkeypatch.setenv("BIST_CORE_SNAPSHOT_DIR", str(snapshot_fixture))

    cli_out = _run_cli_scan(snapshot_fixture)
    r = client.post("/scan", json={"day": "2025-01-15", "top_n": 5})
    assert r.status_code == 200
    api_out = r.json()

    assert api_out["schema_version"] == cli_out["schema_version"] == SCAN_ARTIFACT_SCHEMA_VERSION
    assert api_out["day"] == cli_out["day"]
    assert "generated_at" in api_out
    assert len(api_out["ranked"]) == len(cli_out["ranked"])
    for api_item, cli_item in zip(api_out["ranked"], cli_out["ranked"]):
        assert api_item["symbol"] == cli_item["symbol"]
        assert api_item["score"] == cli_item["score"]
        assert api_item["rationale"] == cli_item["rationale"]
