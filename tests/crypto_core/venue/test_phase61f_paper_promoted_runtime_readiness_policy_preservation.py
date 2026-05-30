from __future__ import annotations

from pathlib import Path

from tests.crypto_core.venue.test_phase61b_paper_promoted_runtime_readiness_artifact import (
    _phase60_post_audit,
    _runtime_readiness,
)

DOC = Path("docs/crypto_core/PAPER_PROMOTED_RUNTIME_READINESS_61A.md")
SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_61H.md")


def test_phase61f_runtime_readiness_preserves_phase60_policy_envelope() -> None:
    phase60 = _phase60_post_audit()
    artifact = _runtime_readiness()

    assert phase60["promotion_scope"] == artifact["promotion_scope"] == "PAPER_ONLY_SIMULATION_ONLY"
    assert phase60["promotion_granted"] is True and artifact["promotion_granted"] is True
    assert phase60["paper_promoted"] is True and artifact["paper_promoted"] is True
    assert artifact["ready_for_paper_runtime"] is True
    assert artifact["runtime_enabled"] is False
    assert artifact["next_blocker"] == "PAPER_PROMOTED_RUNTIME_WIRING_NOT_READY"


def test_phase61f_docs_and_summary_preserve_no_runtime_no_private_policy() -> None:
    doc_text = DOC.read_text(encoding="utf-8")
    summary_text = SUMMARY.read_text(encoding="utf-8")

    for required in (
        "runtime",
        "no-live",
        "no-private",
        "no-new-execution",
        "scheduler",
        "automatic paper loop",
        "order-routing",
        "strategy",
    ):
        assert required in doc_text or required in summary_text
