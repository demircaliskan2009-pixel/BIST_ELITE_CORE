from __future__ import annotations

from dataclasses import replace

from crypto_core.venue.deribit_bounded_paper_campaign import run_deribit_bounded_paper_campaign
from tests.crypto_core.venue.test_phase47b_operator_approval_artifact import _approval
from tests.crypto_core.venue.test_phase48c_campaign_execution_contract import (
    _phase48_request,
    _phase48_sessions,
    _run_phase48_campaign,
)


def test_phase48e_duplicate_campaign_id_cannot_double_mutate_ledger() -> None:
    initial = _run_phase48_campaign()
    rerun = run_deribit_bounded_paper_campaign(
        _phase48_request(),
        _approval(),
        _phase48_sessions(),
        initial.final_ledger_state,
    )

    assert rerun.accepted is False
    assert rerun.ledger_mutated is False
    assert rerun.before_ledger_summary == rerun.after_ledger_summary
    assert "deribit_bounded_paper_campaign:duplicate_campaign_id" in rerun.rejection_reasons


def test_phase48e_duplicate_campaign_idempotency_key_cannot_double_mutate_ledger() -> None:
    initial = _run_phase48_campaign()
    retry_request = replace(
        _phase48_request(),
        campaign_id="phase48-bounded-paper-campaign-retry",
        idempotency_key="idem-phase48-bounded-paper-campaign",
    )
    rerun = run_deribit_bounded_paper_campaign(
        retry_request,
        _approval(),
        _phase48_sessions(),
        initial.final_ledger_state,
    )

    assert rerun.accepted is False
    assert rerun.ledger_mutated is False
    assert "deribit_bounded_paper_campaign:duplicate_campaign_idempotency_key" in rerun.rejection_reasons


def test_phase48e_duplicate_session_and_trade_identifiers_fail_closed() -> None:
    sessions = _phase48_sessions()
    duplicate_session = (
        sessions[0],
        replace(sessions[1], session_id=sessions[0].session_id),
        sessions[2],
    )
    duplicate_trade = (
        sessions[0],
        replace(sessions[1], trade_inputs=(sessions[0].trade_inputs[0], sessions[1].trade_inputs[1])),
        sessions[2],
    )

    duplicate_session_result = run_deribit_bounded_paper_campaign(
        _phase48_request(),
        _approval(),
        duplicate_session,
        _run_phase48_campaign().before_ledger_summary
        and __import__(
            "tests.crypto_core.venue.test_phase48c_campaign_execution_contract",
            fromlist=["_ledger"],
        )._ledger(),
    )
    duplicate_trade_result = run_deribit_bounded_paper_campaign(
        _phase48_request(),
        _approval(),
        duplicate_trade,
        __import__("tests.crypto_core.venue.test_phase48c_campaign_execution_contract", fromlist=["_ledger"])._ledger(),
    )

    assert duplicate_session_result.accepted is False
    assert duplicate_session_result.ledger_mutated is False
    assert "deribit_bounded_paper_campaign:duplicate_session_id" in duplicate_session_result.rejection_reasons
    assert duplicate_trade_result.accepted is False
    assert duplicate_trade_result.ledger_mutated is False
    assert "deribit_bounded_paper_campaign:duplicate_trade_request_id" in duplicate_trade_result.rejection_reasons
