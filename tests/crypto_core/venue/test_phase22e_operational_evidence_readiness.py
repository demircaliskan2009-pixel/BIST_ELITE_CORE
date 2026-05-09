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
    PublicFeedDialectVerificationResult,
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
    operational_evidence_readiness_result_from_dict,
    operational_evidence_readiness_result_to_dict,
    operational_evidence_ready,
)


def test_missing_package_rejects():
    result = _evaluate(evidence_package=None)

    assert result.accepted is False
    assert "operational_evidence:package_missing" in result.rejection_reasons
    assert operational_evidence_ready(result) is False


def test_missing_verification_rejects():
    result = _evaluate(dialect_verification_result=None)

    assert result.accepted is False
    assert "operational_evidence:verification_missing" in result.rejection_reasons


def test_rejected_verification_rejects():
    result = _evaluate(
        dialect_verification_result=PublicFeedDialectVerificationResult(
            accepted=False,
            dialect_id=_DIALECT_ID,
            venue_id=VenueId.DERIBIT,
            feed_type=PublicFeedType.L2_ORDERBOOK,
            official_doc_refs=(),
            content_hashes=(),
            rejection_reasons=("official_doc:content_hash_missing",),
        )
    )

    assert result.accepted is False
    assert "operational_evidence:verification_rejected" in result.rejection_reasons
    assert "official_doc:content_hash_missing" in result.rejection_reasons


def test_content_hash_unavailable_rejects():
    package = _package(evidence_items=(_evidence(content_hash="CONTENT_HASH_UNAVAILABLE:DERIBIT_NOTIFICATIONS"),))
    result = _evaluate(evidence_package=package, dialect_verification_result=_verification(package))

    assert result.accepted is False
    assert "operational_evidence:content_hash_missing" in result.rejection_reasons


def test_retrieval_timestamp_missing_rejects():
    package = _package(evidence_items=(replace(_evidence(), retrieved_at_ns=0),))
    result = _evaluate(evidence_package=package, dialect_verification_result=_verification(package))

    assert result.accepted is False
    assert "operational_evidence:retrieval_timestamp_missing" in result.rejection_reasons


def test_manual_review_missing_rejects():
    result = _evaluate(required_fields=_requirements(manual_review_approved=False))

    assert result.accepted is False
    assert "operational_evidence:manual_review_missing" in result.rejection_reasons


def test_checksum_decision_missing_rejects():
    result = _evaluate(required_fields=_requirements(checksum_decision_verified=False))

    assert result.accepted is False
    assert "operational_evidence:checksum_decision_missing" in result.rejection_reasons


def test_rate_limits_unknown_rejects():
    result = _evaluate(required_fields=_requirements(rate_limits_verified=False))

    assert result.accepted is False
    assert "operational_evidence:rate_limits_unknown" in result.rejection_reasons


def test_staleness_unknown_rejects():
    result = _evaluate(required_fields=_requirements(staleness_budget_verified=False))

    assert result.accepted is False
    assert "operational_evidence:staleness_unknown" in result.rejection_reasons


def test_receive_lag_unknown_rejects():
    result = _evaluate(required_fields=_requirements(receive_lag_budget_verified=False))

    assert result.accepted is False
    assert "operational_evidence:receive_lag_unknown" in result.rejection_reasons


def test_heartbeat_unknown_rejects():
    result = _evaluate(required_fields=_requirements(heartbeat_or_ping_pong_verified=False))

    assert result.accepted is False
    assert "operational_evidence:heartbeat_unknown" in result.rejection_reasons


def test_testnet_prod_unknown_rejects():
    result = _evaluate(required_fields=_requirements(testnet_prod_difference_reviewed=False))

    assert result.accepted is False
    assert "operational_evidence:testnet_prod_unknown" in result.rejection_reasons


def test_regional_access_unknown_rejects():
    result = _evaluate(required_fields=_requirements(regional_access_reviewed=False))

    assert result.accepted is False
    assert "operational_evidence:regional_access_unknown" in result.rejection_reasons


def test_comparison_only_binance_doc_cannot_satisfy_deribit():
    package = _package(
        venue_id=VenueId.BINANCE_USDM,
        evidence_items=(
            _evidence(
                venue_id=VenueId.BINANCE_USDM,
                evidence_id=f"{_DIALECT_ID}::binance-comparison",
                doc_url="https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams",
                source_name="BINANCE_USDM_COMPARISON_ONLY",
            ),
        ),
    )
    result = _evaluate(evidence_package=package, dialect_verification_result=_verification(package))

    assert result.accepted is False
    assert "operational_evidence:comparison_only_not_evidence" in result.rejection_reasons


def test_all_requirements_satisfied_accepts():
    result = _evaluate()

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert operational_evidence_ready(result) is True


def test_serializer_roundtrip_json_safe():
    result = _evaluate()
    payload = operational_evidence_readiness_result_to_dict(result)

    restored = operational_evidence_readiness_result_from_dict(json.loads(json.dumps(payload)))

    assert operational_evidence_readiness_result_to_dict(restored) == payload


def test_deterministic_same_input_same_result():
    first = operational_evidence_readiness_result_to_dict(_evaluate())
    second = operational_evidence_readiness_result_to_dict(_evaluate())

    assert first == second


def test_operational_evidence_module_has_no_forbidden_imports():
    module_path = Path("src/crypto_core/venue/operational_evidence_readiness.py")
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
    assert "getenv" not in source


def test_live_execution_lifecycle_still_rejects_live_mode():
    result = ExecutionLifecycleEngine(ExecutionLifecycleConfig(mode=ExecutionMode.LIVE)).process(_execution_request())

    assert result.approved is False
    assert result.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


_DIALECT_ID = "deribit:l2_orderbook:placeholder"
_RETRIEVED_AT_NS = 2_200_000_000_000


def _evaluate(**overrides: object):
    package = overrides.pop("evidence_package", _package())
    verification = overrides.pop("dialect_verification_result", _verification(package))
    values = {
        "venue_id": VenueId.DERIBIT,
        "dialect_id": _DIALECT_ID,
        "feed_type": PublicFeedType.L2_ORDERBOOK,
        "evidence_package": package,
        "dialect_verification_result": verification,
        "required_fields": _requirements(),
    }
    values.update(overrides)
    return evaluate_operational_public_connector_evidence(**values)


def _requirements(**overrides: bool) -> tuple[OperationalEvidenceReadinessRequirement, ...]:
    values = {field: True for field in OPERATIONAL_PUBLIC_CONNECTOR_REQUIRED_FIELDS}
    values.update(overrides)
    return tuple(
        OperationalEvidenceReadinessRequirement(
            requirement_id=f"req:{field}",
            field_name=field,
            satisfied=satisfied,
            evidence_refs=(f"evidence:{field}",) if satisfied else (),
            rejection_reasons=(),
        )
        for field, satisfied in values.items()
    )


def _verification(package: OfficialEvidencePackage | None):
    if package is None:
        return PublicFeedDialectVerificationResult(
            accepted=False,
            dialect_id=_DIALECT_ID,
            venue_id=VenueId.DERIBIT,
            feed_type=PublicFeedType.L2_ORDERBOOK,
            official_doc_refs=(),
            content_hashes=(),
            rejection_reasons=("official_evidence_package:package_missing",),
        )
    bundle = build_public_feed_dialect_evidence_bundle_from_package(
        package,
        dialect_id=_DIALECT_ID,
        feed_type=PublicFeedType.L2_ORDERBOOK,
    )
    return verify_public_feed_dialect_evidence_bundle(bundle)


def _package(**overrides: object) -> OfficialEvidencePackage:
    evidence_items = overrides.pop("evidence_items", (_evidence(),))
    values = {
        "package_id": "deribit-public-book-operational-ready",
        "venue_id": VenueId.DERIBIT,
        "retrieved_at_ns": _RETRIEVED_AT_NS,
        "source_count": len(evidence_items),  # type: ignore[arg-type]
        "evidence_items": evidence_items,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return OfficialEvidencePackage(**values)  # type: ignore[arg-type]


def _evidence(**overrides: object) -> OfficialDocEvidence:
    values = {
        "evidence_id": f"{_DIALECT_ID}::operational-official-doc",
        "venue_id": VenueId.DERIBIT,
        "doc_type": PublicFeedType.L2_ORDERBOOK.value,
        "doc_url": "https://docs.deribit.com/#notifications",
        "retrieved_at_ns": _RETRIEVED_AT_NS,
        "content_hash": "sha256:deribit-official-doc-content",
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
