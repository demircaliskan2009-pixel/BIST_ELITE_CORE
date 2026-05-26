from __future__ import annotations

from crypto_core.venue.deribit_operator_runtime_enablement_approval import (
    execute_deribit_operator_runtime_enablement_approval,
)
from tests.crypto_core.venue.test_phase64b_runtime_enablement_approval_artifact import (
    APPROVAL_METADATA,
    FALSE_RUNTIME_FIELDS,
    SAFETY_FLAGS,
    _mutated,
    _phase62_wiring,
    _phase63_proposal,
)


def _run_with(phase63: object, phase62: object, reviewed_at_iso: str = APPROVAL_METADATA["reviewed_at_iso"]):
    return execute_deribit_operator_runtime_enablement_approval(phase63, phase62, reviewed_at_iso=reviewed_at_iso)


def test_phase64d_missing_or_malformed_sources_fail_closed() -> None:
    assert (
        "deribit_operator_runtime_enablement_approval:phase63_artifact_missing"
        in _run_with(
            None,
            _phase62_wiring(),
        ).rejection_reasons
    )
    assert (
        "deribit_operator_runtime_enablement_approval:phase62_artifact_missing"
        in _run_with(
            _phase63_proposal(),
            None,
        ).rejection_reasons
    )
    assert (
        "deribit_operator_runtime_enablement_approval:phase63_artifact_missing"
        in _run_with(
            [],
            _phase62_wiring(),
        ).rejection_reasons
    )


def test_phase64d_phase63_metadata_must_remain_ready_and_unapproved() -> None:
    for field, value in (
        ("proposal_status", "FAIL_CLOSED"),
        ("approval_status", "APPROVED"),
        ("approval_decision", "APPROVE_PAPER_RUNTIME_ENABLEMENT_REVIEW"),
        ("runtime_enablement_approved", True),
        ("paper_promoted", False),
        ("promotion_granted", False),
        ("promotion_scope", "LIVE"),
        ("proposal_checks", []),
        ("next_blocker", "OTHER"),
    ):
        result = _run_with(_mutated(_phase63_proposal(), **{field: value}), _phase62_wiring())

        assert "deribit_operator_runtime_enablement_approval:phase63_metadata_invalid" in result.rejection_reasons


def test_phase64d_placeholder_metadata_timestamp_and_sources_fail_closed() -> None:
    for field in ("reviewer_id", "reviewed_at_iso", "approval_scope", "approval_notes"):
        result = _run_with(_mutated(_phase63_proposal(), **{field: "demir_operator"}), _phase62_wiring())

        assert (
            "deribit_operator_runtime_enablement_approval:phase63_placeholder_metadata_invalid"
            in result.rejection_reasons
        )

    assert (
        "deribit_operator_runtime_enablement_approval:reviewed_at_iso_invalid"
        in _run_with(_phase63_proposal(), _phase62_wiring(), reviewed_at_iso="2026-05-26 19:42:53").rejection_reasons
    )
    assert (
        "deribit_operator_runtime_enablement_approval:phase62_metadata_invalid"
        in _run_with(
            _phase63_proposal(),
            _mutated(_phase62_wiring(), runtime_wiring_status="FAIL_CLOSED"),
        ).rejection_reasons
    )


def test_phase64d_runtime_scope_or_safety_drift_fails_closed() -> None:
    for field in FALSE_RUNTIME_FIELDS:
        result = _run_with(_mutated(_phase63_proposal(), **{field: True}), _phase62_wiring())

        assert "deribit_operator_runtime_enablement_approval:phase63_scope_flags_invalid" in result.rejection_reasons

    for field in SAFETY_FLAGS:
        result = _run_with(_mutated(_phase63_proposal(), **{field: False}), _phase62_wiring())

        assert "deribit_operator_runtime_enablement_approval:phase63_safety_flags_invalid" in result.rejection_reasons

    result = _run_with(_phase63_proposal(), _mutated(_phase62_wiring(), connector_ready_dialects_count=2))
    assert (
        "deribit_operator_runtime_enablement_approval:phase62_connector_ready_dialects_invalid"
        in result.rejection_reasons
    )


def test_phase64d_rejected_payload_forces_runtime_disabled() -> None:
    result = _run_with(_mutated(_phase63_proposal(), runtime_started=True, no_live=False), _phase62_wiring())
    payload = result.artifact_payload

    assert result.accepted is False
    assert payload["approval_status"] == "FAIL_CLOSED"
    assert payload["runtime_enablement_approved"] is False
    assert payload["runtime_enabled"] is False
    assert payload["runtime_started"] is False
    assert payload["next_blocker"] == "OPERATOR_PAPER_RUNTIME_ENABLEMENT_APPROVAL_NOT_READY"
