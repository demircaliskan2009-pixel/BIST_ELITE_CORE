from __future__ import annotations

import ast
import json
from pathlib import Path

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
    operational_evidence_readiness_result_to_dict,
    operational_evidence_ready,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect


def test_current_deribit_draft_cannot_pass_operational_readiness():
    result = _deribit_operational_result()

    assert result.accepted is False
    assert operational_evidence_ready(result) is False
    assert result.status.value == "blocked"


def test_current_deribit_blockers_include_content_hash_missing():
    assert "operational_evidence:content_hash_missing" in _deribit_operational_result().rejection_reasons


def test_current_deribit_blockers_include_staleness_unknown():
    assert "operational_evidence:staleness_unknown" in _deribit_operational_result().rejection_reasons


def test_current_deribit_blockers_include_receive_lag_unknown():
    assert "operational_evidence:receive_lag_unknown" in _deribit_operational_result().rejection_reasons


def test_current_deribit_blockers_include_heartbeat_unknown():
    assert "operational_evidence:heartbeat_unknown" in _deribit_operational_result().rejection_reasons


def test_current_deribit_blockers_include_checksum_decision_missing():
    assert "operational_evidence:checksum_decision_missing" in _deribit_operational_result().rejection_reasons


def test_current_deribit_blockers_include_regional_access_unknown():
    assert "operational_evidence:regional_access_unknown" in _deribit_operational_result().rejection_reasons


def test_static_deribit_registry_remains_unverified():
    spec = get_public_feed_dialect(_DIALECT_ID)

    assert spec.verification_status.value == "unverified"
    assert spec.enabled_for_connector is False


def test_connector_ready_dialects_remains_empty():
    assert connector_ready_dialects() == ()


def test_binance_comparison_remains_docs_only_and_cannot_unlock_deribit():
    text = Path("docs/crypto_core/BINANCE_USDM_PUBLIC_FEED_COMPARISON_DRAFT.md").read_text(encoding="utf-8")
    package = _binance_comparison_package()
    result = evaluate_operational_public_connector_evidence(
        venue_id=VenueId.DERIBIT,
        dialect_id=_DIALECT_ID,
        feed_type=PublicFeedType.L2_ORDERBOOK,
        evidence_package=package,
        dialect_verification_result=_verification(package),
        required_fields=_current_deribit_requirements(),
    )

    assert "Status: `COMPARISON_ONLY`." in text
    assert result.accepted is False
    assert "operational_evidence:comparison_only_not_evidence" in result.rejection_reasons


def test_no_connector_network_client_or_endpoint_strings_added_to_venue_sources():
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
        assert "endpoint" not in source
        assert "api_key" not in source
        assert "api_secret" not in source
        assert "getenv" not in source


def test_deribit_operational_result_json_safe():
    payload = operational_evidence_readiness_result_to_dict(_deribit_operational_result())

    assert json.loads(json.dumps(payload)) == payload
    assert "operational_evidence:content_hash_missing" in payload["rejection_reasons"]


_DIALECT_ID = "deribit:l2_orderbook:placeholder"
_RETRIEVED_AT_NS = 2_200_000_000_000


def _deribit_operational_result():
    package = _deribit_draft_package()
    return evaluate_operational_public_connector_evidence(
        venue_id=VenueId.DERIBIT,
        dialect_id=_DIALECT_ID,
        feed_type=PublicFeedType.L2_ORDERBOOK,
        evidence_package=package,
        dialect_verification_result=_verification(package),
        required_fields=_current_deribit_requirements(),
    )


def _current_deribit_requirements() -> tuple[OperationalEvidenceReadinessRequirement, ...]:
    blocked_fields = {
        "reproducible_content_hashes_present",
        "checksum_decision_verified",
        "staleness_budget_verified",
        "receive_lag_budget_verified",
        "heartbeat_or_ping_pong_verified",
        "testnet_prod_difference_reviewed",
        "regional_access_reviewed",
    }
    return tuple(
        OperationalEvidenceReadinessRequirement(
            requirement_id=f"deribit-current:{field}",
            field_name=field,
            satisfied=field not in blocked_fields,
            evidence_refs=(f"deribit-draft:{field}",) if field not in blocked_fields else (),
            rejection_reasons=(),
        )
        for field in OPERATIONAL_PUBLIC_CONNECTOR_REQUIRED_FIELDS
    )


def _verification(package: OfficialEvidencePackage):
    bundle = build_public_feed_dialect_evidence_bundle_from_package(
        package,
        dialect_id=_DIALECT_ID,
        feed_type=PublicFeedType.L2_ORDERBOOK,
    )
    return verify_public_feed_dialect_evidence_bundle(bundle)


def _deribit_draft_package() -> OfficialEvidencePackage:
    evidence_items = (
        _deribit_evidence("initial-book-snapshot"),
        _deribit_evidence("subsequent-book-deltas"),
        _deribit_evidence("change-id-continuity"),
        _deribit_evidence("prev-change-id-resync"),
        _deribit_evidence("max-gap-tolerance-zero"),
    )
    return OfficialEvidencePackage(
        package_id="deribit-public-book-phase22d-draft",
        venue_id=VenueId.DERIBIT,
        retrieved_at_ns=_RETRIEVED_AT_NS,
        source_count=len(evidence_items),
        evidence_items=evidence_items,
        rejection_reasons=(),
    )


def _deribit_evidence(claim_id: str) -> OfficialDocEvidence:
    return OfficialDocEvidence(
        evidence_id=f"{_DIALECT_ID}::{claim_id}",
        venue_id=VenueId.DERIBIT,
        doc_type=PublicFeedType.L2_ORDERBOOK.value,
        doc_url=f"https://docs.deribit.com/#notifications-{claim_id}",
        retrieved_at_ns=_RETRIEVED_AT_NS + len(claim_id),
        content_hash=f"CONTENT_HASH_UNAVAILABLE:DERIBIT_NOTIFICATIONS:{claim_id}",
        source_name="DERIBIT_NOTIFICATIONS",
        status=OfficialDocEvidenceStatus.VERIFIED,
        rejection_reasons=(),
    )


def _binance_comparison_package() -> OfficialEvidencePackage:
    item = OfficialDocEvidence(
        evidence_id=f"{_DIALECT_ID}::binance-usdm-comparison",
        venue_id=VenueId.BINANCE_USDM,
        doc_type=PublicFeedType.L2_ORDERBOOK.value,
        doc_url="https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams",
        retrieved_at_ns=_RETRIEVED_AT_NS,
        content_hash="CONTENT_HASH_UNAVAILABLE:BINANCE_USDM_COMPARISON",
        source_name="BINANCE_USDM_COMPARISON_ONLY",
        status=OfficialDocEvidenceStatus.VERIFIED,
        rejection_reasons=(),
    )
    return OfficialEvidencePackage(
        package_id="binance-usdm-comparison-only",
        venue_id=VenueId.BINANCE_USDM,
        retrieved_at_ns=_RETRIEVED_AT_NS,
        source_count=1,
        evidence_items=(item,),
        rejection_reasons=(),
    )
