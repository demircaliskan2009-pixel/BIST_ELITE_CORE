from __future__ import annotations

from tests.crypto_core.venue.test_phase46b_operator_proposal_artifact import (
    _mutated,
    _mutated_safety,
    _mutated_scope,
    _phase44_report_pack,
    _phase45_evaluation,
    _proposal,
    _proposal_rejection_reasons,
)


def test_phase46d_missing_or_malformed_source_fields_fail_closed() -> None:
    missing_source = _mutated(_proposal(), source_phase45_evaluation="")
    bad_hash = _mutated(_proposal(), source_phase45_evaluation_sha256="bad")

    assert "proposal:source_phase45_mismatch" in _proposal_rejection_reasons(
        _phase45_evaluation(), _phase44_report_pack(), missing_source
    )
    assert "proposal:source_phase45_hash_mismatch" in _proposal_rejection_reasons(
        _phase45_evaluation(), _phase44_report_pack(), bad_hash
    )


def test_phase46d_non_placeholder_approval_metadata_fails_closed() -> None:
    for field, value in (
        ("reviewer_id", "demir_operator"),
        ("reviewed_at_iso", "2026-05-25T00:00:00Z"),
        ("approval_scope", "BOUNDED_REPEATED_PAPER_CAMPAIGN"),
        ("approval_decision", "APPROVE"),
        ("approval_notes", "approved"),
    ):
        proposal = _mutated(_proposal(), **{field: value})
        reasons = _proposal_rejection_reasons(_phase45_evaluation(), _phase44_report_pack(), proposal)

        assert f"proposal:{field}_not_placeholder" in reasons


def test_phase46d_approval_or_promotion_flags_fail_closed() -> None:
    approved = _mutated(_proposal(), approval_status="APPROVED")
    promoted = _mutated(_proposal(), promotion_granted=True)
    no_operator_gate = _mutated(_proposal(), operator_approval_required=False)

    assert "proposal:approval_status_not_not_approved" in _proposal_rejection_reasons(
        _phase45_evaluation(), _phase44_report_pack(), approved
    )
    assert "proposal:promotion_granted_not_false" in _proposal_rejection_reasons(
        _phase45_evaluation(), _phase44_report_pack(), promoted
    )
    assert "proposal:operator_approval_required_not_true" in _proposal_rejection_reasons(
        _phase45_evaluation(), _phase44_report_pack(), no_operator_gate
    )


def test_phase46d_live_shadow_loop_scheduler_scope_flags_fail_closed() -> None:
    for field in ("live_enabled", "shadow_enabled", "auto_loop_enabled", "scheduler_enabled"):
        proposal = _mutated_scope(_proposal(), **{field: True})
        reasons = _proposal_rejection_reasons(_phase45_evaluation(), _phase44_report_pack(), proposal)

        assert f"proposal:campaign_scope_{field}_not_false" in reasons


def test_phase46d_private_execution_safety_flags_fail_closed() -> None:
    for field in ("no_private_api", "no_credentials", "no_exchange_orders", "no_execution_adapter"):
        proposal = _mutated_safety(_proposal(), **{field: False})
        reasons = _proposal_rejection_reasons(_phase45_evaluation(), _phase44_report_pack(), proposal)

        assert f"proposal:safety_{field}_not_true" in reasons
