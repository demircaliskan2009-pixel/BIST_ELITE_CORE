"""Phase 24C manual-review workflow readiness assertions."""

from __future__ import annotations

import ast
import pathlib

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.operational_evidence_readiness import (
    OperationalEvidenceAcceptanceResult,
)
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

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
WORKFLOW_DOC = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_MANUAL_REVIEW_WORKFLOW_READINESS.md"
CHECKLIST = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md"
SELF_PATH = pathlib.Path(__file__)
WORKFLOW_MARKERS = (
    "status: REVIEW_WORKFLOW_ONLY",
    "operational_status: BLOCKED",
    "operational_evidence_ready: false",
    "connector_ready_dialects_expected: []",
    "static_registry_verified: false",
    "paper_shadow_integration_ready: false",
    "live_trading_ready: false",
    "private_api: FORBIDDEN",
    "credentials: FORBIDDEN",
    "orders: FORBIDDEN",
    "agent_can_approve_b1_b5: NO",
    "B8: CLOSED_BY_PROXY_AND_MAIN_CI_PUBLIC_SMOKE_PROOF",
    "B10: CLOSED_WORKFLOW_REGISTERED_ON_MAIN",
    "phase23l_run_id: 25671516104",
    "phase23l_classification: MAIN_ISOLATED_DERIBIT_SMOKE_ACCEPTED",
    "advisory_readiness_effect: DOES_NOT_CLOSE_B1_B5",
)
BLOCKER_ROW_MARKERS = (
    "| B1 | checklist.operational_status | operational_status BLOCKED |",
    "| B2 | DERIBIT_NOTIFICATIONS, DERIBIT_ENVIRONMENT, DERIBIT_RATE_LIMITS",
    "| B3 | checksum_decision, liveness_policy, staleness_budget",
    "| B4 | checklist.static_registry_verified and public_feed_dialects.deribit:l2_orderbook:placeholder.enabled_for_connector | static_registry_verified false |",
    "| B5 | separate_connector_enablement, phase22s_public_connector_enablement_status",
)
HUMAN_REVIEW_MARKERS = (
    "1. Source snapshot manual review",
    "2. Claim review manual review",
    "3. Operational policy review",
    "4. Operational evidence acceptance review",
    "5. Static registry verification review",
    "6. Separate public connector enablement review",
    "7. Connector-ready dialect enablement phase",
    "8. Paper/shadow integration phase",
    "9. Private/live/order authorization phase",
    "reviewer_id: REQUIRED",
    "reviewed_at_iso: REQUIRED",
    "decision: REQUIRED",
    "approval_scope: REQUIRED",
    "evidence_refs: REQUIRED",
    "source_hash_refs: REQUIRED_WHEN_APPLICABLE",
    "rejection_reasons: REQUIRED_IF_REJECTED",
    "defer_reasons: REQUIRED_IF_DEFERRED",
    "live_trading_authorization: FORBIDDEN",
    "private_api_authorization: FORBIDDEN",
    "order_authorization: FORBIDDEN",
    "APPROVE: permitted only when the reviewer records all required metadata",
    "REJECT: permitted only when rejection_reasons is populated",
    "DEFER: the current fail-closed default for every unresolved row",
    "b1:operational_status_blocked",
    "b2:source_snapshot_review_pending",
    "b2:claim_review_pending",
    "b3:policy_approval_pending",
    "b4:static_registry_unverified",
    "b5:connector_ready_dialects_empty",
    "policy:checksum_pending",
    "policy:liveness_pending",
    "policy:staleness_budget_pending",
    "policy:receive_lag_budget_pending",
    "policy:testnet_prod_pending",
    "policy:regional_legal_pending",
    "connector:separate_enablement_required",
    "safety:private_api_forbidden",
    "safety:orders_forbidden",
    "safety:live_trading_forbidden",
    "review:metadata_missing",
    "review:evidence_refs_missing",
    "review:defer_requires_reason",
    "this document does not approve B1-B5.",
    "this document does not change operational_status.",
    "this document does not mark operational_evidence_ready true.",
    "this document does not mark static_registry_verified true.",
    "this document does not enable connector_ready_dialects.",
    "this document does not authorize paper-shadow integration.",
    "this document does not authorize private API.",
    "this document does not authorize orders.",
    "this document does not authorize live trading.",
)
ALLOWED_CRYPTO_IMPORTS = {
    "crypto_core.venue.contracts",
    "crypto_core.venue.operational_evidence_readiness",
    "crypto_core.venue.public_connector_enablement",
    "crypto_core.venue.public_connector_readiness_report",
    "crypto_core.venue.public_feed_dialects",
}


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def test_phase24c_documents_and_runtime_stay_blocked() -> None:
    workflow = _read(WORKFLOW_DOC)
    checklist = _read(CHECKLIST)
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
                "docs/crypto_core/DERIBIT_MANUAL_REVIEW_WORKFLOW_READINESS.md",
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
        evidence_refs=("docs/crypto_core/DERIBIT_MANUAL_REVIEW_WORKFLOW_READINESS.md",),
    )

    assert WORKFLOW_DOC.is_file()
    for marker in WORKFLOW_MARKERS + HUMAN_REVIEW_MARKERS + BLOCKER_ROW_MARKERS:
        assert marker in workflow
    assert workflow.count("| YES | NO |") == 5
    assert workflow.count("| APPROVE / REJECT / DEFER | DEFER | NONE | YES |") == 5
    assert "DERIBIT_MANUAL_REVIEW_WORKFLOW_READINESS.md" in checklist
    assert "`phase24c_manual_review_workflow_status`: `REVIEW_WORKFLOW_ONLY`" in checklist
    assert "`phase24c_readiness_effect`: `DOES_NOT_CLOSE_B1_B5`" in checklist
    assert "`operational_status`: `BLOCKED`" in checklist
    assert "`connector_ready_dialects_expected`: `[]`" in checklist
    assert len(connector_ready_dialects()) == 1
    assert enablement.accepted is False
    assert public_connector_enablement_ready(enablement) is False
    assert report.connector_ready is False
    assert public_connector_readiness_ready(report) is False
    assert report.source_snapshots_ready is PublicConnectorReadinessStageStatus.BLOCKED
    assert report.claim_reviews_ready is PublicConnectorReadinessStageStatus.BLOCKED
    assert report.operational_evidence_ready is PublicConnectorReadinessStageStatus.BLOCKED
    assert report.connector_enablement_ready is PublicConnectorReadinessStageStatus.BLOCKED
    assert report.static_registry_verified is False


def test_phase24c_test_file_imports_only_inert_gate_modules() -> None:
    tree = ast.parse(SELF_PATH.read_text(encoding="utf-8"))
    import_from_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    direct_import_roots = {
        alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
    }

    assert direct_import_roots <= {"ast", "pathlib"}
    assert "__future__" in import_from_modules
    assert {module for module in import_from_modules if module.startswith("crypto_core.")} <= ALLOWED_CRYPTO_IMPORTS
