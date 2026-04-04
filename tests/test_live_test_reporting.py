import json
from pathlib import Path

from bist_core.live_test.reporting import build_report, export_records_csv, write_report_json
from bist_core.live_test.store import append_recommendation, close_recommendation


def test_live_test_reporting_roundtrip(tmp_path: Path) -> None:
    rec_trade = append_recommendation(
        root=tmp_path,
        source="gateway_chat",
        symbol="AKBNK",
        day="2026-02-27",
        decision="WATCH",
        entry=91.05,
        stop=88.35,
        target=92.85,
        metadata={"message": "AKBNK için kısa vade senaryo üret"},
    )
    close_recommendation(
        root=tmp_path,
        recommendation_id=rec_trade.recommendation_id,
        outcome_label="win",
        realized_return_r=1.0,
        realized_return_pct=2.5,
        outcome_note="t1 hit",
    )

    rec_scan = append_recommendation(
        root=tmp_path,
        source="gateway_chat",
        symbol="AKFIS",
        day="2026-02-27",
        decision="SCAN_CANDIDATE",
        metadata={"message": "scan top 3", "top_n": 3},
    )
    close_recommendation(
        root=tmp_path,
        recommendation_id=rec_scan.recommendation_id,
        outcome_label="skipped",
        outcome_note="missing_trade_plan(entry/stop/target)",
    )

    report = build_report(tmp_path)
    assert report["total_recommendations"] == 2
    assert report["closed_count"] == 2
    assert report["open_count"] == 0
    assert report["outcome_counts"]["win"] == 1
    assert report["outcome_counts"]["skipped"] == 1

    symbols = {x["symbol"]: x for x in report["symbols"]}
    assert symbols["AKBNK"]["outcome_counts"]["win"] == 1
    assert symbols["AKFIS"]["outcome_counts"]["skipped"] == 1

    json_out = tmp_path / "report.json"
    write_report_json(report, json_out)
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["closed_count"] == 2

    csv_out = tmp_path / "report.csv"
    export_records_csv(root=tmp_path, out_path=csv_out)
    csv_text = csv_out.read_text(encoding="utf-8-sig")
    assert "recommendation_id" in csv_text
    assert "AKBNK" in csv_text
    assert "AKBNK için kısa vade senaryo üret" in csv_text
