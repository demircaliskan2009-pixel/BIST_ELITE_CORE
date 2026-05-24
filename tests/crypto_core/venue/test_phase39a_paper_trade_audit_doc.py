from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_TRADE_AUDIT_REPORTING_GATE_39A.md")


def test_phase39a_audit_doc_records_verified_phase38_state() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "status: PAPER_TRADE_AUDIT_REPORTING_GATE_READY" in text
    assert "| `main` | `9eafd7f599b58fa1ec86f4fd5eb7bfb12317080f` |" in text
    assert "| `accepted` | `True` |" in text
    assert "| `connector_ready_dialects` | `1` |" in text
    assert "| `phase38_proof_status` | `READY` |" in text
    assert "| `automatic_paper_loop_status` | `NO` |" in text
    assert "| `live_or_shadow_status` | `NO` |" in text


def test_phase39a_audit_doc_keeps_scope_to_reporting_only() -> None:
    text = DOC.read_text(encoding="utf-8").lower()

    assert "does not execute a new paper trade" in text
    assert "audit fails closed" in text
    assert "private api" in text
    assert "credentials" in text
    assert "exchange orders" in text
    assert "execution adapters" in text
    assert "scheduler" in text
    assert "automatic paper loop" in text
    assert "bounded operator-triggered paper run harness" in text
