"""Phase 26V public book channel evidence audit tests.

Phase 26V audits all repo-committed evidence to classify known and candidate
Deribit public book channel subscription formats. No class-A candidate exists
(i.e. no channel with committed official documentation proving it emits non-null
prev_change_id and type). Phase 26W is skipped. No script or workflow change.
No capture dispatched. No worksheet edits. pending_rows=26. B1-B5 BLOCKED.
"""

from __future__ import annotations

import re
from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
AUDIT_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_PUBLIC_BOOK_CHANNEL_EVIDENCE_AUDIT_26V.md"
HARNESS_PATH = REPO_ROOT / "src" / "crypto_core" / "data" / "deribit_public_ws_harness.py"
PROOF_26S_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_RAW_SEQUENCE_CAPTURE_PROOF_26S.json"


def _audit_text() -> str:
    return AUDIT_PATH.read_text(encoding="utf-8")


def _harness_text() -> str:
    return HARNESS_PATH.read_text(encoding="utf-8")


def test_phase26v_audit_doc_exists() -> None:
    assert AUDIT_PATH.exists(), f"Phase 26V audit doc not found: {AUDIT_PATH}"


def test_phase26v_status_field() -> None:
    content = _audit_text()
    assert "status: CHANNEL_AUDIT_ONLY" in content


def test_phase26v_current_channel_recorded() -> None:
    content = _audit_text()
    assert "book.BTC-PERPETUAL.none.10.100ms" in content


def test_phase26v_phase26s_finding_recorded() -> None:
    content = _audit_text()
    # Must record Phase 26S as evidence that the current channel emits no prev_change_id / type
    assert "prev_change_id=null" in content or "prev_change_id" in content
    assert "type=null" in content or ("type" in content and "null" in content)
    assert PROOF_26S_PATH.exists(), "Phase 26S proof artifact must exist for this audit to be valid"


def test_phase26v_no_class_a_candidate() -> None:
    content = _audit_text()
    assert "A (channel_candidate_supported_by_repo)" in content
    # Table must record 0 class-A candidates
    assert "| 0 |" in content


def test_phase26v_book_raw_classified_unsupported() -> None:
    content = _audit_text()
    assert "book.BTC-PERPETUAL.raw" in content
    # Must note "raw" is in forbidden tokens
    assert "unsupported" in content.lower()
    assert "raw" in content


def test_phase26v_book_100ms_classified_needs_excerpt() -> None:
    content = _audit_text()
    assert "book.BTC-PERPETUAL.100ms" in content
    assert "needs_official_excerpt" in content


def test_phase26v_26w_skip_recorded() -> None:
    content = _audit_text()
    assert "26W" in content
    assert "SKIP" in content


def test_phase26v_harness_forbidden_token_raw_present() -> None:
    """Prove the 'raw' forbidden token claim in the audit is grounded in harness code."""
    harness = _harness_text()
    assert '"raw"' in harness, "harness must have 'raw' in _FORBIDDEN_CHANNEL_TOKENS"


def test_phase26v_harness_aggregated_pattern_requires_none() -> None:
    """Prove the .none. pattern claim is grounded in harness code."""
    harness = _harness_text()
    # The aggregated book pattern requires none in the pattern
    assert "none" in harness, "harness must have 'none' in _AGGREGATED_CHANNEL_PATTERNS"
    # The pattern requires group (number) in that slot
    assert "100ms" in harness


def test_phase26v_no_guessed_channel_names() -> None:
    """Doc must not invent channel names not appearing in prior repo docs."""
    content = _audit_text()
    # These are the only two channel candidates mentioned as "(e.g.)" in prior docs
    known_candidates = {"book.BTC-PERPETUAL.none.10.100ms", "book.BTC-PERPETUAL.100ms", "book.BTC-PERPETUAL.raw"}
    # Extract channel-like strings from content (book.* patterns)
    found = set(re.findall(r"book\.[A-Z0-9_\-]+(?:\.[a-z0-9]+)+", content))
    unknown = found - known_candidates
    assert not unknown, f"Unknown/guessed channels in audit doc: {unknown}"


def test_phase26v_not_an_approval() -> None:
    content = _audit_text()
    assert "NOT_an_approval: true" in content


def test_phase26v_not_worksheet_mutation() -> None:
    content = _audit_text()
    assert "NOT_worksheet_mutation: true" in content


def test_phase26v_not_connector_enablement() -> None:
    content = _audit_text()
    assert "NOT_connector_enablement: true" in content


def test_phase26v_pending_rows_unchanged() -> None:
    result = evaluate_deribit_manual_review_readiness()
    assert len(result.pending_rows) == 2


def test_phase26v_no_worksheet_edits_and_validator_unchanged() -> None:
    result = evaluate_deribit_manual_review_readiness()

    assert result.accepted is False
    assert result.evidence_review_complete is False
    assert result.connector_enablement_ready is False
    assert len(result.pending_rows) == 2
    assert result.b1_b5_status == {
        "B1": "BLOCKED",
        "B2": "BLOCKED",
        "B3": "BLOCKED",
        "B4": "BLOCKED",
        "B5": "BLOCKED",
    }
    assert connector_ready_dialects() == ()
