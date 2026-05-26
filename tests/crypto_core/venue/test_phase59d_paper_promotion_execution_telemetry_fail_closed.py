from __future__ import annotations

from crypto_core.venue.deribit_paper_promotion_telemetry_audit import (
    audit_deribit_paper_promotion_execution_telemetry,
)
from tests.crypto_core.venue.test_phase59b_paper_promotion_execution_telemetry_artifact import (
    SAFETY_FLAGS,
    _mutated,
    _phase55_readiness,
    _phase58_execution,
)


def _run_with(phase58: object, phase55: object):
    return audit_deribit_paper_promotion_execution_telemetry(phase58, phase55)


PHASE58_FALSE_FLAGS = (
    "campaign_execution",
    "session_execution",
    "run_execution",
    "ledger_mutation",
    "ledger_mutated",
    "live_ready",
    "shadow_ready",
    "auto_loop_enabled",
    "scheduler_enabled",
    "live_enabled",
    "shadow_enabled",
)


def test_phase59d_missing_or_malformed_sources_fail_closed() -> None:
    assert _run_with(None, _phase55_readiness()).rejection_reasons == (
        "deribit_paper_promotion_telemetry_audit:phase58_artifact_missing",
    )
    assert (
        "deribit_paper_promotion_telemetry_audit:phase55_artifact_missing"
        in _run_with(_phase58_execution(), []).rejection_reasons
    )


def test_phase59d_phase58_metadata_must_be_exact() -> None:
    for field, value in (
        ("promotion_execution_status", "FAIL_CLOSED"),
        ("approved_action", "OTHER_ACTION"),
        ("promotion_scope", "LIVE"),
        ("approval_status", "NOT_APPROVED"),
        ("approval_decision", "OTHER"),
        ("next_blocker", "OTHER"),
    ):
        result = _run_with(_mutated(_phase58_execution(), **{field: value}), _phase55_readiness())

        assert "deribit_paper_promotion_telemetry_audit:phase58_metadata_invalid" in result.rejection_reasons


def test_phase59d_phase58_scope_or_safety_drift_fails_closed() -> None:
    for field in (
        "campaign_execution",
        "session_execution",
        "run_execution",
        "ledger_mutation",
        "ledger_mutated",
        "live_ready",
        "shadow_ready",
        "auto_loop_enabled",
        "scheduler_enabled",
        "live_enabled",
        "shadow_enabled",
    ):
        result = _run_with(_mutated(_phase58_execution(), **{field: True}), _phase55_readiness())

        assert "deribit_paper_promotion_telemetry_audit:phase58_scope_flags_invalid" in result.rejection_reasons

    for field in SAFETY_FLAGS:
        result = _run_with(_mutated(_phase58_execution(), **{field: False}), _phase55_readiness())

        assert "deribit_paper_promotion_telemetry_audit:phase58_safety_flags_invalid" in result.rejection_reasons


def test_phase59d_rejected_payload_forces_fail_closed_scope_and_safety() -> None:
    result = _run_with(_mutated(_phase58_execution(), live_enabled=True, no_live=False), _phase55_readiness())
    payload = result.artifact_payload

    assert result.accepted is False
    assert "deribit_paper_promotion_telemetry_audit:phase58_scope_flags_invalid" in result.rejection_reasons
    assert "deribit_paper_promotion_telemetry_audit:phase58_safety_flags_invalid" in result.rejection_reasons
    for field in PHASE58_FALSE_FLAGS:
        assert payload[field] is False
    for field in SAFETY_FLAGS:
        assert payload[field] is True


def test_phase59d_phase55_readiness_or_safety_drift_fails_closed() -> None:
    for field, value in (
        ("promotion_readiness_verdict", "FAIL_CLOSED"),
        ("ready_for_operator_promotion_review", False),
    ):
        result = _run_with(_phase58_execution(), _mutated(_phase55_readiness(), **{field: value}))

        assert "deribit_paper_promotion_telemetry_audit:phase55_metadata_invalid" in result.rejection_reasons

    bad_safety = _mutated(_phase55_readiness(), no_private_api=False)
    bad_connector = _mutated(_phase55_readiness(), connector_ready_dialects_count=0)
    assert (
        "deribit_paper_promotion_telemetry_audit:phase55_safety_flags_invalid"
        in _run_with(_phase58_execution(), bad_safety).rejection_reasons
    )
    assert (
        "deribit_paper_promotion_telemetry_audit:phase55_connector_ready_dialects_invalid"
        in _run_with(_phase58_execution(), bad_connector).rejection_reasons
    )
