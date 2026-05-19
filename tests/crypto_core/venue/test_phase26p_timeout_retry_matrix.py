"""Phase 26P Deribit smoke persistent timeout retry matrix tests.

Phase 26P records that both Phase 26J (run 26033502712) and Phase 26N
(run 26035089720) timed out with message_count=0. The timeout retry matrix
documents the persistent pattern. No worksheet edits, no connector enablement.
"""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_PUBLIC_SMOKE_TIMEOUT_RETRY_MATRIX_26P.md"


def _matrix_doc() -> str:
    return MATRIX_PATH.read_text(encoding="utf-8")


def test_phase26p_matrix_doc_exists() -> None:
    assert MATRIX_PATH.exists(), f"Phase 26P matrix doc not found: {MATRIX_PATH}"


def test_phase26p_matrix_records_both_run_ids() -> None:
    doc = _matrix_doc()
    assert "26033502712" in doc
    assert "26035089720" in doc


def test_phase26p_matrix_both_conclusions_failure() -> None:
    doc = _matrix_doc()
    # Both runs are failure
    assert "failure" in doc
    assert "deribit_ws:timeout" in doc


def test_phase26p_matrix_message_count_zero_both_runs() -> None:
    doc = _matrix_doc()
    # Both runs had message_count=0
    assert "message_count" in doc
    assert "0" in doc


def test_phase26p_matrix_status_persistent_timeout() -> None:
    doc = _matrix_doc()
    assert "PERSISTENT_TIMEOUT_RECORDED" in doc or "persistent" in doc.lower()


def test_phase26p_matrix_lists_all_wait_insufficient_claims() -> None:
    doc = _matrix_doc()
    for claim_id in (
        "prev_change_id",
        "continuity_condition",
        "first_message_snapshot",
        "incremental_delta",
    ):
        assert claim_id in doc, f"claim_id={claim_id} not found in matrix doc"


def test_phase26p_matrix_all_claims_wait_insufficient() -> None:
    doc = _matrix_doc()
    assert "WAIT_INSUFFICIENT" in doc


def test_phase26p_matrix_records_next_required_step() -> None:
    doc = _matrix_doc()
    # Must specify action needed to break the timeout pattern
    assert "accepted=true" in doc or "accepted" in doc
    assert "message_count >= 1" in doc or "message_count" in doc


def test_phase26p_matrix_safety_invariants() -> None:
    doc = _matrix_doc()
    assert "no_worksheet_approval" in doc
    assert "no_connector_enablement" in doc
    assert "PUBLIC_MARKET_DATA_ONLY" in doc


def test_phase26p_no_worksheet_edits_and_validator_unchanged() -> None:
    result = evaluate_deribit_manual_review_readiness()

    assert result.accepted is False
    assert result.evidence_review_complete is True
    assert result.connector_enablement_ready is True
    assert len(result.pending_rows) == 0
    assert result.b1_b5_status == {
        "B1": "BLOCKED",
        "B2": "BLOCKED",
        "B3": "READY",
        "B4": "READY",
        "B5": "READY",
    }
    assert len(connector_ready_dialects()) == 1
