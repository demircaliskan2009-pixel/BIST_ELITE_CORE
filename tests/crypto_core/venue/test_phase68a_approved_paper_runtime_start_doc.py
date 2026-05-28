from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/APPROVED_PAPER_RUNTIME_START_EXECUTION_68A.md")


def _normalized_doc_text() -> str:
    return " ".join(DOC.read_text(encoding="utf-8").split())


def test_phase68a_doc_records_source_artifacts_and_verified_source_state() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "docs/crypto_core/DERIBIT_PAPER_RUNTIME_START_OPERATOR_APPROVAL_67B.json" in text
    assert "docs/crypto_core/DERIBIT_APPROVED_PAPER_RUNTIME_ENABLEMENT_EXECUTION_65B.json" in text
    for required in (
        "`approval_status` | `APPROVED`",
        "`runtime_start_approved` | `True`",
        "`runtime_enabled` | `True`",
        "`runtime_started` | `False`",
        "`source_phase65_runtime_enablement_status` | `EXECUTED`",
        "`connector_ready_dialects_count` | `1`",
    ):
        assert required in text


def test_phase68a_doc_records_runtime_start_execution_without_scope_widening() -> None:
    text = _normalized_doc_text()

    for required in (
        "`runtime_start_execution_status` | `EXECUTED`",
        "`runtime_enabled` | `True`",
        "`runtime_started` | `True`",
        "`paper_promoted` | `True`",
        "`promotion_granted` | `True`",
        "`promotion_scope` | `PAPER_ONLY_SIMULATION_ONLY`",
    ):
        assert required in text
    assert "starts approved paper runtime metadata" in text


def test_phase68a_doc_preserves_no_live_no_private_and_no_execution_boundary() -> None:
    text = _normalized_doc_text()

    for required in (
        "EXECUTES_runtime_start: true",
        "PAPER_RUNTIME_START_TELEMETRY_NOT_READY",
        "no-live",
        "no-private",
        "no-new-execution",
        "scheduler",
        "automatic paper loop",
        "order routing",
        "strategy generation",
    ):
        assert required in text
