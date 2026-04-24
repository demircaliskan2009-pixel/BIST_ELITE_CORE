from __future__ import annotations

import os
import shlex
import time
from collections import deque
from typing import Any, Deque, Dict, Optional, Sequence

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

API_KEY_ENV = "BIST_GATEWAY_API_KEY"
RATE_LIMIT_ENV = "BIST_GATEWAY_RPM"
API_KEY_HEADER = "X-API-Key"
DEFAULT_RPM = 60

# ---- helpers ----

def _expected_api_key() -> str:
    return os.getenv(API_KEY_ENV, "").strip()

def _bearer_from_auth(auth: Optional[str]) -> Optional[str]:
    if not auth:
        return None
    a = auth.strip()
    if a.lower().startswith("bearer "):
        return a.split(None, 1)[1].strip()
    return None

def _client_id(request: Request) -> str:
    xf = request.headers.get("x-forwarded-for")
    if xf:
        return xf.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"

_BAD_TOKENS = {";", "&&", "||", "|", "\n", "\r"}

def _extract_tokens(payload: Any) -> Optional[list[str]]:
    if payload is None:
        return None
    if isinstance(payload, dict):
        for k in ("argv", "args"):
            v = payload.get(k)
            if isinstance(v, list) and all(isinstance(x, str) for x in v):
                return [x for x in v if x is not None]
        for k in ("cmd", "command", "text"):
            v = payload.get(k)
            if isinstance(v, str) and v.strip():
                try:
                    return shlex.split(v)
                except Exception:
                    return v.strip().split()
    if isinstance(payload, list) and all(isinstance(x, str) for x in payload):
        return payload
    if isinstance(payload, str) and payload.strip():
        try:
            return shlex.split(payload)
        except Exception:
            return payload.strip().split()
    return None

def _first_subcommand(tokens: Sequence[str]) -> Optional[str]:
    if not tokens:
        return None
    toks = [t for t in tokens if isinstance(t, str)]
    if not toks:
        return None
    for t in toks:
        if t in _BAD_TOKENS or any(sep in t for sep in ("&&", "||", ";", "|", "\n", "\r")):
            return None

    i = 0

    if i < len(toks) and toks[i].lower() in ("python", "python3", "py"):
        if i + 2 < len(toks) and toks[i + 1] == "-m":
            i += 3
        else:
            i += 1

    if i < len(toks) and toks[i].endswith(".py"):
        i += 1

    if i < len(toks) and toks[i] in ("bist", "bist-core", "bist_core"):
        i += 1

    while i < len(toks) and toks[i].startswith("-"):
        i += 1

    if i >= len(toks):
        return None
    return toks[i]

def cli_payload_allowlisted(payload: Any) -> bool:
    tokens = _extract_tokens(payload) or []
    return _first_subcommand(tokens) == "data"

# ---- rate limiter ----

class _SlidingWindowRPM:
    def __init__(self, rpm: int) -> None:
        self.rpm = max(1, int(rpm))
        self.window_sec = 60.0
        self._hits: Dict[str, Deque[float]] = {}

    def allow(self, key: str, now: float) -> bool:
        q = self._hits.get(key)
        if q is None:
            q = deque()
            self._hits[key] = q
        cutoff = now - self.window_sec
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= self.rpm:
            return False
        q.append(now)
        return True

def _rpm_from_env() -> int:
    v = os.getenv(RATE_LIMIT_ENV, "").strip()
    if not v:
        return DEFAULT_RPM
    try:
        n = int(v)
        return max(1, n)
    except Exception:
        return DEFAULT_RPM

_RL = _SlidingWindowRPM(_rpm_from_env())

# ---- middleware ----

class GatewaySecurityMiddleware(BaseHTTPMiddleware):
    """
    Fail-closed security for gateway endpoints.

    - Protects all /v1/* endpoints with API key (X-API-Key or Authorization: Bearer)
    - Per-client rate limit (RPM) with in-memory sliding window
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if not path.startswith("/v1/"):
            return await call_next(request)

        expected = _expected_api_key()
        if not expected:
            return JSONResponse({"detail": "API key not configured (fail-closed)"}, status_code=503)

        provided = request.headers.get(API_KEY_HEADER)
        if not provided:
            provided = _bearer_from_auth(request.headers.get("authorization"))
        if not provided or provided != expected:
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)

        cid = _client_id(request)
        now = time.monotonic()
        if not _RL.allow(cid, now):
            return JSONResponse({"detail": "Too Many Requests"}, status_code=429)

        return await call_next(request)

# ---- OpenAPI security (contract) ----

def customize_openapi(app: FastAPI) -> dict:
    if getattr(app, "openapi_schema", None):
        return app.openapi_schema  # type: ignore[attr-defined]

    schema = get_openapi(
        title=app.title,
        version=getattr(app, "version", "0.0.0"),
        description=getattr(app, "description", None),
        routes=app.routes,
    )

    components = schema.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes["ApiKeyAuth"] = {"type": "apiKey", "in": "header", "name": API_KEY_HEADER}

    paths = schema.get("paths", {}) or {}
    for p, ops in paths.items():
        if not isinstance(p, str) or not p.startswith("/v1/"):
            continue
        if not isinstance(ops, dict):
            continue
        for _m, op in ops.items():
            if not isinstance(op, dict):
                continue
            op.setdefault("security", [{"ApiKeyAuth": []}])
            responses = op.setdefault("responses", {})
            if isinstance(responses, dict):
                responses.setdefault("401", {"description": "Unauthorized"})
                responses.setdefault("429", {"description": "Too Many Requests"})
                responses.setdefault("503", {"description": "Service Unavailable"})

    app.openapi_schema = schema  # type: ignore[attr-defined]
    return schema
