from __future__ import annotations

import copy
from dataclasses import replace

from crypto_core.venue.deribit_bounded_paper_campaign import run_deribit_bounded_paper_campaign
from tests.crypto_core.venue.test_phase47b_operator_approval_artifact import _approval
from tests.crypto_core.venue.test_phase48c_campaign_execution_contract import (
    _ledger,
    _phase48_request,
    _phase48_sessions,
    _trade_input,
)


def _rejects(request, approval, sessions, expected_reason: str, *, kill_switch_active: bool = False) -> None:
    result = run_deribit_bounded_paper_campaign(
        request,
        approval,
        sessions,
        _ledger(),
        kill_switch_active=kill_switch_active,
    )

    assert result.accepted is False
    assert expected_reason in result.rejection_reasons


def test_phase48d_missing_or_unapproved_approval_fails_closed() -> None:
    _rejects(_phase48_request(), None, _phase48_sessions(), "deribit_bounded_paper_campaign:approval_artifact_missing")

    bad_approval = copy.deepcopy(_approval())
    bad_approval["approval_status"] = "NOT_APPROVED"
    _rejects(
        _phase48_request(),
        bad_approval,
        _phase48_sessions(),
        "deribit_bounded_paper_campaign:approval_status_not_approved",
    )


def test_phase48d_invalid_request_flags_fail_closed() -> None:
    base = _phase48_request()
    cases = (
        (replace(base, simulation_only=False), "deribit_bounded_paper_campaign:not_simulation_only"),
        (replace(base, live_enabled=True), "deribit_bounded_paper_campaign:live_enabled"),
        (replace(base, shadow_enabled=True), "deribit_bounded_paper_campaign:shadow_enabled"),
        (replace(base, auto_loop_enabled=True), "deribit_bounded_paper_campaign:auto_loop_enabled"),
        (replace(base, scheduler_enabled=True), "deribit_bounded_paper_campaign:scheduler_enabled"),
        (replace(base, approved_campaign=False), "deribit_bounded_paper_campaign:campaign_not_approved"),
    )

    for request, expected_reason in cases:
        _rejects(request, _approval(), _phase48_sessions(), expected_reason)


def test_phase48d_hard_bounds_and_kill_switch_fail_closed() -> None:
    _rejects(
        replace(_phase48_request(), hard_cap=4),
        _approval(),
        _phase48_sessions(),
        "deribit_bounded_paper_campaign:hard_cap_mismatch",
    )
    _rejects(
        replace(_phase48_request(), per_session_max_trades=3),
        _approval(),
        _phase48_sessions(),
        "deribit_bounded_paper_campaign:per_session_max_trades_mismatch",
    )
    _rejects(
        replace(_phase48_request(), max_campaign_sessions=2),
        _approval(),
        _phase48_sessions(),
        "deribit_bounded_paper_campaign:session_count_exceeds_campaign_bound",
    )
    oversized_fixture = replace(
        _phase48_sessions()[0],
        trade_inputs=(
            *_phase48_sessions()[0].trade_inputs,
            _trade_input("phase48-oversized-session-trade-3"),
        ),
    )
    _rejects(
        _phase48_request(),
        _approval(),
        (oversized_fixture, *_phase48_sessions()[1:]),
        "deribit_bounded_paper_campaign:session_trade_count_exceeds_session_bound",
    )
    _rejects(
        _phase48_request(),
        _approval(),
        _phase48_sessions(),
        "deribit_bounded_paper_campaign:kill_switch_active",
        kill_switch_active=True,
    )


def test_phase48d_malformed_trade_input_fails_closed_without_attribute_error() -> None:
    sessions = list(_phase48_sessions())
    sessions[0] = replace(sessions[0], trade_inputs=("malformed", sessions[0].trade_inputs[1]))
    result = run_deribit_bounded_paper_campaign(_phase48_request(), _approval(), tuple(sessions), _ledger())

    assert result.accepted is False
    assert result.ledger_mutated is False
    assert "deribit_bounded_paper_campaign:session_trade_input_malformed" in result.rejection_reasons


def test_phase48d_malformed_approval_bounds_fail_closed_without_value_error() -> None:
    bad_approval = copy.deepcopy(_approval())
    bad_approval["campaign_bounds"]["max_sessions_approved"] = "three"
    bad_approval["campaign_bounds"]["max_total_paper_trades_approved"] = "six"
    result = run_deribit_bounded_paper_campaign(
        _phase48_request(),
        bad_approval,
        _phase48_sessions(),
        _ledger(),
    )

    assert result.accepted is False
    assert result.ledger_mutated is False
    assert "deribit_bounded_paper_campaign:approval_max_sessions_invalid" in result.rejection_reasons
    assert "deribit_bounded_paper_campaign:approval_max_total_trades_invalid" in result.rejection_reasons


def test_phase48d_rejected_session_result_stops_campaign_fail_closed() -> None:
    sessions = list(_phase48_sessions())
    bad_input = replace(
        sessions[0].trade_inputs[0], decision=replace(sessions[0].trade_inputs[0].decision, fill_request=None)
    )
    sessions[0] = replace(sessions[0], trade_inputs=(bad_input, sessions[0].trade_inputs[1]))
    result = run_deribit_bounded_paper_campaign(_phase48_request(), _approval(), tuple(sessions), _ledger())

    assert result.accepted is False
    assert result.ledger_mutated is False
    assert result.sessions_attempted == 1
    assert result.sessions_rejected == 1
    assert "deribit_bounded_paper_campaign:session_rejected" in result.rejection_reasons
    assert "deribit_paper_run_harness:fill_request_mismatch" in result.rejection_reasons
