"""Phase 26J Deribit raw sequence capture proof tests."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PROOF_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_RAW_SEQUENCE_CAPTURE_PROOF_26J.json"


def _proof() -> dict[str, object]:
    return json.loads(PROOF_PATH.read_text(encoding="utf-8"))


def test_phase26j_proof_records_downloaded_artifact_identity_and_run() -> None:
    proof = _proof()

    assert proof["schema"] == "deribit_raw_sequence_capture_proof_26j"
    assert proof["source"] == "downloaded_github_actions_artifact"
    assert proof["run_id"] == 26033502712
    assert proof["run_url"] == "https://github.com/demircaliskan2009-pixel/BIST_ELITE_CORE/actions/runs/26033502712"
    assert proof["run_conclusion"] == "failure"
    assert proof["head_branch"] == "main"
    assert proof["head_sha"] == "30aa40d95ad75f204635766f12f1249387786ac8"
    assert proof["artifact_name"] == "deribit-public-smoke-proof"
    assert proof["artifact_file"] == "smoke_result.json"
    assert proof["artifact_sha256"] == "f41fa6a8a02a678a7d6714f7a9b6a9ced717d234e8e370a3ba42883479f7456d"


def test_phase26j_proof_matches_actual_smoke_result_fields() -> None:
    proof = _proof()

    assert proof["artifact_payload"] == {
        "accepted": False,
        "channels": ["book.BTC-PERPETUAL.none.10.100ms"],
        "completed_at_ns": 1779107394863923161,
        "dry_run": True,
        "duration_seconds": 30.0,
        "max_messages": 100,
        "message_count": 0,
        "operator_authorization": "PUBLIC_MARKET_DATA_ONLY",
        "rejection_reasons": ["deribit_ws:timeout"],
        "sample_events": [],
        "started_at_ns": 1779107364640752570,
        "ws_url": "wss://www.deribit.com/ws/api/v2",
    }
    assert proof["accepted"] is False
    assert proof["duration_seconds"] == 30.0
    assert proof["max_messages"] == 100
    assert proof["message_count"] == 0
    assert proof["rejection_reasons"] == ["deribit_ws:timeout"]
    assert proof["sanitized_sample_events"] == []


def test_phase26j_rejects_artifact_for_classification_without_events() -> None:
    proof = _proof()

    acceptance = proof["artifact_acceptance"]
    assert isinstance(acceptance, dict)
    assert acceptance["accepted_for_classification"] is False
    assert acceptance["rejection_reasons"] == [
        "artifact:accepted_false",
        "artifact:rejection_reasons_non_empty",
        "artifact:message_count_lt_1",
        "artifact:sample_events_missing_or_empty",
    ]
    assert proof["computed_counts"] == {
        "non_null_prev_change_id_count": 0,
        "adjacent_pair_count": 0,
        "continuity_match_count": 0,
        "snapshot_type_count": 0,
        "delta_or_change_type_count": 0,
    }
    assert proof["classification_effect"] == {
        "prev_change_id": "WAIT_INSUFFICIENT",
        "continuity_condition": "WAIT_INSUFFICIENT",
        "first_message_snapshot": "WAIT_INSUFFICIENT",
        "incremental_delta": "WAIT_INSUFFICIENT",
    }


def test_phase26j_safety_invariants_remain_public_only() -> None:
    proof = _proof()

    assert proof["safety_invariants"] == {
        "public_market_data_only": True,
        "dry_run": True,
        "no_private_api": True,
        "no_credentials": True,
        "no_orders": True,
        "no_connector_enablement": True,
        "no_worksheet_approval": True,
    }
