from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

PHASE45_EVALUATION = Path("docs/crypto_core/DERIBIT_PAPER_SESSION_PROMOTION_EVALUATION_45B.json")
PHASE44_REPORT_PACK = Path("docs/crypto_core/DERIBIT_REPEATED_HARD_CAPPED_SESSION_REPORT_PACK_44B.json")
PHASE43_CRITERIA = Path("docs/crypto_core/PAPER_SESSION_PROMOTION_CRITERIA_43A.md")
PROPOSAL = Path("docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_OPERATOR_PROPOSAL_46B.json")

PLACEHOLDER = "<OPERATOR_REQUIRED>"
APPROVAL_METADATA_FIELDS = (
    "reviewer_id",
    "reviewed_at_iso",
    "approval_scope",
    "approval_decision",
    "approval_notes",
)
FALSE_SCOPE_FLAGS = ("live_enabled", "shadow_enabled", "auto_loop_enabled", "scheduler_enabled")
TRUE_SCOPE_FLAGS = ("public_market_data_only", "paper_only", "simulation_only", "explicit_operator_triggered")
SAFETY_FLAGS = (
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


def _phase45_evaluation() -> dict[str, object]:
    return _json(PHASE45_EVALUATION)


def _phase44_report_pack() -> dict[str, object]:
    return _json(PHASE44_REPORT_PACK)


def _proposal() -> dict[str, object]:
    return _json(PROPOSAL)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mutated(mapping: dict[str, object], **updates: object) -> dict[str, object]:
    next_mapping = copy.deepcopy(mapping)
    next_mapping.update(updates)
    return next_mapping


def _mutated_scope(proposal: dict[str, object], **updates: object) -> dict[str, object]:
    next_proposal = copy.deepcopy(proposal)
    scope = dict(next_proposal["campaign_scope"])
    scope.update(updates)
    next_proposal["campaign_scope"] = scope
    return next_proposal


def _mutated_bounds(proposal: dict[str, object], **updates: object) -> dict[str, object]:
    next_proposal = copy.deepcopy(proposal)
    bounds = dict(next_proposal["campaign_bounds"])
    bounds.update(updates)
    next_proposal["campaign_bounds"] = bounds
    return next_proposal


def _mutated_safety(proposal: dict[str, object], **updates: object) -> dict[str, object]:
    next_proposal = copy.deepcopy(proposal)
    safety = dict(next_proposal["safety_flags"])
    safety.update(updates)
    next_proposal["safety_flags"] = safety
    return next_proposal


def _proposal_rejection_reasons(
    evaluation: dict[str, object],
    report_pack: dict[str, object],
    proposal: dict[str, object],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if proposal.get("source_phase45_evaluation") != str(PHASE45_EVALUATION).replace("\\", "/"):
        reasons.append("proposal:source_phase45_mismatch")
    if proposal.get("source_phase44_report_pack") != str(PHASE44_REPORT_PACK).replace("\\", "/"):
        reasons.append("proposal:source_phase44_mismatch")
    if proposal.get("source_phase43_criteria") != str(PHASE43_CRITERIA).replace("\\", "/"):
        reasons.append("proposal:source_phase43_criteria_mismatch")
    if proposal.get("source_phase45_evaluation_sha256") != _sha256(PHASE45_EVALUATION):
        reasons.append("proposal:source_phase45_hash_mismatch")
    if proposal.get("source_phase44_report_pack_sha256") != _sha256(PHASE44_REPORT_PACK):
        reasons.append("proposal:source_phase44_hash_mismatch")
    if proposal.get("source_phase43_criteria_sha256") != _sha256(PHASE43_CRITERIA):
        reasons.append("proposal:source_phase43_criteria_hash_mismatch")
    if evaluation.get("promotion_verdict") != "READY_FOR_OPERATOR_REVIEW":
        reasons.append("proposal:phase45_not_ready_for_operator_review")
    if evaluation.get("promotion_granted") is not False:
        reasons.append("proposal:phase45_promotion_granted_not_false")
    if evaluation.get("operator_approval_required") is not True:
        reasons.append("proposal:phase45_operator_approval_not_required")
    if report_pack.get("report_pack_verdict") != "PASS":
        reasons.append("proposal:phase44_report_pack_not_pass")
    if report_pack.get("promotion_granted") is not False:
        reasons.append("proposal:phase44_promotion_granted_not_false")
    if proposal.get("proposal_status") != "READY_FOR_OPERATOR_REVIEW":
        reasons.append("proposal:proposal_status_mismatch")
    if proposal.get("approval_status") != "NOT_APPROVED":
        reasons.append("proposal:approval_status_not_not_approved")
    if proposal.get("promotion_granted") is not False:
        reasons.append("proposal:promotion_granted_not_false")
    if proposal.get("operator_approval_required") is not True:
        reasons.append("proposal:operator_approval_required_not_true")
    for field in APPROVAL_METADATA_FIELDS:
        if proposal.get(field) != PLACEHOLDER:
            reasons.append(f"proposal:{field}_not_placeholder")
    scope = proposal.get("campaign_scope")
    if not isinstance(scope, dict):
        reasons.append("proposal:campaign_scope_missing")
        scope = {}
    if scope.get("venue") != "deribit":
        reasons.append("proposal:venue_mismatch")
    for field in TRUE_SCOPE_FLAGS:
        if scope.get(field) is not True:
            reasons.append(f"proposal:campaign_scope_{field}_not_true")
    for field in FALSE_SCOPE_FLAGS:
        if scope.get(field) is not False:
            reasons.append(f"proposal:campaign_scope_{field}_not_false")
    bounds = proposal.get("campaign_bounds")
    if not isinstance(bounds, dict):
        reasons.append("proposal:campaign_bounds_missing")
        bounds = {}
    if bounds.get("hard_cap") != 3 or bounds.get("hard_cap") != report_pack.get("hard_cap"):
        reasons.append("proposal:hard_cap_mismatch")
    if bounds.get("per_session_max_trades") != 2 or bounds.get("per_session_max_trades") != report_pack.get(
        "per_session_max_trades"
    ):
        reasons.append("proposal:per_session_max_trades_mismatch")
    if bounds.get("max_sessions_proposed") != report_pack.get("session_count"):
        reasons.append("proposal:max_sessions_proposed_mismatch")
    if bounds.get("max_total_paper_trades_proposed") != report_pack.get("aggregate_trades_requested"):
        reasons.append("proposal:max_total_trades_mismatch")
    safety = proposal.get("safety_flags")
    if not isinstance(safety, dict):
        reasons.append("proposal:safety_flags_missing")
        safety = {}
    for field in SAFETY_FLAGS:
        if safety.get(field) is not True:
            reasons.append(f"proposal:safety_{field}_not_true")
    requirements = proposal.get("approval_requirements")
    if not isinstance(requirements, list) or "separate_approval_execution_phase_required" not in requirements:
        reasons.append("proposal:approval_requirements_missing")
    checks = proposal.get("proposal_checks")
    if not isinstance(checks, list) or "approval_metadata_placeholders_only" not in checks:
        reasons.append("proposal:proposal_checks_missing")
    if proposal.get("connector_ready_dialects_count") != 1:
        reasons.append("proposal:connector_ready_count_mismatch")
    if proposal.get("next_blocker") != "OPERATOR_APPROVAL_METADATA_REQUIRED":
        reasons.append("proposal:next_blocker_mismatch")
    return tuple(dict.fromkeys(reasons))


def test_phase46b_artifact_has_required_schema_and_source_references() -> None:
    proposal = _proposal()

    assert PHASE45_EVALUATION.exists()
    assert PHASE44_REPORT_PACK.exists()
    assert PHASE43_CRITERIA.exists()
    assert PROPOSAL.exists()
    assert proposal["schema_version"] == "deribit_bounded_repeated_paper_campaign_operator_proposal.v1"
    assert proposal["phase"] == "46"
    assert proposal["source"] == "deterministic_phase46_operator_proposal"
    assert proposal["source_phase45_evaluation"] == str(PHASE45_EVALUATION).replace("\\", "/")
    assert proposal["source_phase44_report_pack"] == str(PHASE44_REPORT_PACK).replace("\\", "/")
    assert proposal["source_phase43_criteria"] == str(PHASE43_CRITERIA).replace("\\", "/")
    assert proposal["source_phase45_evaluation_sha256"] == _sha256(PHASE45_EVALUATION)
    assert proposal["source_phase44_report_pack_sha256"] == _sha256(PHASE44_REPORT_PACK)
    assert proposal["source_phase43_criteria_sha256"] == _sha256(PHASE43_CRITERIA)


def test_phase46b_artifact_records_not_approved_operator_proposal() -> None:
    proposal = _proposal()

    assert proposal["proposal_status"] == "READY_FOR_OPERATOR_REVIEW"
    assert proposal["approval_status"] == "NOT_APPROVED"
    assert proposal["promotion_granted"] is False
    assert proposal["operator_approval_required"] is True
    assert all(proposal[field] == PLACEHOLDER for field in APPROVAL_METADATA_FIELDS)
    assert _proposal_rejection_reasons(_phase45_evaluation(), _phase44_report_pack(), proposal) == ()


def test_phase46b_artifact_records_current_readiness_state() -> None:
    readiness = evaluate_deribit_manual_review_readiness()
    proposal = _proposal()

    assert readiness.accepted is True
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert proposal["connector_ready_dialects_count"] == len(connector_ready_dialects()) == 1
