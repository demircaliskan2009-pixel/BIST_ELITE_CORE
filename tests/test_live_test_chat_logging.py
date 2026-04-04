from pathlib import Path

from bist_core.live_test.chat_logging import log_from_chat_payload
from bist_core.live_test.store import compute_stats, list_recommendations


def test_log_from_chat_payload_ask(tmp_path: Path) -> None:
    response = {
        "mode": "ask",
        "answer": "Symbol: AKBNK",
        "payload": {
            "symbol": "AKBNK",
            "day": "2026-02-27",
            "decision_raw": "WATCH",
            "score": 1.0,
            "text": "AKBNK için karar WATCH; skor 1.00. Plan: entry 91.05, stop 88.35, t1 92.85.",
        },
    }

    records = log_from_chat_payload(
        root=tmp_path,
        response_json=response,
        source="gateway_chat",
        timeframe="short",
        request_meta={"request_id": "req_1"},
    )

    assert len(records) == 1
    rec = records[0]
    assert rec.symbol == "AKBNK"
    assert rec.day == "2026-02-27"
    assert rec.decision == "WATCH"
    assert rec.entry == 91.05
    assert rec.stop == 88.35
    assert rec.target == 92.85
    assert rec.metadata["mode"] == "ask"
    assert rec.metadata["request_id"] == "req_1"


def test_log_from_chat_payload_scan(tmp_path: Path) -> None:
    response = {
        "mode": "scan",
        "payload": {
            "day": "2026-02-27",
            "ranked": [
                {"symbol": "AKFIS", "score": 1.5, "rationale": "Momentum pozitif"},
                {"symbol": "AKSUE", "score": 1.5, "rationale": "Momentum pozitif"},
                {"symbol": "ALTNY", "score": 1.5, "rationale": "Momentum pozitif"},
            ],
        },
    }

    records = log_from_chat_payload(
        root=tmp_path,
        response_json=response,
        source="gateway_chat",
        timeframe="short",
        request_meta={"request_id": "req_2"},
    )

    assert len(records) == 3
    assert {x.symbol for x in records} == {"AKFIS", "AKSUE", "ALTNY"}
    assert all(x.decision == "SCAN_CANDIDATE" for x in records)

    stats = compute_stats(tmp_path)
    assert stats["total_recommendations"] == 3
    assert stats["open_count"] == 3

    listed = list_recommendations(root=tmp_path, limit=10)
    assert len(listed) == 3
