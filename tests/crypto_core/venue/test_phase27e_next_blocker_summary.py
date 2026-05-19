"""Phase 27E next blocker summary tests."""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
SUMMARY = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_NEXT_BLOCKER_SUMMARY_27E.md"
STATIC_VERIFICATION = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_STATIC_REGISTRY_VERIFICATION_27A.md"


def test_phase27e_docs_exist_and_record_superseded_b4_ready_b5_blocked() -> None:
    summary = SUMMARY.read_text(encoding="utf-8")
    verification = STATIC_VERIFICATION.read_text(encoding="utf-8")
    assert "status: NEXT_ACTION_PLAN_ONLY" in summary
    assert "status: STATIC_REGISTRY_VERIFICATION_ONLY" in verification
    assert "| `B4` | `READY` |" in summary
    assert "| `B5` | `BLOCKED` |" in summary
    assert "`connector_ready_dialects()` | `()`" in verification


def test_phase27e_summary_records_remaining_deferred_connector_row() -> None:
    summary = SUMMARY.read_text(encoding="utf-8")
    assert "`policy_review:separate_connector_enablement`" in summary
    assert "Separate explicit `PUBLIC_MARKET_DATA_ONLY` connector-readiness authorization" in summary
    assert "`enabled_for_connector` | `False`" in summary


def test_phase27e_validator_and_connector_state_match_summary() -> None:
    result = evaluate_deribit_manual_review_readiness()
    assert result.evidence_review_complete is True
    assert result.ready_for_engineering_patch is True
    assert len(result.pending_rows) == 0
    assert result.deferred_rows == ()
    assert result.connector_enablement_ready is True
    assert result.b1_b5_status["B4"] == "READY"
    assert result.b1_b5_status["B5"] == "READY"
    assert len(connector_ready_dialects()) == 1


def test_phase27e_forbidden_runtime_terms_absent() -> None:
    text = SUMMARY.read_text(encoding="utf-8").lower()
    for forbidden in (
        "no private api",
        "no connector enablement",
        "no `enabled_for_connector=true`",
        "no bist files or assumptions",
    ):
        assert forbidden in text
    assert "paper, shadow, or live integration" in text
    assert "credentials, orders" in text
