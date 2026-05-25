from __future__ import annotations

from tests.crypto_core.venue.test_phase57b_operator_promotion_approval_artifact import (
    _approval,
    _approval_rejection_reasons,
    _mutated,
    _mutated_scope,
    _phase55_readiness,
    _phase56_proposal,
)


def _reasons(payload: dict[str, object]) -> tuple[str, ...]:
    return _approval_rejection_reasons(_phase56_proposal(), _phase55_readiness(), payload)


def test_phase57d_missing_or_malformed_source_fields_fail_closed() -> None:
    bad_phase56_source = _mutated(_approval(), source_phase56_operator_promotion_review_proposal="")
    bad_phase55_source = _mutated(_approval(), source_phase55_promotion_readiness="")
    bad_phase56 = _mutated(_phase56_proposal(), proposal_status="FAIL_CLOSED")
    bad_phase56_approval = _mutated(_phase56_proposal(), approval_status="APPROVED")
    bad_phase55 = _mutated(_phase55_readiness(), promotion_readiness_verdict="FAIL_CLOSED")

    assert "approval:source_phase56_mismatch" in _reasons(bad_phase56_source)
    assert "approval:source_phase55_mismatch" in _reasons(bad_phase55_source)
    assert "approval:phase56_not_ready_for_operator_promotion_review" in _approval_rejection_reasons(
        bad_phase56, _phase55_readiness(), _approval()
    )
    assert "approval:phase56_already_approved_or_invalid" in _approval_rejection_reasons(
        bad_phase56_approval, _phase55_readiness(), _approval()
    )
    assert "approval:phase55_not_ready_for_operator_promotion_review" in _approval_rejection_reasons(
        _phase56_proposal(), bad_phase55, _approval()
    )


def test_phase57d_non_exact_operator_metadata_fails_closed() -> None:
    for field, value in (
        ("operator_id", ""),
        ("reviewed_at_iso", "2026-05-25T21:34:05+03:00"),
        ("approval_decision", "APPROVE_LIVE_PROMOTION"),
        ("merge_policy_note", "NOT_RECORDED"),
    ):
        payload = _mutated(_approval(), **{field: value})
        reasons = _reasons(payload)

        assert f"approval:{field}_mismatch" in reasons

    bad_timestamp = _mutated(_approval(), reviewed_at_iso="2026-05-25 21:34:05")
    assert "approval:reviewed_at_iso_mismatch" in _reasons(bad_timestamp)
    assert "approval:reviewed_at_iso_not_utc_z" in _reasons(bad_timestamp)


def test_phase57d_scope_or_policy_widening_fails_closed() -> None:
    for field in (
        "paper_only",
        "simulation_only",
        "deribit_public_market_data_only",
        "no_private_api",
        "no_credentials",
        "no_exchange_orders",
        "no_execution_adapter",
        "no_order_routing",
        "no_scheduler",
        "no_automatic_paper_loop",
        "no_strategy_signal",
        "no_shadow",
        "no_live",
    ):
        payload = _mutated_scope(_approval(), **{field: False})
        reasons = _reasons(payload)

        assert f"approval:approval_scope_{field}_not_true" in reasons


def test_phase57d_promotion_execution_or_live_flags_fail_closed() -> None:
    for field in (
        "promotion_granted",
        "campaign_execution",
        "session_execution",
        "run_execution",
        "ledger_mutated",
        "live_ready",
        "shadow_ready",
        "live_enabled",
        "shadow_enabled",
        "auto_loop_enabled",
        "scheduler_enabled",
    ):
        payload = _mutated(_approval(), **{field: True})
        reasons = _reasons(payload)

        assert f"approval:{field}_not_false" in reasons


def test_phase57d_private_execution_safety_flags_fail_closed() -> None:
    for field in (
        "no_private_api",
        "no_credentials",
        "no_exchange_orders",
        "no_execution_adapter",
        "no_strategy_signal",
        "no_order_routing",
        "no_scheduler",
        "no_automatic_paper_loop",
        "no_shadow",
        "no_live",
    ):
        payload = _mutated(_approval(), **{field: False})
        reasons = _reasons(payload)

        assert f"approval:{field}_not_true" in reasons
