from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


from bist_core.gateway.security import GatewaySecurityMiddleware, customize_openapi, cli_payload_allowlisted
from bist_core.gateway.audit import AuditLogMiddleware, RequestIdMiddleware
def _repo_root() -> Path:
    # .../src/bist_core/gateway/app.py -> parents[3] == repo root
    return Path(__file__).resolve().parents[3]


def _with_src_on_pythonpath(env: dict[str, str]) -> dict[str, str]:
    repo = _repo_root()
    src = str(repo / "src")
    cur = env.get("PYTHONPATH", "")
    if cur:
        env["PYTHONPATH"] = src + os.pathsep + cur
    else:
        env["PYTHONPATH"] = src
    return env


app = FastAPI(title="BIST_ELITE_CORE Gateway", version="0.1.0")
# PACK6: fail-closed API-key auth + rate-limit (non-invasive)
app.add_middleware(GatewaySecurityMiddleware)
app.openapi = (lambda _app=app: customize_openapi(_app))
# PACK7: audit-log + request-id
app.add_middleware(AuditLogMiddleware)
app.add_middleware(RequestIdMiddleware)



@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "bist_core_gateway", "version": "0.1.0"}


class CliRequest(BaseModel):
    args: List[str] = Field(..., description="Arguments after 'bist_core.cli' module. Example: ['data','snapshots','doctor','--json']")
    timeout_s: int = Field(30, ge=1, le=120)


@app.post("/v1/cli")
def run_cli(req: CliRequest) -> dict[str, Any]:
    # SECURITY NOTE (pack6): endpoint will be protected by API-key + rate limit.
    if not req.args:
        raise HTTPException(status_code=400, detail="args required")

    # Fail-closed allowlist for now: only "data" subtree.
    if req.args[0] != "data":
        raise HTTPException(status_code=403, detail="only 'data' commands allowed (pack4 skeleton)")

    env = _with_src_on_pythonpath(os.environ.copy())

    cp = subprocess.run(
        [sys.executable, "-m", "bist_core.cli", *req.args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=int(req.timeout_s),
    )
    return {
        "returncode": cp.returncode,
        "stdout": cp.stdout,
        "stderr": cp.stderr,
    }
