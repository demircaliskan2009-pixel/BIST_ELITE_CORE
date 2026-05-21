from __future__ import annotations

import json

from crypto_core.venue.deribit_paper_order_intent import DeribitPaperOrderIntentSide
from crypto_core.venue.deribit_paper_trade_gate import (
    deribit_paper_trade_gate_audit_record_to_dict,
    run_deribit_paper_trade_gate,
)
from tests.crypto_core.venue.test_phase37b_paper_trade_gate_contract import _accepted_trade_gate_inputs


def test_phase37f_audit_record_is_deterministic_for_identical_explicit_run() -> None:
    first_inputs = _accepted_trade_gate_inputs(
        intent_id="paper-trade-gate-audit",
        side=DeribitPaperOrderIntentSide.BUY,
        limit_price=50_020.0,
    )
    second_inputs = _accepted_trade_gate_inputs(
        intent_id="paper-trade-gate-audit",
        side=DeribitPaperOrderIntentSide.BUY,
        limit_price=50_020.0,
    )

    first = run_deribit_paper_trade_gate(*first_inputs)
    second = run_deribit_paper_trade_gate(*second_inputs)

    assert first.audit_record == second.audit_record


def test_phase37f_audit_record_contains_no_private_or_live_data() -> None:
    trigger, intent, decision, fill_request, frame, ledger = _accepted_trade_gate_inputs(
        intent_id="paper-trade-gate-audit-safe",
        side=DeribitPaperOrderIntentSide.BUY,
        limit_price=50_020.0,
    )
    result = run_deribit_paper_trade_gate(trigger, intent, decision, fill_request, frame, ledger)
    payload = json.dumps(deribit_paper_trade_gate_audit_record_to_dict(result.audit_record), sort_keys=True).lower()

    for forbidden in (
        "credential",
        "password",
        "private",
        "secret",
        "signature",
        "token",
        "paper_adapter",
        "https://",
        "wss://",
    ):
        assert forbidden not in payload
