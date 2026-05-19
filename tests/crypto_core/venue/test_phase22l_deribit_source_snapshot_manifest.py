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
from crypto_core.venue.contracts import PublicFeedType, VenueId
from crypto_core.venue.dialect_evidence import (
    OfficialDocEvidence,
    OfficialDocEvidenceStatus,
    verify_public_feed_dialect_evidence_bundle,
)
from crypto_core.venue.official_evidence_packages import (
    OfficialEvidencePackage,
    build_public_feed_dialect_evidence_bundle_from_package,
)
from crypto_core.venue.operational_evidence_readiness import (
    OPERATIONAL_PUBLIC_CONNECTOR_REQUIRED_FIELDS,
    OperationalEvidenceReadinessRequirement,
    evaluate_operational_public_connector_evidence,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect

MANIFEST_PATH = Path("docs/crypto_core/official_sources/deribit/20260510/DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md")
DERIBIT_DRAFT_PATH = Path("docs/crypto_core/DERIBIT_OFFICIAL_EVIDENCE_PACKAGE_DRAFT.md")
CHECKLIST_PATH = Path("docs/crypto_core/DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md")
SNAPSHOT_CONTRACT_PATH = Path("src/crypto_core/venue/official_source_snapshots.py")
CONNECTOR_CONTRACT_PATH = Path("src/crypto_core/data/deribit_public_connector_contract.py")
DIALECT_ID = "deribit:l2_orderbook:placeholder"
EXPECTED_HASH = "a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd"
EXPECTED_SOURCES = {
    "DERIBIT_NOTIFICATIONS": "https://docs.deribit.com/#notifications",
    "DERIBIT_ENVIRONMENT": "https://docs.deribit.com/#json-rpc-over-websocket",
    "DERIBIT_RATE_LIMITS": "https://docs.deribit.com/#rate-limits",
    "DERIBIT_INSTRUMENTS": "https://docs.deribit.com/#public-get_instruments",
    "DERIBIT_TICKER": "https://docs.deribit.com/#ticker-instrument_name-interval",
    "DERIBIT_RESTRICTED": "https://docs.deribit.com/#restricted-countries",
}


def test_deribit_source_snapshot_manifest_exists():
    assert MANIFEST_PATH.is_file()


def test_manifest_has_official_urls_and_successful_hash_metadata():
    rows = _manifest_rows()

    assert set(rows) == set(EXPECTED_SOURCES)
    for source_id, row in rows.items():
        assert row["official_url"] == EXPECTED_SOURCES[source_id]
        assert re.fullmatch(r"2026-05-10T\d{2}:\d{2}:\d{2}Z", row["retrieved_at_iso"])
        assert row["retrieval_status"] == "REVIEWED_APPROVED"
        assert re.fullmatch(r"[0-9a-f]{64}", row["content_sha256"])
        assert row["content_sha256"] == EXPECTED_HASH
        assert int(row["content_size_bytes"]) > 0
        assert row["local_temp_path"].startswith(".tmp_official_sources/deribit/20260510/")


def test_manifest_is_hash_only_and_raw_html_is_not_committed():
    assert "`retrieval_method`: `TERMINAL_DOC_FETCH`" in _manifest()
    assert "`operational_status`: `BLOCKED`" in _manifest()
    assert "`manual_review_status`: `PENDING`" in _manifest()
    assert not list(MANIFEST_PATH.parent.glob("*.html"))


def test_deribit_draft_remains_blocked_after_hash_intake():
    draft = _draft()

    assert "DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md" in draft
    assert "`operational_status`: `BLOCKED`" in draft
    assert "`manual_review_required`: `YES`" in draft
    assert "`phase22l_manual_review_status`: `PENDING`" in draft
    assert "`phase22l_enabled_for_connector`: `false`" in draft
    assert "`phase22l_static_registry_verified`: `false`" in draft
    assert "`operational_status`: `READY`" not in draft
    assert "`enabled_for_connector`: `true`" not in draft


def test_checklist_keeps_manual_review_and_operational_blockers_pending():
    checklist = _checklist()

    assert "`phase22l_source_retrieval_hash_status`: `SUPPLIED_HASHED_PENDING_REVIEW`" in checklist
    assert "`manual_approval_status`: `PENDING`" in checklist
    assert "`heartbeat_ping_pong_liveness_proof_reviewed`: `PENDING`" in checklist
    assert "`checksum_decision_reviewed`: `PENDING`" in checklist
    assert "`staleness_budget_defined`: `PENDING`" in checklist
    assert "`receive_lag_budget_defined`: `PENDING`" in checklist
    assert "`testnet_prod_difference_reviewed`: `PENDING`" in checklist
    assert "`regional_legal_access_reviewed`: `PENDING`" in checklist
    assert "`enabled_for_connector`: `false`" in checklist


def test_operational_readiness_is_not_accepted_from_hashes_alone():
    package = OfficialEvidencePackage(
        package_id="deribit-phase22l-hash-only",
        venue_id=VenueId.DERIBIT,
        retrieved_at_ns=2_600_510_075_121,
        source_count=1,
        evidence_items=(
            OfficialDocEvidence(
                evidence_id=f"{DIALECT_ID}::phase22l-hash-only",
                venue_id=VenueId.DERIBIT,
                doc_type=PublicFeedType.L2_ORDERBOOK.value,
                doc_url=EXPECTED_SOURCES["DERIBIT_NOTIFICATIONS"],
                retrieved_at_ns=2_600_510_075_121,
                content_hash=EXPECTED_HASH,
                source_name="DERIBIT_NOTIFICATIONS",
                status=OfficialDocEvidenceStatus.VERIFIED,
                rejection_reasons=(),
            ),
        ),
        rejection_reasons=(),
    )
    verification = verify_public_feed_dialect_evidence_bundle(
        build_public_feed_dialect_evidence_bundle_from_package(
            package,
            dialect_id=DIALECT_ID,
            feed_type=PublicFeedType.L2_ORDERBOOK,
        )
    )
    result = evaluate_operational_public_connector_evidence(
        venue_id=VenueId.DERIBIT,
        dialect_id=DIALECT_ID,
        feed_type=PublicFeedType.L2_ORDERBOOK,
        evidence_package=package,
        dialect_verification_result=verification,
        required_fields=_hash_only_requirements(),
    )

    assert verification.accepted is True
    assert result.accepted is False
    assert "operational_evidence:manual_review_missing" in result.rejection_reasons
    assert "operational_evidence:staleness_unknown" in result.rejection_reasons
    assert "operational_evidence:receive_lag_unknown" in result.rejection_reasons


def test_static_registry_verified_and_connector_ready_dialects_empty():
    spec = get_public_feed_dialect(DIALECT_ID)

    assert spec.verification_status.value == "verified_from_official_docs"
    assert spec.enabled_for_connector is True
    assert len(connector_ready_dialects()) == 1


def test_no_source_network_imports_or_runtime_methods_added():
    for path in (SNAPSHOT_CONTRACT_PATH, CONNECTOR_CONTRACT_PATH):
        source = path.read_text(encoding="utf-8").lower()
        tree = ast.parse(source)
        forbidden_import_roots = {
            "aiohttp",
            "httpx",
            "requests",
            "socket",
            "urllib",
            "websocket",
            "websockets",
        }
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
        assert "api_key" not in source
        assert "api_secret" not in source
        assert "getenv" not in source
        assert "os.environ" not in source


def test_no_credentials_env_or_api_key_values_added_to_docs():
    combined = "\n".join((_draft(), _checklist(), _manifest()))

    assert re.search(r"(?i)(api[_ -]?key|secret|token|passphrase)\s*[:=]\s*[a-z0-9_-]{8,}", combined) is None
    assert "TURKEY_ALLOWED" not in combined


def test_live_execution_lifecycle_still_rejects_live_mode():
    result = ExecutionLifecycleEngine(ExecutionLifecycleConfig(mode=ExecutionMode.LIVE)).process(_execution_request())

    assert result.approved is False
    assert result.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


def _manifest_rows() -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for line in _manifest().splitlines():
        if not line.startswith("| `DERIBIT_"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        source_id = cells[0].strip("`")
        rows[source_id] = {
            "official_url": cells[1].strip("`"),
            "retrieved_at_iso": cells[2].strip("`"),
            "retrieval_status": cells[3].strip("`"),
            "content_sha256": cells[4].strip("`"),
            "content_size_bytes": cells[5],
            "local_temp_path": cells[6].strip("`"),
        }
    return rows


def _hash_only_requirements() -> tuple[OperationalEvidenceReadinessRequirement, ...]:
    supplied = {
        "real_official_urls_present",
        "reproducible_content_hashes_present",
        "retrieval_timestamps_present",
        "static_registry_not_enabled",
        "connector_ready_dialects_empty",
    }
    return tuple(
        OperationalEvidenceReadinessRequirement(
            requirement_id=f"phase22l:{field}",
            field_name=field,
            satisfied=field in supplied,
            evidence_refs=(f"phase22l:{field}",) if field in supplied else (),
            rejection_reasons=(),
        )
        for field in OPERATIONAL_PUBLIC_CONNECTOR_REQUIRED_FIELDS
    )


def _manifest() -> str:
    return MANIFEST_PATH.read_text(encoding="utf-8")


def _draft() -> str:
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
