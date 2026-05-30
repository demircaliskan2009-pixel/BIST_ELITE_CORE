from __future__ import annotations

from tests.crypto_core.venue.test_phase56b_operator_promotion_review_proposal_artifact import (
    _mutated,
    _phase54_telemetry,
    _phase55_readiness,
    _proposal,
    _proposal_rejection_reasons,
)


def test_phase56d_missing_or_malformed_source_fields_fail_closed() -> None:
    bad_phase55_source = _mutated(_proposal(), source_phase55_promotion_readiness="")
    bad_phase54_source = _mutated(_proposal(), source_phase54_execution_telemetry="")
    bad_phase55 = _mutated(_phase55_readiness(), promotion_readiness_verdict="FAIL_CLOSED")
    bad_phase54 = _mutated(_phase54_telemetry(), telemetry_audit_verdict="FAIL_CLOSED")

    assert "proposal:source_phase55_mismatch" in _proposal_rejection_reasons(
        _phase55_readiness(), _phase54_telemetry(), bad_phase55_source
    )
    assert "proposal:source_phase54_mismatch" in _proposal_rejection_reasons(
        _phase55_readiness(), _phase54_telemetry(), bad_phase54_source
    )
    assert "proposal:phase55_not_ready_for_operator_review" in _proposal_rejection_reasons(
        bad_phase55, _phase54_telemetry(), _proposal()
    )
    assert "proposal:phase54_telemetry_verdict_not_pass" in _proposal_rejection_reasons(
        _phase55_readiness(), bad_phase54, _proposal()
    )


def test_phase56d_non_placeholder_approval_metadata_fails_closed() -> None:
    for field, value in (
        ("reviewer_id", "operator_demir"),
        ("reviewed_at_iso", "2026-05-25T00:00:00Z"),
        ("approval_scope", "promote paper performance"),
        ("approval_notes", "approved"),
    ):
        proposal = _mutated(_proposal(), **{field: value})
        reasons = _proposal_rejection_reasons(_phase55_readiness(), _phase54_telemetry(), proposal)

        assert f"proposal:{field}_not_placeholder" in reasons

    decision = _mutated(_proposal(), approval_decision="APPROVE")
    assert "proposal:approval_decision_not_placeholder" in _proposal_rejection_reasons(
        _phase55_readiness(), _phase54_telemetry(), decision
    )


def test_phase56d_approval_or_promotion_or_live_flags_fail_closed() -> None:
    approved = _mutated(_proposal(), approval_status="APPROVED")
    promoted = _mutated(_proposal(), promotion_granted=True)

    assert "proposal:approval_status_not_not_approved" in _proposal_rejection_reasons(
        _phase55_readiness(), _phase54_telemetry(), approved
    )
    assert "proposal:promotion_granted_not_false" in _proposal_rejection_reasons(
        _phase55_readiness(), _phase54_telemetry(), promoted
    )

    for field in (
        "ready_for_live",
        "ready_for_shadow",
        "live_enabled",
        "shadow_enabled",
        "scheduler_enabled",
        "auto_loop_enabled",
    ):
        proposal = _mutated(_proposal(), **{field: True})
        reasons = _proposal_rejection_reasons(_phase55_readiness(), _phase54_telemetry(), proposal)

        assert f"proposal:{field}_not_false" in reasons
