from __future__ import annotations

from tests.crypto_core.venue.test_phase44b_repeated_session_report_pack_artifact import (
    _mutated,
    _mutated_first_session,
    _promotion_readiness,
    _report_pack,
    _report_pack_rejection_reasons,
    _session_artifact,
)


def test_phase44d_missing_session_id_fails_closed() -> None:
    pack = _mutated_first_session(_report_pack(), session_id="")
    reasons = _report_pack_rejection_reasons(_session_artifact(), _promotion_readiness(), pack)

    assert "report_pack:session_id_missing" in reasons


def test_phase44d_duplicate_session_or_idempotency_fails_closed() -> None:
    pack = _report_pack()
    sessions = [dict(item) for item in pack["sessions"]]
    sessions[1]["session_id"] = sessions[0]["session_id"]
    duplicate_session = _mutated(pack, sessions=sessions)

    sessions = [dict(item) for item in pack["sessions"]]
    sessions[1]["idempotency_key_sha256"] = sessions[0]["idempotency_key_sha256"]
    duplicate_idempotency = _mutated(pack, sessions=sessions)

    assert "report_pack:duplicate_session_id" in _report_pack_rejection_reasons(
        _session_artifact(), _promotion_readiness(), duplicate_session
    )
    assert "report_pack:duplicate_idempotency" in _report_pack_rejection_reasons(
        _session_artifact(), _promotion_readiness(), duplicate_idempotency
    )


def test_phase44d_live_shadow_loop_scheduler_flags_fail_closed() -> None:
    for field in ("live_enabled", "shadow_enabled", "auto_loop_enabled", "scheduler_enabled"):
        bad_pack = _mutated(_report_pack(), **{field: True})
        reasons = _report_pack_rejection_reasons(_session_artifact(), _promotion_readiness(), bad_pack)

        assert f"report_pack:{field}_not_false" in reasons


def test_phase44d_private_execution_safety_flags_fail_closed() -> None:
    for field in (
        "no_private_api",
        "no_credentials",
        "no_exchange_orders",
        "no_execution_adapter",
        "no_order_routing",
        "no_strategy_signal",
    ):
        bad_pack = _mutated(_report_pack(), **{field: False})
        reasons = _report_pack_rejection_reasons(_session_artifact(), _promotion_readiness(), bad_pack)

        assert f"report_pack:{field}_not_true" in reasons


def test_phase44d_per_session_simulation_flag_fails_closed() -> None:
    pack = _mutated_first_session(_report_pack(), simulation_only=False)
    reasons = _report_pack_rejection_reasons(_session_artifact(), _promotion_readiness(), pack)

    assert "report_pack:session_simulation_only_not_true" in reasons


def test_phase44d_impossible_per_session_trade_counts_fail_closed() -> None:
    attempted_exceeds_requested = _mutated_first_session(
        _report_pack(),
        trades_requested=2,
        trades_attempted=3,
        trades_filled=3,
        trades_rejected=0,
        ledger_mutations=3,
    )
    fill_reject_mismatch = _mutated_first_session(
        _report_pack(),
        trades_requested=2,
        trades_attempted=2,
        trades_filled=3,
        trades_rejected=0,
        ledger_mutations=3,
    )
    ledger_mismatch = _mutated_first_session(
        _report_pack(),
        trades_requested=2,
        trades_attempted=2,
        trades_filled=2,
        trades_rejected=0,
        ledger_mutations=1,
    )

    assert "report_pack:session_attempted_exceeds_requested" in _report_pack_rejection_reasons(
        _session_artifact(), _promotion_readiness(), attempted_exceeds_requested
    )
    assert "report_pack:session_trade_count_mismatch" in _report_pack_rejection_reasons(
        _session_artifact(), _promotion_readiness(), fill_reject_mismatch
    )
    assert "report_pack:session_ledger_mutation_mismatch" in _report_pack_rejection_reasons(
        _session_artifact(), _promotion_readiness(), ledger_mismatch
    )


def test_phase44d_promotion_or_unbounded_session_fails_closed() -> None:
    promoted = _mutated(_report_pack(), promotion_granted=True)
    too_many_trades = _mutated_first_session(_report_pack(), trades_requested=3)

    assert "report_pack:promotion_granted_not_false" in _report_pack_rejection_reasons(
        _session_artifact(), _promotion_readiness(), promoted
    )
    assert "report_pack:session_exceeds_max_trades" in _report_pack_rejection_reasons(
        _session_artifact(), _promotion_readiness(), too_many_trades
    )
