"""Phase 27F public-market-data connector enablement audit tests."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
AUDIT = REPO_ROOT / "docs" / "crypto_core" / "DERIBIT_PUBLIC_MARKET_DATA_CONNECTOR_ENABLEMENT_AUDIT_27F.md"
POLICY = (
    REPO_ROOT
    / "docs"
    / "crypto_core"
    / "official_sources"
    / "deribit"
    / "20260510"
    / "DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md"
)


def _policy_rows() -> dict[str, dict[str, str]]:
    text = POLICY.read_text(encoding="utf-8")
    headers: list[str] | None = None
    rows: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip("|").split("|")]
        if cells[0] == "policy_id":
            headers = cells
            continue
        if headers is None or cells[0] == "---" or not cells[0]:
            continue
        row = {header: value for header, value in zip(headers, cells, strict=True)}
        rows[row["policy_id"]] = row
    return rows


def test_phase27f_audit_records_exact_operator_approval_scope() -> None:
    text = AUDIT.read_text(encoding="utf-8")

    assert "reviewer_id: demir_operator" in text
    assert "reviewed_at_iso: 2026-05-19T00:00:00Z" in text
    assert "approval_scope: Phase27F_PUBLIC_MARKET_DATA_ONLY_CONNECTOR_ENABLEMENT" in text
    assert "decision: APPROVE" in text
    assert "approved_run_mode: PUBLIC_MARKET_DATA_ONLY" in text


def test_phase27f_separate_connector_enablement_approved_exactly_once() -> None:
    rows = _policy_rows()
    connector_rows = [row for row in rows.values() if row["policy_id"] == "separate_connector_enablement"]

    assert len(connector_rows) == 1
    row = connector_rows[0]
    assert row["policy_status"] == "APPROVED"
    assert row["decision"] == "APPROVE"
    assert row["reviewer_id"] == "demir_operator"
    assert row["reviewed_at_iso"] == "2026-05-19T00:00:00Z"
    assert "Phase27F_PUBLIC_MARKET_DATA_ONLY_CONNECTOR_ENABLEMENT" in row["rejection_reason_if_pending"]
    assert (
        "PUBLIC_MARKET_DATA_ONLY_NO_PRIVATE_API_NO_CREDENTIALS_NO_ORDERS_NO_LIVE_NO_PAPER_SHADOW_EXECUTION"
        in row["rejection_reason_if_pending"]
    )


def test_phase27f_audit_forbids_private_credentials_orders_and_trading() -> None:
    text = AUDIT.read_text(encoding="utf-8").lower()
    for phrase in (
        "no private api",
        "no credentials",
        "no orders",
        "no deposits or withdrawals",
        "no live trading",
        "no paper execution",
        "no shadow execution",
        "no bist code or assumptions",
    ):
        assert phrase in text
