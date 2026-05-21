"""Phase 27K source snapshot acceptance audit tests."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
AUDIT = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_SOURCE_SNAPSHOT_ACCEPTANCE_AUDIT_27K.md"


def test_phase27k_audit_records_explicit_operator_acceptance() -> None:
    text = AUDIT.read_text(encoding="utf-8")

    assert "status: SOURCE_SNAPSHOT_OPERATIONAL_EVIDENCE_ACCEPTANCE" in text
    assert "reviewer_id: demir_operator" in text
    assert "reviewed_at_iso: 2026-05-19T00:00:00Z" in text
    assert "approval_scope: Phase27K_SOURCE_SNAPSHOT_OPERATIONAL_EVIDENCE_ACCEPTANCE" in text
    assert "decision: APPROVE" in text


def test_phase27k_audit_lists_all_six_source_snapshot_rows() -> None:
    text = AUDIT.read_text(encoding="utf-8")

    for source_id in (
        "DERIBIT_NOTIFICATIONS",
        "DERIBIT_ENVIRONMENT",
        "DERIBIT_RATE_LIMITS",
        "DERIBIT_INSTRUMENTS",
        "DERIBIT_TICKER",
        "DERIBIT_RESTRICTED",
    ):
        assert f"`{source_id}`" in text


def test_phase27k_audit_documents_fail_closed_rules_and_forbidden_scope() -> None:
    text = AUDIT.read_text(encoding="utf-8")

    assert "`REVIEWED_APPROVED` alone is never an approval signal" in text
    assert "`retrieval_status` containing `PENDING` remains `PENDING`" in text
    assert "NOT_private_api: true" in text
    assert "NOT_credentials: true" in text
    assert "NOT_orders: true" in text
    assert "NOT_live_trading: true" in text
    assert "NOT_paper_shadow_execution: true" in text
    assert "NOT_connector_expansion: true" in text
