from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from crypto_core.venue.deribit_operator_promotion_approval import (
    DERIBIT_PHASE57_MERGE_POLICY_NOTE,
    execute_deribit_operator_promotion_approval,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

PHASE56_PROPOSAL = Path("docs/crypto_core/DERIBIT_PAPER_PERFORMANCE_OPERATOR_PROMOTION_REVIEW_PROPOSAL_56B.json")
PHASE55_READINESS = Path("docs/crypto_core/DERIBIT_PAPER_PERFORMANCE_PROMOTION_READINESS_EVALUATION_55B.json")
APPROVAL = Path("docs/crypto_core/DERIBIT_PAPER_PERFORMANCE_OPERATOR_PROMOTION_APPROVAL_57B.json")
APPROVAL_METADATA = {
    "operator_id": "demir_operator",
    "reviewed_at_iso": "2026-05-25T21:34:05Z",
    "approval_decision": "APPROVE_PAPER_PROMOTION_REVIEW",
    "merge_policy_note": "MERGE_POLICY_VIOLATION_RECORDED",
}
APPROVAL_SCOPE_TRUE_FLAGS = tuple(
    "paper_only simulation_only deribit_public_market_data_only no_private_api no_credentials no_exchange_orders no_execution_adapter no_order_routing no_scheduler no_automatic_paper_loop no_strategy_signal no_shadow no_live".split()
)
FALSE_SCOPE_FLAGS = tuple(
    "promotion_granted campaign_execution session_execution run_execution ledger_mutated live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled".split()
)
SAFETY_FLAGS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _phase56_proposal() -> dict[str, object]:
    return _json(PHASE56_PROPOSAL)


def _phase55_readiness() -> dict[str, object]:
    return _json(PHASE55_READINESS)


def _approval() -> dict[str, object]:
    return _json(APPROVAL)


def _mutated(mapping: dict[str, object], **updates: object) -> dict[str, object]:
    next_mapping = copy.deepcopy(mapping)
    next_mapping.update(updates)
    return next_mapping


def _mutated_scope(approval: dict[str, object], **updates: object) -> dict[str, object]:
    next_approval = copy.deepcopy(approval)
    next_approval["approval_scope"] = dict(next_approval["approval_scope"], **updates)
    return next_approval


def _is_utc_z(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo == timezone.utc
    except ValueError:
        return False


def _expected_approval(phase56: dict[str, object], phase55: dict[str, object]) -> dict[str, object]:
    return execute_deribit_operator_promotion_approval(
        phase56,
        phase55,
        reviewed_at_iso=APPROVAL_METADATA["reviewed_at_iso"],
        merge_policy_note=DERIBIT_PHASE57_MERGE_POLICY_NOTE,
    ).artifact_payload


def _maybe(reason: str, condition: bool) -> tuple[str, ...]:
    return (reason,) if condition else ()


def _approval_rejection_reasons(
    phase56: dict[str, object], phase55: dict[str, object], approval: dict[str, object]
) -> tuple[str, ...]:
    expected = _expected_approval(phase56, phase55)
    reasons = [
        *_maybe(
            "approval:schema_version_mismatch",
            approval.get("schema_version") != "deribit_paper_performance_operator_promotion_approval.v1",
        ),
        *_maybe("approval:phase_mismatch", approval.get("phase") != "57"),
        *_maybe(
            "approval:source_mismatch", approval.get("source") != "deterministic_phase57_operator_promotion_approval"
        ),
        *_maybe(
            "approval:source_phase56_mismatch",
            approval.get("source_phase56_operator_promotion_review_proposal")
            != str(PHASE56_PROPOSAL).replace("\\", "/"),
        ),
        *_maybe(
            "approval:source_phase55_mismatch",
            approval.get("source_phase55_promotion_readiness") != str(PHASE55_READINESS).replace("\\", "/"),
        ),
        *_maybe(
            "approval:source_phase56_proposal_status_mismatch",
            approval.get("source_phase56_proposal_status") != phase56.get("proposal_status"),
        ),
        *_maybe(
            "approval:source_phase56_approval_status_mismatch",
            approval.get("source_phase56_approval_status") != phase56.get("approval_status"),
        ),
        *_maybe(
            "approval:source_phase55_verdict_mismatch",
            approval.get("source_phase55_promotion_readiness_verdict") != phase55.get("promotion_readiness_verdict"),
        ),
        *_maybe(
            "approval:phase56_not_ready_for_operator_promotion_review",
            phase56.get("proposal_status") != "READY_FOR_OPERATOR_REVIEW",
        ),
        *_maybe("approval:phase56_already_approved_or_invalid", phase56.get("approval_status") != "NOT_APPROVED"),
        *_maybe("approval:phase56_ready_flag_not_true", phase56.get("ready_for_operator_promotion_review") is not True),
        *_maybe(
            "approval:phase55_not_ready_for_operator_promotion_review",
            phase55.get("promotion_readiness_verdict") != "READY_FOR_OPERATOR_REVIEW",
        ),
        *_maybe("approval:phase55_ready_flag_not_true", phase55.get("ready_for_operator_promotion_review") is not True),
        *_maybe("approval:approval_status_not_approved", approval.get("approval_status") != "APPROVED"),
        *(
            f"approval:{field}_mismatch"
            for field, expected_value in APPROVAL_METADATA.items()
            if approval.get(field) != expected_value
        ),
        *_maybe("approval:reviewed_at_iso_not_utc_z", not _is_utc_z(approval.get("reviewed_at_iso"))),
        *_maybe(
            "approval:operator_metadata_source_mismatch",
            approval.get("operator_metadata_source") != "explicit_user_approval_in_chat",
        ),
        *_maybe(
            "approval:approval_checks_mismatch", approval.get("approval_checks") != expected.get("approval_checks")
        ),
        *_maybe(
            "approval:connector_ready_count_mismatch",
            approval.get("connector_ready_dialects_count") != len(connector_ready_dialects()),
        ),
        *_maybe("approval:reason_code_mismatch", approval.get("reason_code") != expected.get("reason_code")),
        *_maybe(
            "approval:rejection_reasons_mismatch",
            approval.get("rejection_reasons") != expected.get("rejection_reasons"),
        ),
        *_maybe("approval:next_blocker_mismatch", approval.get("next_blocker") != expected.get("next_blocker")),
    ]
    scope = approval.get("approval_scope") if isinstance(approval.get("approval_scope"), dict) else {}
    if not scope:
        reasons.append("approval:approval_scope_missing")
    reasons.extend(
        f"approval:approval_scope_{field}_not_true"
        for field in APPROVAL_SCOPE_TRUE_FLAGS
        if scope.get(field) is not True
    )
    reasons.extend(f"approval:{field}_not_false" for field in FALSE_SCOPE_FLAGS if approval.get(field) is not False)
    reasons.extend(f"approval:{field}_not_true" for field in SAFETY_FLAGS if approval.get(field) is not True)
    return tuple(dict.fromkeys(reasons))


def test_phase57b_artifact_has_required_schema_and_source_references() -> None:
    approval = _approval()
    assert PHASE56_PROPOSAL.exists() and PHASE55_READINESS.exists() and APPROVAL.exists()
    assert approval["schema_version"] == "deribit_paper_performance_operator_promotion_approval.v1"
    assert approval["phase"] == "57"
    assert approval["source"] == "deterministic_phase57_operator_promotion_approval"
    assert approval["source_phase56_operator_promotion_review_proposal"] == str(PHASE56_PROPOSAL).replace("\\", "/")
    assert approval["source_phase55_promotion_readiness"] == str(PHASE55_READINESS).replace("\\", "/")


def test_phase57b_artifact_matches_runtime_output_and_approved_state() -> None:
    approval = _approval()
    assert approval == _expected_approval(_phase56_proposal(), _phase55_readiness())
    assert approval["approval_status"] == "APPROVED"
    assert approval["operator_id"] == APPROVAL_METADATA["operator_id"]
    assert approval["approval_decision"] == APPROVAL_METADATA["approval_decision"]
    assert approval["promotion_granted"] is False
    assert _approval_rejection_reasons(_phase56_proposal(), _phase55_readiness(), approval) == ()


def test_phase57b_artifact_records_current_source_state_and_merge_policy_note() -> None:
    phase56 = _phase56_proposal()
    phase55 = _phase55_readiness()
    approval = _approval()
    assert phase56["proposal_status"] == "READY_FOR_OPERATOR_REVIEW"
    assert phase56["approval_status"] == "NOT_APPROVED"
    assert phase56["ready_for_operator_promotion_review"] is True
    assert phase55["promotion_readiness_verdict"] == "READY_FOR_OPERATOR_REVIEW"
    assert phase55["ready_for_operator_promotion_review"] is True
    assert len(connector_ready_dialects()) == 1 and approval["connector_ready_dialects_count"] == 1
    assert approval["merge_policy_note"] == APPROVAL_METADATA["merge_policy_note"]
