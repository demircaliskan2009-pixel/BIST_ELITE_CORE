from __future__ import annotations

from pathlib import Path

from tests.crypto_core.venue.test_phase60b_paper_promotion_post_audit_artifact import (
    _phase59_audit,
    _post_audit,
)

DOC = Path("docs/crypto_core/PAPER_PROMOTION_EXECUTION_POST_AUDIT_60A.md")
SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_60H.md")


def test_phase60f_post_audit_preserves_phase59_policy_envelope() -> None:
    phase59 = _phase59_audit()
    artifact = _post_audit()

    assert phase59["promotion_scope"] == artifact["promotion_scope"] == "PAPER_ONLY_SIMULATION_ONLY"
    assert phase59["promotion_granted"] is True and artifact["promotion_granted"] is True
    assert phase59["paper_promoted"] is True and artifact["paper_promoted"] is True
    assert artifact["next_blocker"] == "PAPER_PROMOTED_RUNTIME_READINESS_NOT_READY"
    assert artifact["post_audit_checks"] == [
        "source_hashes_stable",
        "no_live_scope_preserved",
        "no_private_execution_scope_preserved",
        "no_scheduler_loop_scope_preserved",
        "connector_ready_dialects_preserved",
    ]


def test_phase60f_docs_and_summary_preserve_no_private_no_new_execution_policy() -> None:
    doc_text = DOC.read_text(encoding="utf-8")
    summary_text = SUMMARY.read_text(encoding="utf-8")

    for required in (
        "no-live",
        "no-private",
        "no-new-execution",
        "scheduler",
        "automatic paper loop",
        "order routing",
        "strategy",
    ):
        assert required in doc_text or required in summary_text
