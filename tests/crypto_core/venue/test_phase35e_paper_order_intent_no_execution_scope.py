from __future__ import annotations

import ast
from pathlib import Path

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_paper_feed import build_deribit_paper_feed_input
from crypto_core.venue.deribit_paper_order_intent import (
    DeribitPaperOrderIntent,
    DeribitPaperOrderIntentSide,
    DeribitPaperOrderStyle,
    validate_deribit_paper_order_intent,
)
from tests.crypto_core.venue.phase33_deribit_paper_feed_helpers import accepted_replay_result

SOURCE = Path("src/crypto_core/venue/deribit_paper_order_intent.py")
DOC = Path("docs/crypto_core/PAPER_ORDER_INTENT_RISK_GATE_35A.md")
SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_35G.md")


def test_phase35e_order_intent_gate_has_no_network_or_execution_imports() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    imports: set[str] = set()
    function_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
        elif isinstance(node, ast.FunctionDef):
            function_names.add(node.name)

    assert not any(module.startswith("crypto_core.execution") for module in imports)
    assert {"os", "requests", "httpx", "aiohttp", "websocket", "websockets"}.isdisjoint(imports)
    assert {"authenticate", "cancel_order", "create_order", "login", "place_order", "submit_order"}.isdisjoint(
        function_names
    )


def test_phase35e_source_has_no_routeable_runtime_calls() -> None:
    source = SOURCE.read_text(encoding="utf-8").lower()

    for forbidden in (
        "api_secret",
        "os.environ",
        "paper_adapter",
        "place_order",
        "submit_order",
        "shadow_execution",
    ):
        assert forbidden not in source


def test_phase35e_accepted_decision_never_marks_execution_or_trading_ready() -> None:
    decision = validate_deribit_paper_order_intent(_frame(), _intent())

    assert decision.accepted is True
    assert decision.exchange_order_ready is False
    assert decision.venue_submission_ready is False
    assert decision.trade_ready is False
    assert decision.paper_execution_loop_ready is False
    assert decision.ledger_mutation_ready is False
    assert decision.position_mutation_ready is False
    assert decision.strategy_signal_ready is False
    assert decision.live_trading_ready is False
    assert decision.shadow_trading_ready is False


def test_phase35e_docs_and_source_do_not_reference_legacy_equity_system() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in (SOURCE, DOC, SUMMARY))

    assert "BIST" not in combined


def _frame():
    paper_feed = build_deribit_paper_feed_input(accepted_replay_result())
    assert paper_feed.frame is not None
    return paper_feed.frame


def _intent() -> DeribitPaperOrderIntent:
    return DeribitPaperOrderIntent(
        intent_id="paper-intent-scope",
        idempotency_key="idem-paper-intent-scope",
        venue_id=VenueId.DERIBIT,
        symbol="BTC-PERPETUAL",
        canonical_symbol="BTC-PERP",
        side=DeribitPaperOrderIntentSide.BUY,
        order_style=DeribitPaperOrderStyle.LIMIT,
        quantity=0.5,
        limit_price=50_020.0,
        simulation_only=True,
    )
