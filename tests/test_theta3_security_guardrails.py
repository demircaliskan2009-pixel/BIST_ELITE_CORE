"""Theta3: Security Guardrails Runner — network default off, data validation, CLI sandboxing.

Enforces:
- No unintended network usage (network_allowed default False)
- Data validation layers reject invalid input
- CLI commands run sandboxed (no network when BIST_CORE_ALLOW_NETWORK unset)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bist_core.env import network_allowed, NETWORK_ALLOW_ENV


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_cli(args: list[str], env: dict | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    e["PYTHONPATH"] = str(_project_root() / "src")
    if env is not None:
        e.update(env)
    return subprocess.run(
        [sys.executable, "-m", "bist_core.cli", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=e,
        cwd=str(cwd or _project_root()),
        timeout=30,
    )


# ---- Network default off ----
def test_theta3_network_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """network_allowed() returns False when BIST_CORE_ALLOW_NETWORK unset or 0/false/no."""
    monkeypatch.delenv(NETWORK_ALLOW_ENV, raising=False)
    assert network_allowed() is False

    for val in ("0", "false", "False", "no", "NO", ""):
        monkeypatch.setenv(NETWORK_ALLOW_ENV, val)
        assert network_allowed() is False, f"Expected False for {val!r}"


def test_theta3_network_allowed_only_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    """network_allowed() returns True only for 1/true/yes (case-insensitive)."""
    for val in ("1", "true", "True", "yes", "YES"):
        monkeypatch.setenv(NETWORK_ALLOW_ENV, val)
        assert network_allowed() is True, f"Expected True for {val!r}"


# ---- CLI sandbox: no network required ----
def test_theta3_cli_healthcheck_no_network(tmp_path: Path) -> None:
    """healthcheck runs successfully with BIST_CORE_ALLOW_NETWORK unset."""
    env = {"BIST_CORE_SNAPSHOT_DIR": str(tmp_path)}
    env.pop("BIST_CORE_ALLOW_NETWORK", None)
    result = _run_cli(["healthcheck"], env=env)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "checks" in data
    assert "ok" in data


def test_theta3_cli_info_no_network(tmp_path: Path) -> None:
    """info --json runs successfully with network off."""
    reg = tmp_path / "registry.json"
    reg.write_text("{}", encoding="utf-8")
    env = {"BIST_CORE_REGISTRY_PATH": str(reg)}
    env.pop("BIST_CORE_ALLOW_NETWORK", None)
    result = _run_cli(["info", "--json"], env=env)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "registry_path" in data
    assert "datasets" in data


# ---- CLI network-guarded commands fail when network off ----
def test_theta3_cli_events_pull_kap_no_network_guard(tmp_path: Path) -> None:
    """events pull with kap_html and empty cache: provider raises, no network call; manifest records error."""
    env = {
        "BIST_KAP_CACHE_DIR": str(tmp_path),
        "BIST_CORE_ALLOW_NETWORK": "0",  # Explicitly disable to override inherited env
    }
    _run_cli(
        [
            "events",
            "pull",
            "--day",
            "2024-01-01",
            "--provider",
            "kap_html",
            "--input",
            str(tmp_path),
            "--outdir",
            str(tmp_path),
        ],
        env=env,
    )
    # Pipeline catches provider exception; manifest records ProviderError (no network used)
    manifest_path = tmp_path / "_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = manifest.get("errors", []) or manifest.get("error_list", [])
    error_markers = [e.get("error_marker", "") for e in errors]
    assert any("ProviderError" in m or "RuntimeError" in m or "KAP" in m for m in error_markers), (
        f"Expected ProviderError in manifest when network off and cache empty; got {error_markers}"
    )


# ---- Data validation layers ----
def test_theta3_rules_validate_rejects_malformed_json(tmp_path: Path) -> None:
    """rules validate rejects malformed JSON file with RulesetLoadError."""
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{ invalid json }", encoding="utf-8")
    result = _run_cli(["rules", "validate", "--file", str(bad_path)])
    assert result.returncode == 2
    data = json.loads(result.stdout)
    assert data["valid"] is False
    assert "RulesetLoadError" in data.get("errors", [])


def test_theta3_rules_validate_rejects_missing_file(tmp_path: Path) -> None:
    """rules validate rejects non-existent file."""
    missing = tmp_path / "nonexistent.json"
    assert not missing.exists()
    result = _run_cli(["rules", "validate", "--file", str(missing)])
    assert result.returncode == 2
    data = json.loads(result.stdout)
    assert data["valid"] is False


# ---- Regression: existing network guards still work ----
def test_theta3_regression_faz109_vendor_api_network_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """VendorAPIProvider raises NETWORK_DISABLED when network off (faz109 regression)."""
    monkeypatch.delenv("BIST_CORE_ALLOW_NETWORK", raising=False)
    from unittest.mock import MagicMock
    from bist_core.providers.vendor_api import VendorAPIConfig, VendorAPIProvider

    provider = VendorAPIProvider(
        cfg=VendorAPIConfig(eod_endpoint="http://fake", kap_endpoint=None, api_key=None),
        session=MagicMock(),
    )
    with pytest.raises(RuntimeError, match="NETWORK_DISABLED"):
        provider.symbols("2099-01-01")


def test_theta3_regression_api_503_when_network_allowed() -> None:
    """API returns 503 when BIST_CORE_ALLOW_NETWORK is set (faz189 regression)."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from bist_core.api.app import app

    with patch.dict(os.environ, {"BIST_CORE_ALLOW_NETWORK": "1"}):
        client = TestClient(app)
        r = client.post("/ask", json={"symbol": "THYAO", "day": "2024-01-15"})
        assert r.status_code == 503
        r2 = client.post("/scan", json={"day": "2024-01-15"})
        assert r2.status_code == 503
