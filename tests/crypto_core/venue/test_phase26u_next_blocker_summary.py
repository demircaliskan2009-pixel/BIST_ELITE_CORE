"""Phase 26U next blocker summary tests.

Phase 26U supersedes Phase 26Q. It records the full run history (26J timeout,
26N timeout, 26R accepted with 9 events), the channel limitation finding
(book.BTC-PERPETUAL.none.10.100ms does not emit prev_change_id or type), and
the updated next action plan. pending_rows=26. B1-B5 BLOCKED. No connector
enablement. No worksheet edits.
"""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
SUMMARY_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_26U.md"


def _summary_text() -> str:
    return SUMMARY_PATH.read_text(encoding="utf-8")


def test_phase26u_blocker_summary_exists() -> None:
    assert SUMMARY_PATH.exists(), f"Phase 26U blocker summary not found: {SUMMARY_PATH}"


def test_phase26u_status_field() -> None:
    content = _summary_text()
    assert "status: NEXT_ACTION_PLAN_ONLY" in content


def test_phase26u_supersedes_26q() -> None:
    content = _summary_text()
    assert "26U" in content
    assert "26Q" in content


def test_phase26u_all_three_runs_recorded() -> None:
    content = _summary_text()
    # Phase 26J/26R/26N all present
    assert "26033502712" in content  # Phase 26J timeout
    assert "26035089720" in content  # Phase 26N timeout
    assert "26038507233" in content  # Phase 26R success


def test_phase26u_timeout_runs_recorded_as_failure() -> None:
    content = _summary_text()
    assert "deribit_ws:timeout" in content


def test_phase26u_26r_run_recorded_as_success() -> None:
    content = _summary_text()
    # The Phase 26R row must show success
    assert "26038507233" in content
    assert "success" in content


def test_phase26u_pending_rows_unchanged() -> None:
    result = evaluate_deribit_manual_review_readiness()
    assert len(result.pending_rows) == 0


def test_phase26u_channel_limitation_recorded() -> None:
    content = _summary_text()
    assert "book.BTC-PERPETUAL.none.10.100ms" in content
    assert "prev_change_id" in content
    assert "type" in content


def test_phase26u_no_new_proof_ready() -> None:
    content = _summary_text()
    assert "NO_PROPOSAL" in content


def test_phase26u_no_worksheet_edits_and_validator_unchanged() -> None:
    result = evaluate_deribit_manual_review_readiness()

    assert result.accepted is True
    assert result.evidence_review_complete is True  # True after Phase 26AW
    assert result.connector_enablement_ready is False
    assert len(result.pending_rows) == 0
    assert result.b1_b5_status == {
        "B1": "READY_FOR_HUMAN_GATE",
        "B2": "READY",
        "B3": "READY",
        "B4": "READY",
        "B5": "BLOCKED",
    }
    assert len(connector_ready_dialects()) == 1
