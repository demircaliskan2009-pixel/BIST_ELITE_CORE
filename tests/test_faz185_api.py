"""FAZ185/186/187/188/189/193: API endpoints — health, ask, scan; BIST-only; network OFF."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from bist_core.api.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def snapshot_fixture(tmp_path: Path) -> Path:
    """Minimal snapshot dir with one day for offline tests (symbol,close format)."""
    day_dir = tmp_path / "2025-01-15"
    day_dir.mkdir()
    snap = day_dir / "snapshot.csv"
    snap.write_text("symbol,close\nAKBNK,50.0\n", encoding="utf-8")
    return tmp_path


def test_faz193_health(client: TestClient) -> None:
    """GET /health returns 200 and status ok."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_faz186_ask_bist_only_rejects_invalid(client: TestClient) -> None:
    """POST /ask rejects non-BIST symbol (400) or invalid format (422)."""
    r = client.post("/ask", json={"symbol": "INVALID_SYMBOL_TOO_LONG"})
    assert r.status_code == 422  # Pydantic validation (max_length=6)

    r2 = client.post("/ask", json={"symbol": "123"})  # digits-only fails BIST (isupper)
    assert r2.status_code == 400
    assert "BIST" in r2.json().get("detail", "")


def test_faz189_network_off_guard(client: TestClient) -> None:
    """POST /ask and /scan return 503 when BIST_CORE_ALLOW_NETWORK is set."""
    with patch.dict(os.environ, {"BIST_CORE_ALLOW_NETWORK": "1"}):
        r_ask = client.post("/ask", json={"symbol": "AKBNK"})
        r_scan = client.post("/scan", json={})
    assert r_ask.status_code == 503
    assert r_scan.status_code == 503
    assert "offline" in r_ask.json().get("detail", "").lower()


def test_faz186_ask_with_snapshot(
    client: TestClient, snapshot_fixture: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /ask returns advice when snapshot exists (offline)."""
    monkeypatch.delenv("BIST_CORE_ALLOW_NETWORK", raising=False)
    monkeypatch.setenv("BIST_CORE_SNAPSHOT_DIR", str(snapshot_fixture))
    r = client.post(
        "/ask",
        json={"symbol": "AKBNK", "day": "2025-01-15"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["symbol"] == "AKBNK"
    assert data["day"] == "2025-01-15"
    assert "decision_raw" in data
    assert "score" in data


def test_faz187_scan_with_snapshot(
    client: TestClient, snapshot_fixture: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /scan returns ranked list when snapshot exists (offline)."""
    monkeypatch.delenv("BIST_CORE_ALLOW_NETWORK", raising=False)
    monkeypatch.setenv("BIST_CORE_SNAPSHOT_DIR", str(snapshot_fixture))
    r = client.post(
        "/scan",
        json={"day": "2025-01-15", "top_n": 5},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["day"] == "2025-01-15"
    assert "ranked" in data
    assert isinstance(data["ranked"], list)


def test_faz187_scan_no_snapshots_400(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /scan returns 400 when no snapshots and no day provided."""
    monkeypatch.delenv("BIST_CORE_ALLOW_NETWORK", raising=False)
    monkeypatch.setenv("BIST_CORE_SNAPSHOT_DIR", "/nonexistent/path/12345")
    r = client.post("/scan", json={})
    assert r.status_code == 400


def test_faz185_ask_response_schema(
    client: TestClient, snapshot_fixture: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ask response has required schema: symbol, day, decision_raw, score, text."""
    monkeypatch.delenv("BIST_CORE_ALLOW_NETWORK", raising=False)
    monkeypatch.setenv("BIST_CORE_SNAPSHOT_DIR", str(snapshot_fixture))
    r = client.post("/ask", json={"symbol": "AKBNK", "day": "2025-01-15"})
    assert r.status_code == 200
    data = r.json()
    for key in ("symbol", "day", "decision_raw", "score", "text"):
        assert key in data, f"Missing key: {key}"
    assert isinstance(data["score"], (int, float))


def test_faz185_scan_response_schema(
    client: TestClient, snapshot_fixture: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scan response has required schema: day, ranked list with symbol/score/rationale."""
    monkeypatch.delenv("BIST_CORE_ALLOW_NETWORK", raising=False)
    monkeypatch.setenv("BIST_CORE_SNAPSHOT_DIR", str(snapshot_fixture))
    r = client.post("/scan", json={"day": "2025-01-15", "top_n": 5})
    assert r.status_code == 200
    data = r.json()
    assert "day" in data
    assert "ranked" in data
    assert isinstance(data["ranked"], list)
    for item in data["ranked"]:
        assert "symbol" in item and "score" in item and "rationale" in item
