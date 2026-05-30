from __future__ import annotations

import json
from dataclasses import replace

from crypto_core.venue.deribit_paper_order_intent import DeribitPaperOrderIntentSide
from crypto_core.venue.deribit_paper_trade_gate import (
    deribit_paper_trade_gate_result_to_dict,
    run_deribit_paper_trade_gate,
)
from tests.crypto_core.venue.test_phase37b_paper_trade_gate_contract import _accepted_trade_gate_inputs
from tests.crypto_core.venue.test_phase38b_first_paper_trade_proof_artifact import _phase38_trade_result, _proof


def test_phase38e_live_shadow_and_auto_loop_flags_reject() -> None:
    trigger, intent, decision, fill_request, frame, ledger = _accepted_trade_gate_inputs(
        intent_id="phase38-scope-flags",
        side=DeribitPaperOrderIntentSide.BUY,
        limit_price=50_020.0,
    )
    cases = (
        (replace(trigger, live_enabled=True), "deribit_paper_trade_gate:live_enabled"),
        (replace(trigger, shadow_enabled=True), "deribit_paper_trade_gate:shadow_enabled"),
        (replace(trigger, auto_loop_enabled=True), "deribit_paper_trade_gate:auto_loop_enabled"),
    )

    for bad_trigger, expected_reason in cases:
        result = run_deribit_paper_trade_gate(bad_trigger, intent, decision, fill_request, frame, ledger)

        assert result.accepted is False
        assert result.ledger_mutated is False
        assert expected_reason in result.rejection_reasons


def test_phase38e_artifact_and_output_contain_no_sensitive_runtime_scope() -> None:
    payload = json.dumps(
        {
            "artifact": _proof(),
            "gate_result": deribit_paper_trade_gate_result_to_dict(_phase38_trade_result()),
        },
        sort_keys=True,
    ).lower()

    for forbidden in (
        "password",
        "secret",
        "signature",
        "token",
        "api_key",
        "https://",
        "wss://",
        "exchange_order_id",
        "execution_adapter_call",
        "scheduler_enabled",
        "strategy_signal_payload",
    ):
        assert forbidden not in payload
