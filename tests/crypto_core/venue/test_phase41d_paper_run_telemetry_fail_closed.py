from __future__ import annotations

from tests.crypto_core.venue.test_phase41b_paper_run_telemetry_report_artifact import (
    _mutated,
    _report,
    _run_artifact,
    _telemetry_rejection_reasons,
)


def test_phase41d_missing_run_id_fails_closed() -> None:
    run = _mutated(_run_artifact(), run_id="")
    reasons = _telemetry_rejection_reasons(run, _report())

    assert "telemetry:run_id_missing" in reasons
    assert "telemetry:run_id_mismatch" in reasons


def test_phase41d_live_shadow_loop_and_scheduler_flags_fail_closed() -> None:
    run = _run_artifact()

    for field in ("live_enabled", "shadow_enabled", "auto_loop_enabled", "scheduler_enabled"):
        bad_report = _mutated(_report(), **{field: True})
        reasons = _telemetry_rejection_reasons(run, bad_report)

        assert f"telemetry:{field}_not_false" in reasons


def test_phase41d_private_execution_safety_flags_fail_closed() -> None:
    run = _run_artifact()

    for field in (
        "no_private_api",
        "no_credentials",
        "no_exchange_orders",
        "no_execution_adapter",
        "no_order_routing",
        "no_strategy_signal",
    ):
        bad_report = _mutated(_report(), **{field: False})
        reasons = _telemetry_rejection_reasons(run, bad_report)

        assert f"telemetry:{field}_not_true" in reasons


def test_phase41d_max_trades_widening_fails_closed() -> None:
    run = _run_artifact()
    bad_report = _mutated(_report(), max_trades=2)

    assert "telemetry:max_trades_not_one" in _telemetry_rejection_reasons(run, bad_report)


def test_phase41d_ledger_and_duplicate_requirements_fail_closed() -> None:
    run = _run_artifact()

    bad_ledger = _mutated(_report(), ledger_mutated=False)
    bad_duplicate = _mutated(_report(), duplicate_mutation_blocked=False)

    assert "telemetry:ledger_mutated_not_true" in _telemetry_rejection_reasons(run, bad_ledger)
    assert "telemetry:duplicate_mutation_not_blocked" in _telemetry_rejection_reasons(run, bad_duplicate)
