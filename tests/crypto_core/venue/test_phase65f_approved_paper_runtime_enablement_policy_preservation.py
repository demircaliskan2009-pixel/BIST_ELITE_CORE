from __future__ import annotations

from pathlib import Path

from tests.crypto_core.venue.test_phase65b_approved_paper_runtime_enablement_artifact import (
    _execution,
    _phase62_wiring,
    _phase64_approval,
)

DOC = Path("docs/crypto_core/APPROVED_PAPER_RUNTIME_ENABLEMENT_EXECUTION_65A.md")
SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_65H.md")


def test_phase65f_execution_preserves_approved_paper_only_policy() -> None:
    phase64 = _phase64_approval()
    phase62 = _phase62_wiring()
    artifact = _execution()

    assert phase64["approval_status"] == artifact["approval_status"] == "APPROVED"
    assert phase64["runtime_enablement_approved"] is True and artifact["runtime_enablement_approved"] is True
    assert phase62["runtime_wiring_status"] == artifact["runtime_wiring_status"] == "WIRED"
    assert artifact["runtime_enabled"] is True
    assert artifact["runtime_started"] is False
    assert artifact["promotion_scope"] == "PAPER_ONLY_SIMULATION_ONLY"
    assert artifact["next_blocker"] == "PAPER_RUNTIME_START_PROPOSAL_NOT_READY"


def test_phase65f_docs_and_summary_preserve_no_start_no_private_policy() -> None:
    doc_text = DOC.read_text(encoding="utf-8")
    summary_text = SUMMARY.read_text(encoding="utf-8")

    for required in (
        "does not start runtime",
        "no-live",
        "no-private",
        "no-new-execution",
        "scheduler",
        "automatic paper loop",
        "order routing",
        "strategy",
    ):
        assert required in doc_text or required in summary_text
