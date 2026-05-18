"""Phase 26AG proof artifact classification tests."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BATCH_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_PROOF_ARTIFACT_BATCH_26AG.md"
PROOF_BATCH_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OFFICIAL_DOCS_PROOF_BATCH_26AF.md"

PROOF_READY_ROWS = (
    "claim_review:public_rest_availability",
    "claim_review:prod_testnet_ws_endpoint",
    "claim_review:prod_testnet_rest_endpoint",
    "claim_review:rest_snapshot_requirement",
    "claim_review:gap_resubscribe_rule",
    "claim_review:heartbeat_liveness_proof",
    "claim_review:public_rate_subscription_limits",
    "claim_review:public_trades",
    "claim_review:ticker",
    "claim_review:mark_index_funding_open_interest",
    "claim_review:testnet_prod_difference",
    "claim_review:first_message_snapshot",
    "claim_review:incremental_delta",
    "claim_review:prev_change_id",
    "claim_review:continuity_condition",
)


def _text() -> str:
    return BATCH_PATH.read_text(encoding="utf-8")


def _row_line(row_id: str) -> str:
    for line in _text().splitlines():
        if line.startswith(f"| `{row_id}` |"):
            return line
    raise AssertionError(f"row missing from 26AG batch: {row_id}")


def test_phase26ag_batch_exists_and_is_classification_only() -> None:
    content = _text()
    assert PROOF_BATCH_PATH.exists()
    assert "status: CLASSIFICATION_BATCH_ONLY" in content
    assert "NOT_an_approval: true" in content
    assert "NOT_connector_enablement: true" in content


def test_phase26ag_all_proof_ready_rows_are_classified_from_26ae_26af() -> None:
    for row in PROOF_READY_ROWS:
        line = _row_line(row)
        assert "PROOF_READY_NOT_APPROVED" in line
        assert "26AE" in line
        assert "26AF" in line


def test_phase26ag_legal_access_documentation_only() -> None:
    line = _row_line("claim_review:regional_legal_access")
    assert "DOCUMENTATION_PROOF_READY" in line
    assert "NO_LEGAL_APPROVAL" in line


def test_phase26ag_ambiguous_rows_stay_wait_insufficient_or_policy() -> None:
    assert "claim_review:checksum_decision` | `WAIT_INSUFFICIENT`" in _text()
    assert "claim_review:staleness_budget` | `WAIT_POLICY`" in _text()
    assert "policy_review:separate_connector_enablement` | `WAIT_POLICY`" in _text()


def test_phase26ag_validator_state_is_documented_blocked() -> None:
    content = _text()
    assert "| `pending_rows` | 26 |" in content
    assert "| `accepted` | False |" in content
    assert "| `connector_ready_dialects()` | `()` |" in content
    assert "| `B1-B5` | `BLOCKED` |" in content
