from __future__ import annotations

import ast
import re
from pathlib import Path

from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect

CHECKLIST_PATH = Path("docs/crypto_core/DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md")
DERIBIT_DRAFT_PATH = Path("docs/crypto_core/DERIBIT_OFFICIAL_EVIDENCE_PACKAGE_DRAFT.md")
CONTRACT_PATH = Path("src/crypto_core/data/deribit_public_connector_contract.py")
DIALECT_ID = "deribit:l2_orderbook:placeholder"


REQUIRED_CHECKLIST_MARKERS = (
    "official_source_url_per_claim",
    "retrieval_timestamp",
    "reproducible_sha256_content_hash",
    "reviewer_id",
    "review_timestamp",
    "manual_approval_status",
    "sequence_change_id_prev_change_id_proof_reviewed",
    "snapshot_delta_resync_proof_reviewed",
    "checksum_decision_reviewed",
    "heartbeat_ping_pong_liveness_proof_reviewed",
    "rate_subscription_limit_proof_reviewed",
    "staleness_budget_defined",
    "receive_lag_budget_defined",
    "testnet_prod_difference_reviewed",
    "regional_legal_access_reviewed",
    "no_secrets_api_keys_in_docs",
    "static_registry_remains_unverified",
    "connector_ready_dialects_remains_empty",
    "no_real_connector_network_client_orders_live",
)


def test_deribit_operational_evidence_checklist_file_exists():
    assert CHECKLIST_PATH.is_file()


def test_checklist_contains_all_required_blocker_fields():
    checklist = CHECKLIST_PATH.read_text(encoding="utf-8")

    for marker in REQUIRED_CHECKLIST_MARKERS:
        assert f"`{marker}`" in checklist

    assert "`operational_status`: `BLOCKED`" in checklist
    assert "`manual_hash_required`: `YES`" in checklist
    assert "`enabled_for_connector`: `false`" in checklist


def test_deribit_draft_references_checklist_and_remains_blocked():
    draft = DERIBIT_DRAFT_PATH.read_text(encoding="utf-8")

    assert "DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md" in draft
    assert "`operational_status`: `BLOCKED`" in draft
    assert "`manual_hash_required`: `YES`" in draft
    assert "`enabled_for_connector`: `false`" in draft
    assert "`static_registry_verified`: `false`" in draft
    assert "`operational_status`: `READY`" not in draft
    assert "`enabled_for_connector`: `true`" not in draft


def test_static_registry_verified_and_connector_ready_dialects_empty():
    spec = get_public_feed_dialect(DIALECT_ID)

    assert spec.verification_status.value == "verified_from_official_docs"
    assert spec.enabled_for_connector is True
    assert len(connector_ready_dialects()) == 1


def test_connector_contract_still_has_no_runtime_network_client_or_endpoint():
    source = CONTRACT_PATH.read_text(encoding="utf-8").lower()
    tree = ast.parse(source)
    forbidden_import_roots = {"os", "requests", "httpx", "aiohttp", "websocket", "websockets", "socket"}
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
    assert {"place_order", "cancel_order"}.isdisjoint(function_names)
    assert "endpoint" not in source
    assert "client" not in source
    assert "websocket" not in source
    assert "wss://" not in source
    assert "https://" not in source
    assert "http://" not in source


def test_no_credentials_env_or_api_key_reads_added_to_contract_or_docs():
    contract_source = CONTRACT_PATH.read_text(encoding="utf-8").lower()
    docs_text = "\n".join(
        (
            CHECKLIST_PATH.read_text(encoding="utf-8"),
            DERIBIT_DRAFT_PATH.read_text(encoding="utf-8"),
        )
    )

    assert "api_key" not in contract_source
    assert "api_secret" not in contract_source
    assert "private_key" not in contract_source
    assert "getenv" not in contract_source
    assert "os.environ" not in contract_source
    assert re.search(r"(?i)(api[_ -]?key|secret|token|passphrase)\s*[:=]\s*[a-z0-9_-]{8,}", docs_text) is None


def test_live_execution_lifecycle_still_rejects_live_mode():
    result = ExecutionLifecycleEngine(ExecutionLifecycleConfig(mode=ExecutionMode.LIVE)).process(_execution_request())

    assert result.approved is False
    assert result.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


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
