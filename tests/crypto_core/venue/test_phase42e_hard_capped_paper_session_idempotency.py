from __future__ import annotations

from dataclasses import replace

from crypto_core.venue.deribit_hard_capped_paper_session import run_deribit_hard_capped_paper_session
from tests.crypto_core.venue.test_phase42b_hard_capped_paper_session_artifact import (
    _phase42_request,
    _phase42_trade_inputs,
)


def test_phase42e_duplicate_trade_run_and_idempotency_cannot_double_mutate_ledger() -> None:
    request = _phase42_request()
    first = run_deribit_hard_capped_paper_session(request, _phase42_trade_inputs())
    assert first.accepted is True
    assert first.final_ledger_state is not None

    duplicate_inputs = _phase42_trade_inputs()
    duplicate_inputs = (replace(duplicate_inputs[0], ledger_state=first.final_ledger_state), *duplicate_inputs[1:])
    second = run_deribit_hard_capped_paper_session(request, duplicate_inputs)

    assert second.accepted is False
    assert second.trades_attempted == 1
    assert second.trades_filled == 0
    assert second.trades_rejected == 1
    assert second.ledger_mutated is False
    assert "deribit_hard_capped_paper_session:trade_rejected" in second.rejection_reasons
    assert "deribit_paper_trade_gate:duplicate_run_id" in second.rejection_reasons
    assert "deribit_paper_trade_gate:duplicate_gate_idempotency_key" in second.rejection_reasons


def test_phase42e_duplicate_session_identity_markers_fail_closed_before_trade_attempt() -> None:
    request = _phase42_request()
    trade_inputs = _phase42_trade_inputs()
    duplicate_ledger = replace(
        trade_inputs[0].ledger_state,
        applied_request_ids=(request.session_id,),
        applied_idempotency_keys=(request.idempotency_key,),
    )
    duplicate_inputs = (replace(trade_inputs[0], ledger_state=duplicate_ledger), *trade_inputs[1:])

    result = run_deribit_hard_capped_paper_session(request, duplicate_inputs)

    assert result.accepted is False
    assert result.trades_attempted == 0
    assert result.ledger_mutated is False
    assert "deribit_hard_capped_paper_session:duplicate_session_id" in result.rejection_reasons
    assert "deribit_hard_capped_paper_session:duplicate_session_idempotency_key" in result.rejection_reasons


def test_phase42e_duplicate_artifact_payload_is_deterministic() -> None:
    request = _phase42_request()
    first = run_deribit_hard_capped_paper_session(request, _phase42_trade_inputs())
    assert first.final_ledger_state is not None
    duplicate_inputs = _phase42_trade_inputs()
    duplicate_inputs = (replace(duplicate_inputs[0], ledger_state=first.final_ledger_state), *duplicate_inputs[1:])

    one = run_deribit_hard_capped_paper_session(request, duplicate_inputs)
    two = run_deribit_hard_capped_paper_session(request, duplicate_inputs)

    assert one.artifact_payload == two.artifact_payload
    assert one.artifact_payload["session_verdict"] == "FAIL_CLOSED"
    assert one.artifact_payload["trades_rejected"] == 1
