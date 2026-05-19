"""Phase 26AV: Operator legal signoff execution audit document tests."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
AUDIT_DOC_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_OPERATOR_LEGAL_SIGNOFF_EXECUTION_AUDIT_26AV.md"


def _audit_text() -> str:
    return AUDIT_DOC_PATH.read_text(encoding="utf-8")


def test_phase26av_audit_doc_exists() -> None:
    assert AUDIT_DOC_PATH.exists(), f"26AV audit doc missing: {AUDIT_DOC_PATH}"


def test_phase26av_audit_doc_contains_phase_marker() -> None:
    assert "Phase26AV" in _audit_text()


def test_phase26av_audit_doc_contains_turkey_public_market_data_only() -> None:
    assert "TURKEY_PUBLIC_MARKET_DATA_ONLY" in _audit_text()


def test_phase26av_audit_doc_contains_non_legal_advice() -> None:
    assert "NON-LEGAL-ADVICE" in _audit_text()


def test_phase26av_audit_doc_contains_operator_required() -> None:
    assert "OPERATOR_REQUIRED" in _audit_text() or "operator" in _audit_text().lower()


def test_phase26av_audit_doc_references_regional_legal_access_review() -> None:
    assert "regional_legal_access_review" in _audit_text()


def test_phase26av_audit_doc_references_separate_connector_enablement() -> None:
    assert "separate_connector_enablement" in _audit_text()


def test_phase26av_audit_doc_not_empty() -> None:
    text = _audit_text()
    assert len(text) > 200, f"Audit doc unexpectedly short: {len(text)} chars"


def test_phase26av_audit_doc_no_live_trading_approval() -> None:
    text = _audit_text().lower()
    assert "live_trading_approved" not in text
    assert "enabled_for_connector: true" not in text
    assert "static_registry_verified: true" not in text
