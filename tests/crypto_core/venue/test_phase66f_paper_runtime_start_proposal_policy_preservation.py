from __future__ import annotations

from pathlib import Path

from tests.crypto_core.venue.test_phase66b_paper_runtime_start_proposal_artifact import (
    _phase64_approval,
    _phase65_execution,
    _proposal,
)

DOC = Path("docs/crypto_core/PAPER_RUNTIME_START_OPERATOR_REVIEW_PROPOSAL_66A.md")
SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_66H.md")


def test_phase66f_proposal_preserves_runtime_enablement_and_paper_only_policy() -> None:
    phase65 = _phase65_execution()
    phase64 = _phase64_approval()
    proposal = _proposal()

    assert phase65["runtime_enablement_execution_status"] == "EXECUTED"
    assert phase64["approval_status"] == "APPROVED"
    assert proposal["proposal_status"] == "READY_FOR_OPERATOR_REVIEW"
    assert proposal["approval_status"] == "NOT_APPROVED"
    assert proposal["runtime_start_approved"] is False
    assert proposal["runtime_enabled"] is True
    assert proposal["runtime_started"] is False
    assert proposal["promotion_scope"] == "PAPER_ONLY_SIMULATION_ONLY"
    assert proposal["next_blocker"] == "OPERATOR_PAPER_RUNTIME_START_APPROVAL_NOT_READY"


def test_phase66f_docs_and_summary_preserve_no_start_no_private_policy() -> None:
    doc_text = DOC.read_text(encoding="utf-8")
    summary_text = SUMMARY.read_text(encoding="utf-8")

    for required in (
        "does not approve runtime start",
        "does not start runtime",
        "no-live",
        "no-private",
        "no-execution",
        "scheduler",
        "automatic paper loop",
        "order routing",
        "strategy generation",
    ):
        assert required in doc_text or required in summary_text
