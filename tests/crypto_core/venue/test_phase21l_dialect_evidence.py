from __future__ import annotations

import ast
import json
from dataclasses import replace
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
    PublicFeedDialectEvidenceBundle,
    official_doc_evidence_from_dict,
    official_doc_evidence_rejection_reasons,
    official_doc_evidence_to_dict,
    public_feed_dialect_evidence_bundle_from_dict,
    public_feed_dialect_evidence_bundle_rejection_reasons,
    public_feed_dialect_evidence_bundle_to_dict,
    public_feed_dialect_verification_result_from_dict,
    public_feed_dialect_verification_result_to_dict,
    verify_public_feed_dialect_evidence_bundle,
)


def test_valid_official_doc_evidence_accepted():
    assert official_doc_evidence_rejection_reasons(_evidence()) == ()


def test_empty_doc_url_rejected():
    reasons = official_doc_evidence_rejection_reasons(replace(_evidence(), doc_url=""))

    assert "official_doc:doc_url_missing" in reasons


def test_non_http_doc_url_rejected():
    reasons = official_doc_evidence_rejection_reasons(replace(_evidence(), doc_url="file://local-doc"))

    assert "official_doc:doc_url_scheme_invalid" in reasons


def test_empty_content_hash_rejected():
    reasons = official_doc_evidence_rejection_reasons(replace(_evidence(), content_hash=""))

    assert "official_doc:content_hash_missing" in reasons


def test_invalid_timestamp_rejected():
    reasons = official_doc_evidence_rejection_reasons(replace(_evidence(), retrieved_at_ns=0))

    assert "official_doc:retrieved_at_invalid" in reasons


def test_non_verified_status_rejected():
    result = verify_public_feed_dialect_evidence_bundle(
        _bundle(evidence_items=(replace(_evidence(), status=OfficialDocEvidenceStatus.SUPPLIED),))
    )

    assert result.accepted is False
    assert "official_doc:status_not_verified" in result.rejection_reasons


def test_empty_bundle_rejected():
    reasons = public_feed_dialect_evidence_bundle_rejection_reasons(_bundle(evidence_items=()))

    assert "official_doc:evidence_missing" in reasons


def test_duplicate_evidence_id_rejected():
    item = _evidence(content_hash="hash-a")
    duplicate = replace(item, content_hash="hash-b")
    result = verify_public_feed_dialect_evidence_bundle(_bundle(evidence_items=(item, duplicate)))

    assert result.accepted is False
    assert "official_doc:duplicate_evidence_id" in result.rejection_reasons


def test_mixed_venue_rejected():
    result = verify_public_feed_dialect_evidence_bundle(
        _bundle(evidence_items=(replace(_evidence(), venue_id=VenueId.DERIBIT),))
    )

    assert result.accepted is False
    assert "official_doc:venue_mismatch" in result.rejection_reasons


def test_mixed_feed_type_rejected():
    result = verify_public_feed_dialect_evidence_bundle(
        _bundle(evidence_items=(replace(_evidence(), doc_type="trades"),))
    )

    assert result.accepted is False
    assert "official_doc:feed_type_mismatch" in result.rejection_reasons


def test_bundle_rejection_reasons_propagate():
    result = verify_public_feed_dialect_evidence_bundle(_bundle(rejection_reasons=("official_doc:manual_reject",)))

    assert result.accepted is False
    assert "official_doc:manual_reject" in result.rejection_reasons


def test_verification_result_roundtrip_json_safe():
    payload = public_feed_dialect_verification_result_to_dict(verify_public_feed_dialect_evidence_bundle(_bundle()))

    restored = public_feed_dialect_verification_result_from_dict(json.loads(json.dumps(payload)))

    assert public_feed_dialect_verification_result_to_dict(restored) == payload


def test_evidence_and_bundle_serializers_roundtrip_json_safe():
    evidence_payload = official_doc_evidence_to_dict(_evidence())
    bundle_payload = public_feed_dialect_evidence_bundle_to_dict(_bundle())

    assert (
        official_doc_evidence_to_dict(official_doc_evidence_from_dict(json.loads(json.dumps(evidence_payload))))
        == evidence_payload
    )
    assert (
        public_feed_dialect_evidence_bundle_to_dict(
            public_feed_dialect_evidence_bundle_from_dict(json.loads(json.dumps(bundle_payload)))
        )
        == bundle_payload
    )


def test_verification_result_is_deterministic():
    first = public_feed_dialect_verification_result_to_dict(verify_public_feed_dialect_evidence_bundle(_bundle()))
    second = public_feed_dialect_verification_result_to_dict(verify_public_feed_dialect_evidence_bundle(_bundle()))

    assert first == second


def test_new_dialect_evidence_module_has_no_forbidden_imports():
    module_path = Path("src/crypto_core/venue/dialect_evidence.py")
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


def _evidence(**overrides: object) -> OfficialDocEvidence:
    values = {
        "evidence_id": "unit-binance-l2::official-doc-1",
        "venue_id": VenueId.BINANCE_USDM,
        "doc_type": PublicFeedType.L2_ORDERBOOK.value,
        "doc_url": "https://docs.example.test/binance-usdm/l2",
        "retrieved_at_ns": 1_000,
        "content_hash": "content-hash-1",
        "source_name": "unit-official-doc",
        "status": OfficialDocEvidenceStatus.VERIFIED,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return OfficialDocEvidence(**values)  # type: ignore[arg-type]


def _bundle(**overrides: object) -> PublicFeedDialectEvidenceBundle:
    values = {
        "bundle_id": "bundle-21l",
        "dialect_id": "unit-binance-l2",
        "venue_id": VenueId.BINANCE_USDM,
        "feed_type": PublicFeedType.L2_ORDERBOOK,
        "evidence_items": (_evidence(),),
        "verified_at_ns": 1_100,
        "verifier_id": "verifier-21l",
        "rejection_reasons": (),
    }
    values.update(overrides)
    return PublicFeedDialectEvidenceBundle(**values)  # type: ignore[arg-type]


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
