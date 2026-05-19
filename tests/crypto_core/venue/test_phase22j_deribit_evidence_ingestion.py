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

DERIBIT_DRAFT_PATH = Path("docs/crypto_core/DERIBIT_OFFICIAL_EVIDENCE_PACKAGE_DRAFT.md")
CHECKLIST_PATH = Path("docs/crypto_core/DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md")
CONTRACT_PATH = Path("src/crypto_core/data/deribit_public_connector_contract.py")
DIALECT_ID = "deribit:l2_orderbook:placeholder"
DR_STATUS = "DR_REPORTED_OFFICIAL_SOURCE_CITED_NOT_LOCALLY_HASHED"
DR_RETRIEVAL_STATUS = "DR_REPORTED_NEEDS_LOCAL_RETRIEVAL"


EXPECTED_SOURCE_IDS = (
    "DERIBIT_NOTIFICATIONS",
    "DERIBIT_ENVIRONMENT",
    "DERIBIT_RATE_LIMITS",
    "DERIBIT_INSTRUMENTS",
    "DERIBIT_TICKER",
    "DERIBIT_RESTRICTED",
)


def test_deribit_dossier_sources_are_reported_not_locally_hashed():
    text = _deribit_draft()
    source_blocks = _official_source_blocks(text)

    assert tuple(source_blocks) == EXPECTED_SOURCE_IDS
    for source_id, block in source_blocks.items():
        assert f"`source_id`: `{source_id}`" in block
        assert "`venue`: `deribit`" in block
        assert "`official_url`: `https://docs.deribit.com/" in block
        assert "`retrieved_at_iso`: `2026-05-09T00:00:00Z`" in block
        assert f"`retrieval_status`: `{DR_RETRIEVAL_STATUS}`" in block
        assert "`content_hash`: `CONTENT_HASH_UNAVAILABLE`" in block
        assert "`manual_hash_required`: `YES`" in block
        assert "`manual_review_required`: `YES`" in block
        assert f"`evidence_status`: `{DR_STATUS}`" in block


def test_deribit_draft_and_checklist_keep_operational_status_blocked():
    combined = _deribit_draft() + "\n" + _checklist()

    assert "`operational_status`: `BLOCKED`" in combined
    assert "`manual_hash_required`: `YES`" in combined
    assert DR_RETRIEVAL_STATUS in combined
    assert DR_STATUS in combined
    assert "`operational_status`: `READY`" not in combined


def test_dossier_corrections_keep_unknowns_as_blockers():
    combined = _deribit_draft() + "\n" + _checklist()

    assert "`checksum_model`: `UNKNOWN_OR_NOT_DOCUMENTED_IN_REVIEWED_OFFICIAL_SOURCES`" in combined
    assert "VERIFIED_NONE" not in combined
    assert "`heartbeat_ping_pong_status`: `UNKNOWN_BLOCKED`" in combined
    assert "`staleness_budget_status`: `UNSATISFIED`" in combined
    assert "`receive_lag_budget_status`: `UNSATISFIED`" in combined
    assert "`testnet_prod_semantic_equivalence`: `UNKNOWN`" in combined
    assert "`regional_legal_access_status`: `MANUAL_LEGAL_ACCESS_REVIEW_REQUIRED`" in combined
    assert "`turkey_regional_access_status`: `MANUAL_LEGAL_ACCESS_REVIEW_REQUIRED`" in combined
    assert "`deribit_dialect_verification`: `false`" in combined


def test_no_source_or_dialect_marks_deribit_connector_ready():
    combined = _deribit_draft() + "\n" + _checklist()

    assert "`enabled_for_connector`: `false`" in combined
    assert "`connector_ready`: `false`" in combined
    assert "`enabled_for_connector`: `true`" not in combined
    assert "`connector_ready`: `true`" not in combined
    assert "operational connector readiness: **ready**" not in combined.lower()


def test_static_registry_verified_and_connector_ready_dialects_empty():
    spec = get_public_feed_dialect(DIALECT_ID)

    assert spec.verification_status.value == "verified_from_official_docs"
    assert spec.enabled_for_connector is True
    assert len(connector_ready_dialects()) == 1


def test_connector_contract_still_has_no_runtime_network_or_order_surface():
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
    assert "https://" not in source
    assert "http://" not in source


def test_no_credentials_env_or_api_keys_are_introduced_as_values():
    combined = _deribit_draft() + "\n" + _checklist()
    contract_source = CONTRACT_PATH.read_text(encoding="utf-8").lower()

    assert "api_key" not in contract_source
    assert "api_secret" not in contract_source
    assert "private_key" not in contract_source
    assert "getenv" not in contract_source
    assert "os.environ" not in contract_source
    assert re.search(r"(?i)(api[_ -]?key|secret|token|passphrase)\s*[:=]\s*[a-z0-9_-]{8,}", combined) is None


def test_live_execution_lifecycle_still_rejects_live_mode():
    result = ExecutionLifecycleEngine(ExecutionLifecycleConfig(mode=ExecutionMode.LIVE)).process(_execution_request())

    assert result.approved is False
    assert result.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


def _official_source_blocks(text: str) -> dict[str, str]:
    section = text.split("## Official Source Ids", maxsplit=1)[1].split("## Evidence Items", maxsplit=1)[0]
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in section.splitlines():
        if line.startswith("- `DERIBIT_"):
            current = line.split("`", maxsplit=2)[1]
            blocks[current] = [line]
        elif current is not None:
            blocks[current].append(line)
    return {source_id: "\n".join(lines) for source_id, lines in blocks.items()}


def _deribit_draft() -> str:
    return DERIBIT_DRAFT_PATH.read_text(encoding="utf-8")


def _checklist() -> str:
    return CHECKLIST_PATH.read_text(encoding="utf-8")


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
