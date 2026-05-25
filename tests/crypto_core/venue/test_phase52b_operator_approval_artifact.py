from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

PHASE51_PROPOSAL = Path("docs/crypto_core/DERIBIT_PAPER_CAMPAIGN_PERFORMANCE_OPERATOR_REVIEW_PROPOSAL_51B.json")
PHASE50_EVALUATION = Path("docs/crypto_core/DERIBIT_BOUNDED_PAPER_CAMPAIGN_PERFORMANCE_EVALUATION_50B.json")
PHASE49_AUDIT = Path("docs/crypto_core/DERIBIT_BOUNDED_PAPER_CAMPAIGN_TELEMETRY_AUDIT_49B.json")
APPROVAL = Path("docs/crypto_core/DERIBIT_PAPER_CAMPAIGN_PERFORMANCE_OPERATOR_APPROVAL_52B.json")

APPROVAL_METADATA = {
    "operator_id": "demir_operator",
    "reviewed_at_iso": "2026-05-25T17:47:42Z",
    "approval_decision": "APPROVE_PAPER_CAMPAIGN_PERFORMANCE",
}
APPROVAL_SCOPE_TRUE_FLAGS = (
    "paper_only",
    "simulation_only",
    "deribit_public_market_data_only",
    "hard_cap_unchanged",
    "per_session_max_trades_unchanged",
)
FALSE_SCOPE_FLAGS = (
    "promotion_granted",
    "campaign_execution",
    "session_execution",
    "run_execution",
    "ledger_mutated",
    "live_ready",
    "shadow_ready",
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


def _phase51_proposal() -> dict[str, object]:
    return _json(PHASE51_PROPOSAL)


def _phase50_evaluation() -> dict[str, object]:
    return _json(PHASE50_EVALUATION)


def _phase49_audit() -> dict[str, object]:
    return _json(PHASE49_AUDIT)


def _approval() -> dict[str, object]:
    return _json(APPROVAL)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mutated(mapping: dict[str, object], **updates: object) -> dict[str, object]:
    next_mapping = copy.deepcopy(mapping)
    next_mapping.update(updates)
    return next_mapping


def _mutated_scope(approval: dict[str, object], **updates: object) -> dict[str, object]:
    next_approval = copy.deepcopy(approval)
    scope = dict(next_approval["approval_scope"])
    scope.update(updates)
    next_approval["approval_scope"] = scope
    return next_approval


def _is_utc_z(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo == timezone.utc


def _approval_rejection_reasons(
    proposal: dict[str, object],
    evaluation: dict[str, object],
    audit: dict[str, object],
    approval: dict[str, object],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if approval.get("source_phase51_operator_review_proposal") != str(PHASE51_PROPOSAL).replace("\\", "/"):
        reasons.append("approval:source_phase51_mismatch")
    if approval.get("source_phase50_performance_evaluation") != str(PHASE50_EVALUATION).replace("\\", "/"):
        reasons.append("approval:source_phase50_mismatch")
    if approval.get("source_phase49_telemetry_audit") != str(PHASE49_AUDIT).replace("\\", "/"):
        reasons.append("approval:source_phase49_mismatch")
    if approval.get("source_phase51_operator_review_proposal_sha256") != _sha256(PHASE51_PROPOSAL):
        reasons.append("approval:source_phase51_hash_mismatch")
    if approval.get("source_phase50_performance_evaluation_sha256") != _sha256(PHASE50_EVALUATION):
        reasons.append("approval:source_phase50_hash_mismatch")
    if approval.get("source_phase49_telemetry_audit_sha256") != _sha256(PHASE49_AUDIT):
        reasons.append("approval:source_phase49_hash_mismatch")
    if approval.get("source_phase51_proposal_status") != proposal.get("proposal_status"):
        reasons.append("approval:source_phase51_proposal_status_mismatch")
    if approval.get("source_phase51_approval_status") != proposal.get("approval_status"):
        reasons.append("approval:source_phase51_approval_status_mismatch")
    if approval.get("source_phase50_performance_evaluation_verdict") != evaluation.get(
        "performance_evaluation_verdict"
    ):
        reasons.append("approval:source_phase50_verdict_mismatch")
    if approval.get("source_phase50_ready_for_operator_review") != evaluation.get("ready_for_operator_review"):
        reasons.append("approval:source_phase50_ready_for_operator_review_mismatch")
    if approval.get("source_phase49_audit_verdict") != audit.get("audit_verdict"):
        reasons.append("approval:source_phase49_audit_verdict_mismatch")
    if approval.get("source_phase49_campaign_execution_verdict") != audit.get("campaign_execution_verdict"):
        reasons.append("approval:source_phase49_campaign_execution_verdict_mismatch")
    if proposal.get("proposal_status") != "READY_FOR_OPERATOR_REVIEW":
        reasons.append("approval:phase51_not_ready_for_operator_review")
    if proposal.get("approval_status") != "NOT_APPROVED":
        reasons.append("approval:phase51_already_approved_or_invalid")
    if proposal.get("promotion_granted") is not False:
        reasons.append("approval:phase51_promotion_granted_not_false")
    if evaluation.get("performance_evaluation_verdict") != "PASS":
        reasons.append("approval:phase50_not_pass")
    if evaluation.get("ready_for_operator_review") is not True:
        reasons.append("approval:phase50_not_ready_for_operator_review")
    if evaluation.get("promotion_granted") is not False:
        reasons.append("approval:phase50_promotion_granted_not_false")
    if audit.get("audit_verdict") != "PASS":
        reasons.append("approval:phase49_audit_not_pass")
    if audit.get("campaign_execution_verdict") != "PASS":
        reasons.append("approval:phase49_campaign_execution_not_pass")
    if approval.get("approval_status") != "APPROVED":
        reasons.append("approval:approval_status_not_approved")
    for field, expected in APPROVAL_METADATA.items():
        if approval.get(field) != expected:
            reasons.append(f"approval:{field}_mismatch")
    if not _is_utc_z(approval.get("reviewed_at_iso")):
        reasons.append("approval:reviewed_at_iso_not_utc_z")
    scope = approval.get("approval_scope")
    if not isinstance(scope, dict):
        reasons.append("approval:approval_scope_missing")
        scope = {}
    for field in APPROVAL_SCOPE_TRUE_FLAGS:
        if scope.get(field) is not True:
            reasons.append(f"approval:approval_scope_{field}_not_true")
    if approval.get("operator_metadata_source") != "explicit_user_approval_in_chat":
        reasons.append("approval:operator_metadata_source_mismatch")
    for field in FALSE_SCOPE_FLAGS:
        if approval.get(field) is not False:
            reasons.append(f"approval:{field}_not_false")
    for field in SAFETY_FLAGS:
        if approval.get(field) is not True:
            reasons.append(f"approval:{field}_not_true")
    checks = approval.get("approval_checks")
    if not isinstance(checks, list) or "exact_operator_metadata_supplied" not in checks:
        reasons.append("approval:approval_checks_missing")
    if approval.get("connector_ready_dialects_count") != 1:
        reasons.append("approval:connector_ready_count_mismatch")
    if approval.get("next_blocker") != "APPROVED_PAPER_PERFORMANCE_CAMPAIGN_EXECUTION_NOT_READY":
        reasons.append("approval:next_blocker_mismatch")
    return tuple(dict.fromkeys(reasons))


def test_phase52b_artifact_has_required_schema_and_source_references() -> None:
    approval = _approval()

    assert PHASE51_PROPOSAL.exists()
    assert PHASE50_EVALUATION.exists()
    assert PHASE49_AUDIT.exists()
    assert APPROVAL.exists()
    assert approval["schema_version"] == "deribit_paper_campaign_performance_operator_approval.v1"
    assert approval["phase"] == "52"
    assert approval["source"] == "deterministic_phase52_paper_performance_operator_approval"
    assert approval["source_phase51_operator_review_proposal"] == str(PHASE51_PROPOSAL).replace("\\", "/")
    assert approval["source_phase50_performance_evaluation"] == str(PHASE50_EVALUATION).replace("\\", "/")
    assert approval["source_phase49_telemetry_audit"] == str(PHASE49_AUDIT).replace("\\", "/")
    assert approval["source_phase51_operator_review_proposal_sha256"] == _sha256(PHASE51_PROPOSAL)
    assert approval["source_phase50_performance_evaluation_sha256"] == _sha256(PHASE50_EVALUATION)
    assert approval["source_phase49_telemetry_audit_sha256"] == _sha256(PHASE49_AUDIT)


def test_phase52b_artifact_records_exact_operator_approval_metadata() -> None:
    approval = _approval()

    for field, expected in APPROVAL_METADATA.items():
        assert approval[field] == expected
    assert _is_utc_z(approval["reviewed_at_iso"])
    assert approval["approval_status"] == "APPROVED"
    assert approval["operator_metadata_source"] == "explicit_user_approval_in_chat"
    assert _approval_rejection_reasons(_phase51_proposal(), _phase50_evaluation(), _phase49_audit(), approval) == ()


def test_phase52b_artifact_records_current_readiness_state() -> None:
    readiness = evaluate_deribit_manual_review_readiness()
    approval = _approval()

    assert readiness.accepted is True
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert len(connector_ready_dialects()) == 1
    assert approval["connector_ready_dialects_count"] == 1
