from __future__ import annotations

import ast
from pathlib import Path

from crypto_core.venue.contracts import PublicFeedType, VenueId
from crypto_core.venue.official_claim_reviews import (
    OfficialClaimReviewDecision,
    OfficialClaimReviewStatus,
    aggregate_claim_review_results,
    official_claim_review_ready,
    validate_official_claim_review,
)
from crypto_core.venue.operational_evidence_readiness import (
    OPERATIONAL_PUBLIC_CONNECTOR_REQUIRED_FIELDS,
    OperationalEvidenceReadinessRequirement,
    evaluate_operational_public_connector_evidence,
    operational_evidence_ready,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect

WORKSHEET_PATH = Path("docs/crypto_core/official_sources/deribit/20260510/DERIBIT_CLAIM_REVIEW_WORKSHEET.md")
DERIBIT_DRAFT_PATH = Path("docs/crypto_core/DERIBIT_OFFICIAL_EVIDENCE_PACKAGE_DRAFT.md")
CHECKLIST_PATH = Path("docs/crypto_core/DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md")
CLAIM_REVIEW_CONTRACT_PATH = Path("src/crypto_core/venue/official_claim_reviews.py")
SNAPSHOT_CONTRACT_PATH = Path("src/crypto_core/venue/official_source_snapshots.py")
CONNECTOR_CONTRACT_PATH = Path("src/crypto_core/data/deribit_public_connector_contract.py")
DIALECT_ID = "deribit:l2_orderbook:placeholder"
REQUIRED_CLAIM_IDS = {
    "public_websocket_availability",
    "public_rest_availability",
    "prod_testnet_ws_endpoint",
    "prod_testnet_rest_endpoint",
    "unauthenticated_public_market_data",
    "orderbook_channel_feed",
    "first_message_snapshot",
    "incremental_delta",
    "change_id",
    "prev_change_id",
    "continuity_condition",
    "gap_resubscribe_rule",
    "rest_snapshot_requirement",
    "checksum_decision",
    "heartbeat_liveness_proof",
    "public_rate_subscription_limits",
    "public_trades",
    "ticker",
    "mark_index_funding_open_interest",
    "staleness_budget",
    "receive_lag_budget",
    "testnet_prod_difference",
    "regional_legal_access",
}


def test_current_deribit_claim_review_rows_are_not_approved():
    rows = _worksheet_rows()
    # Phase 25I approved 3 rows; Phase 25R approved change_id; Phase 26AJ approved 15 technical rows;
    # Phase 26AN approved 3 policy-decision claim rows (checksum_decision, staleness_budget, receive_lag_budget).
    approved_claim_ids = (
        frozenset({"public_websocket_availability", "unauthenticated_public_market_data", "orderbook_channel_feed"})
        | frozenset({"change_id"})
        | frozenset(
            {
                "public_rest_availability",
                "prod_testnet_ws_endpoint",
                "prod_testnet_rest_endpoint",
                "rest_snapshot_requirement",
                "gap_resubscribe_rule",
                "heartbeat_liveness_proof",
                "public_rate_subscription_limits",
                "public_trades",
                "ticker",
                "mark_index_funding_open_interest",
                "testnet_prod_difference",
                "first_message_snapshot",
                "incremental_delta",
                "prev_change_id",
                "continuity_condition",
            }
        )
        | frozenset({"checksum_decision", "staleness_budget", "receive_lag_budget"})
    )

    assert set(rows) == REQUIRED_CLAIM_IDS
    assert {row["operational_readiness_effect"] for row in rows.values()} == {"LEAVES_BLOCKER"}
    non_approved = {cid: row for cid, row in rows.items() if cid not in approved_claim_ids}
    # 1 row remains PENDING after Phase 26AN: regional_legal_access
    assert len(non_approved) == 1
    assert {row["review_status"] for row in non_approved.values()} == {"PENDING"}
    assert {row["decision"] for row in non_approved.values()} == {"PENDING"}
    assert all(row["reviewer_id"] == "PENDING" for row in non_approved.values())
    assert all(row["reviewed_at_iso"] == "PENDING" for row in non_approved.values())


def test_current_deribit_claim_reviews_cannot_satisfy_operational_readiness():
    results = tuple(validate_official_claim_review(_decision_from_row(row)) for row in _worksheet_rows().values())
    aggregate = aggregate_claim_review_results(results)

    readiness = evaluate_operational_public_connector_evidence(
        venue_id=VenueId.DERIBIT,
        dialect_id=DIALECT_ID,
        feed_type=PublicFeedType.L2_ORDERBOOK,
        evidence_package=None,
        dialect_verification_result=None,
        required_fields=_requirements_from_claim_review_aggregate(aggregate),
    )

    # Phase 26AN approved 3 more claim rows; 1 remains PENDING (regional_legal_access); aggregate + readiness remain blocked.
    rejected_results = [r for r in results if not r.accepted]
    assert len(rejected_results) == 1
    assert aggregate.accepted is False
    assert aggregate.review_status is OfficialClaimReviewStatus.PENDING
    assert "official_claim_review:pending" in aggregate.rejection_reasons
    assert official_claim_review_ready(aggregate) is False
    assert readiness.accepted is False
    assert operational_evidence_ready(readiness) is False
    assert "operational_evidence:manual_review_missing" in readiness.rejection_reasons
    assert "operational_evidence:checksum_decision_missing" in readiness.rejection_reasons
    assert "operational_evidence:heartbeat_unknown" in readiness.rejection_reasons


def test_manual_approval_and_operational_status_remain_blocked_in_docs():
    combined = _checklist() + "\n" + _draft() + "\n" + _worksheet()

    assert "`manual_approval_status`: `PENDING`" in combined
    assert "`manual_review_status`: `PENDING`" in combined
    assert "`operational_status`: `BLOCKED`" in combined
    assert "`operational_status`: `READY`" not in combined
    assert "`enabled_for_connector`: `true`" not in combined


def test_required_operational_blockers_remain_pending_or_unknown():
    checklist = _checklist()
    combined = _checklist() + "\n" + _draft()

    assert "`checksum_decision_reviewed`: `PENDING`" in checklist
    assert "`heartbeat_ping_pong_liveness_proof_reviewed`: `PENDING`" in checklist
    assert "`staleness_budget_defined`: `PENDING`" in checklist
    assert "`receive_lag_budget_defined`: `PENDING`" in checklist
    assert "`testnet_prod_difference_reviewed`: `PENDING`" in checklist
    assert "`regional_legal_access_reviewed`: `PENDING`" in checklist
    assert "`checksum_absence_status`: `UNKNOWN_OR_NOT_DOCUMENTED_IN_REVIEWED_OFFICIAL_SOURCES`" in combined
    assert "`heartbeat_ping_pong_liveness_status`: `UNKNOWN_BLOCKED`" in combined
    assert "`staleness_budget_status`: `UNSATISFIED`" in combined
    assert "`receive_lag_budget_status`: `UNSATISFIED`" in combined
    assert "`testnet_prod_semantic_equivalence`: `UNKNOWN`" in combined
    assert "`regional_legal_access_status`: `MANUAL_LEGAL_ACCESS_REVIEW_REQUIRED`" in combined


def test_static_registry_remains_unverified_and_connector_ready_dialects_empty():
    spec = get_public_feed_dialect(DIALECT_ID)

    assert spec.verification_status.value == "unverified"
    assert spec.enabled_for_connector is False
    assert connector_ready_dialects() == ()


def test_phase22o_source_contracts_have_no_runtime_network_or_connector_methods():
    for path in (CLAIM_REVIEW_CONTRACT_PATH, SNAPSHOT_CONTRACT_PATH, CONNECTOR_CONTRACT_PATH):
        source = path.read_text(encoding="utf-8")
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
        assert "api_key" not in source.lower()
        assert "api_secret" not in source.lower()
        assert "getenv" not in source.lower()
        assert "os.environ" not in source.lower()


def _worksheet_rows() -> dict[str, dict[str, str]]:
    headers: list[str] | None = None
    rows: dict[str, dict[str, str]] = {}
    for line in _worksheet().splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells[0] == "claim_id":
            headers = cells
            continue
        if headers is None or cells[0] == "---" or not cells[0].startswith("`"):
            continue
        row = {header: value.strip("`") for header, value in zip(headers, cells, strict=True)}
        rows[row["claim_id"]] = row
    return rows


def _decision_from_row(row: dict[str, str]) -> OfficialClaimReviewDecision:
    return OfficialClaimReviewDecision(
        claim_id=row["claim_id"],
        source_id=row["source_id"],
        venue_id=VenueId.DERIBIT,
        source_sha256=row["source_sha256"],
        official_url=row["official_url"],
        doc_section_or_anchor=row["doc_section_or_anchor"],
        reviewer_id=row["reviewer_id"],
        reviewed_at_iso=row["reviewed_at_iso"],
        review_status=OfficialClaimReviewStatus(row["review_status"]),
        decision=OfficialClaimReviewStatus(row["decision"]),
        evidence_refs=(f"{row['source_id']}:{row['doc_section_or_anchor']}",),
        rejection_reasons=(),
    )


def _requirements_from_claim_review_aggregate(
    aggregate: object,
) -> tuple[OperationalEvidenceReadinessRequirement, ...]:
    supplied = {
        "real_official_urls_present",
        "reproducible_content_hashes_present",
        "retrieval_timestamps_present",
        "static_registry_not_enabled",
        "connector_ready_dialects_empty",
    }
    if official_claim_review_ready(aggregate):  # pragma: no cover - current worksheet must stay blocked
        supplied |= {
            "manual_review_approved",
            "sequence_model_verified",
            "snapshot_delta_resync_verified",
            "checksum_decision_verified",
            "rate_limits_verified",
            "staleness_budget_verified",
            "receive_lag_budget_verified",
            "heartbeat_or_ping_pong_verified",
            "testnet_prod_difference_reviewed",
            "regional_access_reviewed",
        }
    return tuple(
        OperationalEvidenceReadinessRequirement(
            requirement_id=f"phase22o:{field}",
            field_name=field,
            satisfied=field in supplied,
            evidence_refs=(f"phase22o:{field}",) if field in supplied else (),
            rejection_reasons=(),
        )
        for field in OPERATIONAL_PUBLIC_CONNECTOR_REQUIRED_FIELDS
    )


def _worksheet() -> str:
    return WORKSHEET_PATH.read_text(encoding="utf-8")


def _draft() -> str:
    return DERIBIT_DRAFT_PATH.read_text(encoding="utf-8")


def _checklist() -> str:
    return CHECKLIST_PATH.read_text(encoding="utf-8")
