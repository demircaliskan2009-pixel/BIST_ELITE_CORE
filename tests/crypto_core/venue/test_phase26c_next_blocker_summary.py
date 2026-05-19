"""Phase 26C Deribit next blocker summary tests."""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
SUMMARY_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_26C.md"
PROPOSAL_26B_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OPERATOR_FILL_PROPOSAL_26B.md"


def _summary_doc() -> str:
    return SUMMARY_PATH.read_text(encoding="utf-8")


def test_phase26c_summary_lists_approved_rows_so_far() -> None:
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


def test_phase26c_summary_records_no_proof_ready_rows_or_26b_proposal() -> None:
    doc = _summary_doc()

    assert "| none | NO_PROPOSAL |" in doc
    assert "no Phase 26B" in doc
    assert not PROPOSAL_26B_PATH.exists()


def test_phase26c_summary_lists_remaining_capture_and_excerpt_requirements() -> None:
    doc = _summary_doc()

    assert "| `prev_change_id` | Public artifact with at least one actual observed event" in doc
    assert "| `continuity_condition` | Public artifact with adjacent observed events proving" in doc
    assert "| `first_message_snapshot` | Observed first book event proving snapshot semantics" in doc
    assert "| `incremental_delta` | Observed book event proving change/delta semantics" in doc
    assert "| `gap_resubscribe_rule` | `DERIBIT_NOTIFICATIONS_SECTION_EXCERPT_PROOF.md`. |" in doc
    assert "| `heartbeat_liveness_proof` | `DERIBIT_ENVIRONMENT_SECTION_EXCERPT_PROOF.md`. |" in doc


def test_phase26c_summary_lists_policy_legal_and_deferred_connector_rows() -> None:
    doc = _summary_doc()

    assert "| `checksum_decision` | Operator policy value required. |" in doc
    assert "| `receive_lag_budget` | Concrete approved budget required. |" in doc
    assert "| `regional_legal_access` | External legal/access review required. |" in doc
    assert "`separate_connector_enablement` remains deferred." in doc
    assert "`static_registry_verified` changes" in doc
    assert "`connector_ready_dialects()` changes" in doc


def test_phase26c_validator_state_matches_summary() -> None:
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
