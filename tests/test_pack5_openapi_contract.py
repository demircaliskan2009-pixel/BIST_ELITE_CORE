from __future__ import annotations

import json
from pathlib import Path
import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_openapi_contract_exists_and_has_core_paths() -> None:
    p = _repo_root() / "configs" / "openapi.json"
    assert p.is_file()

    spec = json.loads(p.read_text(encoding="utf-8"))
    assert str(spec.get("openapi", "")).startswith("3.")
    assert spec["info"]["title"] == "BIST_ELITE_CORE Gateway"

    paths = spec["paths"]
    assert "/health" in paths and "get" in paths["/health"]
    assert "/v1/cli" in paths and "post" in paths["/v1/cli"]

    post = paths["/v1/cli"]["post"]
    rb = post["requestBody"]["content"]["application/json"]["schema"]
    assert rb["$ref"] == "#/components/schemas/CliRequest"

    resp = post["responses"]["200"]["content"]["application/json"]["schema"]
    assert resp["$ref"] == "#/components/schemas/CliResponse"

    schemas = spec["components"]["schemas"]
    assert "CliRequest" in schemas and "CliResponse" in schemas and "HealthResponse" in schemas
    assert "args" in schemas["CliRequest"]["properties"]


def test_gateway_app_openapi_includes_contract_paths_if_fastapi_installed() -> None:
    # Optional: only runs if fastapi+pydantic are installed in the env.
    try:
        from bist_core.gateway.app import app  # type: ignore
    except Exception:
        pytest.skip("fastapi not installed; contract-only test executed")

    gen = app.openapi()
    assert "/health" in gen.get("paths", {})
    assert "/v1/cli" in gen.get("paths", {})
    assert "get" in gen["paths"]["/health"]
    assert "post" in gen["paths"]["/v1/cli"]
