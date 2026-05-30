from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_execution_telemetry import (
    DERIBIT_PHASE75_NEXT_BLOCKER,
    audit_deribit_paper_runtime_heartbeat_execution_telemetry,
)

P74 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_74B.json")
P73 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_APPROVAL_73B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase75c_helper_accepts_valid_inputs() -> None:
    r = audit_deribit_paper_runtime_heartbeat_execution_telemetry(_json(P74), _json(P73))
    assert r.accepted is True
    assert r.reason_code == "deribit_paper_runtime_heartbeat_execution_telemetry:accepted"
    assert r.rejection_reasons == ()


def test_phase75c_telemetry_fields_are_set() -> None:
    r = audit_deribit_paper_runtime_heartbeat_execution_telemetry(_json(P74), _json(P73))
    p = r.artifact_payload
    assert p["heartbeat_execution_telemetry_status"] == "PASS"
    assert p["heartbeat_execution_status"] == "EXECUTED"
    assert p["next_blocker"] == DERIBIT_PHASE75_NEXT_BLOCKER


def test_phase75c_preserves_approved_operator_scope() -> None:
    r = audit_deribit_paper_runtime_heartbeat_execution_telemetry(_json(P74), _json(P73))
    p = r.artifact_payload
    assert p["approval_status"] == "APPROVED"
    assert p["operator_id"] == "demir_operator"
    assert p["approval_scope"] == "PAPER_ONLY_SIMULATION_ONLY"
