"""AI interface — SDK docs, version endpoint, interface consistency."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bist_core.api.app import API_VERSION, SCAN_ARTIFACT_SCHEMA_VERSION, app


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_ai_sdk_doc_exists() -> None:
    """docs/AI_SDK.md exists for ChatGPT/AI integration."""
    path = _repo_root() / "docs" / "AI_SDK.md"
    assert path.is_file(), "docs/AI_SDK.md required for AI interface"
    content = path.read_text(encoding="utf-8")
    assert "ask" in content.lower()
    assert "scan" in content.lower()
    assert "version" in content.lower() or "schema" in content.lower()


def test_chat_agent_flow_doc_exists() -> None:
    """docs/CHAT_AGENT_FLOW.md exists with example pseudo-code."""
    path = _repo_root() / "docs" / "CHAT_AGENT_FLOW.md"
    assert path.is_file(), "docs/CHAT_AGENT_FLOW.md required"
    content = path.read_text(encoding="utf-8")
    assert "bist_ask" in content or "ask" in content
    assert "bist_scan" in content or "scan" in content


def test_version_endpoint_returns_versioned_response() -> None:
    """GET /version returns api_version and schema_version."""
    client = TestClient(app)
    r = client.get("/version")
    assert r.status_code == 200
    data = r.json()
    assert data["api_version"] == API_VERSION
    assert data["schema_version"] == str(SCAN_ARTIFACT_SCHEMA_VERSION)


def test_version_endpoint_works_with_network_guard() -> None:
    """GET /version works even when BIST_CORE_ALLOW_NETWORK is set (read-only, no guard)."""
    import os
    from unittest.mock import patch

    with patch.dict(os.environ, {"BIST_CORE_ALLOW_NETWORK": "1"}):
        c = TestClient(app)
        r = c.get("/version")
    assert r.status_code == 200
    assert "api_version" in r.json()
