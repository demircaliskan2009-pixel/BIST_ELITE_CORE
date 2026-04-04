from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"
AUDIT_LOG_ENV = "BIST_GATEWAY_AUDIT_LOG"
DEFAULT_AUDIT_LOG = ".bist_gateway_audit.log"

_LOCK = threading.Lock()

def _client_ip(request: Request) -> str:
    xf = request.headers.get("x-forwarded-for")
    if xf:
        return xf.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"

def _request_id_from(request: Request) -> str:
    rid = request.headers.get(REQUEST_ID_HEADER)
    if rid and rid.strip():
        return rid.strip()
    return uuid.uuid4().hex

def _audit_log_path() -> Path:
    p = os.getenv(AUDIT_LOG_ENV, "").strip()
    if not p:
        return Path(DEFAULT_AUDIT_LOG)
    return Path(p).expanduser()

def _safe_get_request_id(request: Request) -> Optional[str]:
    try:
        rid = getattr(request.state, "request_id", None)
        if rid:
            return str(rid)
    except Exception:
        pass
    rid = request.headers.get(REQUEST_ID_HEADER)
    return rid.strip() if rid and rid.strip() else None

def _append_jsonl(path: Path, record: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        with _LOCK:
            with path.open("a", encoding="utf-8", newline="\n") as f:
                f.write(line)
    except Exception:
        # fail-open: do not block gateway if audit sink fails
        return

class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        rid = _request_id_from(request)
        try:
            request.state.request_id = rid
        except Exception:
            pass

        response = await call_next(request)
        response.headers.setdefault(REQUEST_ID_HEADER, rid)
        return response

class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        dur_ms = int((time.monotonic() - start) * 1000)

        rid = _safe_get_request_id(request)

        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "request_id": rid,
            "client_ip": _client_ip(request),
            "method": request.method,
            "path": request.url.path,
            "status_code": getattr(response, "status_code", None),
            "duration_ms": dur_ms,
        }
        _append_jsonl(_audit_log_path(), rec)
        return response
