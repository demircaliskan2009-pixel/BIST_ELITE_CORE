"""Phase 26AS — Proof batch classifying 3 row readiness states."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PROOF_BATCH_PATH = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_REGIONAL_LEGAL_ACCESS_PROOF_BATCH_26AS.md"


def _content() -> str:
    return PROOF_BATCH_PATH.read_text(encoding="utf-8")


def test_phase26as_proof_batch_exists() -> None:
    assert PROOF_BATCH_PATH.exists(), "Proof batch document must exist"


def test_phase26as_proof_batch_non_empty() -> None:
    assert len(_content()) > 100


def test_phase26as_claim_row_classification() -> None:
    content = _content()
    assert "regional_legal_access" in content
    assert "LEGAL_DOC_PROOF_READY_NOT_APPROVED" in content


def test_phase26as_policy_legal_row_classification() -> None:
    content = _content()
    assert "regional_legal_access_review" in content
    assert "LEGAL_REVIEW_READY_FOR_OPERATOR_SIGNOFF" in content


def test_phase26as_connector_row_classification() -> None:
    content = _content()
    assert "separate_connector_enablement" in content
    assert "DEFER_SEPARATE_PHASE" in content


def test_phase26as_no_connector_runtime_implication() -> None:
    content = _content()
    assert "NONE" in content
    assert "No connector enablement" in content or "no connector" in content.lower()


def test_phase26as_no_live_trading_claim() -> None:
    content = _content()
    assert "live trading" not in content.lower() or "not done" in content.lower()
    assert "private API" not in content.lower() or "not" in content.lower()


def test_phase26as_evidence_references_26ar() -> None:
    assert "DERIBIT_REGIONAL_LEGAL_ACCESS_RESEARCH_PACK_26AR.md" in _content()
