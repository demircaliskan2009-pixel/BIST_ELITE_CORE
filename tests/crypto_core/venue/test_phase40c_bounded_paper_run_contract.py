from __future__ import annotations

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase40b_bounded_paper_run_artifact import _run_phase40_harness


def test_phase40c_current_readiness_preconditions_hold() -> None:
    readiness = evaluate_deribit_manual_review_readiness()

    assert readiness.accepted is True
    assert readiness.evidence_review_complete is True
    assert readiness.connector_enablement_ready is True
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert len(connector_ready_dialects()) == 1


def test_phase40c_explicit_operator_request_runs_phase37_gate_once() -> None:
    result = _run_phase40_harness()

    assert result.accepted is True
    assert result.run_id == "phase40-bounded-paper-run"
    assert result.trade_count_attempted == 1
    assert result.trade_count_accepted == 1
    assert result.fill_count == 1
    assert result.ledger_mutation_count == 1
    assert result.reason_code == "deribit_paper_run_harness:accepted"
    assert result.gate_result is not None
    assert result.gate_result.accepted is True
    assert result.gate_result.filled is True
    assert result.gate_result.ledger_mutated is True


def test_phase40c_run_artifact_contains_before_after_ledger_summaries() -> None:
    payload = _run_phase40_harness().artifact_payload
    before = payload["before_ledger_summary"]
    after = payload["after_ledger_summary"]

    assert isinstance(before, dict)
    assert isinstance(after, dict)
    assert before["applied_fill_count"] == 0
    assert before["applied_request_count"] == 0
    assert before["applied_idempotency_count"] == 0
    assert after["applied_fill_count"] == 1
    assert after["applied_request_count"] == 1
    assert after["applied_idempotency_count"] == 1
    assert after["position_qty"] == 0.5
