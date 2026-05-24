from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_RUN_TELEMETRY_REPORTING_GATE_41A.md")


def _normalized_doc_text() -> str:
    return " ".join(DOC.read_text(encoding="utf-8").split())


def test_phase41a_doc_records_verified_phase40_state() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "status: PAPER_RUN_TELEMETRY_REPORTING_READY" in text
    assert "`main` | `d7107e9b1a51d92a7c49c20c55b98fecf9ca31eb`" in text
    assert "`accepted` | `True`" in text
    assert "`connector_ready_dialects` | `1`" in text
    assert "`phase40_bounded_run_harness_status` | `READY`" in text
    assert "`phase40_max_trades` | `1`" in text


def test_phase41a_doc_keeps_reporting_only_scope() -> None:
    text = _normalized_doc_text()

    for required in (
        "does not run the Phase40 harness",
        "create a new trade",
        "increase the trade bound",
        "schedule work",
        "start a loop",
        "does not add new paper run execution",
        "private API",
        "execution adapters",
        "live trading",
    ):
        assert required in text


def test_phase41a_doc_defines_fail_closed_pass_criteria_and_next_phase() -> None:
    text = _normalized_doc_text()

    assert "Malformed fields, missing run identity, widened bounds" in text
    assert "`max_trades=1`" in text
    assert "hard-capped multi-run paper session gate" in text
    assert "Scheduler-driven operation, live trading, and shadow trading remain out of scope" in text
