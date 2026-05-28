from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_approval import (
    DERIBIT_PHASE73_APPROVAL_DECISION,
    DERIBIT_PHASE73_APPROVAL_SCOPE,
    DERIBIT_PHASE73_OPERATOR_ID,
    DERIBIT_PHASE73_REVIEWED_AT_ISO,
    execute_deribit_paper_runtime_heartbeat_approval,
)

P72 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_REVIEW_PROPOSAL_72B.json")
P71 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_TELEMETRY_AUDIT_71B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase73c_helper_accepts_valid_inputs() -> None:
    r = execute_deribit_paper_runtime_heartbeat_approval(
        _json(P72),
        _json(P71),
        operator_id=DERIBIT_PHASE73_OPERATOR_ID,
        approval_decision=DERIBIT_PHASE73_APPROVAL_DECISION,
        reviewed_at_iso=DERIBIT_PHASE73_REVIEWED_AT_ISO,
        approval_scope=DERIBIT_PHASE73_APPROVAL_SCOPE,
    )
    assert r.accepted is True
    assert r.reason_code == "deribit_paper_runtime_heartbeat_approval:accepted"
    assert r.rejection_reasons == ()


def test_phase73c_approval_fields_are_set() -> None:
    r = execute_deribit_paper_runtime_heartbeat_approval(
        _json(P72),
        _json(P71),
        operator_id=DERIBIT_PHASE73_OPERATOR_ID,
        approval_decision=DERIBIT_PHASE73_APPROVAL_DECISION,
        reviewed_at_iso=DERIBIT_PHASE73_REVIEWED_AT_ISO,
        approval_scope=DERIBIT_PHASE73_APPROVAL_SCOPE,
    )
    assert r.artifact_payload["approval_status"] == "APPROVED"
    assert r.artifact_payload["operator_metadata_required"] is False
    assert r.artifact_payload["operator_id"] == DERIBIT_PHASE73_OPERATOR_ID
    assert r.artifact_payload["reviewed_at_iso"] == DERIBIT_PHASE73_REVIEWED_AT_ISO
    assert r.artifact_payload["approval_decision"] == DERIBIT_PHASE73_APPROVAL_DECISION


def test_phase73c_rejects_wrong_operator_id() -> None:
    r = execute_deribit_paper_runtime_heartbeat_approval(
        _json(P72),
        _json(P71),
        operator_id="wrong_operator",
        approval_decision=DERIBIT_PHASE73_APPROVAL_DECISION,
        reviewed_at_iso=DERIBIT_PHASE73_REVIEWED_AT_ISO,
        approval_scope=DERIBIT_PHASE73_APPROVAL_SCOPE,
    )
    assert r.accepted is False
    assert any("operator_id_mismatch" in rc for rc in r.rejection_reasons)


def test_phase73c_rejects_wrong_approval_decision() -> None:
    r = execute_deribit_paper_runtime_heartbeat_approval(
        _json(P72),
        _json(P71),
        operator_id=DERIBIT_PHASE73_OPERATOR_ID,
        approval_decision="APPROVE_SOMETHING_ELSE",
        reviewed_at_iso=DERIBIT_PHASE73_REVIEWED_AT_ISO,
        approval_scope=DERIBIT_PHASE73_APPROVAL_SCOPE,
    )
    assert r.accepted is False
    assert any("approval_decision_mismatch" in rc for rc in r.rejection_reasons)
