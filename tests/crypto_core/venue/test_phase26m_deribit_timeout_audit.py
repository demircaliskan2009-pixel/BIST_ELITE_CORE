"""Phase 26M Deribit public smoke timeout audit tests.

Phase 26M records a technical audit of run 26033502712, which timed out
with message_count=0. This test validates the audit document contents.
No worksheet edits, no connector enablement, no classifier advancement.
"""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    CLAIM_WORKSHEET_PATH,
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
AUDIT_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_PUBLIC_SMOKE_TIMEOUT_AUDIT_26M.md"
CLAIM_PATH = REPO_ROOT / CLAIM_WORKSHEET_PATH


def _audit_doc() -> str:
    return AUDIT_PATH.read_text(encoding="utf-8")


def test_phase26m_audit_doc_exists() -> None:
    assert AUDIT_PATH.exists(), f"Phase 26M audit doc not found: {AUDIT_PATH}"


def test_phase26m_audit_records_source_run_id() -> None:
    doc = _audit_doc()
    assert "26033502712" in doc
    assert "run_id" in doc


def test_phase26m_audit_records_timeout_rejection() -> None:
    doc = _audit_doc()
    assert "deribit_ws:timeout" in doc
    assert "message_count" in doc
    assert "0" in doc


def test_phase26m_audit_records_zero_messages() -> None:
    doc = _audit_doc()
    assert "message_count" in doc
    assert "`0`" in doc
    assert "sample_events" in doc
    assert "`[]`" in doc


def test_phase26m_audit_records_full_duration_elapsed() -> None:
    doc = _audit_doc()
    # Smoke step ran full 30-second duration
    assert "Run Deribit public WS smoke" in doc
    assert "30" in doc


def test_phase26m_audit_records_retry_trigger() -> None:
    doc = _audit_doc()
    assert "26035089720" in doc
    assert "retry_run_id" in doc or "retry" in doc.lower()


def test_phase26m_audit_records_safety_invariants() -> None:
    doc = _audit_doc()
    assert "no_worksheet_approval" in doc
    assert "no_connector_enablement" in doc
    assert "PUBLIC_MARKET_DATA_ONLY" in doc


def test_phase26m_no_worksheet_edits_and_validator_unchanged() -> None:
    result = evaluate_deribit_manual_review_readiness()

    assert result.accepted is False
    assert result.evidence_review_complete is False
    assert result.connector_enablement_ready is False
    assert len(result.pending_rows) == 3
    assert result.b1_b5_status == {
        "B1": "BLOCKED",
        "B2": "BLOCKED",
        "B3": "BLOCKED",
        "B4": "BLOCKED",
        "B5": "BLOCKED",
    }
    assert connector_ready_dialects() == ()
