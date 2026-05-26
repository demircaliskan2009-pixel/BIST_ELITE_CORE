from __future__ import annotations

from crypto_core.venue.deribit_approved_paper_runtime_enablement import (
    execute_deribit_approved_paper_runtime_enablement,
)
from tests.crypto_core.venue.test_phase65b_approved_paper_runtime_enablement_artifact import (
    FALSE_EXECUTION_DISABLED_FIELDS,
    PHASE64_FALSE_SOURCE_FIELDS,
    SAFETY_FLAGS,
    _mutated,
    _mutated_scope,
    _phase62_wiring,
    _phase64_approval,
)


def _run_with(phase64: object, phase62: object):
    return execute_deribit_approved_paper_runtime_enablement(phase64, phase62)


def test_phase65d_missing_or_malformed_sources_fail_closed() -> None:
    assert _run_with(None, _phase62_wiring()).rejection_reasons == (
        "deribit_approved_paper_runtime_enablement:phase64_artifact_missing",
    )
    assert (
        "deribit_approved_paper_runtime_enablement:phase62_artifact_missing"
        in _run_with(_phase64_approval(), None).rejection_reasons
    )


def test_phase65d_phase64_metadata_must_be_exact() -> None:
    for field, value in (
        ("source_phase63_runtime_enablement_proposal", "docs/crypto_core/TAMPERED_63B.json"),
        ("source_phase62_runtime_wiring", "docs/crypto_core/TAMPERED_62B.json"),
        ("source_phase63_runtime_enablement_proposal_sha256", "OTHER_SHA"),
        ("approval_status", "NOT_APPROVED"),
        ("approval_decision", "OTHER_DECISION"),
        ("operator_id", "other_operator"),
        ("reviewed_at_iso", "2026-05-26T19:42:54Z"),
        ("runtime_enablement_approved", False),
        ("paper_promoted", False),
        ("promotion_granted", False),
        ("promotion_scope", "LIVE"),
        ("next_blocker", "OTHER"),
    ):
        result = _run_with(_mutated(_phase64_approval(), **{field: value}), _phase62_wiring())

        assert "deribit_approved_paper_runtime_enablement:phase64_metadata_invalid" in result.rejection_reasons


def test_phase65d_phase62_metadata_must_be_exact() -> None:
    for field, value in (
        ("runtime_wiring_status", "FAIL_CLOSED"),
        ("ready_for_paper_runtime", False),
        ("promotion_scope", "LIVE"),
        ("next_blocker", "OTHER"),
    ):
        result = _run_with(_phase64_approval(), _mutated(_phase62_wiring(), **{field: value}))

        assert "deribit_approved_paper_runtime_enablement:phase62_metadata_invalid" in result.rejection_reasons


def test_phase65d_phase64_phase62_scope_or_safety_drift_fails_closed() -> None:
    for field in PHASE64_FALSE_SOURCE_FIELDS:
        result = _run_with(_mutated(_phase64_approval(), **{field: True}), _phase62_wiring())

        assert "deribit_approved_paper_runtime_enablement:phase64_scope_flags_invalid" in result.rejection_reasons

    scope_result = _run_with(_mutated_scope(_phase64_approval(), no_live=False), _phase62_wiring())
    assert "deribit_approved_paper_runtime_enablement:phase64_approval_scope_invalid" in scope_result.rejection_reasons

    for field in SAFETY_FLAGS:
        result = _run_with(_mutated(_phase64_approval(), **{field: False}), _phase62_wiring())

        assert "deribit_approved_paper_runtime_enablement:phase64_safety_flags_invalid" in result.rejection_reasons

    for field in PHASE64_FALSE_SOURCE_FIELDS:
        result = _run_with(_phase64_approval(), _mutated(_phase62_wiring(), **{field: True}))

        assert "deribit_approved_paper_runtime_enablement:phase62_scope_flags_invalid" in result.rejection_reasons

    for field in SAFETY_FLAGS:
        result = _run_with(_phase64_approval(), _mutated(_phase62_wiring(), **{field: False}))

        assert "deribit_approved_paper_runtime_enablement:phase62_safety_flags_invalid" in result.rejection_reasons

    phase64_connector = _run_with(_mutated(_phase64_approval(), connector_ready_dialects_count=2), _phase62_wiring())
    assert (
        "deribit_approved_paper_runtime_enablement:phase64_connector_ready_dialects_invalid"
        in phase64_connector.rejection_reasons
    )

    phase62_connector = _run_with(_phase64_approval(), _mutated(_phase62_wiring(), connector_ready_dialects_count=2))
    assert (
        "deribit_approved_paper_runtime_enablement:phase62_connector_ready_dialects_invalid"
        in phase62_connector.rejection_reasons
    )


def test_phase65d_rejected_payload_forces_runtime_disabled_and_no_live_scope() -> None:
    result = _run_with(_mutated(_phase64_approval(), runtime_started=True, no_live=False), _phase62_wiring())
    payload = result.artifact_payload

    assert result.accepted is False
    assert "deribit_approved_paper_runtime_enablement:phase64_scope_flags_invalid" in result.rejection_reasons
    assert "deribit_approved_paper_runtime_enablement:phase64_safety_flags_invalid" in result.rejection_reasons
    assert payload["runtime_enablement_execution_status"] == "FAIL_CLOSED"
    assert payload["runtime_enabled"] is False
    assert payload["runtime_started"] is False
    assert payload["promotion_scope"] == "PAPER_ONLY_SIMULATION_ONLY"
    assert payload["next_blocker"] == "APPROVED_PAPER_RUNTIME_ENABLEMENT_EXECUTION_NOT_READY"
    for field in FALSE_EXECUTION_DISABLED_FIELDS:
        assert payload[field] is False
    for field in SAFETY_FLAGS:
        assert payload[field] is True
