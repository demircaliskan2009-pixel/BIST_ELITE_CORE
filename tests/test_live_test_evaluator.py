from pathlib import Path

from bist_core.live_test.evaluator import evaluate_open_recommendations
from bist_core.live_test.store import append_recommendation, list_recommendations


def _write_snapshot_day(root: Path, day: str, rows: list[dict[str, object]]) -> None:
    day_dir = root / day
    day_dir.mkdir(parents=True, exist_ok=True)

    header = "date,symbol,open,high,low,close,volume,turnover_tl"
    lines = [header]
    for row in rows:
        lines.append(
            ",".join(
                [
                    day,
                    str(row["symbol"]),
                    str(row["open"]),
                    str(row["high"]),
                    str(row["low"]),
                    str(row["close"]),
                    "1000",
                    "100000",
                ]
            )
        )
    (day_dir / "snapshot.csv").write_text("\n".join(lines), encoding="utf-8")


def test_evaluate_open_recommendations_win_and_skipped(tmp_path: Path) -> None:
    live_root = tmp_path / "live_test"
    snap_root = tmp_path / "snapshots"

    _write_snapshot_day(
        snap_root,
        "2026-02-27",
        [
            {"symbol": "AKBNK", "open": 100, "high": 102, "low": 99, "close": 101},
            {"symbol": "AKFIS", "open": 50, "high": 51, "low": 49, "close": 50.5},
        ],
    )
    _write_snapshot_day(
        snap_root,
        "2026-03-02",
        [
            {"symbol": "AKBNK", "open": 103, "high": 111, "low": 103, "close": 110},
            {"symbol": "AKFIS", "open": 50, "high": 50.5, "low": 49.5, "close": 50},
        ],
    )

    rec_trade = append_recommendation(
        root=live_root,
        source="gateway_chat",
        symbol="AKBNK",
        day="2026-02-27",
        decision="WATCH",
        entry=100.0,
        stop=95.0,
        target=110.0,
        rationale="trade candidate",
    )
    rec_scan = append_recommendation(
        root=live_root,
        source="gateway_chat",
        symbol="AKFIS",
        day="2026-02-27",
        decision="SCAN_CANDIDATE",
        rationale="scan candidate",
    )

    summary = evaluate_open_recommendations(
        root=live_root,
        snapshot_root=snap_root,
        max_holding_days=5,
    )

    assert summary["closed_count"] == 2
    assert summary["outcome_counts"]["win"] == 1
    assert summary["outcome_counts"]["skipped"] == 1

    items = {x.recommendation_id: x for x in list_recommendations(root=live_root, limit=10)}
    assert items[rec_trade.recommendation_id].status == "closed"
    assert items[rec_trade.recommendation_id].outcome_label == "win"
    assert items[rec_scan.recommendation_id].status == "closed"
    assert items[rec_scan.recommendation_id].outcome_label == "skipped"
