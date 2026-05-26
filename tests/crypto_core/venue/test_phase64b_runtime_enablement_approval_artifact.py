from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from crypto_core.venue.deribit_operator_runtime_enablement_approval import (
    DERIBIT_PHASE64_REVIEWED_AT_ISO,
    execute_deribit_operator_runtime_enablement_approval,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

PHASE63_PROPOSAL = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_ENABLEMENT_OPERATOR_REVIEW_PROPOSAL_63B.json")
PHASE62_WIRING = Path("docs/crypto_core/DERIBIT_PAPER_PROMOTED_RUNTIME_WIRING_62B.json")
APPROVAL = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_ENABLEMENT_OPERATOR_APPROVAL_64B.json")
APPROVAL_METADATA = {
    "operator_id": "demir_operator",
    "reviewed_at_iso": DERIBIT_PHASE64_REVIEWED_AT_ISO,
    "approval_decision": "APPROVE_PAPER_RUNTIME_ENABLEMENT_REVIEW",
}
APPROVAL_SCOPE_TRUE_FLAGS = tuple(
    "paper_only simulation_only deribit_public_market_data_only no_private_api no_credentials no_exchange_orders no_execution_adapter no_order_routing no_scheduler no_automatic_paper_loop no_strategy_signal no_shadow no_live".split()
)
FALSE_RUNTIME_FIELDS = tuple(
    "runtime_enabled runtime_started live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
SAFETY_FLAGS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _phase63_proposal() -> dict[str, object]:
    return _json(PHASE63_PROPOSAL)


def _phase62_wiring() -> dict[str, object]:
    return _json(PHASE62_WIRING)


def _approval() -> dict[str, object]:
    return _json(APPROVAL)


def _expected_approval(phase63: dict[str, object], phase62: dict[str, object]) -> dict[str, object]:
    return execute_deribit_operator_runtime_enablement_approval(
        phase63,
        phase62,
        reviewed_at_iso=APPROVAL_METADATA["reviewed_at_iso"],
    ).artifact_payload


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


def _maybe(reason: str, condition: bool) -> tuple[str, ...]:
    return (reason,) if condition else ()


def _approval_rejection_reasons(
    phase63: dict[str, object],
    phase62: dict[str, object],
    approval: dict[str, object],
) -> tuple[str, ...]:
    expected = _expected_approval(phase63, phase62)
    reasons = [
        *_maybe(
            "approval:schema_version_mismatch",
            approval.get("schema_version") != "deribit_paper_runtime_enablement_operator_approval.v1",
        ),
        *_maybe("approval:phase_mismatch", approval.get("phase") != "64"),
        *_maybe(
            "approval:source_mismatch",
            approval.get("source") != "deterministic_phase64_operator_runtime_enablement_approval",
        ),
        *_maybe(
            "approval:source_phase63_mismatch",
            approval.get("source_phase63_runtime_enablement_proposal") != str(PHASE63_PROPOSAL).replace("\\", "/"),
        ),
        *_maybe(
            "approval:source_phase62_mismatch",
            approval.get("source_phase62_runtime_wiring") != str(PHASE62_WIRING).replace("\\", "/"),
        ),
        *_maybe(
            "approval:source_phase63_hash_mismatch",
            approval.get("source_phase63_runtime_enablement_proposal_sha256")
            != expected.get("source_phase63_runtime_enablement_proposal_sha256"),
        ),
        *_maybe(
            "approval:source_phase62_hash_mismatch",
            approval.get("source_phase62_runtime_wiring_sha256")
            != expected.get("source_phase62_runtime_wiring_sha256"),
        ),
        *_maybe(
            "approval:source_phase63_proposal_status_mismatch",
            approval.get("source_phase63_proposal_status") != phase63.get("proposal_status"),
        ),
        *_maybe(
            "approval:source_phase63_approval_status_mismatch",
            approval.get("source_phase63_approval_status") != phase63.get("approval_status"),
        ),
        *_maybe(
            "approval:source_phase62_wiring_status_mismatch",
            approval.get("source_phase62_runtime_wiring_status") != phase62.get("runtime_wiring_status"),
        ),
        *_maybe(
            "approval:phase63_not_ready_for_operator_review",
            phase63.get("proposal_status") != "READY_FOR_OPERATOR_REVIEW",
        ),
        *_maybe("approval:phase63_already_approved_or_invalid", phase63.get("approval_status") != "NOT_APPROVED"),
        *_maybe("approval:phase62_not_wired", phase62.get("runtime_wiring_status") != "WIRED"),
        *_maybe("approval:approval_status_not_approved", approval.get("approval_status") != "APPROVED"),
        *(
            f"approval:{field}_mismatch"
            for field, expected_value in APPROVAL_METADATA.items()
            if approval.get(field) != expected_value
        ),
        *_maybe("approval:reviewed_at_iso_not_utc_z", not _is_utc_z(approval.get("reviewed_at_iso"))),
        *_maybe("approval:runtime_enablement_not_approved", approval.get("runtime_enablement_approved") is not True),
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
    reasons.extend(f"approval:{field}_not_false" for field in FALSE_RUNTIME_FIELDS if approval.get(field) is not False)
    reasons.extend(f"approval:{field}_not_true" for field in SAFETY_FLAGS if approval.get(field) is not True)
    return tuple(dict.fromkeys(reasons))


def test_phase64b_artifact_has_required_schema_and_source_references() -> None:
    approval = _approval()

    assert PHASE63_PROPOSAL.exists() and PHASE62_WIRING.exists() and APPROVAL.exists()
    assert approval["schema_version"] == "deribit_paper_runtime_enablement_operator_approval.v1"
    assert approval["phase"] == "64"
    assert approval["source"] == "deterministic_phase64_operator_runtime_enablement_approval"
    assert approval["source_phase63_runtime_enablement_proposal"] == str(PHASE63_PROPOSAL).replace("\\", "/")
    assert approval["source_phase62_runtime_wiring"] == str(PHASE62_WIRING).replace("\\", "/")


def test_phase64b_artifact_matches_runtime_output_and_approved_metadata() -> None:
    approval = _approval()

    assert approval == _expected_approval(_phase63_proposal(), _phase62_wiring())
    assert approval["approval_status"] == "APPROVED"
    for field, expected in APPROVAL_METADATA.items():
        assert approval[field] == expected
    assert _is_utc_z(approval["reviewed_at_iso"])
    assert _approval_rejection_reasons(_phase63_proposal(), _phase62_wiring(), approval) == ()


def test_phase64b_artifact_records_runtime_disabled_and_no_live_scope() -> None:
    approval = _approval()

    assert approval["runtime_enablement_approved"] is True
    assert approval["paper_promoted"] is True
    assert approval["promotion_granted"] is True
    assert approval["promotion_scope"] == "PAPER_ONLY_SIMULATION_ONLY"
    assert len(connector_ready_dialects()) == 1 and approval["connector_ready_dialects_count"] == 1
    for field in FALSE_RUNTIME_FIELDS:
        assert approval[field] is False
    for field in SAFETY_FLAGS:
        assert approval[field] is True
    for field in APPROVAL_SCOPE_TRUE_FLAGS:
        assert approval["approval_scope"][field] is True
