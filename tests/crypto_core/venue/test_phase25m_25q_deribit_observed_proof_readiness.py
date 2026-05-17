"""Phase 25M-25Q Deribit observed proof readiness tests.

These tests validate the docs-only observed proof batch. They prove that actual
artifact sample events can promote only the `change_id` claim to
PROOF_READY_NOT_APPROVED, while all unproven rows remain blocked and no real
worksheets, connector readiness, or B1-B5 gates are changed.
"""

from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    CLAIM_WORKSHEET_PATH,
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
OBSERVED_PROOF_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json"
BATCH_25N_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_PROOF_ARTIFACT_BATCH_25N.md"
CANDIDATES_25O_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_EVIDENCE_BASED_APPROVAL_CANDIDATES_25O.md"
PROPOSAL_25P_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OPERATOR_FILL_PROPOSAL_25P.md"
SUMMARY_25Q_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_25Q.md"


def _observed_proof() -> dict[str, object]:
    return json.loads(OBSERVED_PROOF_PATH.read_text(encoding="utf-8"))


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_phase25m_observed_proof_is_accepted_public_artifact_data() -> None:
    proof = _observed_proof()

    assert proof["status"] == "OBSERVED_PUBLIC_MARKET_DATA_PROOF"
    assert proof["run_id"] == 25671516104
    assert proof["run_branch"] == "main"
    assert proof["source_artifact_name"] == "deribit-public-smoke-proof"
    assert proof["operator_authorization"] == "PUBLIC_MARKET_DATA_ONLY"
    assert proof["dry_run"] is True
    assert proof["accepted"] is True
    assert proof["message_count"] == 19
    assert proof["rejection_reasons"] == []


def test_phase25m_observed_events_prove_change_id_only() -> None:
    events = _observed_proof()["observed_events"]
    assert isinstance(events, list)
    assert len(events) == 5

    for event in events:
        assert isinstance(event["change_id"], int)
        assert event["sequence_id"] == event["change_id"]
        assert event["channel"] == "book.BTC-PERPETUAL.none.10.100ms"
        assert isinstance(event["timestamp"], int)
        assert isinstance(event["receive_lag_ms"], int)

    assert all(event["prev_change_id"] is None for event in events)
    assert all(event["prev_sequence_id"] is None for event in events)
    assert all(event["type"] is None for event in events)


def test_phase25n_classifies_only_change_id_as_proof_ready() -> None:
    doc = _text(BATCH_25N_PATH)

    assert "new_proof_ready_not_approved_count: 1" in doc
    assert "| `change_id` | claim_review | PROOF_READY_NOT_APPROVED |" in doc

    for claim_id in (
        "prev_change_id",
        "first_message_snapshot",
        "incremental_delta",
        "continuity_condition",
        "gap_resubscribe_rule",
        "heartbeat_liveness_proof",
    ):
        assert f"| `{claim_id}` | claim_review | WAIT_INSUFFICIENT |" in doc


def test_phase25o_candidates_include_phase25i_and_new_change_id_only() -> None:
    doc = _text(CANDIDATES_25O_PATH)

    for approved in ("public_websocket_availability", "unauthenticated_public_market_data", "orderbook_channel_feed"):
        assert f"| ALREADY_APPROVED_PHASE25I | claim_review | `{approved}` |" in doc

    assert "| PROOF_READY_NOT_APPROVED | claim_review | `change_id` |" in doc
    assert "| PROOF_READY_NOT_APPROVED | claim_review | `prev_change_id` |" not in doc
    assert "newly_proof_ready_not_approved_claim_count: 1" in doc


def test_phase25p_operator_fill_is_proposal_only_with_placeholders() -> None:
    doc = _text(PROPOSAL_25P_PATH)

    assert "status: PROPOSAL_ONLY_NOT_APPLIED" in doc
    assert "| claim_review | `change_id` | APPROVE_CANDIDATE | `<OPERATOR_REQUIRED>` | `<OPERATOR_REQUIRED>` |" in doc
    assert "| claim_review | `prev_change_id` | APPROVE_CANDIDATE |" not in doc
    assert "final_approvals: NONE" in doc
    assert "connector_enablement: NONE" in doc


def test_phase25q_lists_approveable_and_blocked_rows() -> None:
    doc = _text(SUMMARY_25Q_PATH)

    assert "| `change_id` | claim_review |" in doc
    assert "| `prev_change_id` | Observed book sample with non-null `prev_change_id`. |" in doc
    assert "| `heartbeat_liveness_proof` | `DERIBIT_ENVIRONMENT_SECTION_EXCERPT_PROOF.md`. |" in doc
    assert "| `regional_legal_access` | External legal/access review required. |" in doc
    assert "`separate_connector_enablement` remains deferred" in doc


def test_phase25m_25q_real_worksheets_are_not_changed() -> None:
    claim_doc = _text(REPO_ROOT / CLAIM_WORKSHEET_PATH)

    assert "| `change_id` | `DERIBIT_NOTIFICATIONS`" in claim_doc
    assert "| `change_id` | `DERIBIT_NOTIFICATIONS` | `https://docs.deribit.com/#notifications`" in claim_doc
    assert "manual_review:change_id_pending" in claim_doc
    assert "DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json" not in claim_doc
    assert "`<OPERATOR_REQUIRED>`" not in claim_doc


def test_phase25m_25q_validator_remains_blocked() -> None:
    result = evaluate_deribit_manual_review_readiness()

    assert result.accepted is False
    assert result.evidence_review_complete is False
    assert result.ready_for_engineering_patch is False
    assert result.connector_enablement_ready is False
    assert len(result.pending_rows) == 27
    assert result.b1_b5_status == {
        "B1": "BLOCKED",
        "B2": "BLOCKED",
        "B3": "BLOCKED",
        "B4": "BLOCKED",
        "B5": "BLOCKED",
    }


def test_phase25m_25q_connector_ready_dialects_empty() -> None:
    assert connector_ready_dialects() == ()
