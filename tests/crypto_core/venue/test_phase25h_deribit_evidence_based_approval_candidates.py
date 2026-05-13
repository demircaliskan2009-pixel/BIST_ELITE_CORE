from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    CLAIM_WORKSHEET_PATH,
    MANIFEST_PATH,
    POLICY_WORKSHEET_PATH,
    _parse_md_table_rows,
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
DOC_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_EVIDENCE_BASED_APPROVAL_CANDIDATES.md"


def _doc_text() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def _doc_rows() -> list[dict[str, str]]:
    return _parse_md_table_rows(_doc_text())


def _expected_pairs() -> set[tuple[str, str]]:
    manifest_rows = _parse_md_table_rows((REPO_ROOT / MANIFEST_PATH).read_text(encoding="utf-8"))
    claim_rows = _parse_md_table_rows((REPO_ROOT / CLAIM_WORKSHEET_PATH).read_text(encoding="utf-8"))
    policy_rows = _parse_md_table_rows((REPO_ROOT / POLICY_WORKSHEET_PATH).read_text(encoding="utf-8"))

    expected: set[tuple[str, str]] = set()
    expected.update(("source_snapshot", row["source_id"]) for row in manifest_rows)
    expected.update(("claim_review", row["claim_id"]) for row in claim_rows)
    expected.update(("policy_review", row["policy_id"]) for row in policy_rows)
    return expected


def test_phase25h_doc_exists_and_has_expected_status_and_instruction():
    assert DOC_PATH.exists()

    doc = _doc_text()
    assert "status: OPERATOR_DECISION_CANDIDATES_ONLY" in doc
    assert "total_rows: 36" in doc
    assert "approve_now_candidates_count: 9" in doc
    assert "wait_policy_value_count: 8" in doc
    assert "wait_external_legal_count: 2" in doc
    assert "must_defer_separate_connector_phase_count: 1" in doc
    assert "wait_insufficient_evidence_count: 16" in doc
    assert (
        "If the operator accepts this package, the next phase may patch only APPROVE_NOW_CANDIDATE rows into the worksheets with operator-provided reviewer_id and reviewed_at_iso. All other rows remain PENDING or DEFER."
        in doc
    )


def test_phase25h_all_36_rows_appear_once_in_exactly_one_bucket():
    rows = _doc_rows()
    actual_pairs = {(row["surface"], row["row_id"]) for row in rows}

    assert len(rows) == 36
    assert len(actual_pairs) == 36
    assert actual_pairs == _expected_pairs()

    bucket_counts = Counter(row["bucket"] for row in rows)
    assert bucket_counts == {
        "APPROVE_NOW_CANDIDATE": 9,
        "WAIT_POLICY_VALUE": 8,
        "WAIT_EXTERNAL_LEGAL": 2,
        "MUST_DEFER_SEPARATE_CONNECTOR_PHASE": 1,
        "WAIT_INSUFFICIENT_EVIDENCE": 16,
    }


def test_phase25h_legal_policy_and_connector_bucket_assignments_are_correct():
    rows = {(row["surface"], row["row_id"]): row["bucket"] for row in _doc_rows()}

    assert rows[("claim_review", "regional_legal_access")] == "WAIT_EXTERNAL_LEGAL"
    assert rows[("policy_review", "regional_legal_access_review")] == "WAIT_EXTERNAL_LEGAL"
    assert rows[("policy_review", "separate_connector_enablement")] == "MUST_DEFER_SEPARATE_CONNECTOR_PHASE"

    for pair in (
        ("claim_review", "checksum_decision"),
        ("claim_review", "staleness_budget"),
        ("claim_review", "receive_lag_budget"),
        ("policy_review", "checksum_decision"),
        ("policy_review", "liveness_policy"),
        ("policy_review", "staleness_budget"),
        ("policy_review", "receive_lag_budget"),
        ("policy_review", "testnet_prod_review"),
    ):
        assert rows[pair] == "WAIT_POLICY_VALUE"


def test_phase25h_does_not_add_final_reviewer_values_or_modify_worksheets():
    doc = _doc_text()
    manifest_rows = _parse_md_table_rows((REPO_ROOT / MANIFEST_PATH).read_text(encoding="utf-8"))
    claim_rows = _parse_md_table_rows((REPO_ROOT / CLAIM_WORKSHEET_PATH).read_text(encoding="utf-8"))
    policy_rows = _parse_md_table_rows((REPO_ROOT / POLICY_WORKSHEET_PATH).read_text(encoding="utf-8"))

    assert not re.search(r"reviewer-\d+", doc)
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", doc)
    assert len(manifest_rows) == 6
    assert all(row["retrieval_status"] == "SUPPLIED_HASHED_PENDING_REVIEW" for row in manifest_rows)
    assert len(claim_rows) == 23
    assert all(row["reviewer_id"] == "PENDING" for row in claim_rows)
    assert all(row["reviewed_at_iso"] == "PENDING" for row in claim_rows)
    assert all(row["decision"] == "PENDING" for row in claim_rows)
    assert len(policy_rows) == 7
    assert all(row["reviewer_id"] == "PENDING" for row in policy_rows)
    assert all(row["reviewed_at_iso"] == "PENDING" for row in policy_rows)
    assert all(row["decision"] == "PENDING" for row in policy_rows)


def test_phase25h_validator_and_connector_state_remain_blocked():
    result = evaluate_deribit_manual_review_readiness(
        manifest_path=REPO_ROOT / MANIFEST_PATH,
        claim_worksheet_path=REPO_ROOT / CLAIM_WORKSHEET_PATH,
        policy_worksheet_path=REPO_ROOT / POLICY_WORKSHEET_PATH,
    )

    assert result.accepted is False
    assert result.evidence_review_complete is False
    assert result.ready_for_engineering_patch is False
    assert result.connector_enablement_ready is False
    assert connector_ready_dialects() == ()
