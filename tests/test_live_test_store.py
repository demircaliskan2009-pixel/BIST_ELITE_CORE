from pathlib import Path

from bist_core.live_test.store import (
    append_recommendation,
    close_recommendation,
    compute_stats,
    list_recommendations,
    load_recommendations,
)


def test_live_test_store_roundtrip(tmp_path: Path) -> None:
    rec = append_recommendation(
        root=tmp_path,
        source="gateway_chat",
        symbol="akbnk",
        day="2026-02-27",
        decision="watch",
        timeframe="short",
        score=1.0,
        entry=91.05,
        stop=88.35,
        target=92.85,
        rationale="Momentum pozitif",
        invalidation="Ters haber",
        metadata={"request_id": "abc123"},
    )

    loaded = load_recommendations(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].symbol == "AKBNK"
    assert loaded[0].decision == "WATCH"
    assert loaded[0].status == "open"

    closed = close_recommendation(
        root=tmp_path,
        recommendation_id=rec.recommendation_id,
        outcome_label="win",
        realized_return_r=1.2,
        realized_return_pct=3.1,
        outcome_note="t1 hit",
    )
    assert closed.status == "closed"
    assert closed.outcome_label == "win"

    stats = compute_stats(tmp_path)
    assert stats["total_recommendations"] == 1
    assert stats["closed_count"] == 1
    assert stats["open_count"] == 0
    assert stats["outcome_counts"]["win"] == 1
    assert stats["avg_realized_r"] == 1.2

    items = list_recommendations(root=tmp_path, status="closed", symbol="AKBNK", limit=10)
    assert len(items) == 1
