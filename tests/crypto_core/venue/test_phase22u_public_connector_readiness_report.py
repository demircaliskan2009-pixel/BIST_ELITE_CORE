from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.official_claim_reviews import (
    OfficialClaimReviewDecision,
    OfficialClaimReviewStatus,
    validate_official_claim_review,
)
from crypto_core.venue.official_source_snapshots import OfficialSourceSnapshot, validate_official_source_snapshot
from crypto_core.venue.operational_evidence_readiness import (
    OPERATIONAL_EVIDENCE_ACCEPTANCE_REQUIRED_POLICY_IDS,
    OperationalEvidenceAcceptanceInput,
    OperationalPolicyApproval,
    OperationalPolicyApprovalStatus,
    evaluate_operational_evidence_acceptance,
)
from crypto_core.venue.public_connector_enablement import (
    PUBLIC_MARKET_DATA_ONLY_RUN_MODE,
    PublicConnectorEnablementRequest,
    PublicConnectorEnablementStatus,
    evaluate_public_connector_enablement,
)
from crypto_core.venue.public_connector_readiness_report import (
    PublicConnectorReadinessReportError,
    PublicConnectorReadinessStageStatus,
    build_public_connector_readiness_report,
    public_connector_readiness_ready,
    public_connector_readiness_report_from_dict,
    public_connector_readiness_report_to_dict,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPORT_CONTRACT_PATH = Path("src/crypto_core/venue/public_connector_readiness_report.py")
DIALECT_ID = "deribit:l2_orderbook:placeholder"
VALID_HASH = "a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd"


def test_fully_accepted_public_connector_chain_reports_ready():
    report = _report()

    assert report.connector_ready is True
    assert public_connector_readiness_ready(report) is True
    assert report.source_snapshots_ready is PublicConnectorReadinessStageStatus.READY
    assert report.claim_reviews_ready is PublicConnectorReadinessStageStatus.READY
    assert report.operational_evidence_ready is PublicConnectorReadinessStageStatus.READY
    assert report.connector_enablement_ready is PublicConnectorReadinessStageStatus.READY
    assert report.blocker_reasons == ()


def test_rejected_source_snapshot_blocks_readiness():
    report = _report(
        source_snapshot_results=(
            validate_official_source_snapshot(replace(_snapshot(), manual_review_status="PENDING")),
        )
    )

    assert report.connector_ready is False
    assert report.source_snapshots_ready is PublicConnectorReadinessStageStatus.BLOCKED
    assert "public_connector_readiness:source_snapshots_not_ready" in report.blocker_reasons
    assert "official_snapshot:manual_review_not_approved" in report.blocker_reasons


def test_pending_or_rejected_claim_review_blocks_readiness():
    report = _report(
        claim_review_results=(
            validate_official_claim_review(
                _claim(review_status=OfficialClaimReviewStatus.PENDING, decision=OfficialClaimReviewStatus.PENDING)
            ),
        )
    )

    assert report.connector_ready is False
    assert report.claim_reviews_ready is PublicConnectorReadinessStageStatus.BLOCKED
    assert "public_connector_readiness:claim_reviews_not_ready" in report.blocker_reasons
    assert "official_claim_review:pending" in report.blocker_reasons


def test_rejected_operational_evidence_blocks_readiness():
    report = _report(operational_evidence_result=evaluate_operational_evidence_acceptance(_acceptance_input()))

    assert report.connector_ready is False
    assert report.operational_evidence_ready is PublicConnectorReadinessStageStatus.BLOCKED
    assert "public_connector_readiness:operational_evidence_not_ready" in report.blocker_reasons
    assert "operational_policy:checksum_decision_missing" in report.blocker_reasons


def test_rejected_connector_enablement_blocks_readiness():
    report = _report(
        connector_enablement_decision=evaluate_public_connector_enablement(
            _enablement_request(connector_enablement_status=PublicConnectorEnablementStatus.REJECTED)
        )
    )

    assert report.connector_ready is False
    assert report.connector_enablement_ready is PublicConnectorReadinessStageStatus.BLOCKED
    assert "public_connector_readiness:connector_enablement_not_ready" in report.blocker_reasons
    assert "public_connector_enablement:rejected" in report.blocker_reasons


def test_unverified_static_registry_blocks_readiness():
    report = _report(static_registry_verified=False)

    assert report.connector_ready is False
    assert report.static_registry_verified is False
    assert "public_connector_readiness:static_registry_unverified" in report.blocker_reasons


def test_missing_evidence_refs_blocks_readiness():
    report = _report(evidence_refs=())

    assert report.connector_ready is False
    assert "public_connector_readiness:missing_evidence_ref" in report.blocker_reasons


def test_preexisting_rejection_blocks_readiness():
    report = _report(extra_rejection_reasons=("public_connector_readiness:manual_blocker",))

    assert report.connector_ready is False
    assert "public_connector_readiness:preexisting_rejection" in report.blocker_reasons
    assert "public_connector_readiness:manual_blocker" in report.blocker_reasons


def test_public_connector_readiness_report_serializers_roundtrip_json_safe():
    report = _report()
    payload = public_connector_readiness_report_to_dict(report)

    assert json.loads(json.dumps(payload)) == payload
    assert public_connector_readiness_report_from_dict(payload) == report


def test_malformed_public_connector_readiness_payloads_fail_closed():
    report = build_public_connector_readiness_report(
        venue_id={"bad": "venue"},
        dialect_id="",
        source_snapshot_results={"bad": "snapshots"},
        claim_review_results={"bad": "claims"},
        operational_evidence_result={"bad": "operational"},
        connector_enablement_decision={"bad": "enablement"},
        static_registry_verified="yes",
        evidence_refs=(),
        extra_rejection_reasons={"bad": "reason"},
    )

    assert report.connector_ready is False
    assert "public_connector_readiness:malformed" in report.blocker_reasons
    assert "public_connector_readiness:missing_evidence_ref" in report.blocker_reasons
    with pytest.raises(PublicConnectorReadinessReportError):
        public_connector_readiness_report_from_dict({"connector_ready": "yes"})


def test_public_connector_readiness_report_is_deterministic_on_replay():
    assert _report() == _report()
    assert public_connector_readiness_report_to_dict(_report()) == public_connector_readiness_report_to_dict(_report())


def test_public_connector_readiness_report_has_no_network_file_or_client_imports():
    source = REPORT_CONTRACT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_import_roots = {
        "aiohttp",
        "httpx",
        "os",
        "pathlib",
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
    assert {"open", "connect", "recv", "receive", "send", "subscribe", "start", "stop"}.isdisjoint(function_names)
    assert {"place_order", "cancel_order"}.isdisjoint(function_names)
    assert "client" not in source.lower()
    assert "endpoint" not in source.lower()
    assert "api_key" not in source.lower()
    assert "api_secret" not in source.lower()
    assert "getenv" not in source.lower()
    assert "os.environ" not in source.lower()


def test_public_connector_readiness_report_does_not_mutate_registry_or_ready_dialects():
    before = connector_ready_dialects()

    report = _report()

    assert report.connector_ready is True
    assert connector_ready_dialects() == before
    assert len(before) == 1
    assert before[0].dialect_id == "deribit:l2_orderbook:book_instrument_interval"

    source = REPORT_CONTRACT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert "crypto_core.venue.registry" not in imported_modules
    assert "crypto_core.venue.public_feed_dialects" not in imported_modules


def test_public_connector_readiness_report_has_no_live_or_order_paths():
    source = REPORT_CONTRACT_PATH.read_text(encoding="utf-8").lower()

    assert "place_order" not in source
    assert "cancel_order" not in source
    assert "orderintent" not in source
    assert "executionmode.live" not in source


def _report(**overrides: object):
    values = {
        "venue_id": VenueId.DERIBIT,
        "dialect_id": DIALECT_ID,
        "source_snapshot_results": (validate_official_source_snapshot(_snapshot()),),
        "claim_review_results": (validate_official_claim_review(_claim()),),
        "operational_evidence_result": evaluate_operational_evidence_acceptance(
            _acceptance_input(policy_approvals=_policy_approvals())
        ),
        "connector_enablement_decision": evaluate_public_connector_enablement(_enablement_request()),
        "static_registry_verified": True,
        "evidence_refs": ("phase22u:synthetic-readiness-report",),
        "extra_rejection_reasons": (),
    }
    values.update(overrides)
    return build_public_connector_readiness_report(**values)


def _acceptance_input(**overrides: object) -> OperationalEvidenceAcceptanceInput:
    values = {
        "venue_id": VenueId.DERIBIT,
        "source_snapshot_results": (validate_official_source_snapshot(_snapshot()),),
        "claim_review_results": (validate_official_claim_review(_claim()),),
        "policy_approvals": (),
        "static_registry_verified": True,
        "connector_enablement_requested": False,
        "rejection_reasons": (),
    }
    values.update(overrides)
    return OperationalEvidenceAcceptanceInput(**values)  # type: ignore[arg-type]


def _snapshot() -> OfficialSourceSnapshot:
    return OfficialSourceSnapshot(
        snapshot_id="deribit-source-snapshot",
        source_id="DERIBIT_NOTIFICATIONS",
        venue_id=VenueId.DERIBIT,
        official_url="https://docs.deribit.com/#notifications",
        retrieved_at_iso="2026-05-10T07:51:21Z",
        content_sha256=VALID_HASH,
        content_size_bytes=939_778,
        reviewer_id="phase22u-reviewer",
        reviewed_at_iso="2026-05-10T12:00:00Z",
        manual_review_status="APPROVED",
        rejection_reasons=(),
    )


def _claim(**overrides: object) -> OfficialClaimReviewDecision:
    values = {
        "claim_id": "orderbook_channel_feed",
        "source_id": "DERIBIT_NOTIFICATIONS",
        "venue_id": VenueId.DERIBIT,
        "source_sha256": VALID_HASH,
        "official_url": "https://docs.deribit.com/#notifications",
        "doc_section_or_anchor": "#notifications",
        "reviewer_id": "phase22u-reviewer",
        "reviewed_at_iso": "2026-05-10T12:00:00Z",
        "review_status": OfficialClaimReviewStatus.APPROVED,
        "decision": OfficialClaimReviewStatus.APPROVED,
        "evidence_refs": ("DERIBIT_NOTIFICATIONS:#notifications",),
        "rejection_reasons": (),
    }
    values.update(overrides)
    return OfficialClaimReviewDecision(**values)  # type: ignore[arg-type]


def _policy_approvals() -> tuple[OperationalPolicyApproval, ...]:
    return tuple(
        OperationalPolicyApproval(
            policy_id=policy_id,
            venue_id=VenueId.DERIBIT,
            policy_status=OperationalPolicyApprovalStatus.APPROVED,
            reviewer_id="phase22u-reviewer",
            reviewed_at_iso="2026-05-10T12:00:00Z",
            rejection_reasons=(),
        )
        for policy_id in OPERATIONAL_EVIDENCE_ACCEPTANCE_REQUIRED_POLICY_IDS
    )


def _enablement_request(**overrides: object) -> PublicConnectorEnablementRequest:
    values = {
        "venue_id": VenueId.DERIBIT,
        "dialect_id": DIALECT_ID,
        "operational_evidence_accepted": True,
        "static_registry_verified": True,
        "connector_enablement_status": PublicConnectorEnablementStatus.APPROVED,
        "reviewer_id": "phase22u-reviewer",
        "reviewed_at_iso": "2026-05-10T12:00:00Z",
        "approved_run_mode": PUBLIC_MARKET_DATA_ONLY_RUN_MODE,
        "evidence_refs": ("phase22u:synthetic-public-market-data-only-approval",),
        "rejection_reasons": (),
    }
    values.update(overrides)
    return PublicConnectorEnablementRequest(**values)  # type: ignore[arg-type]
