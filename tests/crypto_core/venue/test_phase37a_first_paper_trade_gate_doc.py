from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/FIRST_PAPER_TRADE_GATE_37A.md")


def test_phase37a_doc_records_verified_pr79_state_and_boundary() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "| `main` | `1c06b3113c52a3ac0633e0dd6b36696f37a217fd` |" in text
    assert "| `accepted` | `True` |" in text
    assert "| `connector_ready_dialects` | `1` |" in text
    assert "| `paper_fill_application_status` | `READY` |" in text
    assert "| `isolated_paper_ledger_accounting_status` | `READY` |" in text
    assert "explicit operator trigger" in text.lower()
    assert "validated paper intent" in text.lower()
    assert "fill model evaluation" in text.lower()
    assert "paper ledger application" in text.lower()


def test_phase37a_doc_keeps_scope_bounded() -> None:
    text = DOC.read_text(encoding="utf-8").lower()

    assert "kill switch" in text
    assert "idempotency" in text
    assert "audit" in text
    assert "automatic paper loops" in text
    assert "execution adapters" in text
    assert "private api" in text
    assert "manual explicit trigger only" in text
