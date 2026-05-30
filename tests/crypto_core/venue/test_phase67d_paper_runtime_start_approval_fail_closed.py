from __future__ import annotations

from crypto_core.venue.deribit_paper_runtime_start_approval import execute_deribit_paper_runtime_start_approval
from tests.crypto_core.venue.test_phase67b_paper_runtime_start_approval_artifact import (
    APPROVAL_METADATA,
    FALSE_APPROVAL_DISABLED_FIELDS,
    PHASE65_FALSE_SOURCE_FIELDS,
    PHASE66_FALSE_SOURCE_FIELDS,
    SAFETY_FLAGS,
    _mutated,
    _phase65_execution,
    _phase66_proposal,
)


def _run_with(phase66: object, phase65: object, reviewed_at_iso: str = APPROVAL_METADATA["reviewed_at_iso"]):
    return execute_deribit_paper_runtime_start_approval(
        phase66,
        phase65,
        reviewed_at_iso=reviewed_at_iso,
    )


def test_phase67d_missing_or_malformed_sources_fail_closed() -> None:
    assert _run_with(None, _phase65_execution()).rejection_reasons == (
        "deribit_paper_runtime_start_approval:phase66_artifact_missing",
    )
    assert (
        "deribit_paper_runtime_start_approval:phase65_artifact_missing"
        in _run_with(
            _phase66_proposal(),
            None,
        ).rejection_reasons
    )


def test_phase67d_phase66_and_phase65_metadata_must_be_exact() -> None:
    for field, value in (
        ("source_phase65_runtime_enablement", "docs/crypto_core/TAMPERED_65B.json"),
        ("source_phase65_runtime_enablement_sha256", "OTHER_SHA"),
        ("source_phase64_runtime_enablement_approval", "docs/crypto_core/TAMPERED_64B.json"),
        ("source_phase64_runtime_enablement_approval_sha256", "OTHER_SHA"),
        ("proposal_status", "FAIL_CLOSED"),
        ("approval_status", "APPROVED"),
        ("runtime_start_approved", True),
        ("runtime_enabled", False),
        ("runtime_started", True),
        ("paper_promoted", False),
        ("promotion_granted", False),
        ("promotion_scope", "LIVE"),
        ("proposal_checks", []),
        ("next_blocker", "OTHER"),
    ):
        result = _run_with(_mutated(_phase66_proposal(), **{field: value}), _phase65_execution())

        assert "deribit_paper_runtime_start_approval:phase66_metadata_invalid" in result.rejection_reasons

    for field, value in (
        ("source_phase64_runtime_enablement_approval", "docs/crypto_core/TAMPERED_64B.json"),
        ("source_phase64_runtime_enablement_approval_sha256", "OTHER_SHA"),
        ("approval_status", "NOT_APPROVED"),
        ("approval_decision", "OTHER_DECISION"),
        ("operator_id", "other_operator"),
        ("reviewed_at_iso", "2026-05-26T19:42:54Z"),
        ("runtime_enablement_approved", False),
        ("runtime_enablement_execution_status", "FAIL_CLOSED"),
        ("runtime_enabled", False),
        ("paper_promoted", False),
        ("promotion_granted", False),
        ("promotion_scope", "LIVE"),
        ("next_blocker", "OTHER"),
    ):
        result = _run_with(_phase66_proposal(), _mutated(_phase65_execution(), **{field: value}))

        assert "deribit_paper_runtime_start_approval:phase65_metadata_invalid" in result.rejection_reasons


def test_phase67d_placeholder_timestamp_scope_and_source_drift_fail_closed() -> None:
    for field in ("reviewer_id", "reviewed_at_iso", "approval_scope", "approval_notes"):
        result = _run_with(_mutated(_phase66_proposal(), **{field: "demir_operator"}), _phase65_execution())

        assert "deribit_paper_runtime_start_approval:phase66_placeholder_metadata_invalid" in result.rejection_reasons

    assert (
        "deribit_paper_runtime_start_approval:reviewed_at_iso_invalid"
        in _run_with(
            _phase66_proposal(),
            _phase65_execution(),
            reviewed_at_iso="2026-05-28 09:36:15",
        ).rejection_reasons
    )
    assert (
        "deribit_paper_runtime_start_approval:reviewed_at_iso_mismatch"
        in _run_with(
            _phase66_proposal(),
            _phase65_execution(),
            reviewed_at_iso="2026-05-28T09:36:16Z",
        ).rejection_reasons
    )


def test_phase67d_runtime_scope_or_safety_drift_fails_closed() -> None:
    for field in PHASE66_FALSE_SOURCE_FIELDS:
        result = _run_with(_mutated(_phase66_proposal(), **{field: True}), _phase65_execution())

        assert "deribit_paper_runtime_start_approval:phase66_scope_flags_invalid" in result.rejection_reasons

    for field in SAFETY_FLAGS:
        result = _run_with(_mutated(_phase66_proposal(), **{field: False}), _phase65_execution())

        assert "deribit_paper_runtime_start_approval:phase66_safety_flags_invalid" in result.rejection_reasons

    for field in PHASE65_FALSE_SOURCE_FIELDS:
        result = _run_with(_phase66_proposal(), _mutated(_phase65_execution(), **{field: True}))

        assert "deribit_paper_runtime_start_approval:phase65_scope_flags_invalid" in result.rejection_reasons

    for field in SAFETY_FLAGS:
        result = _run_with(_phase66_proposal(), _mutated(_phase65_execution(), **{field: False}))

        assert "deribit_paper_runtime_start_approval:phase65_safety_flags_invalid" in result.rejection_reasons

    phase66_connector = _run_with(_mutated(_phase66_proposal(), connector_ready_dialects_count=2), _phase65_execution())
    assert (
        "deribit_paper_runtime_start_approval:phase66_connector_ready_dialects_invalid"
        in phase66_connector.rejection_reasons
    )

    phase65_connector = _run_with(_phase66_proposal(), _mutated(_phase65_execution(), connector_ready_dialects_count=2))
    assert (
        "deribit_paper_runtime_start_approval:phase65_connector_ready_dialects_invalid"
        in phase65_connector.rejection_reasons
    )


def test_phase67d_rejected_payload_forces_runtime_disabled_and_not_started() -> None:
    result = _run_with(
        _mutated(_phase66_proposal(), runtime_enabled=False, runtime_started=True, no_live=False),
        _phase65_execution(),
    )
    payload = result.artifact_payload

    assert result.accepted is False
    assert "deribit_paper_runtime_start_approval:phase66_metadata_invalid" in result.rejection_reasons
    assert "deribit_paper_runtime_start_approval:phase66_scope_flags_invalid" in result.rejection_reasons
    assert "deribit_paper_runtime_start_approval:phase66_safety_flags_invalid" in result.rejection_reasons
    assert payload["approval_status"] == "FAIL_CLOSED"
    assert payload["runtime_start_approved"] is False
    assert payload["runtime_enabled"] is False
    assert payload["runtime_started"] is False
    assert payload["next_blocker"] == "OPERATOR_PAPER_RUNTIME_START_APPROVAL_NOT_READY"
    for field in FALSE_APPROVAL_DISABLED_FIELDS:
        assert payload[field] is False
    for field in SAFETY_FLAGS:
        assert payload[field] is True
