from __future__ import annotations

from dataclasses import replace

from crypto_core.venue.deribit_hard_capped_paper_session import run_deribit_hard_capped_paper_session
from tests.crypto_core.venue.test_phase42b_hard_capped_paper_session_artifact import (
    _phase42_request,
    _phase42_trade_inputs,
)


def _rejects(request, trade_inputs, expected_reason: str, *, kill_switch_active: bool = False) -> None:
    result = run_deribit_hard_capped_paper_session(request, trade_inputs, kill_switch_active=kill_switch_active)

    assert result.accepted is False
    assert result.ledger_mutated is False
    assert expected_reason in result.rejection_reasons


def test_phase42d_session_request_flags_fail_closed() -> None:
    base = _phase42_request()
    cases = (
        (replace(base, simulation_only=False), "deribit_hard_capped_paper_session:not_simulation_only"),
        (replace(base, live_enabled=True), "deribit_hard_capped_paper_session:live_enabled"),
        (replace(base, shadow_enabled=True), "deribit_hard_capped_paper_session:shadow_enabled"),
        (replace(base, auto_loop_enabled=True), "deribit_hard_capped_paper_session:auto_loop_enabled"),
        (replace(base, scheduler_enabled=True), "deribit_hard_capped_paper_session:scheduler_enabled"),
    )

    for request, expected_reason in cases:
        _rejects(request, _phase42_trade_inputs(), expected_reason)


def test_phase42d_missing_identity_fields_fail_closed() -> None:
    base = _phase42_request()
    cases = (
        (replace(base, operator_id=""), "deribit_hard_capped_paper_session:operator_id_missing"),
        (replace(base, session_id=""), "deribit_hard_capped_paper_session:session_id_missing"),
        (replace(base, idempotency_key=""), "deribit_hard_capped_paper_session:idempotency_key_missing"),
        (replace(base, idempotency_key=123), "deribit_hard_capped_paper_session:idempotency_key_missing"),
    )

    for request, expected_reason in cases:
        _rejects(request, _phase42_trade_inputs(), expected_reason)


def test_phase42d_non_string_idempotency_key_rejects_without_hash_crash() -> None:
    result = run_deribit_hard_capped_paper_session(
        replace(_phase42_request(), idempotency_key=123),
        _phase42_trade_inputs(),
    )

    assert result.accepted is False
    assert result.artifact_payload["idempotency_key_sha256"] is None
    assert "deribit_hard_capped_paper_session:idempotency_key_missing" in result.rejection_reasons


def test_phase42d_hard_cap_and_session_bound_fail_closed() -> None:
    _rejects(
        replace(_phase42_request(), max_session_trades=0),
        _phase42_trade_inputs(),
        "deribit_hard_capped_paper_session:max_session_trades_invalid",
    )
    _rejects(
        replace(_phase42_request(), max_session_trades=4),
        _phase42_trade_inputs(),
        "deribit_hard_capped_paper_session:max_session_trades_exceeds_hard_cap",
    )
    _rejects(
        replace(_phase42_request(), max_session_trades=1),
        _phase42_trade_inputs(),
        "deribit_hard_capped_paper_session:trade_count_exceeds_session_bound",
    )
    _rejects(
        replace(_phase42_request(), max_session_trades=3),
        _phase42_trade_inputs(count=4),
        "deribit_hard_capped_paper_session:trade_count_exceeds_hard_cap",
    )


def test_phase42d_kill_switch_and_missing_inputs_fail_closed() -> None:
    _rejects(
        _phase42_request(),
        _phase42_trade_inputs(),
        "deribit_hard_capped_paper_session:kill_switch_active",
        kill_switch_active=True,
    )
    _rejects(
        _phase42_request(),
        (),
        "deribit_hard_capped_paper_session:trade_inputs_missing",
    )
