from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_SIMULATOR_FILL_MODEL_34A.md")


def test_phase34a_doc_records_phase76_baseline_and_selected_seam() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "PAPER_SIMULATOR_FILL_MODEL_CONTRACT_READY" in text
    assert "| `main` | `484e6c893e587529772d82785e6f2574eff1880c` |" in text
    assert "| `connector_ready_dialects` | `1` |" in text
    assert "`DeribitPaperFeedFrame` -> simulation-only fill evaluation -> typed result" in text
    assert "existing paper adapter lives inside the" in text


def test_phase34a_doc_keeps_execution_scope_out() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "NOT_private_api: true" in text
    assert "NOT_credentials: true" in text
    assert "NOT_exchange_orders: true" in text
    assert "NOT_execution_adapter: true" in text
    assert "NOT_strategy_alpha: true" in text
    assert "NOT_position_accounting_mutation: true" in text
    assert "BIST" not in text
