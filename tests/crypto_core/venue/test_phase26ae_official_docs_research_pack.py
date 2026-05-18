"""Phase 26AE official Deribit docs research pack tests."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
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
    return PACK_PATH.read_text(encoding="utf-8")


def _row_line(row_id: str) -> str:
    for line in _text().splitlines():
        if line.startswith(f"| `{row_id}` |"):
            return line
    raise AssertionError(f"row missing from research pack: {row_id}")


def test_phase26ae_research_pack_exists_and_is_not_approval() -> None:
    content = _text()
    assert "status: OFFICIAL_CURRENT_RESEARCH_PACK_ONLY" in content
    assert "NOT_an_approval: true" in content
    assert "NOT_worksheet_mutation: true" in content
    assert "NOT_connector_enablement: true" in content
    assert "NOT_legal_approval: true" in content


def test_phase26ae_every_promoted_row_has_official_url_anchor_evidence() -> None:
    content = _text()
    assert "https://docs.deribit.com/index.html#environments" in content
    assert "https://docs.deribit.com/articles/json-rpc-overview#transport-protocols" in content
    assert (
        "https://docs.deribit.com/subscriptions/orderbook/bookinstrument_nameinterval#bookinstrument_nameinterval"
        in content
    )
    assert "https://docs.deribit.com/articles/notifications#handling-missed-messages" in content
    assert (
        "https://docs.deribit.com/api-reference/session-management/public-set_heartbeat#publicset_heartbeat" in content
    )
    for row in PROOF_READY_ROWS:
        line = _row_line(row)
        assert "PROOF_READY_NOT_APPROVED" in line
        assert "S" in line


def test_phase26ae_uses_only_official_deribit_sources() -> None:
    allowed_hosts = {
        "docs.deribit.com",
        "support.deribit.com",
        "www.deribit.com",
        "test.deribit.com",
    }
    urls = re.findall(r"https://([A-Za-z0-9.-]+)[^` )|]*", _text())
    assert urls, "research pack must contain source URLs"
    assert set(urls).issubset(allowed_hosts)


def test_phase26ae_ambiguous_rows_stay_fail_closed() -> None:
    line = _row_line("checksum_decision")
    assert "WAIT_INSUFFICIENT" in line
    assert "does not cite an official checksum" in line


def test_phase26ae_regional_legal_access_is_documentation_only() -> None:
    line = _row_line("regional_legal_access")
    assert "DOCUMENTATION_PROOF_READY" in line
    assert "S10_RESTRICTED_JURISDICTIONS" in line
    assert "not legal approval" in _text().lower()
