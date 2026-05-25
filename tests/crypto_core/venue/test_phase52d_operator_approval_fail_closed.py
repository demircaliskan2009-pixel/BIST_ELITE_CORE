from __future__ import annotations

from tests.crypto_core.venue.test_phase52b_operator_approval_artifact import (
    APPROVAL_METADATA,
    _approval,
    _approval_rejection_reasons,
    _mutated,
    _mutated_scope,
    _phase49_audit,
    _phase50_evaluation,
    _phase51_proposal,
)


def _reasons(payload: dict[str, object]) -> tuple[str, ...]:
    return _approval_rejection_reasons(_phase51_proposal(), _phase50_evaluation(), _phase49_audit(), payload)


def test_phase52d_malformed_or_missing_metadata_fails_closed() -> None:
    for field in APPROVAL_METADATA:
        payload = _mutated(_approval(), **{field: ""})
        reasons = _reasons(payload)

        assert f"approval:{field}_mismatch" in reasons

    bad_timestamp = _mutated(_approval(), reviewed_at_iso="2026-05-25T17:47:42+03:00")
    assert "approval:reviewed_at_iso_mismatch" in _reasons(bad_timestamp)
    assert "approval:reviewed_at_iso_not_utc_z" in _reasons(bad_timestamp)


def test_phase52d_source_proposal_or_evaluation_drift_fails_closed() -> None:
    bad_phase51_status = _mutated(_approval(), source_phase51_proposal_status="NOT_READY")
    bad_phase51_approval = _mutated(_approval(), source_phase51_approval_status="APPROVED")
    bad_phase50_verdict = _mutated(_approval(), source_phase50_performance_evaluation_verdict="FAIL")
    bad_phase49_verdict = _mutated(_approval(), source_phase49_audit_verdict="FAIL")

    assert "approval:source_phase51_proposal_status_mismatch" in _reasons(bad_phase51_status)
    assert "approval:source_phase51_approval_status_mismatch" in _reasons(bad_phase51_approval)
    assert "approval:source_phase50_verdict_mismatch" in _reasons(bad_phase50_verdict)
    assert "approval:source_phase49_audit_verdict_mismatch" in _reasons(bad_phase49_verdict)


def test_phase52d_approval_scope_widening_fails_closed() -> None:
    bad_decision = _mutated(_approval(), approval_decision="APPROVE_LIVE_TRADING")
    bad_paper_scope = _mutated_scope(_approval(), paper_only=False)
    bad_sim_scope = _mutated_scope(_approval(), simulation_only=False)
    bad_deribit_scope = _mutated_scope(_approval(), deribit_public_market_data_only=False)
    bad_hard_cap = _mutated_scope(_approval(), hard_cap_unchanged=False)
    bad_trade_cap = _mutated_scope(_approval(), per_session_max_trades_unchanged=False)

    assert "approval:approval_decision_mismatch" in _reasons(bad_decision)
    assert "approval:approval_scope_paper_only_not_true" in _reasons(bad_paper_scope)
    assert "approval:approval_scope_simulation_only_not_true" in _reasons(bad_sim_scope)
    assert "approval:approval_scope_deribit_public_market_data_only_not_true" in _reasons(bad_deribit_scope)
    assert "approval:approval_scope_hard_cap_unchanged_not_true" in _reasons(bad_hard_cap)
    assert "approval:approval_scope_per_session_max_trades_unchanged_not_true" in _reasons(bad_trade_cap)


def test_phase52d_promotion_execution_or_ledger_mutation_fails_closed() -> None:
    for field in ("promotion_granted", "campaign_execution", "session_execution", "run_execution", "ledger_mutated"):
        payload = _mutated(_approval(), **{field: True})
        reasons = _reasons(payload)

        assert f"approval:{field}_not_false" in reasons


def test_phase52d_live_shadow_loop_scheduler_flags_fail_closed() -> None:
    for field in (
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


def test_phase52d_private_execution_safety_flags_fail_closed() -> None:
    for field in ("no_private_api", "no_credentials", "no_exchange_orders", "no_execution_adapter"):
        payload = _mutated(_approval(), **{field: False})
        reasons = _reasons(payload)

        assert f"approval:{field}_not_true" in reasons
