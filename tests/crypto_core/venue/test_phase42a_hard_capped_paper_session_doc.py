from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/HARD_CAPPED_PAPER_SESSION_GATE_42A.md")


def _normalized_doc_text() -> str:
    return " ".join(DOC.read_text(encoding="utf-8").split())


def test_phase42a_doc_records_verified_phase41_state() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "status: HARD_CAPPED_PAPER_SESSION_GATE_READY" in text
    assert "`main` | `c7ba8ab9da34ef17288a123fbbc45e783c350ab2`" in text
    assert "`accepted` | `True`" in text
    assert "`connector_ready_dialects` | `1`" in text
    assert "`phase40_bounded_run_harness_status` | `READY`" in text
    assert "`phase41_telemetry_reporting_status` | `PASS`" in text


def test_phase42a_doc_defines_explicit_hard_capped_session_boundary() -> None:
    text = _normalized_doc_text()

    for required in (
        "explicit operator session request",
        "bounded list of explicit paper trade inputs",
        "Phase40 bounded run harness",
        "Phase37 paper trade gate",
        "The session hard cap is `3`",
        "`max_session_trades=2`",
    ):
        assert required in text


def test_phase42a_doc_keeps_scheduler_loop_live_and_strategy_out_of_scope() -> None:
    text = _normalized_doc_text()

    for required in (
        "does not discover trades",
        "generate strategy signals",
        "schedule itself",
        "loop automatically",
        "route exchange orders",
        "call private/live APIs",
        "Scheduler-driven operation, live trading, and shadow trading remain out of scope",
    ):
        assert required in text
