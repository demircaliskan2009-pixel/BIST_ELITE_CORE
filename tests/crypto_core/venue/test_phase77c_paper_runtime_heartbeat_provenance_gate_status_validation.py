from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_provenance_gate_status import (
    DERIBIT_PHASE77_NEXT_BLOCKER,
    audit_deribit_paper_runtime_heartbeat_provenance_gate_status,
)

P76 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_POST_AUDIT_76B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase77c_helper_accepts_valid_phase76_input() -> None:
    r = audit_deribit_paper_runtime_heartbeat_provenance_gate_status(_json(P76))
    assert r.accepted is True
    assert r.reason_code == "deribit_paper_runtime_heartbeat_provenance_gate_status:accepted"
    assert r.rejection_reasons == ()


def test_phase77c_provenance_gate_fields_are_set() -> None:
    r = audit_deribit_paper_runtime_heartbeat_provenance_gate_status(_json(P76))
    p = r.artifact_payload
    assert p["heartbeat_execution_post_audit_status"] == "PASS"
    assert p["b5_status"] == "BLOCKED"
    assert p["connector_enablement_ready"] is False
    assert p["provenance_reason"] == DERIBIT_PHASE77_NEXT_BLOCKER
    assert p["next_blocker"] == DERIBIT_PHASE77_NEXT_BLOCKER


def test_phase77c_b5_remains_blocked() -> None:
    r = audit_deribit_paper_runtime_heartbeat_provenance_gate_status(_json(P76))
    p = r.artifact_payload
    assert p["b5_status"] == "BLOCKED"
    assert p["connector_enablement_ready"] is False
