from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_PROMOTED_RUNTIME_WIRING_62A.md")


def test_phase62a_doc_exists_and_names_sources() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "Phase 62A - Deribit Paper Promoted Runtime Wiring" in text
    assert "DERIBIT_PAPER_PROMOTED_RUNTIME_READINESS_61B.json" in text
    assert "DERIBIT_PAPER_PROMOTION_EXECUTION_POST_AUDIT_60B.json" in text
    assert "`runtime_readiness_verdict` | `PASS`" in text
    assert "`ready_for_paper_runtime` | `True`" in text


def test_phase62a_doc_records_wiring_without_runtime_start() -> None:
    text = " ".join(DOC.read_text(encoding="utf-8").split())

    for required in (
        "`runtime_wiring_status` | `WIRED`",
        "`runtime_enabled` | `False`",
        "`runtime_started` | `False`",
        "`promotion_scope` | `PAPER_ONLY_SIMULATION_ONLY`",
        "`live_ready` | `False`",
        "`shadow_ready` | `False`",
        "`campaign_execution` | `False`",
        "`ledger_mutation` | `False`",
        "does not start runtime",
        "does not set `runtime_enabled=true`",
        "does not execute any campaign/session/run path",
    ):
        assert required in text
