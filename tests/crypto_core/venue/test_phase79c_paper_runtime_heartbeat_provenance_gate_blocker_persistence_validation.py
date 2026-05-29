from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_provenance_gate_blocker_persistence import (
    DERIBIT_PHASE79_NEXT_BLOCKER,
    audit_deribit_paper_runtime_heartbeat_provenance_gate_blocker_persistence,
)

P78 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_CONTINUITY_78B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase79c_accepts_valid_phase78_input() -> None:
    r = audit_deribit_paper_runtime_heartbeat_provenance_gate_blocker_persistence(_json(P78))

    assert r.accepted is True
    assert r.reason_code == "deribit_paper_runtime_heartbeat_provenance_gate_blocker_persistence:accepted"
    assert r.rejection_reasons == ()

    artifact = r.artifact_payload
    assert artifact["provenance_gate_blocker_persistence"] == "PASS"
    assert artifact["b5_status"] == "BLOCKED"
    assert artifact["connector_enablement_ready"] is False
    assert artifact["provenance_reason"] == DERIBIT_PHASE79_NEXT_BLOCKER
    assert artifact["next_blocker"] == DERIBIT_PHASE79_NEXT_BLOCKER
