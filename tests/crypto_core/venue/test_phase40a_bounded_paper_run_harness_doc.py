from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/BOUNDED_OPERATOR_PAPER_RUN_HARNESS_40A.md")


def _normalized_doc_text() -> str:
    return " ".join(DOC.read_text(encoding="utf-8").split())


def test_phase40a_harness_design_doc_records_verified_phase39_state() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "status: BOUNDED_OPERATOR_PAPER_RUN_HARNESS_READY" in text
    assert "`main` | `3273468228766838c703028385fd56c1fc0ce60e`" in text
    assert "`accepted` | `True`" in text
    assert "`connector_ready_dialects` | `1`" in text
    assert "`phase38_proof_status` | `READY`" in text
    assert "`phase39_audit_verdict` | `PASS`" in text


def test_phase40a_harness_doc_keeps_manual_bounded_offline_scope() -> None:
    text = DOC.read_text(encoding="utf-8")

    for required in (
        "explicit operator request",
        "`simulation_only=True`",
        "`live_enabled=False`",
        "`shadow_enabled=False`",
        "`auto_loop_enabled=False`",
        "`scheduler_enabled=False`",
        "`max_trades=1`",
        "does not add private API",
        "automatic paper loops",
        "live trading",
    ):
        assert required in text


def test_phase40a_harness_doc_identifies_next_phase_without_scheduler_or_live_scope() -> None:
    text = _normalized_doc_text()

    assert "bounded paper run telemetry/reporting gate" in text
    assert "multi-run paper session gate with a hard cap" in text
    assert "Scheduler-driven operation, live trading, and shadow trading remain out of scope" in text
