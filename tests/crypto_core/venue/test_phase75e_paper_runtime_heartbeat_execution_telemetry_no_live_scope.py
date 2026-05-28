from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_execution_telemetry import (
    audit_deribit_paper_runtime_heartbeat_execution_telemetry,
)

P74 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_74B.json")
P73 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_APPROVAL_73B.json")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_TELEMETRY_AUDIT_75B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase75e_no_live_scope_in_helper_output() -> None:
    r = audit_deribit_paper_runtime_heartbeat_execution_telemetry(_json(P74), _json(P73))
    p = r.artifact_payload
    assert p["live_ready"] is False
    assert p["shadow_ready"] is False
    assert p["runtime_order_routing_enabled"] is False
    assert p["runtime_loop_started"] is False
    assert p["campaign_execution"] is False
    assert p["session_execution"] is False
    assert p["run_execution"] is False


def test_phase75e_no_live_scope_in_artifact() -> None:
    art = _json(ARTIFACT)
    assert art["live_ready"] is False
    assert art["shadow_ready"] is False
    assert art["runtime_order_routing_enabled"] is False
    assert art["runtime_loop_started"] is False
    assert art["no_live"] is True
    assert art["no_shadow"] is True
    assert art["no_order_routing"] is True


def test_phase75e_no_mutation_and_no_strategy_output() -> None:
    art = _json(ARTIFACT)
    assert art["ledger_mutation"] is False
    assert art["strategy_signal_generated"] is False
    assert art["order_intent_generated"] is False
