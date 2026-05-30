from __future__ import annotations

import ast
import json
from pathlib import Path

from crypto_core.venue.deribit_paper_order_intent import DeribitPaperOrderIntentSide
from crypto_core.venue.deribit_paper_trade_gate import (
    deribit_paper_trade_gate_result_to_dict,
    run_deribit_paper_trade_gate,
)
from tests.crypto_core.venue.test_phase37b_paper_trade_gate_contract import _accepted_trade_gate_inputs

SOURCE = Path("src/crypto_core/venue/deribit_paper_trade_gate.py")
DOC = Path("docs/crypto_core/FIRST_PAPER_TRADE_GATE_37A.md")
SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_37H.md")


def test_phase37e_trade_gate_module_has_no_network_or_execution_imports() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    assert not any(module.startswith("crypto_core.execution") for module in imports)
    assert not any(module.startswith("crypto_core.service") for module in imports)
    assert {"requests", "httpx", "aiohttp", "websocket", "websockets"}.isdisjoint(imports)


def test_phase37e_output_stays_paper_only_and_without_forbidden_scope() -> None:
    trigger, intent, decision, fill_request, frame, ledger = _accepted_trade_gate_inputs(
        intent_id="paper-trade-gate-scope",
        side=DeribitPaperOrderIntentSide.BUY,
        limit_price=50_020.0,
    )
    result = run_deribit_paper_trade_gate(trigger, intent, decision, fill_request, frame, ledger)
    payload = json.dumps(deribit_paper_trade_gate_result_to_dict(result), sort_keys=True).lower()
    combined = "\n".join(path.read_text(encoding="utf-8").lower() for path in (SOURCE, DOC, SUMMARY))

    assert result.accepted is True
    assert "bist" not in combined
    for forbidden in (
        "place_order",
        "submit_order",
        "paper_adapter",
        "private_api",
        "strategy_signal_ready",
        "exchange_order_ready",
        "venue_submission_ready",
        "live_trading_ready",
        "shadow_trading_ready",
        "https://",
        "wss://",
    ):
        assert forbidden not in payload
