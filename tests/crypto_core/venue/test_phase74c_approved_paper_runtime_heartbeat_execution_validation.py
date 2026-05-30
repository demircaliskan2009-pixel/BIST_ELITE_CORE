from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_approved_paper_runtime_heartbeat_execution import (
    DERIBIT_PHASE74_NEXT_BLOCKER,
    execute_deribit_approved_paper_runtime_heartbeat_execution,
)

P73 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_APPROVAL_73B.json")
P72 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_REVIEW_PROPOSAL_72B.json")
P71 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_TELEMETRY_AUDIT_71B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase74c_helper_accepts_valid_inputs() -> None:
    r = execute_deribit_approved_paper_runtime_heartbeat_execution(
        _json(P73),
        _json(P72),
        _json(P71),
    )
    assert r.accepted is True
    assert r.reason_code == "deribit_approved_paper_runtime_heartbeat_execution:accepted"
    assert r.rejection_reasons == ()


def test_phase74c_execution_fields_are_set() -> None:
    r = execute_deribit_approved_paper_runtime_heartbeat_execution(
        _json(P73),
        _json(P72),
        _json(P71),
    )
    assert r.artifact_payload["heartbeat_execution_status"] == "EXECUTED"
    assert r.artifact_payload["execution_mode"] == "APPROVED_PAPER_RUNTIME_HEARTBEAT_ONLY"
    assert r.artifact_payload["approval_status"] == "APPROVED"
    assert r.artifact_payload["next_blocker"] == DERIBIT_PHASE74_NEXT_BLOCKER


def test_phase74c_preserves_approved_operator_metadata() -> None:
    r = execute_deribit_approved_paper_runtime_heartbeat_execution(
        _json(P73),
        _json(P72),
        _json(P71),
    )
    p = r.artifact_payload
    assert p["operator_id"] == "demir_operator"
    assert p["approval_decision"] == "APPROVE_PAPER_RUNTIME_HEARTBEAT_REVIEW"
    assert p["approval_scope"] == "PAPER_ONLY_SIMULATION_ONLY"
