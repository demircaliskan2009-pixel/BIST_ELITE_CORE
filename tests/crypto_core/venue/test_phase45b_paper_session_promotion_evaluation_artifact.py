from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

PROMOTION_READINESS = Path("docs/crypto_core/DERIBIT_PAPER_SESSION_PROMOTION_READINESS_43B.json")
REPORT_PACK = Path("docs/crypto_core/DERIBIT_REPEATED_HARD_CAPPED_SESSION_REPORT_PACK_44B.json")
EVALUATION = Path("docs/crypto_core/DERIBIT_PAPER_SESSION_PROMOTION_EVALUATION_45B.json")

FALSE_FLAGS = ("scheduler_enabled", "auto_loop_enabled", "live_enabled", "shadow_enabled", "live_ready")
TRUE_FLAGS = (
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
PASS_STATUS_FIELDS = (
    "evidence_sufficiency_status",
    "safety_invariants_status",
    "ledger_invariants_status",
    "idempotency_status",
    "no_live_scope_status",
    "determinism_status",
    "fail_closed_negative_cases_status",
)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _promotion_readiness() -> dict[str, object]:
    return _json(PROMOTION_READINESS)


def _report_pack() -> dict[str, object]:
    return _json(REPORT_PACK)


def _evaluation() -> dict[str, object]:
    return _json(EVALUATION)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mutated(mapping: dict[str, object], **updates: object) -> dict[str, object]:
    next_mapping = copy.deepcopy(mapping)
    next_mapping.update(updates)
    return next_mapping


def _evaluation_rejection_reasons(
    promotion: dict[str, object],
    pack: dict[str, object],
    evaluation: dict[str, object],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if evaluation.get("source_phase43_promotion_readiness") != str(PROMOTION_READINESS).replace("\\", "/"):
        reasons.append("evaluation:source_phase43_mismatch")
    if evaluation.get("source_phase44_report_pack") != str(REPORT_PACK).replace("\\", "/"):
        reasons.append("evaluation:source_phase44_mismatch")
    if evaluation.get("source_phase43_promotion_readiness_sha256") != _sha256(PROMOTION_READINESS):
        reasons.append("evaluation:source_phase43_hash_mismatch")
    if evaluation.get("source_phase44_report_pack_sha256") != _sha256(REPORT_PACK):
        reasons.append("evaluation:source_phase44_hash_mismatch")
    if promotion.get("promotion_verdict") != "NOT_READY":
        reasons.append("evaluation:phase43_verdict_mismatch")
    if evaluation.get("source_phase43_promotion_verdict") != promotion.get("promotion_verdict"):
        reasons.append("evaluation:source_phase43_verdict_mismatch")
    if pack.get("report_pack_verdict") != "PASS":
        reasons.append("evaluation:phase44_pack_not_pass")
    if evaluation.get("source_phase44_report_pack_verdict") != pack.get("report_pack_verdict"):
        reasons.append("evaluation:source_phase44_verdict_mismatch")
    if pack.get("promotion_granted") is not False or evaluation.get("source_phase44_promotion_granted") is not False:
        reasons.append("evaluation:source_phase44_promotion_not_false")
    if evaluation.get("hard_cap") != pack.get("hard_cap") or evaluation.get("hard_cap") != 3:
        reasons.append("evaluation:hard_cap_mismatch")
    if evaluation.get("required_future_sessions_minimum") != promotion.get("required_future_sessions_minimum"):
        reasons.append("evaluation:required_minimum_mismatch")
    if evaluation.get("evaluated_session_count") != pack.get("session_count"):
        reasons.append("evaluation:session_count_mismatch")
    if evaluation.get("evaluated_session_count", 0) < promotion.get("required_future_sessions_minimum", 0):
        reasons.append("evaluation:evidence_count_insufficient")
    if evaluation.get("evaluated_max_session_trades") != pack.get("per_session_max_trades"):
        reasons.append("evaluation:max_session_trades_mismatch")
    if evaluation.get("aggregate_trades_requested") != pack.get("aggregate_trades_requested"):
        reasons.append("evaluation:aggregate_requested_mismatch")
    if evaluation.get("aggregate_trades_attempted") != pack.get("aggregate_trades_attempted"):
        reasons.append("evaluation:aggregate_attempted_mismatch")
    if evaluation.get("aggregate_trades_filled") != pack.get("aggregate_trades_filled"):
        reasons.append("evaluation:aggregate_filled_mismatch")
    if evaluation.get("aggregate_trades_rejected") != pack.get("aggregate_trades_rejected"):
        reasons.append("evaluation:aggregate_rejected_mismatch")
    if evaluation.get("aggregate_ledger_mutations") != pack.get("aggregate_ledger_mutations"):
        reasons.append("evaluation:aggregate_ledger_mutations_mismatch")
    for field in PASS_STATUS_FIELDS:
        if evaluation.get(field) != "PASS":
            reasons.append(f"evaluation:{field}_not_pass")
    if evaluation.get("ready_for_operator_review") is not True:
        reasons.append("evaluation:ready_for_operator_review_not_true")
    if evaluation.get("promotion_verdict") != "READY_FOR_OPERATOR_REVIEW":
        reasons.append("evaluation:promotion_verdict_mismatch")
    if evaluation.get("promotion_granted") is not False:
        reasons.append("evaluation:promotion_granted_not_false")
    if evaluation.get("operator_approval_required") is not True:
        reasons.append("evaluation:operator_approval_required_not_true")
    for field in FALSE_FLAGS:
        if evaluation.get(field) is not False:
            reasons.append(f"evaluation:{field}_not_false")
    for field in TRUE_FLAGS:
        if evaluation.get(field) is not True:
            reasons.append(f"evaluation:{field}_not_true")
    if evaluation.get("connector_ready_dialects_count") != 1:
        reasons.append("evaluation:connector_ready_count_mismatch")
    matrix = evaluation.get("evaluation_matrix")
    if not isinstance(matrix, list) or not matrix:
        reasons.append("evaluation:matrix_missing")
    else:
        for item in matrix:
            if not isinstance(item, dict):
                reasons.append("evaluation:matrix_item_not_mapping")
            elif item.get("status") != "PASS":
                reasons.append("evaluation:matrix_status_not_pass")
    checks = evaluation.get("evaluation_checks")
    if not isinstance(checks, list) or "operator_approval_required_before_any_promotion" not in checks:
        reasons.append("evaluation:operator_approval_check_missing")
    if evaluation.get("next_blocker") != "OPERATOR_APPROVAL_FOR_BOUNDED_REPEATED_PAPER_CAMPAIGN":
        reasons.append("evaluation:next_blocker_mismatch")
    return tuple(dict.fromkeys(reasons))


def test_phase45b_artifact_has_required_schema_and_source_references() -> None:
    evaluation = _evaluation()

    assert PROMOTION_READINESS.exists()
    assert REPORT_PACK.exists()
    assert EVALUATION.exists()
    assert evaluation["schema_version"] == "deribit_paper_session_promotion_evaluation.v1"
    assert evaluation["phase"] == "45"
    assert evaluation["source"] == "deterministic_phase45_promotion_criteria_reevaluation"
    assert evaluation["source_phase43_promotion_readiness"] == str(PROMOTION_READINESS).replace("\\", "/")
    assert evaluation["source_phase44_report_pack"] == str(REPORT_PACK).replace("\\", "/")
    assert evaluation["source_phase43_promotion_readiness_sha256"] == _sha256(PROMOTION_READINESS)
    assert evaluation["source_phase44_report_pack_sha256"] == _sha256(REPORT_PACK)


def test_phase45b_artifact_evaluates_phase44_evidence_against_phase43_criteria() -> None:
    promotion = _promotion_readiness()
    pack = _report_pack()
    evaluation = _evaluation()

    assert evaluation["hard_cap"] == pack["hard_cap"] == 3
    assert evaluation["evaluated_session_count"] == pack["session_count"] == 3
    assert evaluation["evaluated_session_count"] >= promotion["required_future_sessions_minimum"]
    assert evaluation["evaluated_max_session_trades"] == pack["per_session_max_trades"] == 2
    assert evaluation["promotion_verdict"] == "READY_FOR_OPERATOR_REVIEW"
    assert evaluation["promotion_granted"] is False
    assert evaluation["operator_approval_required"] is True
    assert _evaluation_rejection_reasons(promotion, pack, evaluation) == ()


def test_phase45b_artifact_records_current_readiness_state() -> None:
    readiness = evaluate_deribit_manual_review_readiness()
    evaluation = _evaluation()

    assert readiness.accepted is True
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert evaluation["connector_ready_dialects_count"] == len(connector_ready_dialects()) == 1
