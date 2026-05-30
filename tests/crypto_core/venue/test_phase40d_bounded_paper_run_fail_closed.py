from __future__ import annotations

from dataclasses import replace

from crypto_core.venue.deribit_paper_run_harness import (
    DeribitPaperRunOperatorRequest,
    run_deribit_bounded_paper_run_harness,
)
from tests.crypto_core.venue.test_phase40b_bounded_paper_run_artifact import _phase40_inputs, _phase40_request


def _rejects(request: DeribitPaperRunOperatorRequest, expected_reason: str) -> None:
    result = run_deribit_bounded_paper_run_harness(request, _phase40_inputs())

    assert result.accepted is False
    assert result.trade_count_attempted == 0
    assert result.ledger_mutation_count == 0
    assert expected_reason in result.rejection_reasons


def test_phase40d_operator_request_flags_fail_closed() -> None:
    base = _phase40_request()
    cases = (
        (replace(base, simulation_only=False), "deribit_paper_run_harness:not_simulation_only"),
        (replace(base, live_enabled=True), "deribit_paper_run_harness:live_enabled"),
        (replace(base, shadow_enabled=True), "deribit_paper_run_harness:shadow_enabled"),
        (replace(base, auto_loop_enabled=True), "deribit_paper_run_harness:auto_loop_enabled"),
        (replace(base, scheduler_enabled=True), "deribit_paper_run_harness:scheduler_enabled"),
    )

    for request, expected_reason in cases:
        _rejects(request, expected_reason)


def test_phase40d_missing_identity_fields_fail_closed() -> None:
    base = _phase40_request()
    cases = (
        (replace(base, operator_id=""), "deribit_paper_run_harness:operator_id_missing"),
        (replace(base, run_id=""), "deribit_paper_run_harness:run_id_missing"),
        (replace(base, idempotency_key=""), "deribit_paper_run_harness:idempotency_key_missing"),
    )

    for request, expected_reason in cases:
        _rejects(request, expected_reason)


def test_phase40d_run_bounds_fail_closed() -> None:
    base = _phase40_request()
    cases = (
        (replace(base, max_trades=0), "deribit_paper_run_harness:max_trades_invalid"),
        (replace(base, max_trades=-1), "deribit_paper_run_harness:max_trades_invalid"),
        (replace(base, max_trades=2), "deribit_paper_run_harness:max_trades_exceeds_phase40_bound"),
    )

    for request, expected_reason in cases:
        _rejects(request, expected_reason)


def test_phase40d_missing_or_malformed_inputs_fail_closed() -> None:
    result = run_deribit_bounded_paper_run_harness(_phase40_request(), None)

    assert result.accepted is False
    assert result.trade_count_attempted == 0
    assert result.ledger_mutation_count == 0
    assert result.rejection_reasons == ("deribit_paper_run_harness:inputs_missing",)


def test_phase40d_scope_markers_in_operator_request_fail_closed() -> None:
    _rejects(
        replace(_phase40_request(), run_id="phase40-live-route"),
        "deribit_paper_run_harness:operator_request_scope_invalid",
    )
