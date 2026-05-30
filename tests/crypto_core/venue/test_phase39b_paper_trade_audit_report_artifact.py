from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

PROOF = Path("docs/crypto_core/DERIBIT_FIRST_PAPER_TRADE_SMOKE_PROOF_38B.json")
REPORT = Path("docs/crypto_core/DERIBIT_FIRST_PAPER_TRADE_AUDIT_REPORT_39B.json")

REPORT_TRUE_FLAGS = (
    "paper_fill_observed",
    "ledger_mutated_once",
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


def _proof() -> dict[str, object]:
    return _json(PROOF)


def _report() -> dict[str, object]:
    return _json(REPORT)


def _source_proof_hash() -> str:
    return hashlib.sha256(PROOF.read_bytes()).hexdigest()


def _mutated(mapping: dict[str, object], **updates: object) -> dict[str, object]:
    next_mapping = copy.deepcopy(mapping)
    next_mapping.update(updates)
    return next_mapping


def _audit_rejection_reasons(proof: dict[str, object], report: dict[str, object]) -> tuple[str, ...]:
    reasons: list[str] = []
    if report.get("source_proof_artifact") != str(PROOF).replace("\\", "/"):
        reasons.append("audit:source_proof_artifact_mismatch")
    if report.get("source_proof_sha256") != _source_proof_hash():
        reasons.append("audit:source_proof_hash_mismatch")
    if not proof.get("run_id"):
        reasons.append("audit:run_id_missing")
    if report.get("audited_run_id") != proof.get("run_id"):
        reasons.append("audit:run_id_mismatch")
    if not proof.get("operator_id"):
        reasons.append("audit:operator_id_missing")
    if report.get("audited_operator_id") != proof.get("operator_id"):
        reasons.append("audit:operator_id_mismatch")
    if proof.get("simulation_only") is not True or report.get("simulation_only") is not True:
        reasons.append("audit:not_simulation_only")
    for field in ("live_enabled", "shadow_enabled", "auto_loop_enabled"):
        if proof.get(field) is not False or report.get(field) is not False:
            reasons.append(f"audit:{field}_not_false")
    if proof.get("fill_status") != "FILLED" or report.get("paper_fill_observed") is not True:
        reasons.append("audit:paper_fill_not_observed")
    if proof.get("ledger_mutated") is not True or report.get("ledger_mutated_once") is not True:
        reasons.append("audit:ledger_mutation_not_confirmed")
    before = proof.get("before_ledger_summary")
    after = proof.get("after_ledger_summary")
    if not isinstance(before, dict) or not isinstance(after, dict):
        reasons.append("audit:ledger_summary_missing")
    else:
        if (
            before.get("applied_fill_count") != 0
            or before.get("applied_request_count") != 0
            or before.get("applied_idempotency_count") != 0
        ):
            reasons.append("audit:before_ledger_not_empty")
        if (
            after.get("applied_fill_count") != 1
            or after.get("applied_request_count") != 1
            or after.get("applied_idempotency_count") != 1
        ):
            reasons.append("audit:ledger_not_mutated_once")
    if report.get("duplicate_mutation_blocked") is not True:
        reasons.append("audit:duplicate_mutation_not_blocked")
    invariants = proof.get("safety_invariants")
    if not isinstance(invariants, dict):
        reasons.append("audit:safety_invariants_missing")
    else:
        for proof_flag in (
            "no_private_api",
            "no_credentials",
            "no_exchange_orders",
            "no_execution_adapter",
            "no_order_routing",
            "no_strategy_alpha",
            "no_scheduler",
            "no_automatic_paper_loop",
            "no_shadow",
            "no_live",
        ):
            if invariants.get(proof_flag) is not True:
                reasons.append(f"audit:{proof_flag}_not_true")
    for report_flag in REPORT_TRUE_FLAGS:
        if report.get(report_flag) is not True:
            reasons.append(f"audit:{report_flag}_not_true")
    if report.get("connector_ready_dialects_count") != 1:
        reasons.append("audit:connector_ready_count_mismatch")
    if report.get("audit_verdict") == "PASS" and reasons:
        reasons.append("audit:pass_verdict_with_rejections")
    return tuple(dict.fromkeys(reasons))


def test_phase39b_report_artifact_has_required_schema_and_source_reference() -> None:
    report = _report()

    assert report["schema_version"] == "deribit_first_paper_trade_audit_report.v1"
    assert report["phase"] == "39"
    assert report["source"] == "deterministic_phase38_proof_artifact_audit"
    assert report["source_proof_artifact"] == "docs/crypto_core/DERIBIT_FIRST_PAPER_TRADE_SMOKE_PROOF_38B.json"
    assert report["source_proof_sha256"] == _source_proof_hash()


def test_phase39b_report_matches_phase38_proof_identity_and_outcome() -> None:
    proof = _proof()
    report = _report()

    assert report["audited_run_id"] == proof["run_id"]
    assert report["audited_operator_id"] == proof["operator_id"]
    assert report["simulation_only"] is proof["simulation_only"] is True
    assert report["live_enabled"] is proof["live_enabled"] is False
    assert report["shadow_enabled"] is proof["shadow_enabled"] is False
    assert report["auto_loop_enabled"] is proof["auto_loop_enabled"] is False
    assert report["paper_fill_observed"] is True
    assert proof["fill_status"] == "FILLED"
    assert report["ledger_mutated_once"] is True
    assert proof["ledger_mutated"] is True


def test_phase39b_report_records_current_readiness_state() -> None:
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


def test_phase39b_report_audit_verdict_passes_only_without_rejections() -> None:
    proof = _proof()
    report = _report()

    assert _audit_rejection_reasons(proof, report) == ()
    assert report["audit_verdict"] == "PASS"
    assert report["next_blocker"] == "BOUNDED_OPERATOR_TRIGGERED_PAPER_RUN_HARNESS_NOT_READY"
