from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_approval import (
    DERIBIT_PHASE73_APPROVAL_DECISION,
    DERIBIT_PHASE73_APPROVAL_SCOPE,
    DERIBIT_PHASE73_OPERATOR_ID,
    DERIBIT_PHASE73_REVIEWED_AT_ISO,
    execute_deribit_paper_runtime_heartbeat_approval,
)

P72 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_REVIEW_PROPOSAL_72B.json")
P71 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_TELEMETRY_AUDIT_71B.json")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_APPROVAL_73B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase73e_no_live_scope_in_helper_output() -> None:
    r = execute_deribit_paper_runtime_heartbeat_approval(
        _json(P72),
        _json(P71),
        operator_id=DERIBIT_PHASE73_OPERATOR_ID,
        approval_decision=DERIBIT_PHASE73_APPROVAL_DECISION,
        reviewed_at_iso=DERIBIT_PHASE73_REVIEWED_AT_ISO,
        approval_scope=DERIBIT_PHASE73_APPROVAL_SCOPE,
    )
    p = r.artifact_payload
    assert p["live_ready"] is False
    assert p["shadow_ready"] is False
    assert p["runtime_order_routing_enabled"] is False
    assert p["runtime_loop_started"] is False
    assert p["campaign_execution"] is False
    assert p["session_execution"] is False
    assert p["run_execution"] is False


def test_phase73e_no_live_scope_in_artifact() -> None:
    art = _json(ARTIFACT)
    assert art["live_ready"] is False
    assert art["shadow_ready"] is False
    assert art["runtime_order_routing_enabled"] is False
    assert art["runtime_loop_started"] is False
    assert art["no_live"] is True
    assert art["no_shadow"] is True
    assert art["no_order_routing"] is True


def test_phase73e_no_private_execution_paths() -> None:
    art = _json(ARTIFACT)
    assert art["no_private_api"] is True
    assert art["no_credentials"] is True
    assert art["no_exchange_orders"] is True
    assert art["no_execution_adapter"] is True
    assert art["no_strategy_signal"] is True
