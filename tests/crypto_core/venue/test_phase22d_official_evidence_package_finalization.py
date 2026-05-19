from __future__ import annotations

import ast
from pathlib import Path

from crypto_core.data.public_feed_dialect import FeedDialectVerificationStatus, public_feed_dialect_connector_ready
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState
from crypto_core.venue.contracts import VenueId
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect


def test_deribit_finalized_draft_has_official_source_ids_and_no_placeholder_refs():
    text = _deribit_doc()

    for source_id in (
        "DERIBIT_NOTIFICATIONS",
        "DERIBIT_ENVIRONMENT",
        "DERIBIT_RATE_LIMITS",
        "DERIBIT_INSTRUMENTS",
        "DERIBIT_TICKER",
        "DERIBIT_RESTRICTED",
    ):
        assert source_id in text
    assert "docs.example.test" not in text
    assert "https://docs.deribit.com/" in text
    assert "`operational_status`: `BLOCKED`" in text
    assert "`enabled_for_connector`: `false`" in text


def test_deribit_evidence_items_have_official_url_retrieval_date_and_manual_hash_placeholder():
    text = _deribit_doc()

    assert text.count("doc_url`: `https://docs.deribit.com/") >= 11
    assert text.count("retrieval_date`: `2026-05-09`") >= 11
    assert text.count("content_hash`: `CONTENT_HASH_UNAVAILABLE") >= 11
    assert text.count("manual_hash_required`: `YES`") >= 11


def test_deribit_doc_blocks_operational_connector_readiness():
    text = _deribit_doc()

    for blocker in (
        "manual_review_required`: `YES`",
        "manual_hash_required`: `YES`",
        "max_staleness_ns_evidence`: `UNKNOWN`",
        "max_receive_lag_ns_evidence`: `UNKNOWN`",
        "heartbeat_ping_pong_evidence`: `UNKNOWN`",
        "turkey_legal_access_evidence`: `UNKNOWN`",
        "NONE_OR_UNKNOWN_WITH_MANUAL_REVIEW",
    ):
        assert blocker in text
    assert "summary-only Deep Research prose" in text
    assert "not operational proof" in text


def test_deribit_static_registry_verified_after_phase27_and_connector_enabled():
    spec = get_public_feed_dialect("deribit:l2_orderbook:placeholder")

    assert spec.venue_id is VenueId.DERIBIT
    assert spec.verification_status is FeedDialectVerificationStatus.VERIFIED_FROM_OFFICIAL_DOCS
    assert spec.enabled_for_connector is True
    assert public_feed_dialect_connector_ready(spec) is True
    assert len(connector_ready_dialects()) == 1


def test_binance_comparison_is_docs_only_and_cannot_enable_any_dialect():
    text = Path("docs/crypto_core/BINANCE_USDM_PUBLIC_FEED_COMPARISON_DRAFT.md").read_text(encoding="utf-8")

    assert "Status: `COMPARISON_ONLY`." in text
    assert "not an official evidence package" in text
    assert "REST Snapshot And WS Diff Book Depth" in text
    assert "U/u/pu Sequence Semantics" in text
    assert "pu Mismatch Resync Rule" in text
    assert "Mark, Index, And Funding Feed" in text
    assert "Open Interest REST" in text
    assert "Connection And Rate-Limit Evidence" in text
    assert "`enabled_for_connector`: `false`" in text
    assert len(connector_ready_dialects()) == 1


def test_no_network_client_or_credential_implementation_added_to_venue_sources():
    for module_path in Path("src/crypto_core/venue").glob("*.py"):
        source = module_path.read_text(encoding="utf-8").lower()
        tree = ast.parse(source)
        forbidden_import_roots = {"os", "requests", "httpx", "aiohttp", "websocket", "websockets"}
        imports: set[str] = set()
        function_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.FunctionDef):
                function_names.add(node.name)

        assert forbidden_import_roots.isdisjoint(imports)
        assert {"connect", "recv", "receive", "send", "subscribe", "start", "stop"}.isdisjoint(function_names)
        assert "api_key" not in source
        assert "api_secret" not in source
        assert "getenv" not in source


def test_no_bist_non_crypto_terms_in_finalized_evidence_docs():
    combined = _deribit_doc() + Path("docs/crypto_core/BINANCE_USDM_PUBLIC_FEED_COMPARISON_DRAFT.md").read_text(
        encoding="utf-8"
    )

    for forbidden in ("BIST", "Matriks", "iDeal", "KAP", "VIOP"):
        assert forbidden not in combined


def test_live_execution_lifecycle_still_rejects_live_mode():
    result = ExecutionLifecycleEngine(ExecutionLifecycleConfig(mode=ExecutionMode.LIVE)).process(_execution_request())

    assert result.approved is False
    assert result.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


def _deribit_doc() -> str:
    return Path("docs/crypto_core/DERIBIT_OFFICIAL_EVIDENCE_PACKAGE_DRAFT.md").read_text(encoding="utf-8")


def _execution_request() -> ExecutionRequest:
    edge_signal = EdgeSignal(
        family=EdgeFamily.ORDER_FLOW_IMBALANCE,
        symbol="BTCUSDT",
        exchange="binance",
        direction=SignalDirection.BUY,
        confidence=0.5,
        score=0.5,
        evidence={"ofi": 0.5},
        timestamp_ns=100,
        is_valid=True,
        block_reason=None,
    )
    return ExecutionRequest(
        symbol="BTCUSDT",
        exchange="binance",
        intent=OrderIntent.BUY,
        size=0.01,
        price_hint=50_000.0,
        risk_evaluation=RiskEvaluation(
            decision=RiskDecision.APPROVED,
            block_reason=None,
            system_state=SystemState.NORMAL,
            edge_signal=edge_signal,
            no_trade_decision=NoTradeDecision.allow(),
            evidence={},
            timestamp_ns=100,
        ),
        timestamp_ns=100,
    )
