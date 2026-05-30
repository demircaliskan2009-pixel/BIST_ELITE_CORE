from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_LEDGER_FILL_APPLICATION_36A.md")


def test_phase36a_doc_exists_and_records_verified_pr78_state() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert DOC.exists()
    assert "PAPER_LEDGER_FILL_APPLICATION_READY" in text
    assert "| `main` | `360ee551fe55dfdba0daacbcd76610f179c1cf10` |" in text
    assert "| `accepted` | `True` |" in text
    assert "| `connector_ready_dialects` | `1` |" in text
    assert "| `ledger_mutation_ready` | `NO` |" in text


def test_phase36a_doc_describes_boundary_accounting_and_non_scope() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "deribit_paper_ledger.py" in text
    assert "accepted normalized intent reference" in text
    assert "accepted explicit DeribitPaperFillResult" in text
    assert "applied_fill_ids" in text
    assert "applied_request_ids" in text
    assert "applied_idempotency_keys" in text
    assert "append-only paper audit entries" in text
    assert "NOT_exchange_orders: true" in text
    assert "NOT_execution_adapter: true" in text
    assert "automatic paper loops" in text
