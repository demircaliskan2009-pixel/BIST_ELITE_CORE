from __future__ import annotations

from crypto_core.venue.deribit_approved_paper_runtime_start import execute_deribit_approved_paper_runtime_start
from tests.crypto_core.venue.test_phase68b_approved_paper_runtime_start_artifact import (
    FALSE_EXECUTION_DISABLED_FIELDS,
    PHASE65_FALSE_SOURCE_FIELDS,
    PHASE67_FALSE_SOURCE_FIELDS,
    SAFETY_FLAGS,
    _mutated,
    _mutated_scope,
    _phase65_execution,
    _phase67_approval,
)


def _run_with(phase67: object, phase65: object):
    return execute_deribit_approved_paper_runtime_start(phase67, phase65)


def test_phase68d_missing_or_malformed_sources_fail_closed() -> None:
    assert _run_with(None, _phase65_execution()).rejection_reasons == (
        "deribit_approved_paper_runtime_start:phase67_artifact_missing",
    )
    assert (
        "deribit_approved_paper_runtime_start:phase65_artifact_missing"
        in _run_with(
            _phase67_approval(),
            None,
        ).rejection_reasons
    )


def test_phase68d_phase67_and_phase65_metadata_must_be_exact() -> None:
    for field, value in (
        ("source_phase66_runtime_start_proposal", "docs/crypto_core/TAMPERED_66B.json"),
        ("source_phase66_runtime_start_proposal_sha256", "OTHER_SHA"),
        ("source_phase65_runtime_enablement", "docs/crypto_core/TAMPERED_65B.json"),
        ("source_phase65_runtime_enablement_sha256", "OTHER_SHA"),
        ("source_phase66_proposal_status", "FAIL_CLOSED"),
        ("source_phase66_approval_status", "APPROVED"),
        ("source_phase65_runtime_enablement_status", "FAIL_CLOSED"),
        ("approval_status", "NOT_APPROVED"),
        ("approval_decision", "OTHER_DECISION"),
        ("operator_id", "other_operator"),
        ("reviewed_at_iso", "2026-05-28T09:36:16Z"),
        ("runtime_start_approved", False),
        ("runtime_enabled", False),
        ("runtime_started", True),
        ("paper_promoted", False),
        ("promotion_granted", False),
        ("promotion_scope", "LIVE"),
        ("approval_checks", []),
        ("next_blocker", "OTHER"),
    ):
        result = _run_with(_mutated(_phase67_approval(), **{field: value}), _phase65_execution())

        assert "deribit_approved_paper_runtime_start:phase67_metadata_invalid" in result.rejection_reasons

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
        result = _run_with(_phase67_approval(), _mutated(_phase65_execution(), **{field: value}))

        assert "deribit_approved_paper_runtime_start:phase65_metadata_invalid" in result.rejection_reasons


def test_phase68d_phase67_phase65_scope_or_safety_drift_fails_closed() -> None:
    for field in PHASE67_FALSE_SOURCE_FIELDS:
        result = _run_with(_mutated(_phase67_approval(), **{field: True}), _phase65_execution())

        assert "deribit_approved_paper_runtime_start:phase67_scope_flags_invalid" in result.rejection_reasons

    scope_result = _run_with(_mutated_scope(_phase67_approval(), no_live=False), _phase65_execution())
    assert "deribit_approved_paper_runtime_start:phase67_approval_scope_invalid" in scope_result.rejection_reasons

    for field in SAFETY_FLAGS:
        result = _run_with(_mutated(_phase67_approval(), **{field: False}), _phase65_execution())

        assert "deribit_approved_paper_runtime_start:phase67_safety_flags_invalid" in result.rejection_reasons

    for field in PHASE65_FALSE_SOURCE_FIELDS:
        result = _run_with(_phase67_approval(), _mutated(_phase65_execution(), **{field: True}))

        assert "deribit_approved_paper_runtime_start:phase65_scope_flags_invalid" in result.rejection_reasons

    for field in SAFETY_FLAGS:
        result = _run_with(_phase67_approval(), _mutated(_phase65_execution(), **{field: False}))

        assert "deribit_approved_paper_runtime_start:phase65_safety_flags_invalid" in result.rejection_reasons

    phase67_connector = _run_with(_mutated(_phase67_approval(), connector_ready_dialects_count=2), _phase65_execution())
    assert (
        "deribit_approved_paper_runtime_start:phase67_connector_ready_dialects_invalid"
        in phase67_connector.rejection_reasons
    )

    phase65_connector = _run_with(_phase67_approval(), _mutated(_phase65_execution(), connector_ready_dialects_count=2))
    assert (
        "deribit_approved_paper_runtime_start:phase65_connector_ready_dialects_invalid"
        in phase65_connector.rejection_reasons
    )


def test_phase68d_rejected_payload_forces_runtime_disabled_and_not_started() -> None:
    result = _run_with(
        _mutated(_phase67_approval(), runtime_enabled=False, runtime_started=True, no_live=False), _phase65_execution()
    )
    payload = result.artifact_payload

    assert result.accepted is False
    assert "deribit_approved_paper_runtime_start:phase67_metadata_invalid" in result.rejection_reasons
    assert "deribit_approved_paper_runtime_start:phase67_scope_flags_invalid" in result.rejection_reasons
    assert "deribit_approved_paper_runtime_start:phase67_safety_flags_invalid" in result.rejection_reasons
    assert payload["runtime_start_execution_status"] == "FAIL_CLOSED"
    assert payload["runtime_enabled"] is False
    assert payload["runtime_started"] is False
    assert payload["next_blocker"] == "APPROVED_PAPER_RUNTIME_START_EXECUTION_NOT_READY"
    for field in FALSE_EXECUTION_DISABLED_FIELDS:
        assert payload[field] is False
    for field in SAFETY_FLAGS:
        assert payload[field] is True
