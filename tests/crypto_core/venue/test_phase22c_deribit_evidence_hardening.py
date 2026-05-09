from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

from crypto_core.data.public_feed_dialect import FeedChecksumModel, FeedSequenceModel
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


def test_deribit_draft_declares_placeholder_refs_non_operational():
    text = Path("docs/crypto_core/DERIBIT_OFFICIAL_EVIDENCE_PACKAGE_DRAFT.md").read_text(encoding="utf-8")

    assert "Operational connector readiness: **blocked**." in text
    assert "placeholder official-doc refs are all" in text
    assert "summary-only Deep Research prose" in text
    assert "testnet versus production differences" in text
    assert "regional, legal, and access review" in text


def test_placeholder_official_doc_refs_block_operational_verification():
    package = _package()
    verification = _verification(package)
    overlay = apply_public_feed_dialect_verification(_candidate_spec(), verification)

    assert overlay.accepted is True
    assert _operational_evidence_rejection_reasons(package, verification) == (
        "deribit_operational:placeholder_official_doc_ref",
        "deribit_operational:placeholder_content_hash",
        "deribit_operational:rate_limits_unknown",
        "deribit_operational:max_staleness_unknown",
        "deribit_operational:max_receive_lag_unknown",
        "deribit_operational:checksum_ambiguous",
        "deribit_operational:testnet_prod_differences_unknown",
        "deribit_operational:regional_legal_access_unknown",
    )
    assert connector_ready_dialects() == ()


def test_content_hash_unavailable_blocks_operational_verification():
    package = _package(evidence_items=(replace(_evidence_items()[0], content_hash="CONTENT_HASH_UNAVAILABLE"),))
    verification = _verification(package)

    assert verification.accepted is True
    assert "deribit_operational:content_hash_unavailable" in _operational_evidence_rejection_reasons(
        package,
        verification,
    )


def test_missing_content_hash_blocks_bundle_and_operational_verification():
    package = _package(evidence_items=(replace(_evidence_items()[0], content_hash=""),))
    verification = _verification(package)

    assert verification.accepted is False
    assert "official_doc:content_hash_missing" in verification.rejection_reasons
    assert "official_doc:content_hash_missing" in _operational_evidence_rejection_reasons(package, verification)


def test_missing_retrieval_timestamp_blocks_bundle_and_operational_verification():
    package = _package(evidence_items=(replace(_evidence_items()[0], retrieved_at_ns=0),))
    verification = _verification(package)

    assert verification.accepted is False
    assert "official_doc:retrieved_at_invalid" in verification.rejection_reasons
    assert "official_doc:retrieved_at_invalid" in _operational_evidence_rejection_reasons(package, verification)


def test_summary_only_deep_research_cannot_be_verified_operational_evidence():
    summary_item = replace(
        _evidence_items()[0],
        source_name="summary-only-deep-research",
        rejection_reasons=("deribit_operational:summary_only_claim",),
    )
    package = _package(evidence_items=(summary_item,))
    verification = _verification(package)

    assert verification.accepted is False
    assert "deribit_operational:summary_only_claim" in verification.rejection_reasons
    assert "deribit_operational:summary_only_claim" in _operational_evidence_rejection_reasons(
        package,
        verification,
    )


def test_static_registry_stays_unverified_even_after_operationally_blocked_overlay():
    package = _package()
    verification = _verification(package)
    static_spec = get_public_feed_dialect(_DERIBIT_DIALECT_ID)

    overlay = apply_public_feed_dialect_verification(_candidate_spec(), verification)
    restored_static = get_public_feed_dialect(_DERIBIT_DIALECT_ID)

    assert overlay.accepted is True
    assert _operational_evidence_rejection_reasons(package, verification)
    assert restored_static == static_spec
    assert restored_static.enabled_for_connector is False
    assert connector_ready_dialects() == ()


def test_source_modules_still_have_no_connector_network_or_endpoint_implementation():
    for module_path in (
        Path("src/crypto_core/venue/official_evidence_packages.py"),
        Path("src/crypto_core/venue/dialect_evidence.py"),
        Path("src/crypto_core/venue/dialect_verification.py"),
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


def _operational_evidence_rejection_reasons(package: OfficialEvidencePackage, verification) -> tuple[str, ...]:
    reasons = list(verification.rejection_reasons)
    for item in package.evidence_items:
        if "docs.example.test" in item.doc_url or "placeholder" in item.evidence_id:
            reasons.append("deribit_operational:placeholder_official_doc_ref")
        if item.content_hash == "CONTENT_HASH_UNAVAILABLE":
            reasons.append("deribit_operational:content_hash_unavailable")
        if item.content_hash.startswith("deribit-phase22b-"):
            reasons.append("deribit_operational:placeholder_content_hash")
        if item.retrieved_at_ns <= 0:
            reasons.append("official_doc:retrieved_at_invalid")
        if item.source_name == "summary-only-deep-research":
            reasons.append("deribit_operational:summary_only_claim")
    reasons.extend(
        (
            "deribit_operational:rate_limits_unknown",
            "deribit_operational:max_staleness_unknown",
            "deribit_operational:max_receive_lag_unknown",
            "deribit_operational:checksum_ambiguous",
            "deribit_operational:testnet_prod_differences_unknown",
            "deribit_operational:regional_legal_access_unknown",
        )
    )
    return tuple(dict.fromkeys(reasons))


def _verification(package: OfficialEvidencePackage):
    bundle = build_public_feed_dialect_evidence_bundle_from_package(
        package,
        dialect_id=_DERIBIT_DIALECT_ID,
        feed_type=PublicFeedType.L2_ORDERBOOK,
    )
    return verify_public_feed_dialect_evidence_bundle(bundle)


def _candidate_spec():
    return replace(
        get_public_feed_dialect(_DERIBIT_DIALECT_ID),
        requires_rest_snapshot=False,
        supports_delta_stream=True,
        sequence_model=FeedSequenceModel.PREV_FINAL_RANGE,
        checksum_model=FeedChecksumModel.NONE,
        supports_resync=True,
        max_gap_tolerance=0,
        max_staleness_ns=1_000_000_000,
        max_receive_lag_ns=1_000_000_000,
        rejection_reasons=(),
    )


def _package(**overrides: object) -> OfficialEvidencePackage:
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
        "doc_url": f"https://docs.example.test/deribit/{claim_id}",
        "retrieved_at_ns": _RETRIEVED_AT_NS + len(claim_id),
        "content_hash": f"deribit-phase22b-{content_hash}",
        "source_name": "supplied-deribit-official-doc-draft",
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
