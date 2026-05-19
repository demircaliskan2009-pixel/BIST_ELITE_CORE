"""Phase 26E-26H Deribit raw sequence capture gap tests."""

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
GAP_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_RAW_SEQUENCE_CAPTURE_TRIGGER_GAP_26E.md"
BATCH_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_PROOF_ARTIFACT_BATCH_26G.md"
SUMMARY_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_26H.md"
PROOF_26F_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_RAW_SEQUENCE_CAPTURE_PROOF_26F.json"
PROPOSAL_26H_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OPERATOR_FILL_PROPOSAL_26H.md"
CLAIM_PATH = REPO_ROOT / CLAIM_WORKSHEET_PATH
POLICY_PATH = REPO_ROOT / POLICY_WORKSHEET_PATH


def _gap_doc() -> str:
    return GAP_PATH.read_text(encoding="utf-8")


def _batch_doc() -> str:
    return BATCH_PATH.read_text(encoding="utf-8")


def _summary_doc() -> str:
    return SUMMARY_PATH.read_text(encoding="utf-8")


def test_phase26e_records_dispatch_gap_and_exact_next_capture_settings() -> None:
    doc = _gap_doc()

    assert "status: CAPTURE_TRIGGER_BLOCKED_BY_LOCAL_DISPATCH_TOOLING" in doc
    assert "latest_dispatch_status: BLOCKED_BY_GH_AUTH" in doc
    assert "workflow_accepts_inputs: true" in doc
    assert "run_id: NOT_AVAILABLE" in doc
    assert "artifact_downloaded: false" in doc
    assert "| `duration_seconds` | `30` |" in doc
    assert "| `max_messages` | `100` |" in doc
    assert "| `sample_limit` | `100` |" in doc
    assert "| `max_receive_lag_ms` | `60000` |" in doc
    assert "| `authorization` | `PUBLIC_MARKET_DATA_ONLY` |" in doc
    assert "| `dry_run` | `true` |" in doc
    assert "book.BTC-PERPETUAL.none.10.100ms" in doc
    assert not PROOF_26F_PATH.exists()


def test_phase26e_records_exact_terminal_auth_blocker_without_secrets() -> None:
    doc = _gap_doc()

    assert "gh version 2.92.0 (2026-04-28)" in doc
    assert "You are not logged into any GitHub hosts" in doc
    assert "GH_TOKEN` local credential probe | `present: false`" in doc
    assert "GITHUB_TOKEN` local credential probe | `present: false`" in doc
    assert "git credential.helper` local credential probe | `configured: false`" in doc
    assert "gh workflow run deribit-public-smoke.yml" in doc
    assert "-f duration_seconds=30" in doc
    assert "-f max_messages=100" in doc
    assert "-f sample_limit=100" in doc
    assert "-f max_receive_lag_ms=60000" in doc
    assert "Alternatively, populate the GH_TOKEN environment variable" in doc
    assert "does not prove any Deribit market-data" in doc
    assert "claim." in doc


def test_phase26g_does_not_promote_without_raw_artifact() -> None:
    doc = _batch_doc()

    assert "status: WAIT_INSUFFICIENT_NO_RAW_SEQUENCE_ARTIFACT" in doc
    assert "latest_dispatch_attempt_status: BLOCKED_BY_GH_AUTH" in doc
    assert "raw_sequence_proof_26f_created: NO" in doc
    assert "newly_proof_ready_not_approved_count: 0" in doc
    assert "operator_proposal_created: NO" in doc
    assert "| `prev_change_id` | claim_review | WAIT_INSUFFICIENT |" in doc
    assert "| `continuity_condition` | claim_review | WAIT_INSUFFICIENT |" in doc
    assert "| `first_message_snapshot` | claim_review | WAIT_INSUFFICIENT |" in doc
    assert "| `incremental_delta` | claim_review | WAIT_INSUFFICIENT |" in doc
    assert "`non_null_prev_change_id_observed=false`" in doc
    assert "`continuity_pair_missing=true`" in doc
    assert "PROOF_READY_NOT_APPROVED |" not in doc
    assert "| latest `gh workflow run` dispatch attempt succeeded | false |" in doc
    assert "| local `GH_TOKEN` or `GITHUB_TOKEN` exists | false |" in doc


def test_phase26g_continuity_requires_exact_adjacent_raw_equality() -> None:
    doc = _batch_doc()

    assert "current.payload_sample.prev_change_id == prior.payload_sample.change_id" in doc
    assert "| adjacent equality `current.prev_change_id == prior.change_id` proven | false |" in doc
    assert "`continuity_condition` remains WAIT_INSUFFICIENT" in doc


def test_phase26h_summary_lists_still_blocked_rows_and_no_proposal() -> None:
    doc = _summary_doc()

    assert "| none | NO_PROPOSAL |" in doc
    assert "no Phase 26F proof JSON was created" in doc
    assert "blocked because `gh`" in doc
    assert "was installed but unauthenticated" in doc
    assert "`prev_change_id`" in doc
    assert "`continuity_condition`" in doc
    assert "`first_message_snapshot`" in doc
    assert "`incremental_delta`" in doc
    assert "`gap_resubscribe_rule`" in doc
    assert "`heartbeat_liveness_proof`" in doc
    assert "`checksum_decision`" in doc
    assert "`regional_legal_access`" in doc
    assert "`separate_connector_enablement` remains deferred" in doc
    assert "Run `gh auth login` locally" in doc
    assert "keep all raw-sequence rows WAIT_INSUFFICIENT" in doc
    assert not PROPOSAL_26H_PATH.exists()


def test_phase26e_26h_no_worksheet_edits_and_validator_remains_blocked() -> None:
    claim_rows = _parse_md_table_rows(CLAIM_PATH.read_text(encoding="utf-8"))
    policy_rows = _parse_md_table_rows(POLICY_PATH.read_text(encoding="utf-8"))
    result = evaluate_deribit_manual_review_readiness()

    # Phase 26AJ approved 15 more rows; total approved = 19
    approved_claim_ids = {row["claim_id"] for row in claim_rows if row["decision"] == "APPROVED"}
    assert len(approved_claim_ids) == 23
    pending_policy = [r for r in policy_rows if r["decision"] == "PENDING"]
    assert len(pending_policy) == 0
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
