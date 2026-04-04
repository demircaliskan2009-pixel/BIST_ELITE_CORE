from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from bist_core.live_test.gateway_middleware import LiveTestChatLoggingMiddleware
from bist_core.live_test.store import list_recommendations


def test_gateway_middleware_preserves_turkish_utf8_message(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BIST_LIVE_TEST_AUTOLOG", "1")
    monkeypatch.setenv("BIST_LIVE_TEST_ROOT", str(tmp_path))

    app = FastAPI()
    app.add_middleware(LiveTestChatLoggingMiddleware)

    @app.post("/v1/chat")
    def chat():
        payload = {
            "mode": "ask",
            "answer": "Symbol: AKBNK",
            "payload": {
                "symbol": "AKBNK",
                "day": "2026-02-27",
                "decision_raw": "WATCH",
                "score": 1.0,
                "text": "AKBNK için karar WATCH; skor 1.00. Plan: entry 91.05, stop 88.35, t1 92.85."
            }
        }
        return Response(
            content=__import__("json").dumps(payload, ensure_ascii=False),
            media_type="application/json",
            headers={"x-request-id": "req_utf8_1"},
        )

    client = TestClient(app)
    resp = client.post("/v1/chat", json={"message": "AKBNK için kısa vade senaryo üret"})
    assert resp.status_code == 200
    assert resp.headers["x-live-test-logged"] == "1"

    items = list_recommendations(root=tmp_path, limit=10)
    assert len(items) == 1
    assert items[0].metadata["message"] == "AKBNK için kısa vade senaryo üret"
    assert items[0].metadata["request_id"] == "req_utf8_1"
