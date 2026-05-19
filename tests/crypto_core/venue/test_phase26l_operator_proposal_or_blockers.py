"""Phase 26L Deribit proposal and blocker summary tests."""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    CLAIM_WORKSHEET_PATH,
    POLICY_WORKSHEET_PATH,
    _parse_md_table_rows,
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
SUMMARY_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_26L.md"
PROPOSAL_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OPERATOR_FILL_PROPOSAL_26L.md"
CLAIM_PATH = REPO_ROOT / CLAIM_WORKSHEET_PATH
POLICY_PATH = REPO_ROOT / POLICY_WORKSHEET_PATH


def _summary_doc() -> str:
    return SUMMARY_PATH.read_text(encoding="utf-8")


def test_phase26l_summary_records_failed_public_smoke_artifact() -> None:
    doc = _summary_doc()

    assert "status: NEXT_ACTION_PLAN_ONLY" in doc
    assert "run_id | `26033502712`" in doc
    assert "run_conclusion | `failure`" in doc
    assert "artifact_name | `deribit-public-smoke-proof`" in doc
    assert "accepted | `false`" in doc
    assert 'rejection_reasons | `["deribit_ws:timeout"]`' in doc
    assert "message_count | `0`" in doc
    assert "sample_events | `[]`" in doc


def test_phase26l_no_operator_proposal_without_proof_ready_rows() -> None:
    doc = _summary_doc()

    assert "| none | NO_PROPOSAL |" in doc
    assert "No Phase 26L operator proposal is created" in doc
    assert "zero rows are newly proof-ready" not in doc
    assert not PROPOSAL_PATH.exists()


def test_phase26l_lists_remaining_raw_sequence_requirements() -> None:
    doc = _summary_doc()

    assert "| `prev_change_id` | Accepted public smoke artifact with `message_count >= 1`" in doc
    assert "| `continuity_condition` | Accepted artifact with adjacent observed events proving" in doc
    assert "| `first_message_snapshot` | Accepted artifact whose first observed book event proves snapshot" in doc
    assert "| `incremental_delta` | Accepted artifact with a later observed event proving change or delta" in doc
    assert "| `deribit_ws:timeout` | Re-run `deribit-public-smoke.yml` on `main`" in doc
    assert "Do not classify until `accepted=true`" in doc


def test_phase26l_no_worksheet_edits_and_validator_remains_blocked() -> None:
    claim_rows = _parse_md_table_rows(CLAIM_PATH.read_text(encoding="utf-8"))
    policy_rows = _parse_md_table_rows(POLICY_PATH.read_text(encoding="utf-8"))
    result = evaluate_deribit_manual_review_readiness()

    # Phase 26AJ approved 15 more rows; total approved = 19
    approved_claim_ids = {row["claim_id"] for row in claim_rows if row["decision"] == "APPROVED"}
    assert len(approved_claim_ids) == 22
    pending_policy = [r for r in policy_rows if r["decision"] == "PENDING"]
    assert len(pending_policy) == 2
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


def test_phase26l_no_connector_or_live_enablement_language() -> None:
    doc = _summary_doc()

    assert "`separate_connector_enablement` remains deferred" in doc
    assert "does not\nauthorize registry mutation" in doc
    assert "connector_ready_dialects()` changes" in doc
    assert "private API, credentials,\norders" in doc
    assert "enabled_for_connector=True" not in doc
    assert "static_registry_verified: true" not in doc
