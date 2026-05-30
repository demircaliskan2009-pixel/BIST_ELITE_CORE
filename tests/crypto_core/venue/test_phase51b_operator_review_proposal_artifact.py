from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

PHASE50_EVALUATION = Path("docs/crypto_core/DERIBIT_BOUNDED_PAPER_CAMPAIGN_PERFORMANCE_EVALUATION_50B.json")
PROPOSAL = Path("docs/crypto_core/DERIBIT_PAPER_CAMPAIGN_PERFORMANCE_OPERATOR_REVIEW_PROPOSAL_51B.json")
PLACEHOLDER = "<OPERATOR_REQUIRED>"
METADATA_PLACEHOLDER_FIELDS = ("reviewer_id", "reviewed_at_iso", "approval_scope", "approval_notes")
SOURCE_FALSE_SCOPE_FLAGS = (
    "promotion_granted",
    "ready_for_live",
    "ready_for_shadow",
    "scheduler_enabled",
    "auto_loop_enabled",
    "live_enabled",
    "shadow_enabled",
)
PROPOSAL_FALSE_SCOPE_FLAGS = (
    "promotion_granted",
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


def _phase50_evaluation() -> dict[str, object]:
    return _json(PHASE50_EVALUATION)


def _proposal() -> dict[str, object]:
    return _json(PROPOSAL)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mutated(mapping: dict[str, object], **updates: object) -> dict[str, object]:
    next_mapping = copy.deepcopy(mapping)
    next_mapping.update(updates)
    return next_mapping


def _proposal_rejection_reasons(source: dict[str, object], proposal: dict[str, object]) -> tuple[str, ...]:
    reasons: list[str] = []
    if proposal.get("source_phase50_performance_evaluation") != str(PHASE50_EVALUATION).replace("\\", "/"):
        reasons.append("proposal:source_phase50_mismatch")
    if proposal.get("source_phase50_performance_evaluation_sha256") != _sha256(PHASE50_EVALUATION):
        reasons.append("proposal:source_phase50_hash_mismatch")
    if proposal.get("source_phase50_performance_evaluation_verdict") != source.get("performance_evaluation_verdict"):
        reasons.append("proposal:source_phase50_verdict_mismatch")
    if proposal.get("source_phase50_ready_for_operator_review") != source.get("ready_for_operator_review"):
        reasons.append("proposal:source_phase50_operator_review_mismatch")
    if source.get("performance_evaluation_verdict") != "PASS":
        reasons.append("proposal:phase50_not_pass")
    if source.get("ready_for_operator_review") is not True:
        reasons.append("proposal:phase50_not_ready_for_operator_review")
    if source.get("promotion_granted") is not False:
        reasons.append("proposal:phase50_promotion_granted_not_false")
    for field in SOURCE_FALSE_SCOPE_FLAGS:
        if source.get(field) is not False:
            reasons.append(f"proposal:phase50_{field}_not_false")
    for field in SAFETY_FLAGS:
        if source.get(field) is not True:
            reasons.append(f"proposal:phase50_{field}_not_true")
    if source.get("connector_ready_dialects_count") != 1:
        reasons.append("proposal:phase50_connector_ready_count_mismatch")
    if proposal.get("proposal_status") != "READY_FOR_OPERATOR_REVIEW":
        reasons.append("proposal:proposal_status_mismatch")
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
    for field in SAFETY_FLAGS:
        if proposal.get(field) is not True:
            reasons.append(f"proposal:{field}_not_true")
    checks = proposal.get("proposal_checks")
    if not isinstance(checks, list) or "operator_metadata_placeholders_only" not in checks:
        reasons.append("proposal:proposal_checks_missing")
    if proposal.get("connector_ready_dialects_count") != 1:
        reasons.append("proposal:connector_ready_count_mismatch")
    if proposal.get("next_blocker") != "OPERATOR_APPROVAL_FOR_PAPER_PERFORMANCE_NOT_READY":
        reasons.append("proposal:next_blocker_mismatch")
    return tuple(dict.fromkeys(reasons))


def test_phase51b_artifact_has_required_schema_and_source_references() -> None:
    proposal = _proposal()

    assert PROPOSAL.exists()
    assert PHASE50_EVALUATION.exists()
    assert proposal["schema_version"] == "deribit_paper_campaign_performance_operator_review_proposal.v1"
    assert proposal["phase"] == "51"
    assert proposal["source"] == "deterministic_phase51_paper_performance_operator_review_proposal"
    assert proposal["source_phase50_performance_evaluation"] == str(PHASE50_EVALUATION).replace("\\", "/")
    assert proposal["source_phase50_performance_evaluation_sha256"] == _sha256(PHASE50_EVALUATION)


def test_phase51b_artifact_records_not_approved_operator_review_proposal() -> None:
    proposal = _proposal()

    assert proposal["proposal_status"] == "READY_FOR_OPERATOR_REVIEW"
    assert proposal["approval_status"] == "NOT_APPROVED"
    assert proposal["operator_metadata_required"] is True
    assert proposal["approval_decision"] == "PLACEHOLDER_ONLY"
    assert proposal["promotion_granted"] is False
    assert _proposal_rejection_reasons(_phase50_evaluation(), proposal) == ()


def test_phase51b_artifact_records_current_readiness_state() -> None:
    readiness = evaluate_deribit_manual_review_readiness()
    proposal = _proposal()

    assert readiness.accepted is True
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert len(connector_ready_dialects()) == 1
    assert proposal["connector_ready_dialects_count"] == 1
