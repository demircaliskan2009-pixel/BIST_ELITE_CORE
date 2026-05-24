from __future__ import annotations

from dataclasses import replace

from crypto_core.venue.deribit_paper_run_harness import (
    DeribitPaperRunHarnessInputs,
    run_deribit_bounded_paper_run_harness,
)
from tests.crypto_core.venue.test_phase40b_bounded_paper_run_artifact import _phase40_inputs, _phase40_request


def test_phase40e_duplicate_run_and_idempotency_key_cannot_double_mutate_ledger() -> None:
    request = _phase40_request()
    inputs = _phase40_inputs()

    first = run_deribit_bounded_paper_run_harness(request, inputs)
    assert first.accepted is True
    assert first.gate_result is not None
    assert first.gate_result.ledger_state is not None
    assert first.ledger_mutation_count == 1

    duplicate_inputs = replace(inputs, ledger_state=first.gate_result.ledger_state)
    second = run_deribit_bounded_paper_run_harness(request, duplicate_inputs)

    assert second.accepted is False
    assert second.trade_count_attempted == 1
    assert second.trade_count_accepted == 0
    assert second.fill_count == 0
    assert second.ledger_mutation_count == 0
    assert "deribit_paper_run_harness:gate_rejected" in second.rejection_reasons
    assert "deribit_paper_trade_gate:duplicate_run_id" in second.rejection_reasons
    assert "deribit_paper_trade_gate:duplicate_gate_idempotency_key" in second.rejection_reasons
    assert second.gate_result is not None
    assert second.gate_result.ledger_state == first.gate_result.ledger_state


def test_phase40e_duplicate_rejection_artifact_is_deterministic_and_non_mutating() -> None:
    request = _phase40_request()
    first = run_deribit_bounded_paper_run_harness(request, _phase40_inputs())
    assert first.gate_result is not None
    assert first.gate_result.ledger_state is not None
    duplicate_inputs = DeribitPaperRunHarnessInputs(
        intent=_phase40_inputs().intent,
        decision=_phase40_inputs().decision,
        fill_request=_phase40_inputs().fill_request,
        frame=_phase40_inputs().frame,
        ledger_state=first.gate_result.ledger_state,
    )

    one = run_deribit_bounded_paper_run_harness(request, duplicate_inputs)
    two = run_deribit_bounded_paper_run_harness(request, duplicate_inputs)

    assert one.artifact_payload == two.artifact_payload
    assert one.artifact_payload["ledger_mutation_count"] == 0
    assert one.artifact_payload["accepted"] is False
