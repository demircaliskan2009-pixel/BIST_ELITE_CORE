from __future__ import annotations

from pathlib import Path

from tests.crypto_core.venue.test_phase67b_paper_runtime_start_approval_artifact import (
    _approval,
    _phase65_execution,
    _phase66_proposal,
)

DOC = Path("docs/crypto_core/PAPER_RUNTIME_START_OPERATOR_APPROVAL_EXECUTION_67A.md")
SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_67H.md")


def test_phase67f_approval_preserves_runtime_enablement_and_paper_only_policy() -> None:
    phase66 = _phase66_proposal()
    phase65 = _phase65_execution()
    approval = _approval()

    assert phase66["proposal_status"] == "READY_FOR_OPERATOR_REVIEW"
    assert phase66["approval_status"] == "NOT_APPROVED"
    assert phase65["runtime_enablement_execution_status"] == "EXECUTED"
    assert approval["approval_status"] == "APPROVED"
    assert approval["runtime_start_approved"] is True
    assert approval["runtime_enabled"] is True
    assert approval["runtime_started"] is False
    assert approval["promotion_scope"] == "PAPER_ONLY_SIMULATION_ONLY"
    assert approval["next_blocker"] == "APPROVED_PAPER_RUNTIME_START_EXECUTION_NOT_READY"


def test_phase67f_docs_and_summary_preserve_no_start_no_private_policy() -> None:
    doc_text = DOC.read_text(encoding="utf-8")
    summary_text = SUMMARY.read_text(encoding="utf-8")

    for required in (
        "does not start runtime",
        "runtime remains enabled and not started",
        "no-live",
        "no-private",
        "no-execution",
        "scheduler",
        "automatic paper loop",
        "order routing",
        "strategy generation",
    ):
        assert required in doc_text or required in summary_text
