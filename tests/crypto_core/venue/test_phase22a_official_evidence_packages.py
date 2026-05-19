from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

from crypto_core.data.public_feed_dialect import FeedDialectVerificationStatus, public_feed_dialect_connector_ready
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
    public_feed_dialect_evidence_bundle_to_dict,
    verify_public_feed_dialect_evidence_bundle,
)
from crypto_core.venue.official_evidence_packages import (
    OfficialEvidencePackage,
    build_public_feed_dialect_evidence_bundle_from_package,
    official_evidence_package_from_dict,
    official_evidence_package_rejection_reasons,
    official_evidence_package_to_dict,
)
from crypto_core.venue.public_feed_dialects import all_public_feed_dialects, connector_ready_dialects


def test_valid_package_builds_evidence_bundle():
    bundle = build_public_feed_dialect_evidence_bundle_from_package(
        _package(),
        dialect_id=_DIALECT_ID,
        feed_type=PublicFeedType.L2_ORDERBOOK,
    )
    result = verify_public_feed_dialect_evidence_bundle(bundle)

    assert result.accepted is True
    assert result.official_doc_refs == ("https://docs.example.test/deribit/l2-orderbook",)
    assert result.content_hashes == ("content-hash-deribit-l2",)


def test_missing_package_rejects():
    assert official_evidence_package_rejection_reasons(None) == ("official_evidence_package:package_missing",)


def test_empty_package_rejects():
    reasons = official_evidence_package_rejection_reasons(_package(source_count=1, evidence_items=()))

    assert "official_evidence_package:evidence_missing" in reasons


def test_non_verified_evidence_rejects():
    package = _package(
        evidence_items=(replace(_evidence(), status=OfficialDocEvidenceStatus.SUPPLIED),),
    )
    bundle = build_public_feed_dialect_evidence_bundle_from_package(
        package,
        dialect_id=_DIALECT_ID,
        feed_type=PublicFeedType.L2_ORDERBOOK,
    )
    result = verify_public_feed_dialect_evidence_bundle(bundle)

    assert result.accepted is False
    assert "official_doc:status_not_verified" in result.rejection_reasons
    assert "official_evidence_package:evidence_rejected" in result.rejection_reasons


def test_mixed_venue_rejects():
    reasons = official_evidence_package_rejection_reasons(
        _package(evidence_items=(replace(_evidence(), venue_id=VenueId.BINANCE_USDM),))
    )

    assert "official_evidence_package:venue_mismatch" in reasons


def test_duplicate_evidence_id_rejects():
    item = _evidence(content_hash="content-hash-a", doc_url="https://docs.example.test/deribit/a")
    duplicate = replace(item, content_hash="content-hash-b", doc_url="https://docs.example.test/deribit/b")
    reasons = official_evidence_package_rejection_reasons(_package(source_count=2, evidence_items=(item, duplicate)))

    assert "official_evidence_package:duplicate_evidence_id" in reasons


def test_duplicate_doc_url_rejects():
    item = _evidence(evidence_id=f"{_DIALECT_ID}::official-doc-a", content_hash="content-hash-a")
    duplicate = replace(item, evidence_id=f"{_DIALECT_ID}::official-doc-b", content_hash="content-hash-b")
    reasons = official_evidence_package_rejection_reasons(_package(source_count=2, evidence_items=(item, duplicate)))

    assert "official_evidence_package:duplicate_doc_url" in reasons


def test_serializer_roundtrip_json_safe():
    payload = official_evidence_package_to_dict(_package())

    restored = official_evidence_package_from_dict(json.loads(json.dumps(payload)))

    assert official_evidence_package_to_dict(restored) == payload


def test_deterministic_same_package_same_bundle():
    first = public_feed_dialect_evidence_bundle_to_dict(
        build_public_feed_dialect_evidence_bundle_from_package(
            _package(),
            dialect_id=_DIALECT_ID,
            feed_type=PublicFeedType.L2_ORDERBOOK,
        )
    )
    second = public_feed_dialect_evidence_bundle_to_dict(
        build_public_feed_dialect_evidence_bundle_from_package(
            _package(),
            dialect_id=_DIALECT_ID,
            feed_type=PublicFeedType.L2_ORDERBOOK,
        )
    )

    assert first == second


def test_static_dialects_remain_connector_disabled_after_deribit_b4_verification():
    specs = all_public_feed_dialects()

    assert specs
    assert connector_ready_dialects() == ()
    assert any(spec.verification_status is FeedDialectVerificationStatus.VERIFIED_FROM_OFFICIAL_DOCS for spec in specs)
    assert all(public_feed_dialect_connector_ready(spec) is False for spec in specs)


def test_docs_template_exists_and_contains_required_fields():
    text = Path("docs/crypto_core/OFFICIAL_VENUE_EVIDENCE_PACKAGE_TEMPLATE.md").read_text(encoding="utf-8")

    for required in (
        "package_id",
        "venue_id",
        "research_date",
        "retrieved_at_ns",
        "doc_url",
        "source_name",
        "doc_type",
        "content_hash",
        "cited_claim_text",
        "supported_dialect_id",
        "supported_feed_type",
        "sequence_model_evidence",
        "checksum_model_evidence",
        "heartbeat_ping_pong_evidence",
        "snapshot_delta_resync_evidence",
        "rate_limit_evidence",
        "official_source_citation",
        "verification_status",
        "verifier_id",
        "rejection_reasons",
    ):
        assert required in text
    assert "Do not include secrets." in text
    assert "Deep Research summaries alone are not enough" in text


def test_new_official_evidence_package_module_has_no_forbidden_imports():
    module_path = Path("src/crypto_core/venue/official_evidence_packages.py")
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    forbidden_import_roots = {"os", "requests", "httpx", "aiohttp", "websocket", "websockets"}

    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])

    assert forbidden_import_roots.isdisjoint(imports)


def test_live_execution_lifecycle_still_rejects_live_mode():
    result = ExecutionLifecycleEngine(ExecutionLifecycleConfig(mode=ExecutionMode.LIVE)).process(_execution_request())

    assert result.approved is False
    assert result.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


_DIALECT_ID = "deribit:l2_orderbook:placeholder"


def _evidence(**overrides: object) -> OfficialDocEvidence:
    values = {
        "evidence_id": f"{_DIALECT_ID}::official-doc-1",
        "venue_id": VenueId.DERIBIT,
        "doc_type": PublicFeedType.L2_ORDERBOOK.value,
        "doc_url": "https://docs.example.test/deribit/l2-orderbook",
        "retrieved_at_ns": 1_000,
        "content_hash": "content-hash-deribit-l2",
        "source_name": "unit-official-doc",
        "status": OfficialDocEvidenceStatus.VERIFIED,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return OfficialDocEvidence(**values)  # type: ignore[arg-type]


def _package(**overrides: object) -> OfficialEvidencePackage:
    values = {
        "package_id": "package-22a-deribit",
        "venue_id": VenueId.DERIBIT,
        "retrieved_at_ns": 1_100,
        "source_count": 1,
        "evidence_items": (_evidence(),),
        "rejection_reasons": (),
    }
    values.update(overrides)
    return OfficialEvidencePackage(**values)  # type: ignore[arg-type]


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
