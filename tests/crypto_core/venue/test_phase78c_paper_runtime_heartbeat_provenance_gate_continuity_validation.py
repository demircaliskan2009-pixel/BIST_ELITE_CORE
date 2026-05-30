from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_provenance_gate_continuity import (
    DERIBIT_PHASE78_NEXT_BLOCKER,
    audit_deribit_paper_runtime_heartbeat_provenance_gate_continuity,
)

P77 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_STATUS_77B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase78c_accepts_valid_phase77_input() -> None:
    r = audit_deribit_paper_runtime_heartbeat_provenance_gate_continuity(_json(P77))

    assert r.accepted is True
    assert r.reason_code == "deribit_paper_runtime_heartbeat_provenance_gate_continuity:accepted"
    assert r.rejection_reasons == ()

    artifact = r.artifact_payload
    assert artifact["provenance_gate_status_continuity"] == "PASS"
    assert artifact["b5_status"] == "BLOCKED"
    assert artifact["connector_enablement_ready"] is False
    assert artifact["provenance_reason"] == DERIBIT_PHASE78_NEXT_BLOCKER
    assert artifact["next_blocker"] == DERIBIT_PHASE78_NEXT_BLOCKER
