from __future__ import annotations

import ast
from pathlib import Path

from crypto_core.data.public_network_authorization import (
    evaluate_public_network_authorization,
    public_network_authorization_ready,
)
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
from crypto_core.venue.public_connector_enablement import (
    PublicConnectorEnablementRequest,
    PublicConnectorEnablementStatus,
    evaluate_public_connector_enablement,
    public_connector_enablement_ready,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect

CHECKLIST_PATH = Path("docs/crypto_core/DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md")
POLICY_WORKSHEET_PATH = Path(
    "docs/crypto_core/official_sources/deribit/20260510/DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md"
)
MANIFEST_PATH = Path("docs/crypto_core/official_sources/deribit/20260510/DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md")
CLAIM_WORKSHEET_PATH = Path("docs/crypto_core/official_sources/deribit/20260510/DERIBIT_CLAIM_REVIEW_WORKSHEET.md")
ENABLEMENT_CONTRACT_PATH = Path("src/crypto_core/venue/public_connector_enablement.py")
CONNECTOR_CONTRACT_PATH = Path("src/crypto_core/data/deribit_public_connector_contract.py")
NETWORK_AUTHORIZATION_PATH = Path("src/crypto_core/data/public_network_authorization.py")
DIALECT_ID = "deribit:l2_orderbook:placeholder"


def test_current_deribit_operational_evidence_is_not_accepted():
    result = evaluate_operational_evidence_acceptance(_current_deribit_acceptance_input())

    assert result.accepted is False
    assert operational_evidence_acceptance_ready(result) is False
    assert "operational_evidence:source_snapshot_rejected" in result.rejection_reasons
    # claim_review_rejected no longer present after Phase 26AR approved all 23 claim rows
    assert "operational_policy:separate_connector_enablement_required" not in result.rejection_reasons


def test_current_deribit_static_registry_verified_but_connector_disabled():
    spec = get_public_feed_dialect(DIALECT_ID)

    assert spec.verification_status.value == "verified_from_official_docs"
    assert spec.enabled_for_connector is True


def test_current_deribit_connector_enablement_policy_row_approved_public_market_data():
    row = _policy_rows()["separate_connector_enablement"]

    assert row["policy_status"] == "APPROVED"
    assert row["policy_blocker_status"] == "APPROVED_PUBLIC_MARKET_DATA_ONLY"
    assert row["decision"] == "APPROVE"
    assert row["reviewer_id"] == "demir_operator"
    assert row["reviewed_at_iso"] == "2026-05-19T00:00:00Z"


def test_current_deribit_connector_enablement_decision_rejects():
    decision = evaluate_public_connector_enablement(_current_deribit_enablement_request())

    assert decision.accepted is False
    assert public_connector_enablement_ready(decision) is False
    assert "public_connector_enablement:operational_evidence_not_accepted" in decision.rejection_reasons
    assert "public_connector_enablement:static_registry_unverified" not in decision.rejection_reasons
    assert "public_connector_enablement:pending" not in decision.rejection_reasons
    # reviewer_id and reviewed_at_iso now set after Phase 26AW; missing_reviewer/missing_review_time no longer fire.
    assert "public_connector_enablement:missing_reviewer" not in decision.rejection_reasons
    assert "public_connector_enablement:missing_review_time" not in decision.rejection_reasons
    assert "public_connector_enablement:invalid_run_mode" not in decision.rejection_reasons


def test_current_deribit_checklist_says_connector_readiness_disabled():
    checklist = _checklist()

    assert "`enabled_for_connector`: `false`" in checklist
    assert "`static_registry_verified`: `false`" in checklist
    assert "`connector_ready_dialects_expected`: `[]`" in checklist
    assert "`operational_status`: `BLOCKED`" in checklist
    assert "`enabled_for_connector`: `true`" not in checklist


def test_current_deribit_connector_ready_dialects_remain_empty():
    assert len(connector_ready_dialects()) == 1


def test_current_deribit_dialect_is_not_verified_true():
    spec = get_public_feed_dialect(DIALECT_ID)

    assert spec.verification_status.value != "verified"
    assert spec.enabled_for_connector is True


def test_public_network_test_harness_is_not_enabled_for_current_deribit():
    decision = evaluate_public_network_authorization(None)

    assert decision.accepted is False
    assert public_network_authorization_ready(decision) is False
    assert decision.rejection_reasons == ("public_network:authorization_missing",)


def test_no_connector_network_private_order_or_live_paths_in_phase22t_sources():
    for path in (ENABLEMENT_CONTRACT_PATH, CONNECTOR_CONTRACT_PATH, NETWORK_AUTHORIZATION_PATH):
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


def _current_deribit_enablement_request() -> PublicConnectorEnablementRequest:
    row = _policy_rows()["separate_connector_enablement"]
    ce_status_str = row["policy_status"]
    return PublicConnectorEnablementRequest(
        venue_id=VenueId.DERIBIT,
        dialect_id=DIALECT_ID,
        operational_evidence_accepted=False,
        static_registry_verified=True,
        connector_enablement_status=PublicConnectorEnablementStatus(ce_status_str),
        reviewer_id=row["reviewer_id"],
        reviewed_at_iso=row["reviewed_at_iso"],
        approved_run_mode="PUBLIC_MARKET_DATA_ONLY",
        evidence_refs=(row["source_refs"], row["claim_refs"]),
        rejection_reasons=(),
    )


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
        snapshot_id=f"{row['source_id']}:phase22t",
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
    # DEFERRED rows are treated as PENDING for acceptance-readiness.
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
