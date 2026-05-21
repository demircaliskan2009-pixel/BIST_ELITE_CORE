from __future__ import annotations

import ast
from pathlib import Path

from crypto_core.venue.deribit_paper_fill_model import evaluate_deribit_paper_limit_fill
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

SOURCE = Path("src/crypto_core/venue/deribit_paper_ledger.py")
DOC = Path("docs/crypto_core/PAPER_LEDGER_FILL_APPLICATION_36A.md")
SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_36H.md")


def test_phase36e_ledger_module_has_no_network_or_execution_imports() -> None:
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


def test_phase36e_output_stays_paper_only_and_without_bist_leakage() -> None:
    ledger = build_deribit_paper_ledger_state(
        initial_cash_balance=10_000.0, symbol="BTC-PERPETUAL", canonical_symbol="BTC-PERP"
    )
    frame = _frame()
    intent = _intent(side=DeribitPaperOrderIntentSide.BUY, intent_id="paper-scope", limit_price=50_020.0)
    decision = validate_deribit_paper_order_intent(frame, intent)
    reference = normalize_deribit_paper_ledger_intent_reference(intent, decision)
    fill_result = evaluate_deribit_paper_limit_fill(frame, decision.fill_request)
    result = apply_deribit_paper_fill_to_ledger(ledger, reference, fill_result)
    combined = "\n".join(path.read_text(encoding="utf-8") for path in (SOURCE, DOC, SUMMARY))

    assert result.accepted is True
    assert hasattr(result, "trade_ready") is False
    assert hasattr(result, "venue_submission_ready") is False
    assert "BIST" not in combined
    for forbidden in ("place_order", "submit_order", "paper_adapter", "shadow_execution", "wss://", "https://"):
        assert forbidden not in SOURCE.read_text(encoding="utf-8").lower()
