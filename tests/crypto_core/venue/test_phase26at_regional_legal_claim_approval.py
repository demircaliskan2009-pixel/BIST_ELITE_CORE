"""Phase 26AT — Verify claim row approval and remaining policy blockers."""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
CLAIM_WORKSHEET_PATH = "docs/crypto_core/official_sources/deribit/20260510/DERIBIT_CLAIM_REVIEW_WORKSHEET.md"
POLICY_WORKSHEET_PATH = (
    "docs/crypto_core/official_sources/deribit/20260510/DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md"
)
MANIFEST_PATH = "docs/crypto_core/official_sources/deribit/20260510/DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md"
PROPOSAL_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OPERATOR_LEGAL_SIGNOFF_PROPOSAL_26AT.md"


def _result():
    return evaluate_deribit_manual_review_readiness(
        manifest_path=REPO_ROOT / MANIFEST_PATH,
        claim_worksheet_path=REPO_ROOT / CLAIM_WORKSHEET_PATH,
        policy_worksheet_path=REPO_ROOT / POLICY_WORKSHEET_PATH,
    )


def test_phase26at_regional_legal_access_claim_approved() -> None:
    result = _result()
    assert "claim_review:regional_legal_access" not in result.pending_rows


def test_phase26at_pending_rows_count_is_2() -> None:
    result = _result()
    assert len(result.pending_rows) == 2


def test_phase26at_policy_regional_legal_access_review_still_pending() -> None:
    result = _result()
    assert "policy_review:regional_legal_access_review" in result.pending_rows


def test_phase26at_policy_separate_connector_enablement_still_pending() -> None:
    result = _result()
    assert "policy_review:separate_connector_enablement" in result.pending_rows


def test_phase26at_accepted_is_false() -> None:
    assert _result().accepted is False


def test_phase26at_evidence_review_complete_is_false() -> None:
    assert _result().evidence_review_complete is False


def test_phase26at_connector_enablement_ready_is_false() -> None:
    assert _result().connector_enablement_ready is False


def test_phase26at_b1_b5_all_blocked() -> None:
    result = _result()
    for blocker in ("B1", "B2", "B3", "B4", "B5"):
        assert result.b1_b5_status[blocker] == "BLOCKED"


def test_phase26at_connector_ready_dialects_empty() -> None:
    assert connector_ready_dialects() == ()


def test_phase26at_policy_worksheet_not_changed() -> None:
    policy_text = (REPO_ROOT / POLICY_WORKSHEET_PATH).read_text(encoding="utf-8")
    # regional_legal_access_review policy row must still be PENDING
    for line in policy_text.splitlines():
        if "regional_legal_access_review" in line:
            assert "PENDING" in line, "policy_review:regional_legal_access_review must remain PENDING in Phase 26AT"
            break


def test_phase26at_operator_proposal_doc_exists() -> None:
    assert PROPOSAL_PATH.exists(), "Operator signoff proposal doc must exist"


def test_phase26at_operator_proposal_for_policy_row_only() -> None:
    content = PROPOSAL_PATH.read_text(encoding="utf-8")
    assert "regional_legal_access_review" in content
    assert "OPERATOR_REQUIRED" in content


def test_phase26at_claim_row_approved_with_phase26ar_scope() -> None:
    claim_text = (REPO_ROOT / CLAIM_WORKSHEET_PATH).read_text(encoding="utf-8")
    for line in claim_text.splitlines():
        if line.startswith("| `regional_legal_access` |"):
            assert "APPROVED" in line
            assert "Phase26AR_TURKEY_PUBLIC_MARKET_DATA_ONLY" in line
            assert "demir_operator" in line
            break


def test_phase26at_no_connector_enablement() -> None:
    result = _result()
    assert result.connector_enablement_ready is False
    assert connector_ready_dialects() == ()
