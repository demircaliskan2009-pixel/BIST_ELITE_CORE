from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_execution_post_audit import (
    DERIBIT_PHASE76_POST_AUDIT_NEXT_BLOCKER,
    audit_deribit_paper_runtime_heartbeat_execution_post_audit,
)

P75 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_TELEMETRY_AUDIT_75B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase76c_helper_accepts_valid_phase75_input() -> None:
    r = audit_deribit_paper_runtime_heartbeat_execution_post_audit(_json(P75))
    assert r.accepted is True
    assert r.reason_code == "deribit_paper_runtime_heartbeat_execution_post_audit:accepted"
    assert r.rejection_reasons == ()


def test_phase76c_post_audit_fields_are_set() -> None:
    r = audit_deribit_paper_runtime_heartbeat_execution_post_audit(_json(P75))
    p = r.artifact_payload
    assert p["heartbeat_execution_post_audit_status"] == "PASS"
    assert p["heartbeat_execution_telemetry_status"] == "PASS"
    assert p["heartbeat_execution_status"] == "EXECUTED"
    assert p["next_blocker"] == DERIBIT_PHASE76_POST_AUDIT_NEXT_BLOCKER


def test_phase76c_preserves_approved_operator_scope() -> None:
    r = audit_deribit_paper_runtime_heartbeat_execution_post_audit(_json(P75))
    p = r.artifact_payload
    assert p["approval_status"] == "APPROVED"
    assert p["operator_id"] == "demir_operator"
    assert p["approval_scope"] == "PAPER_ONLY_SIMULATION_ONLY"
