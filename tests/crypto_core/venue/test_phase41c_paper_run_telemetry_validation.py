from __future__ import annotations

from tests.crypto_core.venue.test_phase41b_paper_run_telemetry_report_artifact import (
    _report,
    _run_artifact,
    _telemetry_rejection_reasons,
)


def test_phase41c_report_references_exact_phase40_run_artifact() -> None:
    run = _run_artifact()
    report = _report()

    assert report["source_phase40_artifact"] == "docs/crypto_core/DERIBIT_BOUNDED_OPERATOR_PAPER_RUN_ARTIFACT_40B.json"
    assert report["audited_run_id"] == run["run_id"]
    assert report["operator_id"] == run["operator_id"]
    assert "source_artifact_hash_matches" in report["telemetry_checks"]


def test_phase41c_ledger_and_position_telemetry_comes_from_final_run_summary() -> None:
    run = _run_artifact()
    report = _report()
    after = run["after_ledger_summary"]

    assert report["final_ledger_summary"] == after
    assert report["final_position_summary"] == {
        "symbol": after["symbol"],
        "canonical_symbol": after["canonical_symbol"],
        "position_qty": after["position_qty"],
        "average_entry_price": after["average_entry_price"],
        "realized_pnl": after["realized_pnl"],
    }
    assert _telemetry_rejection_reasons(run, report) == ()


def test_phase41c_policy_markers_are_explicit_not_faked() -> None:
    report = _report()

    assert report["realized_pnl_policy"] == "REALIZED_PNL_ON_CLOSE_ONLY"
    assert report["fees_policy"] == "NOT_IMPLEMENTED"
    assert report["slippage_policy"] == "NOT_IMPLEMENTED"
    assert report["funding_policy"] == "NOT_IMPLEMENTED"


def test_phase41c_telemetry_counters_match_report_top_level_counts() -> None:
    report = _report()
    counters = report["telemetry_counters"]

    assert counters["accepted_run_count"] == 1
    assert counters["rejected_run_count"] == 0
    assert counters["attempted_trade_count"] == report["trades_attempted"] == 1
    assert counters["filled_trade_count"] == report["trades_filled"] == 1
    assert counters["no_fill_count"] == report["no_fill_count"] == 0
    assert counters["ledger_mutation_count"] == report["ledger_mutation_count"] == 1
    assert counters["duplicate_mutation_blocked_count"] == 1
