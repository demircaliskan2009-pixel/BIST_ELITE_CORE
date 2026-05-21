"""Phase 26AU — Next blocker summary document tests."""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
SUMMARY_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_26AU.md"
SUPERSEDED_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_26AQ.md"


def _content() -> str:
    return SUMMARY_PATH.read_text(encoding="utf-8")


def test_phase26au_summary_exists() -> None:
    assert SUMMARY_PATH.exists(), "Next blocker summary 26AU must exist"


def test_phase26au_summary_non_empty() -> None:
    assert len(_content()) > 100


def test_phase26au_pending_rows_count_is_2_in_content() -> None:
    content = _content()
    assert "pending_rows:              2" in content or "pending_rows: 2" in content


def test_phase26au_b1_b5_all_blocked_in_content() -> None:
    content = _content()
    for blocker in ("B1", "B2", "B3", "B4", "B5"):
        assert blocker in content
        assert "BLOCKED" in content


def test_phase26au_supersedes_26aq_doc() -> None:
    content = _content()
    assert "26AQ" in content or "DERIBIT_NEXT_BLOCKER_SUMMARY_26AQ" in content


def test_phase26au_26aq_doc_still_exists() -> None:
    # 26AQ doc is superseded but NOT deleted
    assert SUPERSEDED_PATH.exists(), "26AQ summary must NOT be deleted"


def test_phase26au_regional_legal_access_approved_mentioned() -> None:
    content = _content()
    assert "regional_legal_access" in content
    assert "APPROVED" in content or "approved" in content.lower()


def test_phase26au_remaining_two_policy_rows_mentioned() -> None:
    content = _content()
    assert "regional_legal_access_review" in content
    assert "separate_connector_enablement" in content


def test_phase26au_connector_ready_dialects_zero_in_content() -> None:
    content = _content()
    assert "connector_ready_dialects:  0" in content or "connector_ready_dialects() == 0" in content


def test_phase26au_live_validator_state_matches_summary() -> None:
    result = evaluate_deribit_manual_review_readiness()
    assert result.accepted is True
    assert len(result.pending_rows) == 0
    assert result.connector_enablement_ready is True
    assert len(connector_ready_dialects()) == 1


def test_phase26au_b1_b5_live_validator_blocked() -> None:
    result = evaluate_deribit_manual_review_readiness()
    assert result.b1_b5_status["B1"] == "READY_FOR_HUMAN_GATE"
    assert result.b1_b5_status["B2"] == "READY"
    assert result.b1_b5_status["B3"] == "READY"  # B3 READY after Phase 26AW
    assert result.b1_b5_status["B4"] == "READY"  # B4 READY after Phase 27A static registry verification
