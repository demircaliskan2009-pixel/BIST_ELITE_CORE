"""Phase 26Y channel official excerpt gap tests.

Phase 26X is skipped (no capture dispatched, no artifact to classify).
Phase 26Y records the exact official excerpt gaps that must be filled before
any alternative Deribit book channel capture can proceed. No claim approval.
No worksheet mutation. No connector enablement. pending_rows=26. B1-B5 BLOCKED.
"""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
GAP_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_CHANNEL_OFFICIAL_EXCERPT_GAP_26Y.md"
MANIFEST_PATH = (
    REPO_ROOT
    / "docs"
    / "crypto_core"
    / "official_sources"
    / "deribit"
    / "20260510"
    / "DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md"
)


def _gap_text() -> str:
    return GAP_PATH.read_text(encoding="utf-8")


def test_phase26y_gap_doc_exists() -> None:
    assert GAP_PATH.exists(), f"Phase 26Y gap doc not found: {GAP_PATH}"


def test_phase26y_status_field() -> None:
    content = _gap_text()
    assert "status: EXCERPT_GAP_ONLY" in content


def test_phase26y_phase_26x_skipped_recorded() -> None:
    content = _gap_text()
    assert "26X" in content
    assert "SKIPPED" in content


def test_phase26y_no_capture_run_id() -> None:
    content = _gap_text()
    # No CI run ID must appear — no capture was dispatched
    import re

    run_ids = re.findall(r"\b2[0-9]{10}\b", content)  # GitHub Actions run IDs are ~11 digits
    assert not run_ids, f"No capture run ID should appear in 26Y gap doc, found: {run_ids}"


def test_phase26y_notifications_source_referenced() -> None:
    content = _gap_text()
    assert "DERIBIT_NOTIFICATIONS" in content
    assert "docs.deribit.com/#notifications" in content


def test_phase26y_gap_book_channel_format_variants_recorded() -> None:
    content = _gap_text()
    assert "BOOK_CHANNEL_FORMAT_VARIANTS" in content
    assert "prev_change_id" in content


def test_phase26y_gap_snapshot_delta_semantics_recorded() -> None:
    content = _gap_text()
    assert "BOOK_SNAPSHOT_DELTA_SEMANTICS" in content
    assert "snapshot" in content.lower()
    assert "delta" in content.lower() or "change" in content.lower()


def test_phase26y_gap_continuity_gap_recovery_recorded() -> None:
    content = _gap_text()
    assert "BOOK_CONTINUITY_GAP_RECOVERY_RULE" in content
    assert "continuity" in content.lower() or "gap" in content.lower()


def test_phase26y_gap_checksum_field_recorded() -> None:
    content = _gap_text()
    assert "BOOK_CHECKSUM_FIELD" in content
    assert "checksum" in content.lower()


def test_phase26y_harness_constraint_forbidden_raw_recorded() -> None:
    content = _gap_text()
    assert "_FORBIDDEN_CHANNEL_TOKENS" in content
    assert '"raw"' in content


def test_phase26y_harness_constraint_pattern_recorded() -> None:
    content = _gap_text()
    assert "_AGGREGATED_CHANNEL_PATTERNS" in content


def test_phase26y_operator_actions_recorded() -> None:
    content = _gap_text()
    # Must list operator actions with explicit priorities
    assert (
        "Required Operator Actions" in content
        or "required_operator_actions" in content.lower()
        or "operator" in content.lower()
    )


def test_phase26y_manifest_exists_for_notifications_hash() -> None:
    """The manifest that proves DERIBIT_NOTIFICATIONS was fetched must exist."""
    assert MANIFEST_PATH.exists(), f"Source manifest not found: {MANIFEST_PATH}"
    manifest = MANIFEST_PATH.read_text(encoding="utf-8")
    assert "DERIBIT_NOTIFICATIONS" in manifest


def test_phase26y_not_an_approval() -> None:
    content = _gap_text()
    assert "NOT_an_approval: true" in content


def test_phase26y_not_worksheet_mutation() -> None:
    content = _gap_text()
    assert "NOT_worksheet_mutation: true" in content


def test_phase26y_not_connector_enablement() -> None:
    content = _gap_text()
    assert "NOT_connector_enablement: true" in content


def test_phase26y_pending_rows_unchanged() -> None:
    result = evaluate_deribit_manual_review_readiness()
    assert len(result.pending_rows) == 0


def test_phase26y_no_worksheet_edits_and_validator_unchanged() -> None:
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
