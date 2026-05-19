from __future__ import annotations

import ast
import re
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
    evaluate_operational_evidence_acceptance,
    operational_evidence_acceptance_ready,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect

MANIFEST_PATH = Path("docs/crypto_core/official_sources/deribit/20260510/DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md")
WORKSHEET_PATH = Path("docs/crypto_core/official_sources/deribit/20260510/DERIBIT_CLAIM_REVIEW_WORKSHEET.md")
CHECKLIST_PATH = Path("docs/crypto_core/DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md")
ACCEPTANCE_CONTRACT_PATH = Path("src/crypto_core/venue/operational_evidence_readiness.py")
CLAIM_REVIEW_CONTRACT_PATH = Path("src/crypto_core/venue/official_claim_reviews.py")
SNAPSHOT_CONTRACT_PATH = Path("src/crypto_core/venue/official_source_snapshots.py")
CONNECTOR_CONTRACT_PATH = Path("src/crypto_core/data/deribit_public_connector_contract.py")
DIALECT_ID = "deribit:l2_orderbook:placeholder"


def test_current_deribit_source_hashes_exist_but_are_not_enough():
    rows = _manifest_rows()
    results = tuple(validate_official_source_snapshot(_snapshot_from_row(row)) for row in rows.values())

    assert rows
    assert all(re.fullmatch(r"[0-9a-f]{64}", row["content_sha256"]) for row in rows.values())
    assert all(int(row["content_size_bytes"]) > 0 for row in rows.values())
    assert all(row["retrieval_status"] == "REVIEWED_APPROVED" for row in rows.values())
    assert all(result.accepted is False for result in results)
    assert all("official_snapshot:manual_review_not_approved" in result.rejection_reasons for result in results)


def test_current_deribit_claim_reviews_are_not_accepted():
    results = tuple(validate_official_claim_review(_claim_from_row(row)) for row in _worksheet_rows().values())

    assert results
    # Phase 25I approved 3 rows, Phase 25R approved change_id, Phase 26AJ approved 15 technical rows,
    # Phase 26AN approved 3 more, Phase 26AR approved regional_legal_access; all 23 rows accepted.
    rejected = [r for r in results if not r.accepted]
    accepted = [r for r in results if r.accepted]
    assert len(rejected) == 0
    assert len(accepted) == 23


def test_current_deribit_required_policies_are_missing_or_pending():
    checklist = _checklist()

    assert "`checksum_decision_reviewed`: `PENDING`" in checklist
    assert "`heartbeat_ping_pong_liveness_proof_reviewed`: `PENDING`" in checklist
    assert "`staleness_budget_defined`: `PENDING`" in checklist
    assert "`receive_lag_budget_defined`: `PENDING`" in checklist
    assert "`testnet_prod_difference_reviewed`: `PENDING`" in checklist
    assert "`regional_legal_access_reviewed`: `PENDING`" in checklist


def test_current_deribit_operational_evidence_acceptance_rejects():
    result = evaluate_operational_evidence_acceptance(_current_deribit_acceptance_input())

    assert result.accepted is False
    assert operational_evidence_acceptance_ready(result) is False
    assert "operational_evidence:source_snapshot_rejected" in result.rejection_reasons
    # claim_review_rejected no longer present after Phase 26AR approved all 23 claim rows
    assert "operational_policy:regional_legal_access_review_missing" in result.rejection_reasons


def test_deribit_checklist_says_operational_status_blocked():
    checklist = _checklist()

    assert "`operational_status`: `BLOCKED`" in checklist
    assert "`phase22p_operational_acceptance_status`: `BLOCKED_PENDING_POLICY_APPROVALS`" in checklist
    assert "`operational_status`: `READY`" not in checklist
    assert "`enabled_for_connector`: `true`" not in checklist


def test_deribit_policy_blockers_remain_in_checklist():
    checklist = _checklist()

    assert "`checksum_decision_reviewed`: `PENDING`" in checklist
    assert "`heartbeat_ping_pong_liveness_proof_reviewed`: `PENDING`" in checklist
    assert "`staleness_budget_defined`: `PENDING`" in checklist
    assert "`receive_lag_budget_defined`: `PENDING`" in checklist
    assert "`testnet_prod_difference_reviewed`: `PENDING`" in checklist
    assert "`regional_legal_access_reviewed`: `PENDING`" in checklist


def test_deribit_static_registry_verified_and_connector_ready_empty():
    spec = get_public_feed_dialect(DIALECT_ID)

    assert spec.verification_status.value == "verified_from_official_docs"
    assert spec.enabled_for_connector is True
    assert len(connector_ready_dialects()) == 1


def test_no_connector_network_private_order_or_live_paths_in_phase22q_sources():
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
            validate_official_claim_review(_claim_from_row(row)) for row in _worksheet_rows().values()
        ),
        policy_approvals=(),
        static_registry_verified=False,
        connector_enablement_requested=False,
        rejection_reasons=(),
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
            "retrieval_status": cells[3].strip("`"),
            "content_sha256": cells[4].strip("`"),
            "content_size_bytes": cells[5],
        }
    return rows


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


def _snapshot_from_row(row: dict[str, str]) -> OfficialSourceSnapshot:
    return OfficialSourceSnapshot(
        snapshot_id=f"{row['source_id']}:phase22q",
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


def _manifest() -> str:
    return MANIFEST_PATH.read_text(encoding="utf-8")


def _worksheet() -> str:
    return WORKSHEET_PATH.read_text(encoding="utf-8")


def _checklist() -> str:
    return CHECKLIST_PATH.read_text(encoding="utf-8")
