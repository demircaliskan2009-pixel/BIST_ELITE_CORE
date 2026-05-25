from __future__ import annotations

from tests.crypto_core.venue.test_phase51b_operator_review_proposal_artifact import (
    _mutated,
    _phase50_evaluation,
    _proposal,
    _proposal_rejection_reasons,
)


def test_phase51d_missing_or_malformed_source_fields_fail_closed() -> None:
    proposal = _mutated(_proposal(), source_phase50_performance_evaluation="")
    bad_hash = _mutated(_proposal(), source_phase50_performance_evaluation_sha256="bad")
    bad_source = _mutated(_phase50_evaluation(), performance_evaluation_verdict="FAIL_CLOSED")

    assert "proposal:source_phase50_mismatch" in _proposal_rejection_reasons(_phase50_evaluation(), proposal)
    assert "proposal:source_phase50_hash_mismatch" in _proposal_rejection_reasons(_phase50_evaluation(), bad_hash)
    assert "proposal:phase50_not_pass" in _proposal_rejection_reasons(bad_source, _proposal())


def test_phase51d_non_placeholder_approval_metadata_fails_closed() -> None:
    for field, value in (
        ("reviewer_id", "demir_operator"),
        ("reviewed_at_iso", "2026-05-25T00:00:00Z"),
        ("approval_scope", "paper performance approved"),
        ("approval_notes", "approved"),
    ):
        proposal = _mutated(_proposal(), **{field: value})
        reasons = _proposal_rejection_reasons(_phase50_evaluation(), proposal)

        assert f"proposal:{field}_not_placeholder" in reasons

    decision = _mutated(_proposal(), approval_decision="APPROVE")
    assert "proposal:approval_decision_not_placeholder" in _proposal_rejection_reasons(_phase50_evaluation(), decision)


def test_phase51d_approval_or_promotion_flags_fail_closed() -> None:
    approved = _mutated(_proposal(), approval_status="APPROVED")
    promoted = _mutated(_proposal(), promotion_granted=True)

    assert "proposal:approval_status_not_not_approved" in _proposal_rejection_reasons(_phase50_evaluation(), approved)
    assert "proposal:promotion_granted_not_false" in _proposal_rejection_reasons(_phase50_evaluation(), promoted)


def test_phase51d_live_shadow_scheduler_execution_drift_fails_closed() -> None:
    for field in (
        "live_ready",
        "shadow_ready",
        "live_enabled",
        "shadow_enabled",
        "scheduler_enabled",
        "auto_loop_enabled",
    ):
        proposal = _mutated(_proposal(), **{field: True})
        reasons = _proposal_rejection_reasons(_phase50_evaluation(), proposal)

        assert f"proposal:{field}_not_false" in reasons

    for field in ("no_private_api", "no_credentials", "no_exchange_orders", "no_execution_adapter"):
        proposal = _mutated(_proposal(), **{field: False})
        reasons = _proposal_rejection_reasons(_phase50_evaluation(), proposal)

        assert f"proposal:{field}_not_true" in reasons
