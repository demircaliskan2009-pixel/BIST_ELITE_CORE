"""Phase 26K Deribit raw sequence classification tests."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BATCH_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_PROOF_ARTIFACT_BATCH_26K.md"
PROOF_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_RAW_SEQUENCE_CAPTURE_PROOF_26J.json"


def _batch_doc() -> str:
    return BATCH_PATH.read_text(encoding="utf-8")


def test_phase26k_classification_uses_phase26j_artifact_only() -> None:
    doc = _batch_doc()

    assert PROOF_PATH.exists()
    assert "status: WAIT_INSUFFICIENT_ARTIFACT_REJECTED" in doc
    assert "source_proof: `docs/crypto_core/DERIBIT_RAW_SEQUENCE_CAPTURE_PROOF_26J.json`" in doc
    assert "source_run_id: `26033502712`" in doc
    assert "source_artifact_name: `deribit-public-smoke-proof`" in doc
    assert "source_artifact_sha256: `f41fa6a8a02a678a7d6714f7a9b6a9ced717d234e8e370a3ba42883479f7456d`" in doc


def test_phase26k_no_false_promotion_without_required_fields() -> None:
    doc = _batch_doc()

    assert "newly_proof_ready_not_approved_count: 0" in doc
    assert "operator_proposal_created: NO" in doc
    assert "| `prev_change_id` | claim_review | WAIT_INSUFFICIENT |" in doc
    assert "| `continuity_condition` | claim_review | WAIT_INSUFFICIENT |" in doc
    assert "| `first_message_snapshot` | claim_review | WAIT_INSUFFICIENT |" in doc
    assert "| `incremental_delta` | claim_review | WAIT_INSUFFICIENT |" in doc
    assert "PROOF_READY_NOT_APPROVED |" not in doc
    assert "`non_null_prev_change_id_observed=false`" in doc
    assert "`first_observed_event_missing=true`" in doc
    assert "`later_change_event_missing=true`" in doc


def test_phase26k_continuity_requires_exact_adjacent_equality() -> None:
    doc = _batch_doc()

    assert "current.payload_sample.prev_change_id == prior.payload_sample.change_id" in doc
    assert "| `adjacent_pair_count` | `0` |" in doc
    assert "| `continuity_match_count` | `0` |" in doc
    assert "| adjacent equality `current.prev_change_id == prior.change_id` proven | false |" in doc
    assert "`continuity_condition` remains WAIT_INSUFFICIENT" in doc


def test_phase26k_records_rejected_timeout_artifact_counts() -> None:
    doc = _batch_doc()

    assert "| `accepted` | `false` |" in doc
    assert '| `rejection_reasons` | `["deribit_ws:timeout"]` |' in doc
    assert "| `message_count` | `0` |" in doc
    assert "| `sample_events` | `[]` |" in doc
    assert "| `non_null_prev_change_id_count` | `0` |" in doc
    assert "| `snapshot_type_count` | `0` |" in doc
    assert "| `delta_or_change_type_count` | `0` |" in doc
