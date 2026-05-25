from __future__ import annotations

from tests.crypto_core.venue.test_phase47b_operator_approval_artifact import (
    APPROVAL_METADATA,
    _approval,
    _approval_rejection_reasons,
    _mutated,
    _mutated_bounds,
    _mutated_safety,
    _mutated_scope,
    _phase44_report_pack,
    _phase45_evaluation,
    _phase46_proposal,
)


def _reasons(payload: dict[str, object]) -> tuple[str, ...]:
    return _approval_rejection_reasons(_phase46_proposal(), _phase45_evaluation(), _phase44_report_pack(), payload)


def test_phase47d_malformed_or_missing_metadata_fails_closed() -> None:
    for field in APPROVAL_METADATA:
        payload = _mutated(_approval(), **{field: ""})
        reasons = _reasons(payload)

        assert f"approval:{field}_mismatch" in reasons


def test_phase47d_approval_outside_exact_scope_fails_closed() -> None:
    bad_scope = _mutated(_approval(), approval_scope="Deribit paper campaign with live path")
    bad_decision = _mutated(_approval(), approval_decision="APPROVE_LIVE_TRADING")
    bad_hard_cap = _mutated_bounds(_approval(), hard_cap=4)
    bad_trade_cap = _mutated_bounds(_approval(), per_session_max_trades=3)

    assert "approval:approval_scope_mismatch" in _reasons(bad_scope)
    assert "approval:approval_decision_mismatch" in _reasons(bad_decision)
    assert "approval:hard_cap_mismatch" in _reasons(bad_hard_cap)
    assert "approval:per_session_max_trades_mismatch" in _reasons(bad_trade_cap)


def test_phase47d_promotion_or_execution_status_fails_closed() -> None:
    promoted = _mutated(_approval(), promotion_granted=True)
    campaign_executed = _mutated(_approval(), campaign_execution_status="EXECUTED")
    session_executed = _mutated(_approval(), session_execution_status="EXECUTED")
    run_executed = _mutated(_approval(), run_execution_status="EXECUTED")

    assert "approval:promotion_granted_not_false" in _reasons(promoted)
    assert "approval:campaign_executed" in _reasons(campaign_executed)
    assert "approval:session_executed" in _reasons(session_executed)
    assert "approval:run_executed" in _reasons(run_executed)


def test_phase47d_live_shadow_loop_scheduler_flags_fail_closed() -> None:
    for field in ("live_enabled", "shadow_enabled", "auto_loop_enabled", "scheduler_enabled"):
        payload = _mutated_scope(_approval(), **{field: True})
        reasons = _reasons(payload)

        assert f"approval:campaign_scope_{field}_not_false" in reasons


def test_phase47d_private_execution_safety_flags_fail_closed() -> None:
    for field in ("no_private_api", "no_credentials", "no_exchange_orders", "no_execution_adapter"):
        payload = _mutated_safety(_approval(), **{field: False})
        reasons = _reasons(payload)

        assert f"approval:safety_{field}_not_true" in reasons
