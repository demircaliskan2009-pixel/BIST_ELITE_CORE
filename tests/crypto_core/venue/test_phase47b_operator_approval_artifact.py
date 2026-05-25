from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

PHASE46_PROPOSAL = Path("docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_OPERATOR_PROPOSAL_46B.json")
PHASE45_EVALUATION = Path("docs/crypto_core/DERIBIT_PAPER_SESSION_PROMOTION_EVALUATION_45B.json")
PHASE44_REPORT_PACK = Path("docs/crypto_core/DERIBIT_REPEATED_HARD_CAPPED_SESSION_REPORT_PACK_44B.json")
APPROVAL = Path("docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_APPROVAL_47B.json")

APPROVAL_METADATA = {
    "reviewer_id": "demir_operator",
    "reviewed_at_iso": "2026-05-25T10:04:41Z",
    "approval_decision": "APPROVE_BOUNDED_REPEATED_PAPER_CAMPAIGN",
    "approval_scope": (
        "Deribit public-market-data-only, paper-only, simulation-only, no private API, no credentials, "
        "no exchange orders, no execution adapter, no scheduler, no auto-loop, no shadow/live, "
        "hard_cap=3, per_session_max_trades=2"
    ),
    "approval_notes": (
        "Operator approves bounded repeated paper campaign execution under Phase46 proposal constraints only. "
        "This approval does not authorize live trading, shadow trading, private API usage, credentials, "
        "exchange orders, execution adapters, schedulers, automatic loops, strategy autonomy, or any production "
        "execution behavior."
    ),
}
FALSE_SCOPE_FLAGS = ("live_ready", "live_enabled", "shadow_enabled", "auto_loop_enabled", "scheduler_enabled")
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


def _phase46_proposal() -> dict[str, object]:
    return _json(PHASE46_PROPOSAL)


def _phase45_evaluation() -> dict[str, object]:
    return _json(PHASE45_EVALUATION)


def _phase44_report_pack() -> dict[str, object]:
    return _json(PHASE44_REPORT_PACK)


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
    scope = dict(next_approval["campaign_scope"])
    scope.update(updates)
    next_approval["campaign_scope"] = scope
    return next_approval


def _mutated_bounds(approval: dict[str, object], **updates: object) -> dict[str, object]:
    next_approval = copy.deepcopy(approval)
    bounds = dict(next_approval["campaign_bounds"])
    bounds.update(updates)
    next_approval["campaign_bounds"] = bounds
    return next_approval


def _mutated_safety(approval: dict[str, object], **updates: object) -> dict[str, object]:
    next_approval = copy.deepcopy(approval)
    safety = dict(next_approval["safety_flags"])
    safety.update(updates)
    next_approval["safety_flags"] = safety
    return next_approval


def _approval_rejection_reasons(
    proposal: dict[str, object],
    evaluation: dict[str, object],
    report_pack: dict[str, object],
    approval: dict[str, object],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if approval.get("source_phase46_operator_proposal") != str(PHASE46_PROPOSAL).replace("\\", "/"):
        reasons.append("approval:source_phase46_mismatch")
    if approval.get("source_phase45_evaluation") != str(PHASE45_EVALUATION).replace("\\", "/"):
        reasons.append("approval:source_phase45_mismatch")
    if approval.get("source_phase44_report_pack") != str(PHASE44_REPORT_PACK).replace("\\", "/"):
        reasons.append("approval:source_phase44_mismatch")
    if approval.get("source_phase46_operator_proposal_sha256") != _sha256(PHASE46_PROPOSAL):
        reasons.append("approval:source_phase46_hash_mismatch")
    if approval.get("source_phase45_evaluation_sha256") != _sha256(PHASE45_EVALUATION):
        reasons.append("approval:source_phase45_hash_mismatch")
    if approval.get("source_phase44_report_pack_sha256") != _sha256(PHASE44_REPORT_PACK):
        reasons.append("approval:source_phase44_hash_mismatch")
    if proposal.get("proposal_status") != "READY_FOR_OPERATOR_REVIEW":
        reasons.append("approval:phase46_not_ready_for_operator_review")
    if proposal.get("approval_status") != "NOT_APPROVED":
        reasons.append("approval:phase46_already_approved_or_invalid")
    if proposal.get("promotion_granted") is not False:
        reasons.append("approval:phase46_promotion_granted_not_false")
    if evaluation.get("promotion_verdict") != "READY_FOR_OPERATOR_REVIEW":
        reasons.append("approval:phase45_not_ready_for_operator_review")
    if evaluation.get("promotion_granted") is not False:
        reasons.append("approval:phase45_promotion_granted_not_false")
    if report_pack.get("report_pack_verdict") != "PASS":
        reasons.append("approval:phase44_report_pack_not_pass")
    if report_pack.get("promotion_granted") is not False:
        reasons.append("approval:phase44_promotion_granted_not_false")
    if approval.get("approval_status") != "APPROVED":
        reasons.append("approval:approval_status_not_approved")
    for field, expected in APPROVAL_METADATA.items():
        if approval.get(field) != expected:
            reasons.append(f"approval:{field}_mismatch")
    if approval.get("bounded_repeated_paper_campaign_approved") is not True:
        reasons.append("approval:bounded_campaign_approval_not_true")
    if approval.get("promotion_granted") is not False:
        reasons.append("approval:promotion_granted_not_false")
    if approval.get("operator_approval_executed") is not True:
        reasons.append("approval:operator_approval_executed_not_true")
    if approval.get("campaign_execution_status") != "NOT_EXECUTED":
        reasons.append("approval:campaign_executed")
    if approval.get("session_execution_status") != "NOT_EXECUTED":
        reasons.append("approval:session_executed")
    if approval.get("run_execution_status") != "NOT_EXECUTED":
        reasons.append("approval:run_executed")
    scope = approval.get("campaign_scope")
    if not isinstance(scope, dict):
        reasons.append("approval:campaign_scope_missing")
        scope = {}
    if scope.get("venue") != "deribit":
        reasons.append("approval:venue_mismatch")
    for field in TRUE_SCOPE_FLAGS:
        if scope.get(field) is not True:
            reasons.append(f"approval:campaign_scope_{field}_not_true")
    for field in FALSE_SCOPE_FLAGS:
        if scope.get(field) is not False:
            reasons.append(f"approval:campaign_scope_{field}_not_false")
    bounds = approval.get("campaign_bounds")
    if not isinstance(bounds, dict):
        reasons.append("approval:campaign_bounds_missing")
        bounds = {}
    if bounds.get("hard_cap") != 3 or bounds.get("hard_cap") != report_pack.get("hard_cap"):
        reasons.append("approval:hard_cap_mismatch")
    if bounds.get("per_session_max_trades") != 2 or bounds.get("per_session_max_trades") != report_pack.get(
        "per_session_max_trades"
    ):
        reasons.append("approval:per_session_max_trades_mismatch")
    if bounds.get("max_sessions_approved") != report_pack.get("session_count"):
        reasons.append("approval:max_sessions_approved_mismatch")
    if bounds.get("max_total_paper_trades_approved") != report_pack.get("aggregate_trades_requested"):
        reasons.append("approval:max_total_trades_approved_mismatch")
    safety = approval.get("safety_flags")
    if not isinstance(safety, dict):
        reasons.append("approval:safety_flags_missing")
        safety = {}
    for field in SAFETY_FLAGS:
        if safety.get(field) is not True:
            reasons.append(f"approval:safety_{field}_not_true")
    checks = approval.get("approval_checks")
    if not isinstance(checks, list) or "exact_operator_metadata_supplied" not in checks:
        reasons.append("approval:approval_checks_missing")
    if approval.get("connector_ready_dialects_count") != 1:
        reasons.append("approval:connector_ready_count_mismatch")
    if approval.get("next_blocker") != "BOUNDED_REPEATED_PAPER_CAMPAIGN_EXECUTION_GATE_NOT_READY":
        reasons.append("approval:next_blocker_mismatch")
    return tuple(dict.fromkeys(reasons))


def test_phase47b_artifact_has_required_schema_and_source_references() -> None:
    approval = _approval()

    assert PHASE46_PROPOSAL.exists()
    assert PHASE45_EVALUATION.exists()
    assert PHASE44_REPORT_PACK.exists()
    assert APPROVAL.exists()
    assert approval["schema_version"] == "deribit_bounded_repeated_paper_campaign_approval.v1"
    assert approval["phase"] == "47"
    assert approval["source"] == "deterministic_phase47_operator_approval_execution"
    assert approval["source_phase46_operator_proposal"] == str(PHASE46_PROPOSAL).replace("\\", "/")
    assert approval["source_phase45_evaluation"] == str(PHASE45_EVALUATION).replace("\\", "/")
    assert approval["source_phase44_report_pack"] == str(PHASE44_REPORT_PACK).replace("\\", "/")
    assert approval["source_phase46_operator_proposal_sha256"] == _sha256(PHASE46_PROPOSAL)
    assert approval["source_phase45_evaluation_sha256"] == _sha256(PHASE45_EVALUATION)
    assert approval["source_phase44_report_pack_sha256"] == _sha256(PHASE44_REPORT_PACK)


def test_phase47b_artifact_records_exact_operator_approval_metadata() -> None:
    approval = _approval()

    for field, expected in APPROVAL_METADATA.items():
        assert approval[field] == expected
    assert approval["approval_status"] == "APPROVED"
    assert approval["bounded_repeated_paper_campaign_approved"] is True
    assert approval["promotion_granted"] is False
    assert (
        _approval_rejection_reasons(_phase46_proposal(), _phase45_evaluation(), _phase44_report_pack(), approval) == ()
    )


def test_phase47b_artifact_records_current_readiness_state() -> None:
    readiness = evaluate_deribit_manual_review_readiness()
    approval = _approval()

    assert readiness.accepted is True
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert approval["connector_ready_dialects_count"] == len(connector_ready_dialects()) == 1
