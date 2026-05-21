from __future__ import annotations

from pathlib import Path

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.deribit_paper_feed import build_deribit_paper_feed_input
from crypto_core.venue.deribit_paper_order_intent import (
    DeribitPaperOrderIntent,
    DeribitPaperOrderIntentSide,
    DeribitPaperOrderStyle,
    validate_deribit_paper_order_intent,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.phase33_deribit_paper_feed_helpers import accepted_replay_result

SUMMARY = Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_35G.md")


def test_phase35g_summary_records_post_patch_outputs() -> None:
    text = SUMMARY.read_text(encoding="utf-8")
    readiness = evaluate_deribit_manual_review_readiness()
    decision = validate_deribit_paper_order_intent(_frame(), _intent())

    assert "| `accepted` | `True` |" in text
    assert "| `evidence_review_complete` | `True` |" in text
    assert "| `connector_enablement_ready` | `True` |" in text
    assert "| `pending_rows` | `0` |" in text
    assert "| `deferred_rows` | `()` |" in text
    assert "| `connector_ready_dialects` | `1` |" in text
    assert "| `paper_order_intent_gate_status` | `READY` |" in text
    assert readiness.accepted is True
    assert len(connector_ready_dialects()) == 1
    assert decision.accepted is True


def test_phase35g_summary_distinguishes_gate_from_execution_loop() -> None:
    text = SUMMARY.read_text(encoding="utf-8").lower()

    assert "order-intent gate readiness is not trade readiness" in text
    assert "not a paper" in text
    assert "execution loop" in text
    assert "request_only_no_auto_fill" in text
    assert "ledger_mutation_ready" in text
    assert "paper ledger/accounting mutation" in text
    assert "live trading" in text
    assert "shadow trading" in text


def test_phase35g_summary_preserves_no_execution_scope_markers() -> None:
    text = SUMMARY.read_text(encoding="utf-8")

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


def _frame():
    paper_feed = build_deribit_paper_feed_input(accepted_replay_result())
    assert paper_feed.frame is not None
    return paper_feed.frame


def _intent() -> DeribitPaperOrderIntent:
    return DeribitPaperOrderIntent(
        intent_id="paper-intent-summary",
        idempotency_key="idem-paper-intent-summary",
        venue_id=VenueId.DERIBIT,
        symbol="BTC-PERPETUAL",
        canonical_symbol="BTC-PERP",
        side=DeribitPaperOrderIntentSide.BUY,
        order_style=DeribitPaperOrderStyle.LIMIT,
        quantity=0.5,
        limit_price=50_020.0,
        simulation_only=True,
    )
