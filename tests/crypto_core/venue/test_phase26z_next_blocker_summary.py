"""Phase 26Z next blocker summary tests.

Phase 26Z supersedes Phase 26U. It records the channel audit finding from 26V
(no class-A candidate, book.BTC-PERPETUAL.raw forbidden, book.BTC-PERPETUAL.100ms
needs official excerpt), confirms Phase 26W/26X were skipped, and records the
official excerpt gap (26Y). pending_rows=26. B1-B5 BLOCKED. No connector
enablement. No worksheet edits.
"""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
SUMMARY_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_26Z.md"
PRIOR_SUMMARY_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_26U.md"
AUDIT_26V_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_PUBLIC_BOOK_CHANNEL_EVIDENCE_AUDIT_26V.md"
GAP_26Y_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_CHANNEL_OFFICIAL_EXCERPT_GAP_26Y.md"


def _summary_text() -> str:
    return SUMMARY_PATH.read_text(encoding="utf-8")


def test_phase26z_summary_exists() -> None:
    assert SUMMARY_PATH.exists(), f"Phase 26Z summary not found: {SUMMARY_PATH}"


def test_phase26z_supersedes_26u() -> None:
    content = _summary_text()
    assert "supersedes: DERIBIT_NEXT_BLOCKER_SUMMARY_26U.md" in content


def test_phase26z_prior_26u_summary_still_exists() -> None:
    assert PRIOR_SUMMARY_PATH.exists(), "Phase 26U summary must not be deleted"


def test_phase26z_status_field() -> None:
    content = _summary_text()
    assert "status: NEXT_ACTION_PLAN_ONLY" in content


def test_phase26z_channel_audit_finding_recorded() -> None:
    content = _summary_text()
    # Must reference the channel audit finding
    assert "26V" in content
    assert "book.BTC-PERPETUAL.none.10.100ms" in content
    assert "prev_change_id=null" in content or "prev_change_id" in content


def test_phase26z_no_class_a_candidate_recorded() -> None:
    content = _summary_text()
    # Must record that no class-A candidate exists
    assert "none" in content.lower()
    assert "class-A" in content or "class_A" in content or "A-class" in content or "class A" in content.lower()


def test_phase26z_book_raw_forbidden_recorded() -> None:
    content = _summary_text()
    assert "book.BTC-PERPETUAL.raw" in content
    assert "forbidden" in content.lower() or "FORBIDDEN" in content


def test_phase26z_book_100ms_needs_excerpt_recorded() -> None:
    content = _summary_text()
    assert "book.BTC-PERPETUAL.100ms" in content
    assert "needs_official_excerpt" in content or "official excerpt" in content.lower()


def test_phase26z_26w_skip_recorded() -> None:
    content = _summary_text()
    assert "26W" in content
    assert "SKIP" in content or "skipped" in content.lower()


def test_phase26z_26x_skip_recorded() -> None:
    content = _summary_text()
    assert "26X" in content
    assert "SKIP" in content or "skipped" in content.lower()


def test_phase26z_26y_gap_doc_referenced() -> None:
    content = _summary_text()
    assert "26Y" in content
    assert "DERIBIT_CHANNEL_OFFICIAL_EXCERPT_GAP_26Y.md" in content


def test_phase26z_26y_gap_doc_exists() -> None:
    assert GAP_26Y_PATH.exists(), f"Phase 26Y gap doc not found: {GAP_26Y_PATH}"


def test_phase26z_26v_audit_doc_exists() -> None:
    assert AUDIT_26V_PATH.exists(), f"Phase 26V audit doc not found: {AUDIT_26V_PATH}"


def test_phase26z_approved_rows_preserved() -> None:
    content = _summary_text()
    # The 4 approved rows from prior phases must still appear
    assert "public_websocket_availability" in content
    assert "unauthenticated_public_market_data" in content
    assert "orderbook_channel_feed" in content
    assert "change_id" in content


def test_phase26z_all_pending_row_categories_present() -> None:
    content = _summary_text()
    assert "prev_change_id" in content
    assert "continuity_condition" in content
    assert "first_message_snapshot" in content
    assert "incremental_delta" in content
    assert "checksum_decision" in content
    assert "liveness_policy" in content
    assert "separate_connector_enablement" in content


def test_phase26z_not_an_approval() -> None:
    content = _summary_text()
    assert "NOT_an_approval: true" in content


def test_phase26z_not_worksheet_mutation() -> None:
    content = _summary_text()
    assert "NOT_worksheet_mutation: true" in content


def test_phase26z_not_connector_enablement() -> None:
    content = _summary_text()
    assert "NOT_connector_enablement: true" in content


def test_phase26z_pending_rows_unchanged() -> None:
    result = evaluate_deribit_manual_review_readiness()
    assert len(result.pending_rows) == 0


def test_phase26z_no_worksheet_edits_and_validator_unchanged() -> None:
    result = evaluate_deribit_manual_review_readiness()

    assert result.accepted is False
    assert result.evidence_review_complete is True  # True after Phase 26AW
    assert result.connector_enablement_ready is False
    assert len(result.pending_rows) == 0
    assert result.b1_b5_status == {
        "B1": "BLOCKED",
        "B2": "BLOCKED",
        "B3": "READY",
        "B4": "BLOCKED",
        "B5": "BLOCKED",
    }
    assert connector_ready_dialects() == ()
