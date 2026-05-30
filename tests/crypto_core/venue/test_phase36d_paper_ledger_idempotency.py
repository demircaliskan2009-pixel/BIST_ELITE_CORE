from __future__ import annotations

from dataclasses import replace

from crypto_core.venue.deribit_paper_fill_model import DERIBIT_PAPER_FILL_MODEL_ID, evaluate_deribit_paper_limit_fill
from crypto_core.venue.deribit_paper_ledger import (
    apply_deribit_paper_fill_to_ledger,
    build_deribit_paper_ledger_state,
    normalize_deribit_paper_ledger_intent_reference,
)
from crypto_core.venue.deribit_paper_order_intent import (
    DeribitPaperOrderIntentSide,
    validate_deribit_paper_order_intent,
)
from tests.crypto_core.venue.test_phase36b_paper_ledger_contract import _frame, _intent


def test_phase36d_duplicate_fill_id_is_rejected_without_double_count() -> None:
    ledger = build_deribit_paper_ledger_state(
        initial_cash_balance=10_000.0, symbol="BTC-PERPETUAL", canonical_symbol="BTC-PERP"
    )
    frame = _frame()
    intent = _intent(side=DeribitPaperOrderIntentSide.BUY, intent_id="paper-idem", limit_price=50_020.0)
    decision = validate_deribit_paper_order_intent(frame, intent)
    reference = normalize_deribit_paper_ledger_intent_reference(intent, decision)
    fill_result = evaluate_deribit_paper_limit_fill(frame, decision.fill_request)
    first = apply_deribit_paper_fill_to_ledger(ledger, reference, fill_result)
    second = apply_deribit_paper_fill_to_ledger(first.ledger_state, reference, fill_result)

    assert first.accepted is True
    assert second.accepted is False
    assert second.ledger_state == first.ledger_state
    assert "deribit_paper_ledger:duplicate_fill_id" in second.rejection_reasons


def test_phase36d_duplicate_request_id_or_idempotency_key_is_rejected() -> None:
    ledger = build_deribit_paper_ledger_state(
        initial_cash_balance=10_000.0, symbol="BTC-PERPETUAL", canonical_symbol="BTC-PERP"
    )
    frame = _frame()
    intent = _intent(side=DeribitPaperOrderIntentSide.BUY, intent_id="paper-req", limit_price=50_020.0)
    decision = validate_deribit_paper_order_intent(frame, intent)
    reference = normalize_deribit_paper_ledger_intent_reference(intent, decision)
    fill_result = evaluate_deribit_paper_limit_fill(frame, decision.fill_request)
    first = apply_deribit_paper_fill_to_ledger(ledger, reference, fill_result)
    duplicate = replace(
        fill_result,
        fill_id=f"{DERIBIT_PAPER_FILL_MODEL_ID}:{reference.request_id}:seq:{fill_result.source_sequence_id + 1}",
        source_sequence_id=fill_result.source_sequence_id + 1,
    )
    second = apply_deribit_paper_fill_to_ledger(first.ledger_state, reference, duplicate)

    assert second.accepted is False
    assert "deribit_paper_ledger:duplicate_request_id" in second.rejection_reasons
    assert "deribit_paper_ledger:duplicate_idempotency_key" in second.rejection_reasons
