from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

from crypto_core.data.public_feed_dialect import (
    FeedChecksumModel,
    FeedDialectVerificationStatus,
    FeedSequenceModel,
    PublicFeedDialectSpec,
    public_feed_dialect_connector_ready,
)
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState
from crypto_core.venue.contracts import InstrumentType, PublicFeedType, VenueId
from crypto_core.venue.dialect_evidence import (
    OfficialDocEvidence,
    OfficialDocEvidenceStatus,
    PublicFeedDialectEvidenceBundle,
    verify_public_feed_dialect_evidence_bundle,
)
from crypto_core.venue.dialect_verification import (
    apply_public_feed_dialect_verification,
    public_feed_dialect_verification_overlay_result_from_dict,
    public_feed_dialect_verification_overlay_result_to_dict,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect


def test_valid_overlay_produces_verified_connector_ready_spec():
    result = apply_public_feed_dialect_verification(_spec(), _verification())

    assert result.accepted is True
    assert result.verified_spec is not None
    assert result.verified_spec.verification_status is FeedDialectVerificationStatus.VERIFIED_FROM_OFFICIAL_DOCS
    assert result.verified_spec.official_doc_refs == ("https://docs.example.test/binance-usdm/l2",)
    assert public_feed_dialect_connector_ready(result.verified_spec) is True


def test_missing_verification_rejects():
    result = apply_public_feed_dialect_verification(_spec(), None)

    assert result.accepted is False
    assert result.rejection_reasons == ("public_feed_dialect_overlay:verification_missing",)


def test_rejected_verification_rejects():
    verification = verify_public_feed_dialect_evidence_bundle(
        _bundle(evidence_items=(replace(_evidence(), status=OfficialDocEvidenceStatus.REJECTED),))
    )

    result = apply_public_feed_dialect_verification(_spec(), verification)

    assert result.accepted is False
    assert "public_feed_dialect_overlay:verification_rejected" in result.rejection_reasons
    assert "official_doc:status_not_verified" in result.rejection_reasons


def test_dialect_mismatch_rejects():
    verification = verify_public_feed_dialect_evidence_bundle(_bundle(dialect_id="other-dialect"))

    result = apply_public_feed_dialect_verification(_spec(), verification)

    assert result.accepted is False
    assert "public_feed_dialect_overlay:verification_rejected" in result.rejection_reasons
    assert "public_feed_dialect_overlay:dialect_mismatch" in result.rejection_reasons


def test_venue_mismatch_rejects():
    verification = verify_public_feed_dialect_evidence_bundle(
        _bundle(venue_id=VenueId.DERIBIT, evidence_items=(replace(_evidence(), venue_id=VenueId.DERIBIT),))
    )

    result = apply_public_feed_dialect_verification(_spec(), verification)

    assert result.accepted is False
    assert "public_feed_dialect_overlay:venue_mismatch" in result.rejection_reasons


def test_feed_mismatch_rejects():
    verification = verify_public_feed_dialect_evidence_bundle(
        _bundle(
            feed_type=PublicFeedType.TRADES,
            evidence_items=(replace(_evidence(), doc_type=PublicFeedType.TRADES.value),),
        )
    )

    result = apply_public_feed_dialect_verification(_spec(), verification)

    assert result.accepted is False
    assert "public_feed_dialect_overlay:feed_type_mismatch" in result.rejection_reasons


def test_missing_doc_refs_rejects():
    verification = replace(_verification(), official_doc_refs=())

    result = apply_public_feed_dialect_verification(_spec(), verification)

    assert result.accepted is False
    assert "public_feed_dialect_overlay:official_docs_missing" in result.rejection_reasons


def test_missing_content_hashes_rejects():
    verification = replace(_verification(), content_hashes=())

    result = apply_public_feed_dialect_verification(_spec(), verification)

    assert result.accepted is False
    assert "public_feed_dialect_overlay:content_hashes_missing" in result.rejection_reasons


def test_unknown_sequence_model_remains_not_connector_ready():
    result = apply_public_feed_dialect_verification(_spec(sequence_model=FeedSequenceModel.UNKNOWN), _verification())

    assert result.accepted is False
    assert "public_feed_dialect_overlay:sequence_model_unknown" in result.rejection_reasons
    assert result.verified_spec is None


def test_no_delta_stream_remains_not_connector_ready():
    result = apply_public_feed_dialect_verification(_spec(supports_delta_stream=False), _verification())

    assert result.accepted is False
    assert "public_feed_dialect_overlay:delta_stream_unsupported" in result.rejection_reasons
    assert result.verified_spec is None


def test_original_spec_unchanged():
    spec = _spec()

    result = apply_public_feed_dialect_verification(spec, _verification())

    assert result.original_spec == spec
    assert spec.verification_status is FeedDialectVerificationStatus.UNVERIFIED
    assert spec.enabled_for_connector is False


def test_overlay_result_serializer_roundtrip_json_safe():
    result = apply_public_feed_dialect_verification(_spec(), _verification())
    payload = public_feed_dialect_verification_overlay_result_to_dict(result)

    restored = public_feed_dialect_verification_overlay_result_from_dict(json.loads(json.dumps(payload)))

    assert public_feed_dialect_verification_overlay_result_to_dict(restored) == payload


def test_static_registry_remains_unverified_after_overlay():
    static_spec = get_public_feed_dialect("binance_usdm:l2_orderbook:placeholder")
    verification = verify_public_feed_dialect_evidence_bundle(
        _bundle(
            dialect_id=static_spec.dialect_id,
            evidence_items=(
                _evidence(
                    evidence_id=f"{static_spec.dialect_id}::official-doc-1",
                    content_hash="static-content-hash",
                ),
            ),
        )
    )

    result = apply_public_feed_dialect_verification(static_spec, verification)

    assert result.accepted is False
    assert static_spec.verification_status is FeedDialectVerificationStatus.UNVERIFIED
    ready = connector_ready_dialects()
    assert len(ready) == 1
    assert ready[0].dialect_id == "deribit:l2_orderbook:book_instrument_interval"


def test_overlay_is_deterministic():
    first = public_feed_dialect_verification_overlay_result_to_dict(
        apply_public_feed_dialect_verification(_spec(), _verification())
    )
    second = public_feed_dialect_verification_overlay_result_to_dict(
        apply_public_feed_dialect_verification(_spec(), _verification())
    )

    assert first == second


def test_new_dialect_verification_module_has_no_forbidden_imports():
    module_path = Path("src/crypto_core/venue/dialect_verification.py")
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


def _spec(**overrides: object) -> PublicFeedDialectSpec:
    values = {
        "dialect_id": "unit-binance-l2",
        "venue_id": VenueId.BINANCE_USDM,
        "feed_type": PublicFeedType.L2_ORDERBOOK,
        "instrument_type": InstrumentType.USDT_PERP,
        "verification_status": FeedDialectVerificationStatus.UNVERIFIED,
        "official_doc_refs": (),
        "requires_rest_snapshot": True,
        "supports_delta_stream": True,
        "supports_checksum": False,
        "sequence_model": FeedSequenceModel.PREV_FINAL_RANGE,
        "checksum_model": FeedChecksumModel.NONE,
        "requires_heartbeat": True,
        "requires_ping_pong": False,
        "supports_resync": True,
        "max_gap_tolerance": 0,
        "max_staleness_ns": 1_000,
        "max_receive_lag_ns": 1_000,
        "enabled_for_connector": False,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return PublicFeedDialectSpec(**values)  # type: ignore[arg-type]


def _verification():
    return verify_public_feed_dialect_evidence_bundle(_bundle())


def _bundle(**overrides: object) -> PublicFeedDialectEvidenceBundle:
    values = {
        "bundle_id": "bundle-21m",
        "dialect_id": "unit-binance-l2",
        "venue_id": VenueId.BINANCE_USDM,
        "feed_type": PublicFeedType.L2_ORDERBOOK,
        "evidence_items": (_evidence(),),
        "verified_at_ns": 1_100,
        "verifier_id": "verifier-21m",
        "rejection_reasons": (),
    }
    values.update(overrides)
    return PublicFeedDialectEvidenceBundle(**values)  # type: ignore[arg-type]


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
