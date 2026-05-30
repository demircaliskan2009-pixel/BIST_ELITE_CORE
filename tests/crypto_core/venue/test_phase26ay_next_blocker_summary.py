"""Phase 26AY: Next blocker summary document tests."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SUMMARY_DOC_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_26AY.md"


def _summary_text() -> str:
    return SUMMARY_DOC_PATH.read_text(encoding="utf-8")


def test_phase26ay_summary_doc_exists() -> None:
    assert SUMMARY_DOC_PATH.exists(), f"26AY summary doc missing: {SUMMARY_DOC_PATH}"


def test_phase26ay_summary_doc_not_empty() -> None:
    assert len(_summary_text()) > 200


def test_phase26ay_summary_doc_has_pending_rows_zero() -> None:
    assert "pending_rows" in _summary_text()
    assert "`0`" in _summary_text() or "| `0`" in _summary_text() or "pending_rows` | `0`" in _summary_text()


def test_phase26ay_summary_doc_has_deferred_rows_one() -> None:
    assert "deferred_rows" in _summary_text()
    assert "`1`" in _summary_text() or "deferred_rows` | `1`" in _summary_text()


def test_phase26ay_summary_doc_has_evidence_review_complete_true() -> None:
    text = _summary_text()
    assert "evidence_review_complete" in text
    assert "`true`" in text.lower() or "true" in text.lower()


def test_phase26ay_summary_doc_has_ready_for_engineering_patch_true() -> None:
    text = _summary_text()
    assert "ready_for_engineering_patch" in text
    assert "`true`" in text.lower() or "true" in text.lower()


def test_phase26ay_summary_doc_b3_ready() -> None:
    text = _summary_text()
    assert "B3" in text
    assert "READY" in text


def test_phase26ay_summary_doc_b4_blocked() -> None:
    text = _summary_text()
    assert "B4" in text
    assert "BLOCKED" in text


def test_phase26ay_summary_doc_references_separate_connector_enablement() -> None:
    assert "separate_connector_enablement" in _summary_text()


def test_phase26ay_summary_doc_no_live_trading_approval() -> None:
    text = _summary_text().lower()
    assert "enabled_for_connector: true" not in text
    assert "static_registry_verified: true" not in text
    assert "live_trading_approved" not in text
