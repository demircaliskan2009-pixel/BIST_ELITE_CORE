from __future__ import annotations

import ast
import re
from pathlib import Path

from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect

WORKSHEET_PATH = Path("docs/crypto_core/official_sources/deribit/20260510/DERIBIT_CLAIM_REVIEW_WORKSHEET.md")
MANIFEST_PATH = Path("docs/crypto_core/official_sources/deribit/20260510/DERIBIT_SOURCE_SNAPSHOT_MANIFEST.md")
DERIBIT_DRAFT_PATH = Path("docs/crypto_core/DERIBIT_OFFICIAL_EVIDENCE_PACKAGE_DRAFT.md")
CHECKLIST_PATH = Path("docs/crypto_core/DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md")
SNAPSHOT_CONTRACT_PATH = Path("src/crypto_core/venue/official_source_snapshots.py")
CONNECTOR_CONTRACT_PATH = Path("src/crypto_core/data/deribit_public_connector_contract.py")
DIALECT_ID = "deribit:l2_orderbook:placeholder"
EXPECTED_HASH = "a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd"
REQUIRED_CLAIM_IDS = {
    "public_websocket_availability",
    "public_rest_availability",
    "prod_testnet_ws_endpoint",
    "prod_testnet_rest_endpoint",
    "unauthenticated_public_market_data",
    "orderbook_channel_feed",
    "first_message_snapshot",
    "incremental_delta",
    "change_id",
    "prev_change_id",
    "continuity_condition",
    "gap_resubscribe_rule",
    "rest_snapshot_requirement",
    "checksum_decision",
    "heartbeat_liveness_proof",
    "public_rate_subscription_limits",
    "public_trades",
    "ticker",
    "mark_index_funding_open_interest",
    "staleness_budget",
    "receive_lag_budget",
    "testnet_prod_difference",
    "regional_legal_access",
}


def test_claim_review_worksheet_exists():
    assert WORKSHEET_PATH.is_file()


def test_every_required_claim_row_exists():
    rows = _worksheet_rows()

    assert set(rows) == REQUIRED_CLAIM_IDS


def test_every_claim_row_has_expected_review_fields_and_hash():
    # Phase 25I approved three rows; Phase 25R later approved only change_id.
    phase25i_approved_claim_ids = frozenset(
        {"public_websocket_availability", "unauthenticated_public_market_data", "orderbook_channel_feed"}
    )
    phase25r_approved_claim_ids = frozenset({"change_id"})
    # Phase 26AJ approved 15 technical rows.
    phase26aj_approved_claim_ids = frozenset(
        {
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
        }
    )
    # Phase 26AN approved 3 policy-decision claim rows.
    phase26an_approved_claim_ids = frozenset(
        {
            "checksum_decision",
            "staleness_budget",
            "receive_lag_budget",
        }
    )
    approved_claim_ids = (
        phase25i_approved_claim_ids
        | phase25r_approved_claim_ids
        | phase26aj_approved_claim_ids
        | phase26an_approved_claim_ids
    )
    for claim_id, row in _worksheet_rows().items():
        assert row["claim_id"] == claim_id
        assert row["source_id"].startswith("DERIBIT_")
        assert row["official_url"].startswith("https://docs.deribit.com/")
        assert re.fullmatch(r"[0-9a-f]{64}", row["source_sha256"])
        assert row["source_sha256"] == EXPECTED_HASH
        assert row["operational_readiness_effect"] == "LEAVES_BLOCKER"
        if claim_id in approved_claim_ids:
            assert row["review_status"] == "APPROVED"
            assert row["reviewer_id"] == "demir_operator"
            assert row["decision"] == "APPROVED"
            if claim_id in phase26an_approved_claim_ids:
                assert row["reviewed_at_iso"] == "2026-05-19T00:00:00Z"
                assert "Phase26AM_POLICY_DECISIONS_PUBLIC_DATA_ONLY" in row["rejection_reason_if_pending"]
            elif claim_id in phase26aj_approved_claim_ids:
                assert row["reviewed_at_iso"] == "2026-05-19T00:00:00Z"
                assert "Phase26AI_OFFICIAL_DOCS_TECHNICAL_ROWS_ONLY" in row["rejection_reason_if_pending"]
            else:
                assert row["reviewed_at_iso"] == "2026-05-11T00:00:00Z"
                expected_scope = (
                    "Phase25R_CHANGE_ID_ONLY"
                    if claim_id in phase25r_approved_claim_ids
                    else "Phase25I_APPROVE_NOW_CANDIDATES_ONLY"
                )
                assert expected_scope in row["rejection_reason_if_pending"]
        else:
            assert row["review_status"] == "PENDING"
            assert row["reviewer_id"] == "PENDING"
            assert row["reviewed_at_iso"] == "PENDING"
            assert row["decision"] == "PENDING"
            assert row["rejection_reason_if_pending"].startswith("manual_review:")


def test_no_claim_row_marks_operational_readiness_accepted():
    worksheet = _worksheet()

    assert "`operational_status`: `BLOCKED`" in worksheet
    assert "`manual_review_status`: `PENDING`" in worksheet
    assert "`enabled_for_connector`: `false`" in worksheet
    assert "`static_registry_verified`: `false`" in worksheet
    assert "`connector_ready_dialects_expected`: `[]`" in worksheet
    assert "`operational_readiness_effect`: `LEAVES_BLOCKER`" in worksheet
    assert "`decision`: `APPROVED`" not in worksheet
    assert "operational_readiness_effect=ACCEPTED" not in worksheet


def test_same_hash_caveat_is_documented():
    combined = " ".join("\n".join((_worksheet(), _manifest(), _checklist())).split())

    assert "same single-page documentation payload" in combined
    assert "same content hash and byte size" in combined
    assert "do not prove claim-level" in combined or "do not equal claim-level approval" in combined


def test_deribit_draft_and_checklist_remain_blocked():
    combined = _draft() + "\n" + _checklist()

    assert "`operational_status`: `BLOCKED`" in combined
    assert "`phase22m_claim_review_status`: `PENDING`" in combined
    assert "`manual_review_required`: `YES`" in combined
    assert "`enabled_for_connector`: `false`" in combined
    assert "`static_registry_verified`: `false`" in combined
    assert "`operational_status`: `READY`" not in combined
    assert "`enabled_for_connector`: `true`" not in combined


def test_static_registry_remains_unverified_and_connector_ready_dialects_empty():
    spec = get_public_feed_dialect(DIALECT_ID)

    assert spec.verification_status.value == "unverified"
    assert spec.enabled_for_connector is False
    assert connector_ready_dialects() == ()


def test_no_source_network_or_connector_behavior_added():
    for path in (SNAPSHOT_CONTRACT_PATH, CONNECTOR_CONTRACT_PATH):
        source = path.read_text(encoding="utf-8").lower()
        tree = ast.parse(source)
        forbidden_import_roots = {
            "aiohttp",
            "httpx",
            "requests",
            "socket",
            "urllib",
            "websocket",
            "websockets",
        }
        imports: set[str] = set()
        function_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
            elif isinstance(node, ast.FunctionDef):
                function_names.add(node.name)

        assert forbidden_import_roots.isdisjoint(imports)
        assert {"connect", "recv", "receive", "send", "subscribe", "start", "stop"}.isdisjoint(function_names)
        assert {"place_order", "cancel_order"}.isdisjoint(function_names)
        assert "api_key" not in source
        assert "api_secret" not in source
        assert "getenv" not in source
        assert "os.environ" not in source


def test_no_raw_html_snapshots_committed():
    assert not list(MANIFEST_PATH.parent.glob("*.html"))


def _worksheet_rows() -> dict[str, dict[str, str]]:
    headers: list[str] | None = None
    rows: dict[str, dict[str, str]] = {}
    for line in _worksheet().splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells[0] == "claim_id":
            headers = cells
            continue
        if headers is None or cells[0] == "---" or not cells[0].startswith("`"):
            continue
        row = {header: value.strip("`") for header, value in zip(headers, cells, strict=True)}
        rows[row["claim_id"]] = row
    return rows


def _worksheet() -> str:
    return WORKSHEET_PATH.read_text(encoding="utf-8")


def _manifest() -> str:
    return MANIFEST_PATH.read_text(encoding="utf-8")


def _draft() -> str:
    return DERIBIT_DRAFT_PATH.read_text(encoding="utf-8")


def _checklist() -> str:
    return CHECKLIST_PATH.read_text(encoding="utf-8")
