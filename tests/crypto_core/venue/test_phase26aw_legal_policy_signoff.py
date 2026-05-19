"""Phase 26AW: Legal policy signoff worksheet verification tests."""

from __future__ import annotations

from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    evaluate_deribit_manual_review_readiness,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
POLICY_WORKSHEET_PATH = (
    REPO_ROOT
    / "docs"
    / "crypto_core"
    / "official_sources"
    / "deribit"
    / "20260510"
    / "DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md"
)


def _policy_text() -> str:
    return POLICY_WORKSHEET_PATH.read_text(encoding="utf-8")


def _policy_rows() -> list[dict[str, str]]:
    from crypto_core.venue.deribit_manual_review_readiness import _parse_md_table_rows  # type: ignore[attr-defined]

    return _parse_md_table_rows(_policy_text())


def _rows_by_id() -> dict[str, dict[str, str]]:
    return {row["policy_id"]: row for row in _policy_rows()}


# --- Policy worksheet structure ---


def test_phase26aw_policy_worksheet_exists() -> None:
    assert POLICY_WORKSHEET_PATH.exists()


def test_phase26aw_policy_worksheet_has_7_rows() -> None:
    rows = _rows_by_id()
    assert len(rows) == 7, f"Expected 7 policy rows, got {len(rows)}"


# --- regional_legal_access_review approved ---


def test_phase26aw_regional_legal_access_review_decision_approve() -> None:
    row = _rows_by_id().get("regional_legal_access_review")
    assert row is not None
    assert row.get("decision", "").upper() in ("APPROVE", "APPROVED"), (
        f"regional_legal_access_review decision must be APPROVE, got {row.get('decision')!r}"
    )


def test_phase26aw_regional_legal_access_review_reviewer_id() -> None:
    row = _rows_by_id()["regional_legal_access_review"]
    assert row.get("reviewer_id") == "demir_operator"


def test_phase26aw_regional_legal_access_review_reviewed_at() -> None:
    row = _rows_by_id()["regional_legal_access_review"]
    assert row.get("reviewed_at_iso", "").startswith("2026-05-19")


def test_phase26aw_regional_legal_access_review_policy_status() -> None:
    row = _rows_by_id()["regional_legal_access_review"]
    assert row.get("policy_status", "").upper() == "APPROVED"


# --- separate_connector_enablement approved in Phase 27F ---


def test_phase26aw_separate_connector_enablement_decision_approve() -> None:
    row = _rows_by_id().get("separate_connector_enablement")
    assert row is not None
    assert row.get("decision", "").upper() == "APPROVE", (
        f"separate_connector_enablement decision must be APPROVE, got {row.get('decision')!r}"
    )


def test_phase26aw_separate_connector_enablement_reviewer_id() -> None:
    row = _rows_by_id()["separate_connector_enablement"]
    assert row.get("reviewer_id") == "demir_operator"


def test_phase26aw_separate_connector_enablement_reviewed_at() -> None:
    row = _rows_by_id()["separate_connector_enablement"]
    assert row.get("reviewed_at_iso", "").startswith("2026-05-19")


def test_phase26aw_separate_connector_enablement_policy_status() -> None:
    row = _rows_by_id()["separate_connector_enablement"]
    assert row.get("policy_status", "").upper() == "APPROVED"


# --- Validator state post-26AW ---


def test_phase26aw_validator_pending_rows_zero() -> None:
    result = evaluate_deribit_manual_review_readiness()
    assert len(result.pending_rows) == 0, f"Expected 0 pending rows, got: {result.pending_rows}"


def test_phase26aw_validator_deferred_rows_empty_after_27f() -> None:
    result = evaluate_deribit_manual_review_readiness()
    assert result.deferred_rows == ()


def test_phase26aw_validator_evidence_review_complete_true() -> None:
    result = evaluate_deribit_manual_review_readiness()
    assert result.evidence_review_complete is True


def test_phase26aw_validator_accepted_false() -> None:
    result = evaluate_deribit_manual_review_readiness()
    assert result.accepted is False
