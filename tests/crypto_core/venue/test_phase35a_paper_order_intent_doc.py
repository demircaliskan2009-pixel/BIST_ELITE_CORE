from __future__ import annotations

from pathlib import Path

DOC = Path("docs/crypto_core/PAPER_ORDER_INTENT_RISK_GATE_35A.md")


def test_phase35a_doc_records_verified_phase34_state_and_scope() -> None:
    text = DOC.read_text(encoding="utf-8")

    assert "status: PAPER_ORDER_INTENT_RISK_GATE_READY" in text
    assert "| `main` | `095d3bca5837b3ea02567f75159dd807b0c50057` |" in text
    assert "| `accepted` | `True` |" in text
    assert "| `connector_ready_dialects` | `1` |" in text
    assert "| `paper_fill_model_contract_status` | `READY` |" in text
    assert "DeribitPaperFeedFrame" in text
    assert "DeribitPaperOrderIntent" in text
    assert "DeribitPaperFillRequest" in text


def test_phase35a_doc_preserves_no_execution_and_no_ledger_scope() -> None:
    text = DOC.read_text(encoding="utf-8")

    for marker in (
        "NOT_private_api: true",
        "NOT_credentials: true",
        "NOT_exchange_orders: true",
        "NOT_execution_adapter: true",
        "NOT_order_routing: true",
        "NOT_strategy_alpha: true",
        "NOT_persistent_ledger_mutation: true",
        "NOT_shadow_live_trading: true",
        "NOT_ci_live_network_dependency: true",
    ):
        assert marker in text
    assert "NOT_READY_FOR_LEDGER_MUTATION" in text
    assert "not automatically sent to the fill model" in text
    assert "BIST" not in text
