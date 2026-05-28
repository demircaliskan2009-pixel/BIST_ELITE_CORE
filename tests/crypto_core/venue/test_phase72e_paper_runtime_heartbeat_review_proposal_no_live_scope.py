from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_review_proposal import (
    DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT,
    evaluate_deribit_paper_runtime_heartbeat_review_proposal,
)

ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_REVIEW_PROPOSAL_72B.json")


def _load_phase71() -> dict[str, object]:
    return json.loads(Path(DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT).read_text(encoding="utf-8"))


def test_phase72e_no_live_scope_in_helper_output() -> None:
    r = evaluate_deribit_paper_runtime_heartbeat_review_proposal(_load_phase71())
    p = r.artifact_payload
    assert p["live_ready"] is False
    assert p["live_enabled"] is False
    assert p["no_live"] is True
    assert p["shadow_ready"] is False
    assert p["shadow_enabled"] is False
    assert p["no_shadow"] is True
    assert p["runtime_loop_started"] is False
    assert p["runtime_order_routing_enabled"] is False


def test_phase72e_no_live_scope_in_artifact() -> None:
    art = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert art["live_ready"] is False
    assert art["live_enabled"] is False
    assert art["no_live"] is True
    assert art["shadow_ready"] is False
    assert art["shadow_enabled"] is False
    assert art["no_shadow"] is True
    assert art["runtime_loop_started"] is False
    assert art["runtime_order_routing_enabled"] is False


def test_phase72e_operator_approval_fields_null() -> None:
    art = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert art["operator_id"] is None
    assert art["reviewed_at_iso"] is None
    assert art["approval_decision"] is None
    assert art["approval_status"] == "NOT_APPROVED"


def test_phase72e_no_campaign_session_run_execution() -> None:
    r = evaluate_deribit_paper_runtime_heartbeat_review_proposal(_load_phase71())
    p = r.artifact_payload
    assert p["campaign_execution"] is False
    assert p["session_execution"] is False
    assert p["run_execution"] is False
    assert p["ledger_mutation"] is False
    assert p["strategy_signal_generated"] is False
    assert p["order_intent_generated"] is False
