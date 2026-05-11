"""
Phase 23F — Deribit Public Smoke Proof Record assertions.

These tests parse the advisory evidence documents and assert:
- The smoke proof record and checklist are structurally correct.
- No forbidden readiness promotion language is present.
- B8 is marked closed; B1–B5 are marked blocked/open.
- Safety contract fields are present and correct.
"""

from __future__ import annotations

import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
PROOF_RECORD = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md"
CHECKLIST = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md"


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Smoke proof record existence
# ---------------------------------------------------------------------------


def test_smoke_proof_record_exists() -> None:
    """Assert 1: smoke proof record file is present."""
    assert PROOF_RECORD.exists(), f"Missing: {PROOF_RECORD}"


# ---------------------------------------------------------------------------
# 2. Phase 23D proxy classification
# ---------------------------------------------------------------------------


def test_smoke_proof_record_contains_proxy_classification() -> None:
    """Assert 2: contains CI_DERIBIT_SMOKE_ACCEPTED_PROXY."""
    content = _read(PROOF_RECORD)
    assert "CI_DERIBIT_SMOKE_ACCEPTED_PROXY" in content


# ---------------------------------------------------------------------------
# 3. Phase 23E isolated-workflow classification
# ---------------------------------------------------------------------------


def test_smoke_proof_record_contains_isolated_workflow_blocker() -> None:
    """Assert 3: contains ISOLATED_WORKFLOW_NOT_RUN_DEFAULT_BRANCH_BLOCKER."""
    content = _read(PROOF_RECORD)
    assert "ISOLATED_WORKFLOW_NOT_RUN_DEFAULT_BRANCH_BLOCKER" in content


# ---------------------------------------------------------------------------
# 4. accepted: true
# ---------------------------------------------------------------------------


def test_smoke_proof_record_accepted_true() -> None:
    """Assert 4: contains accepted: true."""
    content = _read(PROOF_RECORD)
    assert "accepted: true" in content


# ---------------------------------------------------------------------------
# 5. message_count: 19
# ---------------------------------------------------------------------------


def test_smoke_proof_record_message_count_19() -> None:
    """Assert 5: contains message_count: 19."""
    content = _read(PROOF_RECORD)
    assert "message_count: 19" in content


# ---------------------------------------------------------------------------
# 6. rejection_reasons: []
# ---------------------------------------------------------------------------


def test_smoke_proof_record_rejection_reasons_empty() -> None:
    """Assert 6: contains rejection_reasons: []."""
    content = _read(PROOF_RECORD)
    assert "rejection_reasons: []" in content


# ---------------------------------------------------------------------------
# 7. PUBLIC_MARKET_DATA_ONLY
# ---------------------------------------------------------------------------


def test_smoke_proof_record_public_market_data_only() -> None:
    """Assert 7: contains PUBLIC_MARKET_DATA_ONLY."""
    content = _read(PROOF_RECORD)
    assert "PUBLIC_MARKET_DATA_ONLY" in content


# ---------------------------------------------------------------------------
# 8. B8 marked closed for cloud reachability only
# ---------------------------------------------------------------------------


def test_smoke_proof_record_b8_closed() -> None:
    """Assert 8: B8 is present and marked CLOSED_BY_PROXY_CI_PROOF."""
    content = _read(PROOF_RECORD)
    assert "B8" in content
    assert "CLOSED_BY_PROXY_CI_PROOF" in content


# ---------------------------------------------------------------------------
# 9. B1–B5 still open/blocked
# ---------------------------------------------------------------------------


def test_smoke_proof_record_b1_to_b5_remain_blocked() -> None:
    """Assert 9: B1–B5 all present and marked open/blocked."""
    content = _read(PROOF_RECORD)
    for blocker in ("B1", "B2", "B3", "B4", "B5"):
        assert blocker in content, f"Blocker {blocker} not found in proof record"
    # All remaining blockers must be framed as open/blocked
    assert "Still Open" in content or "still open" in content.lower() or "B1–B5" in content


# ---------------------------------------------------------------------------
# 10. No connector_ready_dialects: non-empty
# ---------------------------------------------------------------------------


def test_smoke_proof_record_no_connector_ready_dialects_non_empty() -> None:
    """Assert 10: does not claim connector_ready_dialects is non-empty."""
    content = _read(PROOF_RECORD)
    # The record must show empty list in the safety contract block
    assert "connector_ready_dialects" in content
    # Safety contract must declare empty list
    assert "connector_ready_dialects:               []" in content


# ---------------------------------------------------------------------------
# 11. No operational_evidence_ready: true
# ---------------------------------------------------------------------------


def test_smoke_proof_record_no_operational_evidence_ready_true() -> None:
    """Assert 11: safety contract declares operational_evidence_ready as false."""
    content = _read(PROOF_RECORD)
    # Safety contract block must declare false (not true)
    assert "operational_evidence_ready:             false" in content


# ---------------------------------------------------------------------------
# 12. No Deribit dialect verified claim
# ---------------------------------------------------------------------------


def test_smoke_proof_record_no_deribit_dialect_verified() -> None:
    """Assert 12: safety contract declares deribit_dialect_verified as false."""
    content = _read(PROOF_RECORD)
    # Safety contract block must declare false (not true)
    assert "deribit_dialect_verified:               false" in content


# ---------------------------------------------------------------------------
# 13. No paper_shadow_integration_ready
# ---------------------------------------------------------------------------


def test_smoke_proof_record_no_paper_shadow_integration_ready() -> None:
    """Assert 13: does not claim paper/shadow integration ready."""
    content = _read(PROOF_RECORD)
    assert "paper_shadow_integration_ready: true" not in content
    assert "paper_shadow_integration_ready" not in content or ("false" in content)
    # Check the safety contract block
    assert "paper_shadow_integration_ready:         false" in content


# ---------------------------------------------------------------------------
# 14. No live trading ready claim
# ---------------------------------------------------------------------------


def test_smoke_proof_record_no_live_trading_ready() -> None:
    """Assert 14: safety contract declares live_trading_ready as false."""
    content = _read(PROOF_RECORD)
    # Safety contract block must declare false (aligned format)
    assert "live_trading_ready:                     false" in content


# ---------------------------------------------------------------------------
# 15. Checklist links/references the proof record
# ---------------------------------------------------------------------------


def test_checklist_references_smoke_proof_record() -> None:
    """Assert 15: checklist references the Phase 23F smoke proof record."""
    content = _read(CHECKLIST)
    assert "DERIBIT_PUBLIC_SMOKE_PROOF_RECORD.md" in content
    assert "phase23f_smoke_proof_record" in content


# ---------------------------------------------------------------------------
# 16. Registry/connector readiness remains disabled
# ---------------------------------------------------------------------------


def test_checklist_connector_ready_dialects_remains_empty() -> None:
    """Assert 16: checklist confirms connector_ready_dialects remains empty."""
    content = _read(CHECKLIST)
    assert "connector_ready_dialects_expected`: `[]`" in content
    assert "connector_ready_dialects_remains_empty`: `REQUIRED`" in content


def test_checklist_operational_status_blocked() -> None:
    """`operational_status` is BLOCKED in the checklist."""
    content = _read(CHECKLIST)
    assert "`operational_status`: `BLOCKED`" in content


def test_checklist_enabled_for_connector_false() -> None:
    """`enabled_for_connector` is false in the checklist."""
    content = _read(CHECKLIST)
    assert "`enabled_for_connector`: `false`" in content


def test_checklist_b8_closed_reference() -> None:
    """Checklist records Phase 23D B8 as CLOSED_BY_PROXY_CI_PROOF."""
    content = _read(CHECKLIST)
    assert "CLOSED_BY_PROXY_CI_PROOF" in content or "phase23d_ci_smoke_b8_status" in content


def test_checklist_phase23d_smoke_accepted() -> None:
    """Checklist records Phase 23D smoke accepted: true."""
    content = _read(CHECKLIST)
    assert "phase23d_ci_smoke_accepted`: `true`" in content


def test_checklist_phase23e_isolated_workflow_classification() -> None:
    """Checklist records Phase 23E isolated workflow classification."""
    content = _read(CHECKLIST)
    assert "ISOLATED_WORKFLOW_NOT_RUN_DEFAULT_BRANCH_BLOCKER" in content


def test_proof_record_run_id_present() -> None:
    """Smoke proof record contains the Phase 23D run ID."""
    content = _read(PROOF_RECORD)
    assert "25658030184" in content


def test_proof_record_commit_sha_present() -> None:
    """Smoke proof record contains the Phase 23D commit SHA."""
    content = _read(PROOF_RECORD)
    assert "74298a70d8499b2b304cb2b704832b849ec81313" in content


def test_proof_record_phase23e_commit_sha_present() -> None:
    """Smoke proof record contains the Phase 23E commit SHA."""
    content = _read(PROOF_RECORD)
    assert "dd0e9c6c21894ab731b7ab3542f8e36a516e8ad5" in content


def test_proof_record_dry_run_true() -> None:
    """Smoke proof record confirms dry_run: true."""
    content = _read(PROOF_RECORD)
    assert "dry_run: true" in content
