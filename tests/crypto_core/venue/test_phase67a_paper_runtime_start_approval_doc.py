from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_RUNTIME_START_OPERATOR_APPROVAL_EXECUTION_67A.md")


def _normalized_doc_text() -> str:
    return " ".join(DOC.read_text(encoding="utf-8").split())


def test_phase67a_doc_records_source_artifacts_and_verified_source_state() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "docs/crypto_core/DERIBIT_PAPER_RUNTIME_START_OPERATOR_REVIEW_PROPOSAL_66B.json" in text
    assert "docs/crypto_core/DERIBIT_APPROVED_PAPER_RUNTIME_ENABLEMENT_EXECUTION_65B.json" in text
    for required in (
        "`proposal_status` | `READY_FOR_OPERATOR_REVIEW`",
        "`prior_approval_status` | `NOT_APPROVED`",
        "`runtime_start_approved` | `False`",
        "`runtime_enabled` | `True`",
        "`runtime_started` | `False`",
        "`paper_promoted` | `True`",
        "`promotion_granted` | `True`",
        "`promotion_scope` | `PAPER_ONLY_SIMULATION_ONLY`",
        "`connector_ready_dialects_count` | `1`",
    ):
        assert required in text


def test_phase67a_doc_records_exact_operator_approval_metadata_without_runtime_start() -> None:
    text = _normalized_doc_text()

    for required in (
        "`approval_status` | `APPROVED`",
        "`operator_id` | `demir_operator`",
        "`reviewed_at_iso` | `2026-05-28T09:36:15Z`",
        "`approval_decision` | `APPROVE_PAPER_RUNTIME_START_REVIEW`",
        "`runtime_start_approved` | `True`",
        "`runtime_enabled` | `True`",
        "`runtime_started` | `False`",
    ):
        assert required in text
    assert "does not start runtime" in text
    assert "runtime remains enabled and not started" in text


def test_phase67a_doc_preserves_no_live_no_private_and_no_execution_boundary() -> None:
    text = _normalized_doc_text()

    for required in (
        "APPROVED_PAPER_RUNTIME_START_EXECUTION_NOT_READY",
        "no-live",
        "no-private",
        "no-execution",
        "scheduler",
        "automatic paper loop",
        "order routing",
        "strategy generation",
    ):
        assert required in text
