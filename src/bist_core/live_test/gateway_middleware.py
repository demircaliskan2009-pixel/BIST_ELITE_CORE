from __future__ import annotations

import json
import os
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .chat_logging import log_from_chat_payload


class LiveTestChatLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)

    @staticmethod
    def _enabled() -> bool:
        return str(os.getenv("BIST_LIVE_TEST_AUTOLOG", "0")).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _root() -> str:
        return str(os.getenv("BIST_LIVE_TEST_ROOT", "data/live_test")).strip()

    @staticmethod
    def _safe_json_body(raw_body: bytes) -> dict[str, Any]:
        if not raw_body:
            return {}
        try:
            obj = json.loads(raw_body.decode("utf-8-sig"))
        except Exception:
            return {}
        return obj if isinstance(obj, dict) else {}

    @staticmethod
    def _extract_request_meta(request: Request, response: Response, request_payload: dict[str, Any]) -> dict[str, Any]:
        meta: dict[str, Any] = {}

        req_id = (
            response.headers.get("x-request-id")
            or response.headers.get("X-Request-Id")
            or getattr(getattr(request, "state", object()), "request_id", None)
        )
        if req_id:
            meta["request_id"] = str(req_id)

        for key in ("message", "top_n", "day", "horizon", "risk", "capital", "max_loss_tl", "exclusions"):
            value = request_payload.get(key)
            if value is not None and value != "":
                meta[key] = value

        client = getattr(request, "client", None)
        host = getattr(client, "host", None) if client is not None else None
        if host:
            meta["client_host"] = str(host)

        return meta

    async def dispatch(self, request: Request, call_next):
        raw_request_body = await request.body()

        async def _replay_receive() -> dict[str, Any]:
            return {"type": "http.request", "body": raw_request_body, "more_body": False}

        request._receive = _replay_receive  # type: ignore[attr-defined]

        response = await call_next(request)

        if request.method.upper() != "POST" or request.url.path != "/v1/chat":
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        headers = dict(response.headers)

        try:
            if not self._enabled():
                headers["X-Live-Test-Logged"] = "disabled"
                return Response(
                    content=body,
                    status_code=response.status_code,
                    headers=headers,
                    media_type=response.media_type,
                )

            if response.status_code != 200:
                headers["X-Live-Test-Logged"] = "0"
                headers["X-Live-Test-Log-Error"] = "non_200_response"
                return Response(
                    content=body,
                    status_code=response.status_code,
                    headers=headers,
                    media_type=response.media_type,
                )

            response_json: dict[str, Any] = json.loads(body.decode("utf-8-sig"))
            request_payload = self._safe_json_body(raw_request_body)
            request_meta = self._extract_request_meta(request, response, request_payload)

            records = log_from_chat_payload(
                root=self._root(),
                response_json=response_json,
                source="gateway_chat",
                timeframe=None,
                request_meta=request_meta,
            )

            headers["X-Live-Test-Logged"] = str(len(records))
            return Response(
                content=body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type,
            )

        except Exception as exc:
            headers["X-Live-Test-Logged"] = "0"
            headers["X-Live-Test-Log-Error"] = exc.__class__.__name__
            return Response(
                content=body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type,
            )
