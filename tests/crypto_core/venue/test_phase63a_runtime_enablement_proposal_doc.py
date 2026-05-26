from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_RUNTIME_ENABLEMENT_OPERATOR_REVIEW_PROPOSAL_63A.md")


def test_phase63a_doc_exists_and_names_source() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "Phase 63A - Deribit Paper Runtime Enablement Operator Review Proposal" in text
    assert "DERIBIT_PAPER_PROMOTED_RUNTIME_WIRING_62B.json" in text
    assert "`runtime_wiring_status` | `WIRED`" in text
    assert "`proposal_status` | `READY_FOR_OPERATOR_REVIEW`" in text


def test_phase63a_doc_records_proposal_without_approval_or_runtime_start() -> None:
    text = " ".join(DOC.read_text(encoding="utf-8").split())

    for required in (
        "`approval_status` | `NOT_APPROVED`",
        "`operator_metadata_required` | `True`",
        "`runtime_enablement_approved` | `False`",
        "`runtime_enabled` | `False`",
        "`runtime_started` | `False`",
        "`live_ready` | `False`",
        "`shadow_ready` | `False`",
        "`campaign_execution` | `False`",
        "`ledger_mutation` | `False`",
        "does not approve runtime enablement",
        "does not enable runtime",
        "does not start runtime",
    ):
        assert required in text
