from __future__ import annotations

from pathlib import Path

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.operational_evidence_readiness import OperationalEvidenceAcceptanceResult
from crypto_core.venue.public_connector_enablement import (
    PublicConnectorEnablementRequest,
    PublicConnectorEnablementStatus,
    evaluate_public_connector_enablement,
    public_connector_enablement_ready,
)
from crypto_core.venue.public_connector_readiness_report import (
    PublicConnectorReadinessStageStatus,
    build_public_connector_readiness_report,
    public_connector_readiness_ready,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

PACKET_PATH = Path("docs/crypto_core/DERIBIT_B1_B5_OPERATOR_APPROVAL_PACKET.md")
CHECKLIST_PATH = Path("docs/crypto_core/DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md")
ENABLEMENT_PATH = Path("src/crypto_core/venue/public_connector_enablement.py")
READINESS_REPORT_PATH = Path("src/crypto_core/venue/public_connector_readiness_report.py")
PACKET_MARKERS = (
    "REVIEW_PACKET_ONLY~operational_status: BLOCKED~operational_evidence_ready: false~"
    "connector_ready_dialects_expected: []~paper_shadow_integration_ready: false~"
    "live_trading_ready: false~classification=MAIN_ISOLATED_DERIBIT_SMOKE_ACCEPTED~"
    "classification=CI_DERIBIT_SMOKE_ACCEPTED_PROXY~"
    "B8 status: CLOSED_BY_PROXY_AND_MAIN_CI_PUBLIC_SMOKE_PROOF~"
    "B10 status: CLOSED_WORKFLOW_REGISTERED_ON_MAIN~| B1 |~| B2 |~| B3 |~| B4 |~| B5 |~"
    "| checksum_decision |~| liveness_policy |~| staleness_budget |~| receive_lag_budget |~"
    "| testnet_prod_review |~| regional_legal_access_review |~| separate_connector_enablement |~"
    "reviewer_id: REQUIRED~reviewed_at_iso: REQUIRED~decision: REQUIRED~approval_scope: REQUIRED~"
    "evidence_refs: REQUIRED~rejection_reasons: REQUIRED_IF_REJECTED~"
    "approval_does_not_authorize_live_trading: REQUIRED~1. source snapshot manual approval~"
    "2. claim review manual approval~3. operational policy approval~4. operational evidence acceptance~"
    "5. static registry verification~6. separate public connector enablement approval~"
    "7. connector_ready_dialects enablement~8. paper-shadow integration only in separate phase~"
    "9. private/live/order API only in future separate research/authorization~"
    "b1:operational_status_blocked~b2:claim_review_pending~b2:source_snapshot_review_pending~"
    "b3:policy_approval_pending~b4:static_registry_unverified~b5:connector_ready_dialects_empty~"
    "policy:checksum_pending~policy:liveness_pending~policy:staleness_budget_pending~"
    "policy:receive_lag_budget_pending~policy:testnet_prod_pending~policy:regional_legal_pending~"
    "connector:separate_enablement_required~safety:private_api_forbidden~safety:orders_forbidden~"
    "safety:live_trading_forbidden~this packet does not approve anything.~"
    "this packet does not change operational_status.~this packet does not enable connector_ready_dialects.~"
    "this packet does not authorize paper-shadow integration.~this packet does not authorize private API.~"
    "this packet does not authorize orders.~this packet does not authorize live trading."
)
FORBIDDEN_SOURCE_MARKERS = (
    "aiohttp|httpx|requests|websocket|websockets|socket|api_key|api_secret|getenv|os.environ|"
    "place_order|cancel_order|executionmode.live|orderintent"
)


def test_phase24a_packet_and_checklist_keep_deribit_blocked():
    packet = PACKET_PATH.read_text(encoding="utf-8")
    checklist = CHECKLIST_PATH.read_text(encoding="utf-8")

    assert PACKET_PATH.is_file()
    for marker in PACKET_MARKERS.split("~"):
        assert marker in packet
    assert packet.count("| YES |") >= 5
    assert "DERIBIT_B1_B5_OPERATOR_APPROVAL_PACKET.md" in checklist
    assert "`phase24a_operator_approval_packet_status`: `REVIEW_PACKET_ONLY`" in checklist
    assert "`operational_status`: `BLOCKED`" in checklist
    assert "`connector_ready_dialects_expected`: `[]`" in checklist


def test_phase24a_runtime_gates_stay_blocked_and_safe():
    enablement = evaluate_public_connector_enablement(
        PublicConnectorEnablementRequest(
            venue_id=VenueId.DERIBIT,
            dialect_id="deribit:l2_orderbook:placeholder",
            operational_evidence_accepted=False,
            static_registry_verified=False,
            connector_enablement_status=PublicConnectorEnablementStatus.PENDING,
            reviewer_id="PENDING",
            reviewed_at_iso="PENDING",
            approved_run_mode="REQUIRED_SEPARATE_PHASE",
            evidence_refs=(
                "docs/crypto_core/DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md",
                "connector_ready_dialects_expected",
            ),
            rejection_reasons=(),
        )
    )
    report = build_public_connector_readiness_report(
        venue_id=VenueId.DERIBIT,
        dialect_id="deribit:l2_orderbook:placeholder",
        source_snapshot_results=(),
        claim_review_results=(),
        operational_evidence_result=OperationalEvidenceAcceptanceResult(
            accepted=False,
            venue_id=VenueId.DERIBIT,
            rejection_reasons=("operational_policy:checksum_decision_missing",),
        ),
        connector_enablement_decision=enablement,
        static_registry_verified=False,
        evidence_refs=("docs/crypto_core/DERIBIT_B1_B5_OPERATOR_APPROVAL_PACKET.md",),
    )

    assert connector_ready_dialects() == ()
    assert enablement.accepted is False
    assert public_connector_enablement_ready(enablement) is False
    assert report.connector_ready is False
    assert public_connector_readiness_ready(report) is False
    assert report.source_snapshots_ready is PublicConnectorReadinessStageStatus.BLOCKED
    assert report.claim_reviews_ready is PublicConnectorReadinessStageStatus.BLOCKED
    assert report.operational_evidence_ready is PublicConnectorReadinessStageStatus.BLOCKED
    assert report.connector_enablement_ready is PublicConnectorReadinessStageStatus.BLOCKED
    assert report.static_registry_verified is False


def test_phase24a_imported_modules_have_no_network_private_order_or_live_paths():
    for path in (ENABLEMENT_PATH, READINESS_REPORT_PATH):
        source = path.read_text(encoding="utf-8").lower()
        for forbidden in FORBIDDEN_SOURCE_MARKERS.split("|"):
            assert forbidden not in source
