from __future__ import annotations

import json
from pathlib import Path

PHASE70 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_OPERATOR_TRIGGERED_HEARTBEAT_70B.json")
PHASE69 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_START_TELEMETRY_AUDIT_69B.json")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_TELEMETRY_AUDIT_71B.json")


def test_phase71f_policy_preservation_from_phase70_and_phase69() -> None:
    phase70 = json.loads(PHASE70.read_text(encoding="utf-8"))
    phase69 = json.loads(PHASE69.read_text(encoding="utf-8"))
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    assert phase70["runtime_enabled"] is True and artifact["runtime_enabled"] is True
    assert phase70["runtime_started"] is True and artifact["runtime_started"] is True
    assert phase70["runtime_loop_started"] is False and artifact["runtime_loop_started"] is False
    assert phase70["runtime_order_routing_enabled"] is False and artifact["runtime_order_routing_enabled"] is False
    assert phase69["runtime_enabled"] is True and artifact["runtime_enabled"] is True
    assert phase69["runtime_started"] is True and artifact["runtime_started"] is True
    assert artifact["heartbeat_status"] == "RECORDED"
    assert artifact["heartbeat_mode"] == "OPERATOR_TRIGGERED_PAPER_RUNTIME_ONLY"
    assert artifact["heartbeat_trigger"] == "OPERATOR_MANUAL"
    assert artifact["heartbeat_sequence"] == 1
    assert artifact["heartbeat_count"] == 1
    assert artifact["promotion_scope"] == "PAPER_ONLY_SIMULATION_ONLY"
    assert artifact["next_blocker"] == "PAPER_RUNTIME_HEARTBEAT_OPERATOR_REVIEW_NOT_READY"
