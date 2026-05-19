"""Phase 27C connector-disabled regression tests."""

from __future__ import annotations

from crypto_core.data.public_feed_dialect import evaluate_public_feed_dialect_gate
from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_manual_review_readiness import (
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_connector_enablement import (
    PUBLIC_MARKET_DATA_ONLY_RUN_MODE,
    PublicConnectorEnablementRequest,
    PublicConnectorEnablementStatus,
    evaluate_public_connector_enablement,
)
from crypto_core.venue.public_connector_readiness_report import (
    PublicConnectorReadinessStageStatus,
    build_public_connector_readiness_report,
    public_connector_readiness_ready,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, dialects_for_venue


def test_phase27c_enabled_for_connector_is_public_market_data_ready() -> None:
    spec = dialects_for_venue(VenueId.DERIBIT)[0]
    decision = evaluate_public_feed_dialect_gate(spec)
    assert spec.enabled_for_connector is True
    assert decision.accepted is True
    assert decision.connector_allowed is True
    assert decision.rejection_reasons == ()
    assert len(connector_ready_dialects()) == 1


def test_phase27c_connector_enablement_ready_for_public_market_data() -> None:
    result = evaluate_deribit_manual_review_readiness()
    assert result.connector_enablement_ready is True
    assert result.b1_b5_status["B4"] == "READY"
    assert result.b1_b5_status["B5"] == "READY"


def test_phase27c_public_connector_enablement_requires_public_market_data_mode() -> None:
    spec = dialects_for_venue(VenueId.DERIBIT)[0]
    request = PublicConnectorEnablementRequest(
        venue_id=VenueId.DERIBIT,
        dialect_id=spec.dialect_id,
        operational_evidence_accepted=True,
        static_registry_verified=True,
        connector_enablement_status=PublicConnectorEnablementStatus.APPROVED,
        reviewer_id="demir_operator",
        reviewed_at_iso="2026-05-19T00:00:00Z",
        approved_run_mode="PRIVATE_API",
        evidence_refs=("DERIBIT_STATIC_REGISTRY_VERIFICATION_27A.md",),
    )
    decision = evaluate_public_connector_enablement(request)
    assert decision.accepted is False
    assert "public_connector_enablement:invalid_run_mode" in decision.rejection_reasons


def test_phase27c_readiness_report_contract_still_requires_all_report_stages() -> None:
    spec = dialects_for_venue(VenueId.DERIBIT)[0]
    enablement_decision = evaluate_public_connector_enablement(
        PublicConnectorEnablementRequest(
            venue_id=VenueId.DERIBIT,
            dialect_id=spec.dialect_id,
            operational_evidence_accepted=True,
            static_registry_verified=True,
            connector_enablement_status=PublicConnectorEnablementStatus.APPROVED,
            reviewer_id="demir_operator",
            reviewed_at_iso="2026-05-19T00:00:00Z",
            approved_run_mode=PUBLIC_MARKET_DATA_ONLY_RUN_MODE,
            evidence_refs=("DERIBIT_STATIC_REGISTRY_VERIFICATION_27A.md",),
        )
    )
    report = build_public_connector_readiness_report(
        venue_id=VenueId.DERIBIT,
        dialect_id=spec.dialect_id,
        source_snapshot_results=(),
        claim_review_results=(),
        operational_evidence_result=object(),
        connector_enablement_decision=enablement_decision,
        static_registry_verified=True,
        evidence_refs=("DERIBIT_STATIC_REGISTRY_VERIFICATION_27A.md",),
    )
    assert report.static_registry_verified is True
    assert report.connector_enablement_ready is PublicConnectorReadinessStageStatus.READY
    assert report.connector_ready is False
    assert public_connector_readiness_ready(report) is False
