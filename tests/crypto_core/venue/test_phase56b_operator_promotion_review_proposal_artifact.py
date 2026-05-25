from __future__ import annotations

import copy
import json
from pathlib import Path

from crypto_core.venue.deribit_operator_promotion_review_proposal import (
    DERIBIT_OPERATOR_PROMOTION_REVIEW_PROPOSAL_ID,
    propose_deribit_operator_promotion_review,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

PHASE55_READINESS = Path("docs/crypto_core/DERIBIT_PAPER_PERFORMANCE_PROMOTION_READINESS_EVALUATION_55B.json")
PHASE54_TELEMETRY = Path("docs/crypto_core/DERIBIT_APPROVED_PAPER_PERFORMANCE_EXECUTION_TELEMETRY_AUDIT_54B.json")
PROPOSAL = Path("docs/crypto_core/DERIBIT_PAPER_PERFORMANCE_OPERATOR_PROMOTION_REVIEW_PROPOSAL_56B.json")
PLACEHOLDER = "<OPERATOR_REQUIRED>"
METADATA_PLACEHOLDER_FIELDS = ("reviewer_id", "reviewed_at_iso", "approval_scope", "approval_notes")
PROPOSAL_FALSE_SCOPE_FLAGS = (
    "promotion_granted",
    "ready_for_live",
    "ready_for_shadow",
    "scheduler_enabled",
    "auto_loop_enabled",
    "live_enabled",
    "shadow_enabled",
)
SAFETY_FLAGS = (
    "no_private_api",
    "no_credentials",
    "no_exchange_orders",
    "no_execution_adapter",
    "no_strategy_signal",
    "no_order_routing",
    "no_scheduler",
    "no_automatic_paper_loop",
    "no_shadow",
    "no_live",
)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _phase55_readiness() -> dict[str, object]:
    return _json(PHASE55_READINESS)


def _phase54_telemetry() -> dict[str, object]:
    return _json(PHASE54_TELEMETRY)


def _proposal() -> dict[str, object]:
    return _json(PROPOSAL)


def _mutated(mapping: dict[str, object], **updates: object) -> dict[str, object]:
    next_mapping = copy.deepcopy(mapping)
    next_mapping.update(updates)
    return next_mapping


def _expected_proposal(phase55: dict[str, object], phase54: dict[str, object]) -> dict[str, object]:
    return propose_deribit_operator_promotion_review(phase55, phase54).artifact_payload


def _proposal_rejection_reasons(
    phase55: dict[str, object],
    phase54: dict[str, object],
    proposal: dict[str, object],
) -> tuple[str, ...]:
    expected = _expected_proposal(phase55, phase54)
    reasons: list[str] = []
    if proposal.get("schema_version") != "deribit_paper_performance_operator_promotion_review_proposal.v1":
        reasons.append("proposal:schema_version_mismatch")
    if proposal.get("phase") != "56":
        reasons.append("proposal:phase_mismatch")
    if proposal.get("source") != DERIBIT_OPERATOR_PROMOTION_REVIEW_PROPOSAL_ID:
        reasons.append("proposal:source_mismatch")
    if proposal.get("source_phase55_promotion_readiness") != str(PHASE55_READINESS).replace("\\", "/"):
        reasons.append("proposal:source_phase55_mismatch")
    if proposal.get("source_phase54_execution_telemetry") != str(PHASE54_TELEMETRY).replace("\\", "/"):
        reasons.append("proposal:source_phase54_mismatch")
    if phase55.get("promotion_readiness_verdict") != "READY_FOR_OPERATOR_REVIEW":
        reasons.append("proposal:phase55_not_ready_for_operator_review")
    if phase55.get("ready_for_operator_promotion_review") is not True:
        reasons.append("proposal:phase55_ready_flag_not_true")
    if phase54.get("telemetry_audit_verdict") != "PASS":
        reasons.append("proposal:phase54_telemetry_verdict_not_pass")
    if phase54.get("execution_verdict") != "PASS":
        reasons.append("proposal:phase54_execution_verdict_not_pass")
    if proposal.get("source_phase55_promotion_readiness_verdict") != expected.get(
        "source_phase55_promotion_readiness_verdict"
    ):
        reasons.append("proposal:source_phase55_verdict_mismatch")
    if proposal.get("source_phase55_ready_for_operator_promotion_review") != expected.get(
        "source_phase55_ready_for_operator_promotion_review"
    ):
        reasons.append("proposal:source_phase55_ready_flag_mismatch")
    if proposal.get("source_phase54_telemetry_audit_verdict") != expected.get("source_phase54_telemetry_audit_verdict"):
        reasons.append("proposal:source_phase54_telemetry_verdict_mismatch")
    if proposal.get("source_phase54_execution_verdict") != expected.get("source_phase54_execution_verdict"):
        reasons.append("proposal:source_phase54_execution_verdict_mismatch")
    if proposal.get("proposal_status") != expected.get("proposal_status"):
        reasons.append("proposal:proposal_status_mismatch")
    if proposal.get("proposal_type") != "OPERATOR_PROMOTION_REVIEW":
        reasons.append("proposal:proposal_type_mismatch")
    if proposal.get("approval_status") != "NOT_APPROVED":
        reasons.append("proposal:approval_status_not_not_approved")
    if proposal.get("operator_metadata_required") is not True:
        reasons.append("proposal:operator_metadata_required_not_true")
    if proposal.get("approval_decision") != "PLACEHOLDER_ONLY":
        reasons.append("proposal:approval_decision_not_placeholder")
    for field in METADATA_PLACEHOLDER_FIELDS:
        if proposal.get(field) != PLACEHOLDER:
            reasons.append(f"proposal:{field}_not_placeholder")
    for field in PROPOSAL_FALSE_SCOPE_FLAGS:
        if proposal.get(field) is not False:
            reasons.append(f"proposal:{field}_not_false")
    if proposal.get("ready_for_operator_promotion_review") != expected.get("ready_for_operator_promotion_review"):
        reasons.append("proposal:ready_for_operator_promotion_review_mismatch")
    for field in SAFETY_FLAGS:
        if proposal.get(field) is not True:
            reasons.append(f"proposal:{field}_not_true")
    checks = proposal.get("proposal_checks")
    if checks != expected.get("proposal_checks"):
        reasons.append("proposal:proposal_checks_mismatch")
    if proposal.get("connector_ready_dialects_count") != len(connector_ready_dialects()):
        reasons.append("proposal:connector_ready_count_mismatch")
    if proposal.get("reason_code") != expected.get("reason_code"):
        reasons.append("proposal:reason_code_mismatch")
    if proposal.get("rejection_reasons") != expected.get("rejection_reasons"):
        reasons.append("proposal:rejection_reasons_mismatch")
    if proposal.get("next_blocker") != expected.get("next_blocker"):
        reasons.append("proposal:next_blocker_mismatch")
    return tuple(dict.fromkeys(reasons))


def test_phase56b_artifact_has_required_schema_and_source_references() -> None:
    proposal = _proposal()

    assert PROPOSAL.exists()
    assert PHASE55_READINESS.exists()
    assert PHASE54_TELEMETRY.exists()
    assert proposal["schema_version"] == "deribit_paper_performance_operator_promotion_review_proposal.v1"
    assert proposal["phase"] == "56"
    assert proposal["source"] == "deterministic_phase56_operator_promotion_review_proposal"
    assert proposal["source_phase55_promotion_readiness"] == str(PHASE55_READINESS).replace("\\", "/")
    assert proposal["source_phase54_execution_telemetry"] == str(PHASE54_TELEMETRY).replace("\\", "/")


def test_phase56b_artifact_matches_runtime_output_and_not_approved_state() -> None:
    proposal = _proposal()
    runtime = _expected_proposal(_phase55_readiness(), _phase54_telemetry())

    assert proposal == runtime
    assert proposal["proposal_status"] == "READY_FOR_OPERATOR_REVIEW"
    assert proposal["proposal_type"] == "OPERATOR_PROMOTION_REVIEW"
    assert proposal["approval_status"] == "NOT_APPROVED"
    assert proposal["operator_metadata_required"] is True
    assert proposal["approval_decision"] == "PLACEHOLDER_ONLY"
    assert proposal["promotion_granted"] is False
    assert _proposal_rejection_reasons(_phase55_readiness(), _phase54_telemetry(), proposal) == ()


def test_phase56b_artifact_records_current_readiness_state() -> None:
    phase55 = _phase55_readiness()
    phase54 = _phase54_telemetry()
    proposal = _proposal()

    assert phase55["promotion_readiness_verdict"] == "READY_FOR_OPERATOR_REVIEW"
    assert phase55["ready_for_operator_promotion_review"] is True
    assert phase54["telemetry_audit_verdict"] == "PASS"
    assert phase54["execution_verdict"] == "PASS"
    assert len(connector_ready_dialects()) == 1
    assert proposal["connector_ready_dialects_count"] == 1
