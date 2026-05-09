from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

from crypto_core.data.public_feed_dialect import (
    FeedChecksumModel,
    FeedDialectVerificationStatus,
    FeedSequenceModel,
    public_feed_dialect_connector_ready,
)
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
from crypto_core.venue.dialect_verification import apply_public_feed_dialect_verification
from crypto_core.venue.official_evidence_packages import (
    OfficialEvidencePackage,
    build_public_feed_dialect_evidence_bundle_from_package,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect


def test_deribit_draft_records_supplied_book_claims_without_static_authorization():
    text = Path("docs/crypto_core/DERIBIT_OFFICIAL_EVIDENCE_PACKAGE_DRAFT.md").read_text(encoding="utf-8")

    assert "DERIBIT_NOTIFICATIONS" in text
    assert "https://docs.deribit.com/#notifications" in text
    assert "First public WebSocket book notification is a snapshot." in text
    assert "Subsequent public book notifications are incremental deltas." in text
    assert "`change_id` and `prev_change_id` continuity" in text
    assert "`prev_change_id` mismatch requires resubscribe or resync." in text
    assert "`max_gap_tolerance` is zero" in text
    assert "CONTENT_HASH_UNAVAILABLE" in text
    assert "Do not enable connector readiness globally from this draft." in text


def test_deribit_evidence_package_verifies_supplied_orderbook_facts():
    verification = _verification_from_package(_deribit_evidence_package())

    assert verification.accepted is True
    assert verification.dialect_id == _DERIBIT_DIALECT_ID
    assert verification.venue_id is VenueId.DERIBIT
    assert verification.feed_type is PublicFeedType.L2_ORDERBOOK
    assert len(verification.official_doc_refs) == 5
    assert len(verification.content_hashes) == 5


def test_overlay_derives_local_deribit_orderbook_candidate_without_operational_authorization():
    result = apply_public_feed_dialect_verification(_deribit_candidate_spec(), _verification_from_package())

    assert result.accepted is True
    assert result.verified_spec is not None
    assert result.verified_spec.venue_id is VenueId.DERIBIT
    assert result.verified_spec.feed_type is PublicFeedType.L2_ORDERBOOK
    assert result.verified_spec.verification_status is FeedDialectVerificationStatus.VERIFIED_FROM_OFFICIAL_DOCS
    assert result.verified_spec.sequence_model is FeedSequenceModel.PREV_FINAL_RANGE
    assert result.verified_spec.max_gap_tolerance == 0
    assert result.verified_spec.supports_delta_stream is True
    assert result.verified_spec.supports_resync is True
    assert connector_ready_dialects() == ()


def test_static_deribit_registry_remains_unverified_connector_disabled():
    static_spec = get_public_feed_dialect(_DERIBIT_DIALECT_ID)

    assert static_spec.verification_status is FeedDialectVerificationStatus.UNVERIFIED
    assert static_spec.enabled_for_connector is False
    assert public_feed_dialect_connector_ready(static_spec) is False
    assert connector_ready_dialects() == ()


def test_missing_content_hash_blocks_overlay_connector_readiness():
    package = _deribit_evidence_package(evidence_items=(replace(_evidence_items()[0], content_hash=""),))
    verification = _verification_from_package(package)
    result = apply_public_feed_dialect_verification(_deribit_candidate_spec(), verification)

    assert verification.accepted is False
    assert "official_doc:content_hash_missing" in verification.rejection_reasons
    assert result.accepted is False
    assert result.verified_spec is None
    assert "public_feed_dialect_overlay:verification_rejected" in result.rejection_reasons


def test_manual_hash_rejection_blocks_overlay_connector_readiness():
    manual_hash_item = replace(
        _evidence_items()[0],
        content_hash="manual-hash-not-content-derived",
        rejection_reasons=("official_doc:manual_hash_not_verified",),
    )
    package = _deribit_evidence_package(evidence_items=(manual_hash_item,))
    verification = _verification_from_package(package)
    result = apply_public_feed_dialect_verification(_deribit_candidate_spec(), verification)

    assert verification.accepted is False
    assert "official_doc:manual_hash_not_verified" in verification.rejection_reasons
    assert result.accepted is False
    assert result.verified_spec is None


def test_unknown_subscription_rate_limits_and_regional_access_remain_fail_closed():
    package = _deribit_evidence_package(
        rejection_reasons=(
            "deribit_evidence:public_subscription_rate_limits_unknown",
            "deribit_evidence:regional_legal_access_unknown",
        )
    )
    verification = _verification_from_package(package)
    result = apply_public_feed_dialect_verification(_deribit_candidate_spec(), verification)

    assert verification.accepted is False
    assert "deribit_evidence:public_subscription_rate_limits_unknown" in verification.rejection_reasons
    assert "deribit_evidence:regional_legal_access_unknown" in verification.rejection_reasons
    assert result.accepted is False
    assert result.verified_spec is None


def test_unknown_max_staleness_remains_fail_closed():
    result = apply_public_feed_dialect_verification(
        _deribit_candidate_spec(max_staleness_ns=0),
        _verification_from_package(),
    )

    assert result.accepted is False
    assert result.verified_spec is None
    assert "public_feed_dialect:invalid_staleness" in result.rejection_reasons


def test_unknown_max_receive_lag_remains_fail_closed():
    result = apply_public_feed_dialect_verification(
        _deribit_candidate_spec(max_receive_lag_ns=0),
        _verification_from_package(),
    )

    assert result.accepted is False
    assert result.verified_spec is None
    assert "public_feed_dialect:invalid_receive_lag" in result.rejection_reasons


def test_unknown_sequence_or_delta_fields_still_fail_closed():
    unknown_sequence = apply_public_feed_dialect_verification(
        _deribit_candidate_spec(sequence_model=FeedSequenceModel.UNKNOWN),
        _verification_from_package(),
    )
    no_delta = apply_public_feed_dialect_verification(
        _deribit_candidate_spec(supports_delta_stream=False),
        _verification_from_package(),
    )

    assert unknown_sequence.accepted is False
    assert "public_feed_dialect_overlay:sequence_model_unknown" in unknown_sequence.rejection_reasons
    assert no_delta.accepted is False
    assert "public_feed_dialect_overlay:delta_stream_unsupported" in no_delta.rejection_reasons


def test_deribit_evidence_overlay_test_adds_no_connector_implementation():
    for module_path in (
        Path("src/crypto_core/venue/official_evidence_packages.py"),
        Path("src/crypto_core/venue/public_feed_dialects.py"),
    ):
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
        assert "endpoint" not in source
        assert "api_key" not in source
        assert "api_secret" not in source


def test_live_execution_lifecycle_still_rejects_live_mode():
    result = ExecutionLifecycleEngine(ExecutionLifecycleConfig(mode=ExecutionMode.LIVE)).process(_execution_request())

    assert result.approved is False
    assert result.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


_DERIBIT_DIALECT_ID = "deribit:l2_orderbook:placeholder"
_RETRIEVED_AT_NS = 2_200_000_000_000


def _verification_from_package(package: OfficialEvidencePackage | None = None):
    package = _deribit_evidence_package() if package is None else package
    bundle = build_public_feed_dialect_evidence_bundle_from_package(
        package,
        dialect_id=_DERIBIT_DIALECT_ID,
        feed_type=PublicFeedType.L2_ORDERBOOK,
    )
    return verify_public_feed_dialect_evidence_bundle(bundle)


def _deribit_candidate_spec(**overrides: object):
    values = {
        "requires_rest_snapshot": False,
        "supports_delta_stream": True,
        "supports_checksum": False,
        "sequence_model": FeedSequenceModel.PREV_FINAL_RANGE,
        "checksum_model": FeedChecksumModel.NONE,
        "requires_heartbeat": False,
        "requires_ping_pong": False,
        "supports_resync": True,
        "max_gap_tolerance": 0,
        "max_staleness_ns": 1_000_000_000,
        "max_receive_lag_ns": 1_000_000_000,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return replace(get_public_feed_dialect(_DERIBIT_DIALECT_ID), **values)


def _deribit_evidence_package(**overrides: object) -> OfficialEvidencePackage:
    evidence_items = overrides.pop("evidence_items", _evidence_items())
    values = {
        "package_id": "deribit-public-book-phase22b-draft",
        "venue_id": VenueId.DERIBIT,
        "retrieved_at_ns": _RETRIEVED_AT_NS,
        "source_count": len(evidence_items),  # type: ignore[arg-type]
        "evidence_items": evidence_items,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return OfficialEvidencePackage(**values)  # type: ignore[arg-type]


def _evidence_items() -> tuple[OfficialDocEvidence, ...]:
    return (
        _evidence("initial-book-snapshot", "initial-snapshot-hash"),
        _evidence("subsequent-book-deltas", "delta-hash"),
        _evidence("change-id-continuity", "change-id-hash"),
        _evidence("prev-change-id-resync", "resync-hash"),
        _evidence("max-gap-tolerance-zero", "gap-tolerance-hash"),
    )


def _evidence(claim_id: str, content_hash: str, **overrides: object) -> OfficialDocEvidence:
    values = {
        "evidence_id": f"{_DERIBIT_DIALECT_ID}::{claim_id}",
        "venue_id": VenueId.DERIBIT,
        "doc_type": PublicFeedType.L2_ORDERBOOK.value,
        "doc_url": f"https://docs.deribit.com/#notifications-{claim_id}",
        "retrieved_at_ns": _RETRIEVED_AT_NS + len(claim_id),
        "content_hash": f"CONTENT_HASH_UNAVAILABLE:DERIBIT_NOTIFICATIONS:{content_hash}",
        "source_name": "DERIBIT_NOTIFICATIONS",
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
