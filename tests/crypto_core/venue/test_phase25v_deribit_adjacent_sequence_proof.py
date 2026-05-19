"""Phase 25V Deribit adjacent sequence proof-gap tests."""

from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    CLAIM_WORKSHEET_PATH,
    _parse_md_table_rows,
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
OBSERVED_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json"
GAP_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_ADJACENT_SEQUENCE_PROOF_GAP_25V.md"
CLAIM_PATH = REPO_ROOT / CLAIM_WORKSHEET_PATH


def _observed_proof() -> dict[str, object]:
    return json.loads(OBSERVED_PATH.read_text(encoding="utf-8"))


def _gap_doc() -> str:
    return GAP_PATH.read_text(encoding="utf-8")


def test_phase25v_uses_actual_observed_public_artifact_not_synthetic_values() -> None:
    proof = _observed_proof()

    assert proof["status"] == "OBSERVED_PUBLIC_MARKET_DATA_PROOF"
    assert proof["source_artifact_name"] == "deribit-public-smoke-proof"
    assert proof["source_artifact_id"] == 6919007152
    assert proof["run_id"] == 25671516104
    assert proof["operator_authorization"] == "PUBLIC_MARKET_DATA_ONLY"
    assert proof["dry_run"] is True
    assert proof["accepted"] is True
    assert proof["rejection_reasons"] == []
    assert proof["NOT_live_trading"] is True
    assert proof["NOT_connector_enablement"] is True


def test_phase25v_observed_events_are_adjacent_but_do_not_prove_continuity() -> None:
    events = _observed_proof()["observed_events"]

    assert isinstance(events, list)
    assert len(events) >= 2
    for prior, current in zip(events, events[1:]):
        assert prior["channel"] == current["channel"] == "book.BTC-PERPETUAL.none.10.100ms"
        assert isinstance(prior["change_id"], int)
        assert isinstance(current["change_id"], int)
        assert current["prev_change_id"] is None
        assert current["prev_sequence_id"] is None

    assert not any(current["prev_change_id"] == prior["change_id"] for prior, current in zip(events, events[1:]))


def test_phase25v_gap_doc_records_exact_missing_fields_and_no_proof_ready_promotion() -> None:
    doc = _gap_doc()

    assert "status: OBSERVED_ADJACENT_PROOF_GAP" in doc
    assert "source_observed_artifact: `docs/crypto_core/DERIBIT_OBSERVED_BOOK_SEQUENCE_PROOF_25M.json`" in doc
    assert "| 1 | `book.BTC-PERPETUAL.none.10.100ms` | 154673956305 | null | 154673956448 |" in doc
    assert "`prev_change_id[current] == change_id[previous]`" in doc
    assert "`prev_change_id`: WAIT_INSUFFICIENT" in doc
    assert "`continuity_condition`: WAIT_INSUFFICIENT" in doc
    assert "PROOF_READY_NOT_APPROVED" not in doc
    assert "No Phase 25X operator-fill proposal is created" in doc


def test_phase25v_real_worksheet_still_has_no_new_approval_rows() -> None:
    rows = {row["claim_id"]: row for row in _parse_md_table_rows(CLAIM_PATH.read_text(encoding="utf-8"))}

    assert rows["change_id"]["decision"] == "APPROVED"
    # Phase 26AJ later approved prev_change_id, continuity_condition, first_message_snapshot, incremental_delta
    for claim_id in ("prev_change_id", "continuity_condition", "first_message_snapshot", "incremental_delta"):
        assert rows[claim_id]["decision"] == "APPROVED"


def test_phase25v_validator_and_connector_readiness_remain_blocked() -> None:
    result = evaluate_deribit_manual_review_readiness()

    assert result.accepted is False
    assert result.evidence_review_complete is False
    assert result.ready_for_engineering_patch is False
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
