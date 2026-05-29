from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_provenance_gate_continuity import (
    audit_deribit_paper_runtime_heartbeat_provenance_gate_continuity,
)

P77 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_STATUS_77B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase78d_rejects_missing_input() -> None:
    r = audit_deribit_paper_runtime_heartbeat_provenance_gate_continuity(None)
    assert r.accepted is False
    assert "phase77_artifact_missing" in r.reason_code
    assert r.artifact_payload["provenance_gate_status_continuity"] == "FAIL_CLOSED"
    assert r.artifact_payload["next_blocker"] == "PROVENANCE_GATE_CONTINUITY_REPORT_NOT_READY"


def test_phase78d_rejects_provenance_drift() -> None:
    payload = _json(P77)
    payload["provenance_reason"] = "DRIFT"

    r = audit_deribit_paper_runtime_heartbeat_provenance_gate_continuity(payload)

    assert r.accepted is False
    assert "deribit_paper_runtime_heartbeat_provenance_gate_continuity:phase77_provenance_drift" in r.rejection_reasons


def test_phase78d_rejects_connector_count_drift() -> None:
    payload = _json(P77)
    payload["connector_ready_dialects_count"] = 2

    r = audit_deribit_paper_runtime_heartbeat_provenance_gate_continuity(payload)

    assert r.accepted is False
    assert "deribit_paper_runtime_heartbeat_provenance_gate_continuity:phase77_provenance_drift" in r.rejection_reasons
