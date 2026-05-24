from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

RUN_ARTIFACT = Path("docs/crypto_core/DERIBIT_BOUNDED_OPERATOR_PAPER_RUN_ARTIFACT_40B.json")
REPORT = Path("docs/crypto_core/DERIBIT_BOUNDED_PAPER_RUN_TELEMETRY_REPORT_41B.json")

REPORT_TRUE_FLAGS = (
    "ledger_mutated",
    "duplicate_mutation_blocked",
    "no_private_api",
    "no_credentials",
    "no_exchange_orders",
    "no_execution_adapter",
    "no_order_routing",
    "no_strategy_signal",
    "no_scheduler",
    "no_automatic_paper_loop",
    "no_shadow",
    "no_live",
)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_artifact() -> dict[str, object]:
    return _json(RUN_ARTIFACT)


def _report() -> dict[str, object]:
    return _json(REPORT)


def _source_artifact_hash() -> str:
    return hashlib.sha256(RUN_ARTIFACT.read_bytes()).hexdigest()


def _mutated(mapping: dict[str, object], **updates: object) -> dict[str, object]:
    next_mapping = copy.deepcopy(mapping)
    next_mapping.update(updates)
    return next_mapping


def _telemetry_rejection_reasons(run: dict[str, object], report: dict[str, object]) -> tuple[str, ...]:
    reasons: list[str] = []
    if report.get("source_phase40_artifact") != str(RUN_ARTIFACT).replace("\\", "/"):
        reasons.append("telemetry:source_artifact_mismatch")
    if report.get("source_artifact_sha256") != _source_artifact_hash():
        reasons.append("telemetry:source_artifact_hash_mismatch")
    if not run.get("run_id"):
        reasons.append("telemetry:run_id_missing")
    if report.get("audited_run_id") != run.get("run_id"):
        reasons.append("telemetry:run_id_mismatch")
    if not run.get("operator_id"):
        reasons.append("telemetry:operator_id_missing")
    if report.get("operator_id") != run.get("operator_id"):
        reasons.append("telemetry:operator_id_mismatch")
    if run.get("accepted") is not True:
        reasons.append("telemetry:run_not_accepted")
    if run.get("simulation_only") is not True or report.get("simulation_only") is not True:
        reasons.append("telemetry:not_simulation_only")
    for field in ("live_enabled", "shadow_enabled", "auto_loop_enabled", "scheduler_enabled"):
        if run.get(field) is not False or report.get(field) is not False:
            reasons.append(f"telemetry:{field}_not_false")
    if run.get("max_trades") != 1 or report.get("max_trades") != 1:
        reasons.append("telemetry:max_trades_not_one")
    if report.get("trades_attempted") != run.get("trade_count_attempted") or report.get("trades_attempted") != 1:
        reasons.append("telemetry:trades_attempted_mismatch")
    if report.get("trades_filled") != run.get("fill_count") or report.get("trades_filled") != 1:
        reasons.append("telemetry:trades_filled_mismatch")
    if report.get("trades_rejected") != 0:
        reasons.append("telemetry:unexpected_trade_rejections")
    if report.get("no_fill_count") != 0:
        reasons.append("telemetry:unexpected_no_fill_count")
    if run.get("ledger_mutation_count") != 1 or report.get("ledger_mutated") is not True:
        reasons.append("telemetry:ledger_not_mutated_once")
    if report.get("duplicate_mutation_blocked") is not True:
        reasons.append("telemetry:duplicate_mutation_not_blocked")
    after = run.get("after_ledger_summary")
    final_ledger = report.get("final_ledger_summary")
    final_position = report.get("final_position_summary")
    if not isinstance(after, dict) or not isinstance(final_ledger, dict) or not isinstance(final_position, dict):
        reasons.append("telemetry:ledger_summary_missing")
    else:
        if final_ledger != after:
            reasons.append("telemetry:final_ledger_mismatch")
        if final_position.get("position_qty") != after.get("position_qty"):
            reasons.append("telemetry:final_position_qty_mismatch")
        if final_position.get("average_entry_price") != after.get("average_entry_price"):
            reasons.append("telemetry:final_average_entry_price_mismatch")
        if final_position.get("realized_pnl") != after.get("realized_pnl"):
            reasons.append("telemetry:final_realized_pnl_mismatch")
    safety = run.get("safety_invariants")
    if not isinstance(safety, dict):
        reasons.append("telemetry:safety_invariants_missing")
    else:
        for run_flag in (
            "no_private_api",
            "no_credentials",
            "no_exchange_orders",
            "no_execution_adapter",
            "no_order_routing",
            "no_strategy_signal",
            "no_scheduler",
            "no_automatic_paper_loop",
            "no_shadow",
            "no_live",
        ):
            if safety.get(run_flag) is not True:
                reasons.append(f"telemetry:{run_flag}_not_true")
    for report_flag in REPORT_TRUE_FLAGS:
        if report.get(report_flag) is not True:
            reasons.append(f"telemetry:{report_flag}_not_true")
    if report.get("connector_ready_dialects_count") != 1:
        reasons.append("telemetry:connector_ready_count_mismatch")
    if report.get("report_verdict") == "PASS" and reasons:
        reasons.append("telemetry:pass_verdict_with_rejections")
    return tuple(dict.fromkeys(reasons))


def test_phase41b_report_artifact_has_required_schema_and_source_reference() -> None:
    report = _report()

    assert RUN_ARTIFACT.exists()
    assert REPORT.exists()
    assert report["schema_version"] == "deribit_bounded_paper_run_telemetry_report.v1"
    assert report["phase"] == "41"
    assert report["source"] == "deterministic_phase40_bounded_run_artifact_telemetry"
    assert report["source_phase40_artifact"] == str(RUN_ARTIFACT).replace("\\", "/")
    assert report["source_artifact_sha256"] == _source_artifact_hash()


def test_phase41b_report_matches_phase40_run_identity_and_counts() -> None:
    run = _run_artifact()
    report = _report()

    assert report["audited_run_id"] == run["run_id"]
    assert report["operator_id"] == run["operator_id"]
    assert report["simulation_only"] is run["simulation_only"] is True
    assert report["max_trades"] == run["max_trades"] == 1
    assert report["trades_attempted"] == run["trade_count_attempted"] == 1
    assert report["trades_filled"] == run["fill_count"] == 1
    assert report["trades_rejected"] == 0
    assert report["no_fill_count"] == 0
    assert report["ledger_mutated"] is True


def test_phase41b_report_records_current_readiness_state() -> None:
    report = _report()
    readiness = evaluate_deribit_manual_review_readiness()

    assert report["connector_ready_dialects_count"] == len(connector_ready_dialects()) == 1
    assert report["validator_state_summary"] == {
        "accepted": readiness.accepted,
        "evidence_review_complete": readiness.evidence_review_complete,
        "ready_for_engineering_patch": readiness.ready_for_engineering_patch,
        "connector_enablement_ready": readiness.connector_enablement_ready,
        "pending_rows": len(readiness.pending_rows),
        "deferred_rows": list(readiness.deferred_rows),
        "rejection_reasons": list(readiness.rejection_reasons),
        "b1_b5_status": readiness.b1_b5_status,
    }


def test_phase41b_report_verdict_passes_only_without_rejections() -> None:
    run = _run_artifact()
    report = _report()

    assert _telemetry_rejection_reasons(run, report) == ()
    assert report["report_verdict"] == "PASS"
    assert report["next_blocker"] == "HARD_CAPPED_MULTI_RUN_SESSION_NOT_READY"
