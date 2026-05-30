"""Phase 26AF official docs proof batch tests."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BATCH_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OFFICIAL_DOCS_PROOF_BATCH_26AF.md"
PACK_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE.md"

PROOF_READY_ROWS = (
    "public_rest_availability",
    "prod_testnet_ws_endpoint",
    "prod_testnet_rest_endpoint",
    "rest_snapshot_requirement",
    "gap_resubscribe_rule",
    "heartbeat_liveness_proof",
    "public_rate_subscription_limits",
    "public_trades",
    "ticker",
    "mark_index_funding_open_interest",
    "testnet_prod_difference",
    "first_message_snapshot",
    "incremental_delta",
    "prev_change_id",
    "continuity_condition",
)


def _text() -> str:
    return BATCH_PATH.read_text(encoding="utf-8")


def _row_line(row_id: str) -> str:
    for line in _text().splitlines():
        if line.startswith(f"| `{row_id}` |"):
            return line
    raise AssertionError(f"row missing from proof batch: {row_id}")


def test_phase26af_batch_exists_and_references_pack() -> None:
    content = _text()
    assert PACK_PATH.exists()
    assert "status: OFFICIAL_DOCS_PROOF_BATCH_ONLY" in content
    assert "source_pack: DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE.md" in content
    assert "NOT_worksheet_mutation: true" in content


def test_phase26af_promoted_rows_are_official_evidence_gated() -> None:
    for row in PROOF_READY_ROWS:
        line = _row_line(row)
        assert "PROOF_READY_NOT_APPROVED" in line
        assert "DERIBIT_OFFICIAL_DOCS_RESEARCH_PACK_26AE.md#row-evidence" in line


def test_phase26af_counts_proof_ready_rows() -> None:
    content = _text()
    assert "| `PROOF_READY_NOT_APPROVED` | 15 |" in content
    assert "| `DOCUMENTATION_PROOF_READY` | 1 |" in content


def test_phase26af_legal_access_is_not_promoted_to_approval_candidate() -> None:
    line = _row_line("regional_legal_access")
    assert "DOCUMENTATION_PROOF_READY" in line
    assert "NO_LEGAL_APPROVAL" in line
    assert "regional_legal_access` | `claim_review` | `PROOF_READY_NOT_APPROVED" not in _text()


def test_phase26af_ambiguous_checksum_stays_wait_insufficient() -> None:
    line = _row_line("checksum_decision")
    assert "WAIT_INSUFFICIENT" in line
