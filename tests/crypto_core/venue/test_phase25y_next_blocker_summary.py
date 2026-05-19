"""Phase 25Y Deribit next blocker summary tests."""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
SUMMARY_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_25Y.md"
PROPOSAL_25X_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OPERATOR_FILL_PROPOSAL_25X.md"


def _summary_doc() -> str:
    return SUMMARY_PATH.read_text(encoding="utf-8")


def test_phase25y_summary_lists_already_approved_rows_and_change_id() -> None:
    doc = _summary_doc()

    for row_id in (
        "public_websocket_availability",
        "unauthenticated_public_market_data",
        "orderbook_channel_feed",
        "change_id",
    ):
        assert f"| `{row_id}` | claim_review |" in doc

    assert "`Phase25I_APPROVE_NOW_CANDIDATES_ONLY`" in doc
    assert "`Phase25R_CHANGE_ID_ONLY`" in doc


def test_phase25y_summary_records_no_new_proposal_rows() -> None:
    doc = _summary_doc()

    assert "| none | NOT_CREATED |" in doc
    assert "No worksheet row was edited" in doc
    assert "operator-fill proposal was created" in doc
    assert not PROPOSAL_25X_PATH.exists()


def test_phase25y_summary_keeps_observed_official_policy_and_legal_blockers() -> None:
    doc = _summary_doc()

    for row_id in (
        "prev_change_id",
        "continuity_condition",
        "first_message_snapshot",
        "incremental_delta",
        "public_trades",
        "ticker",
        "mark_index_funding_open_interest",
    ):
        assert f"| `{row_id}` |" in doc

    assert "| `gap_resubscribe_rule` | `DERIBIT_NOTIFICATIONS_SECTION_EXCERPT_PROOF.md`. |" in doc
    assert "| `heartbeat_liveness_proof` | `DERIBIT_ENVIRONMENT_SECTION_EXCERPT_PROOF.md`. |" in doc
    assert "| `checksum_decision` | Operator policy value required. |" in doc
    assert "| `regional_legal_access` | External legal/access review required. |" in doc


def test_phase25y_summary_keeps_connector_enablement_deferred() -> None:
    doc = _summary_doc()

    assert "`separate_connector_enablement` remains deferred." in doc
    assert "`static_registry_verified` change" in doc
    assert "`connector_ready_dialects()` change" in doc
    assert "pending_rows: 26" in doc
    assert "B1-B5: BLOCKED" in doc


def test_phase25y_validator_state_matches_summary() -> None:
    result = evaluate_deribit_manual_review_readiness()

    assert result.accepted is False
    assert result.evidence_review_complete is True
    assert result.ready_for_engineering_patch is True
    assert result.connector_enablement_ready is False
    assert len(result.pending_rows) == 0
    assert result.b1_b5_status == {
        "B1": "BLOCKED",
        "B2": "BLOCKED",
        "B3": "READY",
        "B4": "READY",
        "B5": "BLOCKED",
    }
    assert connector_ready_dialects() == ()
