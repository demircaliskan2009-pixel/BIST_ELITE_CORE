from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_RUNTIME_ENABLEMENT_OPERATOR_APPROVAL_EXECUTION_64A.md")


def test_phase64a_doc_records_exact_operator_metadata_and_scope() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "Phase 64A - Paper Runtime Enablement Operator Approval Execution" in text
    assert "`approval_status` | `APPROVED`" in text
    assert "`operator_id` | `demir_operator`" in text
    assert "`reviewed_at_iso` | `2026-05-26T19:42:53Z`" in text
    assert "`approval_decision` | `APPROVE_PAPER_RUNTIME_ENABLEMENT_REVIEW`" in text
    assert "`runtime_enablement_approved` | `True`" in text
    assert "does not enable runtime and does not start runtime" in text
    assert "APPROVED_PAPER_RUNTIME_ENABLEMENT_EXECUTION_NOT_READY" in text
