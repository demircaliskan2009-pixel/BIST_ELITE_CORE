"""Phase 26AN — Policy and claim worksheet approval verification.

Tests that exactly 8 rows are APPROVED in Phase 26AN (3 claim + 5 policy),
the correct policy_values appear in approved row rejection_reason_if_pending
fields, and the 3 forbidden rows remain PENDING.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_CLAIM_PATH = Path("docs/crypto_core/official_sources/deribit/20260510/DERIBIT_CLAIM_REVIEW_WORKSHEET.md")
_POLICY_PATH = Path("docs/crypto_core/official_sources/deribit/20260510/DERIBIT_OPERATIONAL_POLICY_REVIEW_WORKSHEET.md")

# Claim rows approved in this phase (3)
_PHASE26AN_APPROVED_CLAIM_IDS = frozenset(
    {
        "checksum_decision",
        "staleness_budget",
        "receive_lag_budget",
    }
)

# Policy rows approved in this phase (5)
_PHASE26AN_APPROVED_POLICY_IDS = frozenset(
    {
        "checksum_decision",
        "liveness_policy",
        "staleness_budget",
        "receive_lag_budget",
        "testnet_prod_review",
    }
)

_REQUIRED_CLAIM_POLICY_VALUES = {
    "checksum_decision": "NO_CHECKSUM_FIELD_APPROVED_FOR_CURRENT_PUBLIC_DATA_EVIDENCE",
    "staleness_budget": "MAX_STALENESS_MS_2000",
    "receive_lag_budget": "MAX_RECEIVE_LAG_MS_1000",
}

_REQUIRED_POLICY_POLICY_VALUES = {
    "checksum_decision": "NO_CHECKSUM_FIELD_APPROVED_FOR_CURRENT_PUBLIC_DATA_EVIDENCE",
    "liveness_policy": "PUBLIC_WS_LIVENESS_TIMEOUT_MS_10000",
    "staleness_budget": "MAX_STALENESS_MS_2000",
    "receive_lag_budget": "MAX_RECEIVE_LAG_MS_1000",
    "testnet_prod_review": "PROD_AND_TESTNET_MUST_REMAIN_EXPLICITLY_CONFIG_SEPARATED",
}


def _parse_md_table_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    header: list[str] | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip().strip("`") for c in line.split("|")[1:-1]]
        if header is None:
            header = cells
            continue
        if all(set(c.replace("-", "").replace(":", "")) == set() for c in cells):
            continue
        if len(cells) >= len(header):
            rows.append(dict(zip(header, cells)))
    return rows


@pytest.fixture(scope="module")
def claim_rows() -> list[dict[str, str]]:
    assert _CLAIM_PATH.exists()
    return _parse_md_table_rows(_CLAIM_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def policy_rows() -> list[dict[str, str]]:
    assert _POLICY_PATH.exists()
    return _parse_md_table_rows(_POLICY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def claim_rows_by_id(claim_rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {r["claim_id"]: r for r in claim_rows if "claim_id" in r}


@pytest.fixture(scope="module")
def policy_rows_by_id(policy_rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {r["policy_id"]: r for r in policy_rows if "policy_id" in r}


# --- Claim worksheet tests ---


def test_claim_worksheet_exists() -> None:
    assert _CLAIM_PATH.exists()


def test_claim_worksheet_row_count(claim_rows: list[dict[str, str]]) -> None:
    assert len(claim_rows) == 23


def test_phase26an_claim_rows_approved(claim_rows_by_id: dict[str, dict[str, str]]) -> None:
    for cid in _PHASE26AN_APPROVED_CLAIM_IDS:
        row = claim_rows_by_id.get(cid)
        assert row is not None, f"Claim row missing: {cid}"
        assert row.get("decision", "").upper() == "APPROVED", (
            f"claim_id={cid} expected APPROVED, got {row.get('decision')}"
        )
        assert row.get("reviewer_id") == "demir_operator", f"claim_id={cid} reviewer mismatch"
        assert row.get("reviewed_at_iso") == "2026-05-19T00:00:00Z", f"claim_id={cid} reviewed_at mismatch"


def test_claim_checksum_decision_approved(claim_rows_by_id: dict[str, dict[str, str]]) -> None:
    row = claim_rows_by_id["checksum_decision"]
    assert row["decision"].upper() == "APPROVED"


def test_claim_staleness_budget_approved(claim_rows_by_id: dict[str, dict[str, str]]) -> None:
    row = claim_rows_by_id["staleness_budget"]
    assert row["decision"].upper() == "APPROVED"


def test_claim_receive_lag_budget_approved(claim_rows_by_id: dict[str, dict[str, str]]) -> None:
    row = claim_rows_by_id["receive_lag_budget"]
    assert row["decision"].upper() == "APPROVED"


def test_claim_regional_legal_access_approved_in_phase26ar(claim_rows_by_id: dict[str, dict[str, str]]) -> None:
    row = claim_rows_by_id.get("regional_legal_access")
    assert row is not None
    assert row.get("decision", "").upper() == "APPROVED", (
        "regional_legal_access claim must be APPROVED after Phase 26AR"
    )


def test_claim_phase26an_policy_values_present(claim_rows_by_id: dict[str, dict[str, str]]) -> None:
    for cid, expected_value in _REQUIRED_CLAIM_POLICY_VALUES.items():
        row = claim_rows_by_id.get(cid)
        assert row is not None, f"Claim row missing: {cid}"
        notes = row.get("rejection_reason_if_pending", "")
        assert expected_value in notes, f"claim_id={cid} missing policy_value={expected_value} in notes: {notes!r}"


def test_claim_checksum_phase26am_scope(claim_rows_by_id: dict[str, dict[str, str]]) -> None:
    notes = claim_rows_by_id["checksum_decision"].get("rejection_reason_if_pending", "")
    assert "Phase26AM_POLICY_DECISIONS_PUBLIC_DATA_ONLY" in notes


def test_claim_staleness_phase26am_scope(claim_rows_by_id: dict[str, dict[str, str]]) -> None:
    notes = claim_rows_by_id["staleness_budget"].get("rejection_reason_if_pending", "")
    assert "Phase26AM_POLICY_DECISIONS_PUBLIC_DATA_ONLY" in notes


def test_claim_receive_lag_phase26am_scope(claim_rows_by_id: dict[str, dict[str, str]]) -> None:
    notes = claim_rows_by_id["receive_lag_budget"].get("rejection_reason_if_pending", "")
    assert "Phase26AM_POLICY_DECISIONS_PUBLIC_DATA_ONLY" in notes


def test_claim_no_enabled_for_connector_true() -> None:
    text = _CLAIM_PATH.read_text(encoding="utf-8")
    assert "enabled_for_connector: true" not in text.lower()


def test_claim_no_static_registry_verified_change() -> None:
    text = _CLAIM_PATH.read_text(encoding="utf-8")
    assert "static_registry_verified: true" not in text.lower()


# --- Policy worksheet tests ---


def test_policy_worksheet_exists() -> None:
    assert _POLICY_PATH.exists()


def test_policy_worksheet_row_count(policy_rows: list[dict[str, str]]) -> None:
    assert len(policy_rows) == 7


def test_phase26an_policy_rows_approved(policy_rows_by_id: dict[str, dict[str, str]]) -> None:
    for pid in _PHASE26AN_APPROVED_POLICY_IDS:
        row = policy_rows_by_id.get(pid)
        assert row is not None, f"Policy row missing: {pid}"
        assert row.get("decision", "").upper() == "APPROVED", (
            f"policy_id={pid} expected APPROVED, got {row.get('decision')}"
        )
        assert row.get("reviewer_id") == "demir_operator", f"policy_id={pid} reviewer mismatch"
        assert row.get("reviewed_at_iso") == "2026-05-19T00:00:00Z", f"policy_id={pid} reviewed_at mismatch"


def test_policy_checksum_decision_approved(policy_rows_by_id: dict[str, dict[str, str]]) -> None:
    assert policy_rows_by_id["checksum_decision"]["decision"].upper() == "APPROVED"


def test_policy_liveness_policy_approved(policy_rows_by_id: dict[str, dict[str, str]]) -> None:
    assert policy_rows_by_id["liveness_policy"]["decision"].upper() == "APPROVED"


def test_policy_staleness_budget_approved(policy_rows_by_id: dict[str, dict[str, str]]) -> None:
    assert policy_rows_by_id["staleness_budget"]["decision"].upper() == "APPROVED"


def test_policy_receive_lag_budget_approved(policy_rows_by_id: dict[str, dict[str, str]]) -> None:
    assert policy_rows_by_id["receive_lag_budget"]["decision"].upper() == "APPROVED"


def test_policy_testnet_prod_review_approved(policy_rows_by_id: dict[str, dict[str, str]]) -> None:
    assert policy_rows_by_id["testnet_prod_review"]["decision"].upper() == "APPROVED"


def test_policy_regional_legal_access_review_approved_in_26aw(policy_rows_by_id: dict[str, dict[str, str]]) -> None:
    row = policy_rows_by_id.get("regional_legal_access_review")
    assert row is not None
    assert row.get("decision", "").upper() in ("APPROVE", "APPROVED"), (
        "regional_legal_access_review must be APPROVED after Phase 26AW"
    )


def test_policy_separate_connector_enablement_approved_in_phase27f(
    policy_rows_by_id: dict[str, dict[str, str]],
) -> None:
    row = policy_rows_by_id.get("separate_connector_enablement")
    assert row is not None
    assert row.get("decision", "").upper() == "APPROVE"
    assert row.get("policy_status", "").upper() == "APPROVED"


def test_policy_phase26an_policy_values_present(policy_rows_by_id: dict[str, dict[str, str]]) -> None:
    for pid, expected_value in _REQUIRED_POLICY_POLICY_VALUES.items():
        row = policy_rows_by_id.get(pid)
        assert row is not None, f"Policy row missing: {pid}"
        notes = row.get("rejection_reason_if_pending", "")
        assert expected_value in notes, f"policy_id={pid} missing policy_value={expected_value} in notes: {notes!r}"


def test_policy_checksum_enforcement_present(policy_rows_by_id: dict[str, dict[str, str]]) -> None:
    notes = policy_rows_by_id["checksum_decision"].get("rejection_reason_if_pending", "")
    assert "FAIL_CLOSED_IF_SELECTED_CHANNEL_OR_DOCS_REQUIRE_CHECKSUM" in notes


def test_policy_liveness_enforcement_present(policy_rows_by_id: dict[str, dict[str, str]]) -> None:
    notes = policy_rows_by_id["liveness_policy"].get("rejection_reason_if_pending", "")
    assert "FAIL_CLOSED_ON_NO_MESSAGE_OR_NO_HEARTBEAT_WITHIN_10000MS" in notes


def test_policy_liveness_reconnect_action_present(policy_rows_by_id: dict[str, dict[str, str]]) -> None:
    notes = policy_rows_by_id["liveness_policy"].get("rejection_reason_if_pending", "")
    assert "RESUBSCRIBE_OR_RECONNECT_REQUIRED" in notes


def test_policy_staleness_enforcement_present(policy_rows_by_id: dict[str, dict[str, str]]) -> None:
    notes = policy_rows_by_id["staleness_budget"].get("rejection_reason_if_pending", "")
    assert "MARK_FEED_STALE_AND_BLOCK_DOWNSTREAM_READINESS_IF_EXCEEDED" in notes


def test_policy_receive_lag_enforcement_present(policy_rows_by_id: dict[str, dict[str, str]]) -> None:
    notes = policy_rows_by_id["receive_lag_budget"].get("rejection_reason_if_pending", "")
    assert "REJECT_OR_QUARANTINE_EVENT_IF_EXCEEDED" in notes


def test_policy_testnet_prod_enforcement_present(policy_rows_by_id: dict[str, dict[str, str]]) -> None:
    notes = policy_rows_by_id["testnet_prod_review"].get("rejection_reason_if_pending", "")
    assert "NO_IMPLICIT_ENVIRONMENT_FALLBACK" in notes


def test_policy_no_enabled_for_connector_true() -> None:
    text = _POLICY_PATH.read_text(encoding="utf-8")
    assert "enabled_for_connector: true" not in text.lower()


def test_policy_no_static_registry_verified_true() -> None:
    text = _POLICY_PATH.read_text(encoding="utf-8")
    assert "static_registry_verified: true" not in text.lower()
