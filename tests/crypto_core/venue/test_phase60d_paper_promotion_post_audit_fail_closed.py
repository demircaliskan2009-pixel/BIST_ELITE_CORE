from __future__ import annotations

from crypto_core.venue.deribit_paper_promotion_post_audit import (
    audit_deribit_paper_promotion_execution_post_audit,
)
from tests.crypto_core.venue.test_phase60b_paper_promotion_post_audit_artifact import (
    FALSE_EXECUTION_FLAGS,
    SAFETY_FLAGS,
    _mutated,
    _phase58_execution,
    _phase59_audit,
)


def _run_with(phase59: object, phase58: object):
    return audit_deribit_paper_promotion_execution_post_audit(phase59, phase58)


def test_phase60d_missing_or_malformed_sources_fail_closed() -> None:
    assert _run_with(None, _phase58_execution()).rejection_reasons == (
        "deribit_paper_promotion_post_audit:phase59_artifact_missing",
    )
    assert (
        "deribit_paper_promotion_post_audit:phase58_artifact_missing"
        in _run_with(_phase59_audit(), []).rejection_reasons
    )


def test_phase60d_phase59_metadata_must_be_exact() -> None:
    for field, value in (
        ("telemetry_audit_verdict", "FAIL_CLOSED"),
        ("promotion_granted", False),
        ("promotion_scope", "LIVE"),
        ("paper_promoted", False),
        ("report_only", False),
        ("no_new_execution", False),
        ("next_blocker", "OTHER"),
    ):
        result = _run_with(_mutated(_phase59_audit(), **{field: value}), _phase58_execution())

        assert "deribit_paper_promotion_post_audit:phase59_metadata_invalid" in result.rejection_reasons


def test_phase60d_phase58_metadata_must_be_exact() -> None:
    for field, value in (
        ("source_phase57_operator_promotion_approval", "docs/crypto_core/TAMPERED_57B.json"),
        ("source_phase55_promotion_readiness", "docs/crypto_core/TAMPERED_55B.json"),
        ("promotion_execution_status", "FAIL_CLOSED"),
        ("approved_action", "OTHER_ACTION"),
        ("promotion_scope", "LIVE"),
        ("approval_status", "NOT_APPROVED"),
        ("approval_decision", "OTHER"),
        ("next_blocker", "OTHER"),
    ):
        result = _run_with(_phase59_audit(), _mutated(_phase58_execution(), **{field: value}))

        assert "deribit_paper_promotion_post_audit:phase58_metadata_invalid" in result.rejection_reasons


def test_phase60d_phase59_or_phase58_scope_or_safety_drift_fails_closed() -> None:
    for field in FALSE_EXECUTION_FLAGS:
        result = _run_with(_mutated(_phase59_audit(), **{field: True}), _phase58_execution())

        assert "deribit_paper_promotion_post_audit:phase59_scope_flags_invalid" in result.rejection_reasons

    for field in SAFETY_FLAGS:
        result = _run_with(_mutated(_phase59_audit(), **{field: False}), _phase58_execution())

        assert "deribit_paper_promotion_post_audit:phase59_safety_flags_invalid" in result.rejection_reasons

    for field in FALSE_EXECUTION_FLAGS:
        result = _run_with(_phase59_audit(), _mutated(_phase58_execution(), **{field: True}))

        assert "deribit_paper_promotion_post_audit:phase58_scope_flags_invalid" in result.rejection_reasons

    for field in SAFETY_FLAGS:
        result = _run_with(_phase59_audit(), _mutated(_phase58_execution(), **{field: False}))

        assert "deribit_paper_promotion_post_audit:phase58_safety_flags_invalid" in result.rejection_reasons


def test_phase60d_rejected_payload_forces_fail_closed_scope_and_safety() -> None:
    result = _run_with(_mutated(_phase59_audit(), live_enabled=True, no_live=False), _phase58_execution())
    payload = result.artifact_payload

    assert result.accepted is False
    assert "deribit_paper_promotion_post_audit:phase59_scope_flags_invalid" in result.rejection_reasons
    assert "deribit_paper_promotion_post_audit:phase59_safety_flags_invalid" in result.rejection_reasons
    for field in FALSE_EXECUTION_FLAGS:
        assert payload[field] is False
    for field in SAFETY_FLAGS:
        assert payload[field] is True
