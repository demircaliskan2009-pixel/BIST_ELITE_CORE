"""FAZ99: Env contract validator + secrets redaction; execution_result errors[] have code."""

from __future__ import annotations

import json
import os
from pathlib import Path


from bist_core.env import redact_env, redact_secrets, validate_env_contract
from bist_core.execution.result_writer import build_execution_result_payload, write_execution_result
from bist_core.security.env_contract import validate_bist_env_whitelist
from bist_core.security.redact import REDACT_PLACEHOLDER, redact_recursive


def test_faz99_validate_env_contract_missing() -> None:
    """validate_env_contract: missing required var -> errors with code."""
    required = ["BIST_FAZ99_NEVER_SET_REQUIRED"]
    ok, errors = validate_env_contract(required)
    assert ok is False
    assert len(errors) >= 1
    assert errors[0].get("code") == "env_missing_BIST_FAZ99_NEVER_SET_REQUIRED"
    assert "message" in errors[0]


def test_faz99_validate_env_contract_present() -> None:
    """validate_env_contract: all required set -> ok, no errors."""
    os.environ["BIST_FAZ99_TEST_VAR"] = "value"
    try:
        ok, errors = validate_env_contract(["BIST_FAZ99_TEST_VAR"])
        assert ok is True
        assert errors == []
    finally:
        os.environ.pop("BIST_FAZ99_TEST_VAR", None)


def test_faz99_redact_secrets() -> None:
    """redact_secrets: secret-like keys get value ***."""
    payload = {"api_key": "sk-123", "name": "alice", "password": "secret"}
    out = redact_secrets(payload)
    assert out.get("api_key") == "***"
    assert out.get("password") == "***"
    assert out.get("name") == "alice"


def test_faz99_redact_env() -> None:
    """redact_env: env with secret-like key gets value ***."""
    env = {"BIST_API_KEY": "sk-xyz", "BIST_DATA_DIR": "/data", "PATH": "/usr/bin"}
    out = redact_env(env)
    assert out.get("BIST_API_KEY") == "***"
    assert out.get("BIST_DATA_DIR") == "/data"
    assert out.get("PATH") == "/usr/bin"


def test_faz99_execution_result_errors_have_code() -> None:
    """execution_result errors[] entries have code."""
    payload = build_execution_result_payload(
        day="2025-01-01",
        ok=False,
        blocked=True,
        reason="test",
        provider="paper",
        mode="live",
        errors=["no_manifest", "invalid_orders_intent"],
    )
    errs = payload.get("errors", [])
    assert len(errs) == 2
    for e in errs:
        assert "code" in e
        assert isinstance(e["code"], str)
    codes = [e["code"] for e in errs]
    assert "no_manifest" in codes
    assert "invalid_orders_intent" in codes


def test_faz99_execution_result_errors_dict_normalized() -> None:
    """execution_result errors as dicts get code field."""
    payload = build_execution_result_payload(
        day="2025-01-02",
        ok=False,
        blocked=True,
        reason="gate",
        provider="paper",
        mode="live",
        errors=[{"error_marker": "blocked", "detail": "risk"}, "no_orders_intent"],
    )
    errs = payload.get("errors", [])
    assert len(errs) == 2
    for e in errs:
        assert "code" in e
    codes = [e["code"] for e in errs]
    assert "blocked" in codes or "no_orders_intent" in codes


def test_faz99_env_contract_violation() -> None:
    """BIST_* key not on whitelist -> validate_bist_env_whitelist returns env_contract_violation."""
    os.environ["BIST_FAZ99_FORBIDDEN_KEY"] = "value"
    try:
        ok, errors = validate_bist_env_whitelist()
        assert ok is False
        assert len(errors) >= 1
        codes = [e.get("code") for e in errors]
        assert "env_contract_violation" in codes
    finally:
        os.environ.pop("BIST_FAZ99_FORBIDDEN_KEY", None)


def test_faz99_redact_recursive_nested() -> None:
    """redact_recursive: nested dict/list with secret-like keys -> value ***REDACTED***."""
    payload = {"nested": {"api_key": "sk-123", "name": "x"}, "password": "secret", "list": [{"token": "t"}]}
    out = redact_recursive(payload)
    assert out["nested"]["api_key"] == REDACT_PLACEHOLDER
    assert out["nested"]["name"] == "x"
    assert out["password"] == REDACT_PLACEHOLDER
    assert out["list"][0]["token"] == REDACT_PLACEHOLDER


def test_faz99_execution_result_redacted_on_disk(tmp_path: Path) -> None:
    """write_execution_result redacts payload; secret-like keys not written raw."""
    payload = build_execution_result_payload(
        day="2025-01-01",
        ok=False,
        blocked=True,
        reason="test",
        provider="paper",
        mode="live",
        errors=[{"code": "x", "api_key": "sk-leak"}],
    )
    day = "2025-01-01"
    write_execution_result(
        tmp_path,
        day,
        ok=payload["ok"],
        blocked=payload["blocked"],
        reason=payload["reason"],
        provider=payload["provider"],
        mode=payload["mode"],
        errors=[{"code": "x", "api_key": "sk-leak"}],
        execution="live",
    )
    out_file = tmp_path / day / "execution_result.json"
    data = json.loads(out_file.read_text(encoding="utf-8"))
    errs = data.get("errors", [])
    assert len(errs) >= 1
    for e in errs:
        if e.get("code") == "x":
            assert e.get("api_key") == REDACT_PLACEHOLDER
            break
