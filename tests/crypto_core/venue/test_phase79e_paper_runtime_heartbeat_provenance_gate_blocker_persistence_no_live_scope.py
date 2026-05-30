from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_provenance_gate_blocker_persistence import (
    audit_deribit_paper_runtime_heartbeat_provenance_gate_blocker_persistence,
)

P78 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_CONTINUITY_78B.json")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_BLOCKER_PERSISTENCE_79B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase79e_no_live_scope_in_helper_output() -> None:
    r = audit_deribit_paper_runtime_heartbeat_provenance_gate_blocker_persistence(_json(P78))
    p = r.artifact_payload
    assert p["live_ready"] is False
    assert p["shadow_ready"] is False
    assert p["runtime_order_routing_enabled"] is False
    assert p["runtime_loop_started"] is False
    assert p["campaign_execution"] is False
    assert p["session_execution"] is False
    assert p["run_execution"] is False


def test_phase79e_no_live_scope_in_artifact() -> None:
    art = _json(ARTIFACT)
    assert art["live_ready"] is False
    assert art["shadow_ready"] is False
    assert art["runtime_order_routing_enabled"] is False
    assert art["runtime_loop_started"] is False
    assert art["no_live"] is True
    assert art["no_shadow"] is True
    assert art["no_order_routing"] is True


def test_phase79e_no_mutation_and_no_strategy_output() -> None:
    art = _json(ARTIFACT)
    assert art["ledger_mutation"] is False
    assert art["strategy_signal_generated"] is False
    assert art["order_intent_generated"] is False
