from __future__ import annotations

from pathlib import Path

from tests.crypto_core.venue.test_phase68b_approved_paper_runtime_start_artifact import (
    _execution,
    _phase65_execution,
    _phase67_approval,
)

DOC = Path("docs/crypto_core/APPROVED_PAPER_RUNTIME_START_EXECUTION_68A.md")
SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_68H.md")


def test_phase68f_execution_preserves_paper_only_policy_while_starting_runtime() -> None:
    phase67 = _phase67_approval()
    phase65 = _phase65_execution()
    artifact = _execution()

    assert phase67["approval_status"] == "APPROVED"
    assert phase67["runtime_start_approved"] is True
    assert phase67["runtime_enabled"] is True
    assert phase67["runtime_started"] is False
    assert phase65["runtime_enablement_execution_status"] == "EXECUTED"
    assert artifact["runtime_start_execution_status"] == "EXECUTED"
    assert artifact["runtime_enabled"] is True
    assert artifact["runtime_started"] is True
    assert artifact["promotion_scope"] == "PAPER_ONLY_SIMULATION_ONLY"
    assert artifact["next_blocker"] == "PAPER_RUNTIME_START_TELEMETRY_NOT_READY"


def test_phase68f_docs_and_summary_preserve_no_private_no_execution_policy() -> None:
    doc_text = " ".join(DOC.read_text(encoding="utf-8").split())
    summary_text = " ".join(SUMMARY.read_text(encoding="utf-8").split())

    for required in (
        "starts approved paper runtime metadata",
        "started in paper metadata only",
        "no-live",
        "no-private",
        "no-new-execution",
        "scheduler",
        "automatic paper loop",
        "order routing",
        "strategy generation",
    ):
        assert required in doc_text or required in summary_text
