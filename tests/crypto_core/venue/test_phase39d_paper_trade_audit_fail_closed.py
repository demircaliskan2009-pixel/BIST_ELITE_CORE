from __future__ import annotations

from tests.crypto_core.venue.test_phase39b_paper_trade_audit_report_artifact import (
    _audit_rejection_reasons,
    _mutated,
    _proof,
    _report,
)


def test_phase39d_missing_run_id_fails_closed() -> None:
    proof = _mutated(_proof(), run_id="")

    reasons = _audit_rejection_reasons(proof, _report())

    assert "audit:run_id_missing" in reasons
    assert "audit:run_id_mismatch" in reasons


def test_phase39d_live_shadow_and_auto_loop_flags_fail_closed() -> None:
    proof = _proof()

    for field in ("live_enabled", "shadow_enabled", "auto_loop_enabled"):
        report = _mutated(_report(), **{field: True})
        reasons = _audit_rejection_reasons(proof, report)

        assert f"audit:{field}_not_false" in reasons


def test_phase39d_private_order_and_execution_safety_flags_fail_closed() -> None:
    proof = _proof()

    for field in ("no_private_api", "no_credentials", "no_exchange_orders", "no_execution_adapter"):
        report = _mutated(_report(), **{field: False})
        reasons = _audit_rejection_reasons(proof, report)

        assert f"audit:{field}_not_true" in reasons


def test_phase39d_ledger_mutated_once_and_duplicate_guard_are_required() -> None:
    proof = _proof()

    assert "audit:ledger_mutation_not_confirmed" in _audit_rejection_reasons(
        proof,
        _mutated(_report(), ledger_mutated_once=False),
    )
    assert "audit:duplicate_mutation_not_blocked" in _audit_rejection_reasons(
        proof,
        _mutated(_report(), duplicate_mutation_blocked=False),
    )
