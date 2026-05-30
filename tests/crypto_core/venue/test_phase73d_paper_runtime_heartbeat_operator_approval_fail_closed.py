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


def _valid_result() -> object:
    return execute_deribit_paper_runtime_heartbeat_approval(
        _json(P72),
        _json(P71),
        operator_id=DERIBIT_PHASE73_OPERATOR_ID,
        approval_decision=DERIBIT_PHASE73_APPROVAL_DECISION,
        reviewed_at_iso=DERIBIT_PHASE73_REVIEWED_AT_ISO,
        approval_scope=DERIBIT_PHASE73_APPROVAL_SCOPE,
    )


def test_phase73d_rejects_missing_phase72() -> None:
    r = execute_deribit_paper_runtime_heartbeat_approval(
        {},
        _json(P71),
        operator_id=DERIBIT_PHASE73_OPERATOR_ID,
        approval_decision=DERIBIT_PHASE73_APPROVAL_DECISION,
        reviewed_at_iso=DERIBIT_PHASE73_REVIEWED_AT_ISO,
        approval_scope=DERIBIT_PHASE73_APPROVAL_SCOPE,
    )
    assert r.accepted is False
    assert any("phase72_artifact_missing" in rc for rc in r.rejection_reasons)


def test_phase73d_rejects_missing_phase71() -> None:
    r = execute_deribit_paper_runtime_heartbeat_approval(
        _json(P72),
        {},
        operator_id=DERIBIT_PHASE73_OPERATOR_ID,
        approval_decision=DERIBIT_PHASE73_APPROVAL_DECISION,
        reviewed_at_iso=DERIBIT_PHASE73_REVIEWED_AT_ISO,
        approval_scope=DERIBIT_PHASE73_APPROVAL_SCOPE,
    )
    assert r.accepted is False
    assert any("phase71_artifact_missing" in rc for rc in r.rejection_reasons)


def test_phase73d_rejects_phase72_preapproval_drift() -> None:
    bad = _json(P72)
    bad["approval_status"] = "APPROVED"
    r = execute_deribit_paper_runtime_heartbeat_approval(
        bad,
        _json(P71),
        operator_id=DERIBIT_PHASE73_OPERATOR_ID,
        approval_decision=DERIBIT_PHASE73_APPROVAL_DECISION,
        reviewed_at_iso=DERIBIT_PHASE73_REVIEWED_AT_ISO,
        approval_scope=DERIBIT_PHASE73_APPROVAL_SCOPE,
    )
    assert r.accepted is False
    assert any("phase72_approval_status_invalid" in rc for rc in r.rejection_reasons)


def test_phase73d_rejects_invalid_reviewed_at_iso() -> None:
    r = execute_deribit_paper_runtime_heartbeat_approval(
        _json(P72),
        _json(P71),
        operator_id=DERIBIT_PHASE73_OPERATOR_ID,
        approval_decision=DERIBIT_PHASE73_APPROVAL_DECISION,
        reviewed_at_iso="not-iso",
        approval_scope=DERIBIT_PHASE73_APPROVAL_SCOPE,
    )
    assert r.accepted is False
    assert any("reviewed_at_iso_invalid" in rc or "reviewed_at_iso_mismatch" in rc for rc in r.rejection_reasons)


def test_phase73d_valid_payload_keeps_no_live_scope_false_flags() -> None:
    r = _valid_result()
    assert r.artifact_payload["runtime_loop_started"] is False
    assert r.artifact_payload["runtime_order_routing_enabled"] is False
    assert r.artifact_payload["live_ready"] is False
    assert r.artifact_payload["shadow_ready"] is False
    assert r.artifact_payload["ledger_mutation"] is False
