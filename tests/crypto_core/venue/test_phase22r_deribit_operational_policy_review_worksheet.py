from __future__ import annotations

import ast
from pathlib import Path

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.official_claim_reviews import (
    OfficialClaimReviewDecision,
    OfficialClaimReviewStatus,
    validate_official_claim_review,
)
from crypto_core.venue.official_source_snapshots import OfficialSourceSnapshot, validate_official_source_snapshot
from crypto_core.venue.operational_evidence_readiness import (
    OperationalEvidenceAcceptanceInput,
    OperationalPolicyApproval,
    OperationalPolicyApprovalStatus,
    evaluate_operational_evidence_acceptance,
    operational_evidence_acceptance_ready,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect

POLICY_WORKSHEET_PATH = Path(
    "docs/crypto_core/official_sources/deribit/20260510/DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md"
)
CHECKLIST_PATH = Path("docs/crypto_core/DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md")
MANIFEST_PATH = Path("docs/crypto_core/official_sources/deribit/20260510/DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md")
CLAIM_WORKSHEET_PATH = Path("docs/crypto_core/official_sources/deribit/20260510/DERIBIT_CLAIM_REVIEW_WORKSHEET.md")
ACCEPTANCE_CONTRACT_PATH = Path("src/crypto_core/venue/operational_evidence_readiness.py")
CLAIM_REVIEW_CONTRACT_PATH = Path("src/crypto_core/venue/official_claim_reviews.py")
SNAPSHOT_CONTRACT_PATH = Path("src/crypto_core/venue/official_source_snapshots.py")
CONNECTOR_CONTRACT_PATH = Path("src/crypto_core/data/deribit_public_connector_contract.py")
DIALECT_ID = "deribit:l2_orderbook:placeholder"
REQUIRED_POLICY_STATUS = {
    "checksum_decision": "PENDING_MANUAL_REVIEW",
    "liveness_policy": "PENDING_POLICY_BUDGET",
    "staleness_budget": "ENGINEERING_POLICY_PROPOSAL_PENDING_APPROVAL",
    "receive_lag_budget": "ENGINEERING_POLICY_PROPOSAL_PENDING_APPROVAL",
    "testnet_prod_review": "PENDING_MANUAL_REVIEW",
    "regional_legal_access_review": "MANUAL_LEGAL_ACCESS_REVIEW_REQUIRED",
    "separate_connector_enablement": "REQUIRED_SEPARATE_PHASE",
}
_PHASE26AN_APPROVED_POLICY_IDS = frozenset(
    {"checksum_decision", "liveness_policy", "staleness_budget", "receive_lag_budget", "testnet_prod_review"}
)
# Phase 26AW approved regional_legal_access_review; deferred separate_connector_enablement.
_PHASE26AW_APPROVED_POLICY_IDS = frozenset({"regional_legal_access_review"})
_PHASE26AW_DEFERRED_POLICY_IDS = frozenset({"separate_connector_enablement"})


def test_operational_policy_review_worksheet_exists():
    assert POLICY_WORKSHEET_PATH.is_file()


def test_all_required_operational_policy_rows_exist():
    rows = _policy_rows()

    assert set(rows) == set(REQUIRED_POLICY_STATUS)


def test_every_required_policy_row_is_pending_or_approved_or_deferred():
    # Phase 26AN approved 5 rows; Phase 26AW approved regional_legal_access_review and deferred separate_connector_enablement.
    for policy_id, row in _policy_rows().items():
        assert row["policy_id"] == policy_id
        assert row["venue_id"] == "deribit"
        assert row["manual_approval_required"] == "YES"
        assert row["operational_readiness_effect"] == "LEAVES_BLOCKER"
        if policy_id in _PHASE26AN_APPROVED_POLICY_IDS:
            assert row["policy_status"] == "APPROVED"
            assert row["policy_blocker_status"] == "APPROVED_FAIL_CLOSED"
            assert row["reviewer_id"] == "demir_operator"
            assert row["reviewed_at_iso"] == "2026-05-19T00:00:00Z"
            assert row["decision"] == "APPROVED"
        elif policy_id in _PHASE26AW_APPROVED_POLICY_IDS:
            assert row["policy_status"] == "APPROVED"
            assert row["reviewer_id"] == "demir_operator"
            assert row["reviewed_at_iso"] == "2026-05-19T00:00:00Z"
            assert row["decision"] == "APPROVE"
        elif policy_id in _PHASE26AW_DEFERRED_POLICY_IDS:
            assert row["policy_status"] == "DEFERRED"
            assert row["reviewer_id"] == "demir_operator"
            assert row["reviewed_at_iso"] == "2026-05-19T00:00:00Z"
            assert row["decision"] == "DEFER"


def test_checksum_decision_approved_in_phase26an():
    assert _policy_rows()["checksum_decision"]["policy_blocker_status"] == "APPROVED_FAIL_CLOSED"


def test_liveness_policy_approved_in_phase26an():
    assert _policy_rows()["liveness_policy"]["policy_blocker_status"] == "APPROVED_FAIL_CLOSED"


def test_staleness_budget_approved_in_phase26an():
    row = _policy_rows()["staleness_budget"]

    assert row["policy_blocker_status"] == "APPROVED_FAIL_CLOSED"
    assert row["engineering_policy_required"] == "YES"


def test_receive_lag_budget_approved_in_phase26an():
    row = _policy_rows()["receive_lag_budget"]

    assert row["policy_blocker_status"] == "APPROVED_FAIL_CLOSED"
    assert row["engineering_policy_required"] == "YES"


def test_testnet_prod_review_approved_in_phase26an():
    assert _policy_rows()["testnet_prod_review"]["policy_blocker_status"] == "APPROVED_FAIL_CLOSED"


def test_regional_legal_access_approved_in_phase26aw():
    row = _policy_rows()["regional_legal_access_review"]
    assert row["policy_blocker_status"] == "APPROVED_OPERATOR_LEGAL_SIGNOFF"
    assert row["legal_review_required"] == "YES"
    assert row["decision"] == "APPROVE"
    assert row["reviewer_id"] == "demir_operator"


def test_separate_connector_enablement_deferred_in_phase26aw():
    row = _policy_rows()["separate_connector_enablement"]

    assert row["policy_blocker_status"] == "REQUIRED_SEPARATE_PHASE"
    assert row["decision"] == "DEFER"
    assert row["reviewer_id"] == "demir_operator"


def test_checklist_references_policy_worksheet_and_remains_blocked():
    checklist = _checklist()

    assert "DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md" in checklist
    assert "`phase22r_operational_policy_review_status`: `BLOCKED_PENDING_POLICY_APPROVALS`" in checklist
    assert "`operational_status`: `BLOCKED`" in checklist
    assert "`operational_status`: `READY`" not in checklist
    assert "`enabled_for_connector`: `true`" not in checklist


def test_operational_evidence_acceptance_cannot_pass_current_deribit_policy_rows():
    result = evaluate_operational_evidence_acceptance(_current_deribit_acceptance_input())

    assert result.accepted is False
    assert operational_evidence_acceptance_ready(result) is False
    assert "operational_evidence:source_snapshot_rejected" in result.rejection_reasons
    # claim_review_rejected no longer present after Phase 26AR approved all 23 claim rows
    # Phase 26AN approved these 5 policy rows — they must NOT appear as missing.
    assert "operational_policy:checksum_decision_missing" not in result.rejection_reasons
    assert "operational_policy:liveness_policy_missing" not in result.rejection_reasons
    assert "operational_policy:staleness_budget_missing" not in result.rejection_reasons
    assert "operational_policy:receive_lag_budget_missing" not in result.rejection_reasons
    assert "operational_policy:testnet_prod_review_missing" not in result.rejection_reasons
    # regional_legal_access_review APPROVED in Phase 26AW — no longer missing.
    assert "operational_policy:regional_legal_access_review_missing" not in result.rejection_reasons
    # separate_connector_enablement DEFERRED in Phase 26AW — connector enablement still required.
    assert "operational_policy:separate_connector_enablement_required" in result.rejection_reasons


def test_static_registry_remains_unverified_and_connector_ready_empty():
    spec = get_public_feed_dialect(DIALECT_ID)

    assert spec.verification_status.value == "unverified"
    assert spec.enabled_for_connector is False
    assert connector_ready_dialects() == ()


def test_no_source_behavior_network_connector_private_order_or_live_paths_changed():
    for path in (ACCEPTANCE_CONTRACT_PATH, CLAIM_REVIEW_CONTRACT_PATH, SNAPSHOT_CONTRACT_PATH, CONNECTOR_CONTRACT_PATH):
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
        assert "executionmode.live" not in source.lower()
        assert "orderintent" not in source.lower()


def _current_deribit_acceptance_input() -> OperationalEvidenceAcceptanceInput:
    return OperationalEvidenceAcceptanceInput(
        venue_id=VenueId.DERIBIT,
        source_snapshot_results=tuple(
            validate_official_source_snapshot(_snapshot_from_row(row)) for row in _manifest_rows().values()
        ),
        claim_review_results=tuple(
            validate_official_claim_review(_claim_from_row(row)) for row in _claim_rows().values()
        ),
        policy_approvals=tuple(_policy_from_row(row) for row in _policy_rows().values()),
        static_registry_verified=False,
        connector_enablement_requested=False,
        rejection_reasons=(),
    )


def _policy_rows() -> dict[str, dict[str, str]]:
    return _table_rows(_policy_worksheet(), "policy_id")


def _claim_rows() -> dict[str, dict[str, str]]:
    return _table_rows(_claim_worksheet(), "claim_id")


def _manifest_rows() -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for line in _manifest().splitlines():
        if not line.startswith("| `DERIBIT_"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        rows[cells[0].strip("`")] = {
            "source_id": cells[0].strip("`"),
            "official_url": cells[1].strip("`"),
            "retrieved_at_iso": cells[2].strip("`"),
            "content_sha256": cells[4].strip("`"),
            "content_size_bytes": cells[5],
        }
    return rows


def _table_rows(text: str, id_column: str) -> dict[str, dict[str, str]]:
    headers: list[str] | None = None
    rows: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells[0] == id_column:
            headers = cells
            continue
        if headers is None or cells[0] == "---" or not cells[0].startswith("`"):
            continue
        row = {header: value.strip("`") for header, value in zip(headers, cells, strict=True)}
        rows[row[id_column]] = row
    return rows


def _snapshot_from_row(row: dict[str, str]) -> OfficialSourceSnapshot:
    return OfficialSourceSnapshot(
        snapshot_id=f"{row['source_id']}:phase22r",
        source_id=row["source_id"],
        venue_id=VenueId.DERIBIT,
        official_url=row["official_url"],
        retrieved_at_iso=row["retrieved_at_iso"],
        content_sha256=row["content_sha256"],
        content_size_bytes=int(row["content_size_bytes"]),
        reviewer_id="PENDING",
        reviewed_at_iso="PENDING",
        manual_review_status="PENDING",
        rejection_reasons=(),
    )


def _claim_from_row(row: dict[str, str]) -> OfficialClaimReviewDecision:
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


def _policy_from_row(row: dict[str, str]) -> OperationalPolicyApproval:
    # DEFERRED rows are mapped to PENDING for the acceptance-readiness check (not approved).
    status_str = row["policy_status"]
    if status_str == "DEFERRED":
        status_str = "PENDING"
    return OperationalPolicyApproval(
        policy_id=row["policy_id"],
        venue_id=VenueId.DERIBIT,
        policy_status=OperationalPolicyApprovalStatus(status_str),
        reviewer_id=row["reviewer_id"],
        reviewed_at_iso=row["reviewed_at_iso"],
        rejection_reasons=(),
    )


def _policy_worksheet() -> str:
    return POLICY_WORKSHEET_PATH.read_text(encoding="utf-8")


def _claim_worksheet() -> str:
    return CLAIM_WORKSHEET_PATH.read_text(encoding="utf-8")


def _manifest() -> str:
    return MANIFEST_PATH.read_text(encoding="utf-8")


def _checklist() -> str:
    return CHECKLIST_PATH.read_text(encoding="utf-8")
