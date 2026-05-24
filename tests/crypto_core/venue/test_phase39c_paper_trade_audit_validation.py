from __future__ import annotations

from tests.crypto_core.venue.test_phase39b_paper_trade_audit_report_artifact import (
    _audit_rejection_reasons,
    _proof,
    _report,
)


def test_phase39c_audit_report_references_exact_source_proof() -> None:
    proof = _proof()
    report = _report()

    assert report["source_proof_artifact"] == "docs/crypto_core/DERIBIT_FIRST_PAPER_TRADE_SMOKE_PROOF_38B.json"
    assert report["audited_run_id"] == proof["run_id"]
    assert report["audited_operator_id"] == proof["operator_id"]
    assert "source_proof_hash_matches" in report["proof_audit_checks"]


def test_phase39c_ledger_mutated_once_is_derived_from_before_after_counts() -> None:
    proof = _proof()
    report = _report()
    before = proof["before_ledger_summary"]
    after = proof["after_ledger_summary"]

    assert report["ledger_audit"]["before_applied_fill_count"] == before["applied_fill_count"] == 0
    assert report["ledger_audit"]["before_applied_request_count"] == before["applied_request_count"] == 0
    assert report["ledger_audit"]["before_applied_idempotency_count"] == before["applied_idempotency_count"] == 0
    assert report["ledger_audit"]["after_applied_fill_count"] == after["applied_fill_count"] == 1
    assert report["ledger_audit"]["after_applied_request_count"] == after["applied_request_count"] == 1
    assert report["ledger_audit"]["after_applied_idempotency_count"] == after["applied_idempotency_count"] == 1
    assert _audit_rejection_reasons(proof, report) == ()


def test_phase39c_duplicate_mutation_blocked_is_required_for_pass() -> None:
    report = _report()

    assert report["duplicate_mutation_blocked"] is True
    assert "duplicate_mutation_blocked" in report["proof_audit_checks"]
