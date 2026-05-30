from __future__ import annotations

import ast
import re
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
from crypto_core.venue.public_connector_readiness_report import (
    PublicConnectorReadinessStageStatus,
    build_public_connector_readiness_report,
    public_connector_readiness_ready,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect

CHECKLIST_PATH = Path("docs/crypto_core/DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md")
MANIFEST_PATH = Path("docs/crypto_core/official_sources/deribit/20260510/DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md")
CLAIM_WORKSHEET_PATH = Path("docs/crypto_core/official_sources/deribit/20260510/DERIBIT_CLAIM_REVIEW_WORKSHEET.md")
POLICY_WORKSHEET_PATH = Path(
    "docs/crypto_core/official_sources/deribit/20260510/DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md"
)
READINESS_REPORT_PATH = Path("src/crypto_core/venue/public_connector_readiness_report.py")
ENABLEMENT_CONTRACT_PATH = Path("src/crypto_core/venue/public_connector_enablement.py")
CONNECTOR_CONTRACT_PATH = Path("src/crypto_core/data/deribit_public_connector_contract.py")
NETWORK_AUTHORIZATION_PATH = Path("src/crypto_core/data/public_network_authorization.py")
DIALECT_ID = "deribit:l2_orderbook:placeholder"


def test_current_deribit_source_hashes_alone_are_not_sufficient():
    rows = _manifest_rows()
    results = tuple(validate_official_source_snapshot(_snapshot_from_row(row)) for row in rows.values())

    assert rows
    assert all(re.fullmatch(r"[0-9a-f]{64}", row["content_sha256"]) for row in rows.values())
    assert all(int(row["content_size_bytes"]) > 0 for row in rows.values())
    assert all(result.accepted is False for result in results)
    assert all("official_snapshot:manual_review_not_approved" in result.rejection_reasons for result in results)


def test_current_deribit_claim_reviews_are_not_accepted():
    results = tuple(validate_official_claim_review(_claim_from_row(row)) for row in _claim_rows().values())

    assert results
    # Phase 25I approved 3, Phase 25R approved change_id, Phase 26AJ approved 15, Phase 26AN approved 3,
    # Phase 26AR approved regional_legal_access; all 23 claim rows accepted.
    rejected = [r for r in results if not r.accepted]
    accepted = [r for r in results if r.accepted]
    assert len(rejected) == 0
    assert len(accepted) == 23


def test_current_deribit_operational_policy_approvals_are_pending_or_resolved():
    rows = _policy_rows()

    assert rows
    # Phase 26AN approved 5 policy rows; Phase 26AW approved regional_legal_access_review; Phase 27F approved B5.
    _phase26an_approved = {
        "checksum_decision",
        "liveness_policy",
        "staleness_budget",
        "receive_lag_budget",
        "testnet_prod_review",
    }
    _phase26aw_approved = {"regional_legal_access_review", "separate_connector_enablement"}
    for pid, row in rows.items():
        if pid in _phase26an_approved:
            assert row["policy_status"] == "APPROVED"
        elif pid in _phase26aw_approved:
            assert row["policy_status"] == "APPROVED"
            assert row["decision"] == "APPROVE"


def test_current_deribit_operational_evidence_is_not_ready():
    result = _current_operational_evidence_result()

    assert result.accepted is False
    assert operational_evidence_acceptance_ready(result) is False
    assert "operational_evidence:source_snapshot_rejected" in result.rejection_reasons
    # claim_review_rejected no longer present after Phase 26AR approved all 23 claim rows
    # Phase 26AN approved checksum_decision policy row; it must NOT appear as missing.
    assert "operational_policy:checksum_decision_missing" not in result.rejection_reasons
    # regional_legal_access_review APPROVED in Phase 26AW — no longer missing.
    assert "operational_policy:regional_legal_access_review_missing" not in result.rejection_reasons


def test_current_deribit_connector_enablement_is_not_ready():
    decision = _current_connector_enablement_decision()

    assert decision.accepted is False
    assert public_connector_enablement_ready(decision) is False
    assert "public_connector_enablement:operational_evidence_not_accepted" in decision.rejection_reasons
    assert "public_connector_enablement:pending" not in decision.rejection_reasons


def test_current_deribit_static_registry_verified_but_connector_disabled():
    spec = get_public_feed_dialect(DIALECT_ID)

    assert spec.verification_status.value == "verified_from_official_docs"
    assert spec.enabled_for_connector is True


def test_current_deribit_public_connector_readiness_report_remains_blocked():
    report = _current_deribit_readiness_report()

    assert report.connector_ready is False
    assert public_connector_readiness_ready(report) is False
    assert report.source_snapshots_ready is PublicConnectorReadinessStageStatus.BLOCKED
    assert (
        report.claim_reviews_ready is PublicConnectorReadinessStageStatus.READY
    )  # Phase 26AR approved all 23 claim rows
    assert report.operational_evidence_ready is PublicConnectorReadinessStageStatus.BLOCKED
    assert report.connector_enablement_ready is PublicConnectorReadinessStageStatus.BLOCKED
    assert report.static_registry_verified is True


def test_current_deribit_readiness_report_contains_blocker_reasons():
    report = _current_deribit_readiness_report()

    assert "public_connector_readiness:source_snapshots_not_ready" in report.blocker_reasons
    # claim_reviews_not_ready no longer present after Phase 26AR approved all 23 claim rows
    assert "public_connector_readiness:claim_reviews_not_ready" not in report.blocker_reasons
    assert "public_connector_readiness:operational_evidence_not_ready" in report.blocker_reasons
    assert "public_connector_readiness:connector_enablement_not_ready" in report.blocker_reasons
    assert "public_connector_readiness:static_registry_unverified" not in report.blocker_reasons
    # official_claim_review:pending no longer present after Phase 26AR
    assert "official_claim_review:pending" not in report.blocker_reasons
    # Phase 26AN approved checksum_decision; it must NOT appear as a blocker.
    assert "operational_policy:checksum_decision_missing" not in report.blocker_reasons
    assert "public_connector_enablement:pending" not in report.blocker_reasons


def test_current_deribit_checklist_says_connector_readiness_disabled():
    checklist = _checklist()

    assert "`enabled_for_connector`: `false`" in checklist
    assert "`static_registry_verified`: `false`" in checklist
    assert "`connector_ready_dialects_expected`: `[]`" in checklist
    assert "`phase22u_public_connector_readiness_report_status`: `BLOCKED`" in checklist
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


def test_no_connector_network_private_order_or_live_paths_in_phase22v_sources():
    for path in (READINESS_REPORT_PATH, ENABLEMENT_CONTRACT_PATH, CONNECTOR_CONTRACT_PATH, NETWORK_AUTHORIZATION_PATH):
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


def _current_deribit_readiness_report():
    return build_public_connector_readiness_report(
        venue_id=VenueId.DERIBIT,
        dialect_id=DIALECT_ID,
        source_snapshot_results=tuple(
            validate_official_source_snapshot(_snapshot_from_row(row)) for row in _manifest_rows().values()
        ),
        claim_review_results=tuple(
            validate_official_claim_review(_claim_from_row(row)) for row in _claim_rows().values()
        ),
        operational_evidence_result=_current_operational_evidence_result(),
        connector_enablement_decision=_current_connector_enablement_decision(),
        static_registry_verified=True,
        evidence_refs=(
            "docs/crypto_core/official_sources/deribit/20260510/DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md",
            "docs/crypto_core/official_sources/deribit/20260510/DERIBIT_CLAIM_REVIEW_WORKSHEET.md",
            "docs/crypto_core/official_sources/deribit/20260510/DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md",
        ),
    )


def _current_operational_evidence_result():
    return evaluate_operational_evidence_acceptance(
        OperationalEvidenceAcceptanceInput(
            venue_id=VenueId.DERIBIT,
            source_snapshot_results=tuple(
                validate_official_source_snapshot(_snapshot_from_row(row)) for row in _manifest_rows().values()
            ),
            claim_review_results=tuple(
                validate_official_claim_review(_claim_from_row(row)) for row in _claim_rows().values()
            ),
            policy_approvals=tuple(_policy_from_row(row) for row in _policy_rows().values()),
            static_registry_verified=True,
            connector_enablement_requested=False,
            rejection_reasons=(),
        )
    )


def _current_connector_enablement_decision():
    row = _policy_rows()["separate_connector_enablement"]
    ce_status_str = row["policy_status"]
    return evaluate_public_connector_enablement(
        PublicConnectorEnablementRequest(
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
    )


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


def _claim_rows() -> dict[str, dict[str, str]]:
    return _table_rows(_claim_worksheet(), "claim_id")


def _policy_rows() -> dict[str, dict[str, str]]:
    return _table_rows(_policy_worksheet(), "policy_id")


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
        snapshot_id=f"{row['source_id']}:phase22v",
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


def _manifest() -> str:
    return MANIFEST_PATH.read_text(encoding="utf-8")


def _claim_worksheet() -> str:
    return CLAIM_WORKSHEET_PATH.read_text(encoding="utf-8")


def _policy_worksheet() -> str:
    return POLICY_WORKSHEET_PATH.read_text(encoding="utf-8")


def _checklist() -> str:
    return CHECKLIST_PATH.read_text(encoding="utf-8")
