from __future__ import annotations

from crypto_core.venue.deribit_paper_runtime_start_proposal import propose_deribit_paper_runtime_start
from tests.crypto_core.venue.test_phase66b_paper_runtime_start_proposal_artifact import (
    FALSE_PROPOSAL_DISABLED_FIELDS,
    PHASE64_FALSE_SOURCE_FIELDS,
    PHASE65_FALSE_SOURCE_FIELDS,
    SAFETY_FLAGS,
    _mutated,
    _mutated_scope,
    _phase64_approval,
    _phase65_execution,
)


def _run_with(phase65: object, phase64: object):
    return propose_deribit_paper_runtime_start(phase65, phase64)


def test_phase66d_missing_or_malformed_sources_fail_closed() -> None:
    assert _run_with(None, _phase64_approval()).rejection_reasons == (
        "deribit_paper_runtime_start_proposal:phase65_artifact_missing",
    )
    assert (
        "deribit_paper_runtime_start_proposal:phase64_artifact_missing"
        in _run_with(
            _phase65_execution(),
            None,
        ).rejection_reasons
    )


def test_phase66d_phase65_metadata_must_be_exact() -> None:
    for field, value in (
        ("source_phase64_runtime_enablement_approval", "docs/crypto_core/TAMPERED_64B.json"),
        ("source_phase64_runtime_enablement_approval_sha256", "OTHER_SHA"),
        ("source_phase63_runtime_enablement_proposal", "docs/crypto_core/TAMPERED_63B.json"),
        ("source_phase62_runtime_wiring", "docs/crypto_core/TAMPERED_62B.json"),
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
        result = _run_with(_mutated(_phase65_execution(), **{field: value}), _phase64_approval())

        assert "deribit_paper_runtime_start_proposal:phase65_metadata_invalid" in result.rejection_reasons


def test_phase66d_phase64_metadata_must_be_exact() -> None:
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
        result = _run_with(_phase65_execution(), _mutated(_phase64_approval(), **{field: value}))

        assert "deribit_paper_runtime_start_proposal:phase64_metadata_invalid" in result.rejection_reasons


def test_phase66d_phase65_phase64_scope_or_safety_drift_fails_closed() -> None:
    for field in PHASE65_FALSE_SOURCE_FIELDS:
        result = _run_with(_mutated(_phase65_execution(), **{field: True}), _phase64_approval())

        assert "deribit_paper_runtime_start_proposal:phase65_scope_flags_invalid" in result.rejection_reasons

    for field in SAFETY_FLAGS:
        result = _run_with(_mutated(_phase65_execution(), **{field: False}), _phase64_approval())

        assert "deribit_paper_runtime_start_proposal:phase65_safety_flags_invalid" in result.rejection_reasons

    for field in PHASE64_FALSE_SOURCE_FIELDS:
        result = _run_with(_phase65_execution(), _mutated(_phase64_approval(), **{field: True}))

        assert "deribit_paper_runtime_start_proposal:phase64_scope_flags_invalid" in result.rejection_reasons

    scope_result = _run_with(_phase65_execution(), _mutated_scope(_phase64_approval(), no_live=False))
    assert "deribit_paper_runtime_start_proposal:phase64_approval_scope_invalid" in scope_result.rejection_reasons

    for field in SAFETY_FLAGS:
        result = _run_with(_phase65_execution(), _mutated(_phase64_approval(), **{field: False}))

        assert "deribit_paper_runtime_start_proposal:phase64_safety_flags_invalid" in result.rejection_reasons

    phase65_connector = _run_with(_mutated(_phase65_execution(), connector_ready_dialects_count=2), _phase64_approval())
    assert (
        "deribit_paper_runtime_start_proposal:phase65_connector_ready_dialects_invalid"
        in phase65_connector.rejection_reasons
    )

    phase64_connector = _run_with(_phase65_execution(), _mutated(_phase64_approval(), connector_ready_dialects_count=2))
    assert (
        "deribit_paper_runtime_start_proposal:phase64_connector_ready_dialects_invalid"
        in phase64_connector.rejection_reasons
    )


def test_phase66d_rejected_payload_forces_fail_closed_scope_and_safety() -> None:
    result = _run_with(
        _mutated(_phase65_execution(), runtime_enabled=False, runtime_started=True, no_live=False), _phase64_approval()
    )
    payload = result.artifact_payload

    assert result.accepted is False
    assert "deribit_paper_runtime_start_proposal:phase65_metadata_invalid" in result.rejection_reasons
    assert "deribit_paper_runtime_start_proposal:phase65_scope_flags_invalid" in result.rejection_reasons
    assert "deribit_paper_runtime_start_proposal:phase65_safety_flags_invalid" in result.rejection_reasons
    assert payload["proposal_status"] == "FAIL_CLOSED"
    assert payload["approval_status"] == "NOT_APPROVED"
    assert payload["runtime_start_approved"] is False
    assert payload["runtime_enabled"] is False
    assert payload["runtime_started"] is False
    assert payload["promotion_scope"] == "PAPER_ONLY_SIMULATION_ONLY"
    assert payload["next_blocker"] == "PAPER_RUNTIME_START_PROPOSAL_NOT_READY"
    for field in FALSE_PROPOSAL_DISABLED_FIELDS:
        assert payload[field] is False
    for field in SAFETY_FLAGS:
        assert payload[field] is True
