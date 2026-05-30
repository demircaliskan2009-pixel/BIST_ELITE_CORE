from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_approved_paper_runtime_heartbeat_execution import (
    execute_deribit_approved_paper_runtime_heartbeat_execution,
)

P73 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_APPROVAL_73B.json")
P72 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_REVIEW_PROPOSAL_72B.json")
P71 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_TELEMETRY_AUDIT_71B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase74d_rejects_missing_phase73() -> None:
    r = execute_deribit_approved_paper_runtime_heartbeat_execution({}, _json(P72), _json(P71))
    assert r.accepted is False
    assert any("phase73_artifact_missing" in rc for rc in r.rejection_reasons)


def test_phase74d_rejects_missing_phase72() -> None:
    r = execute_deribit_approved_paper_runtime_heartbeat_execution(_json(P73), {}, _json(P71))
    assert r.accepted is False
    assert any("phase72_artifact_missing" in rc for rc in r.rejection_reasons)


def test_phase74d_rejects_missing_phase71() -> None:
    r = execute_deribit_approved_paper_runtime_heartbeat_execution(_json(P73), _json(P72), {})
    assert r.accepted is False
    assert any("phase71_artifact_missing" in rc for rc in r.rejection_reasons)


def test_phase74d_rejects_approval_status_drift() -> None:
    bad73 = _json(P73)
    bad73["approval_status"] = "NOT_APPROVED"
    r = execute_deribit_approved_paper_runtime_heartbeat_execution(bad73, _json(P72), _json(P71))
    assert r.accepted is False
    assert any("approval_status_invalid" in rc for rc in r.rejection_reasons)


def test_phase74d_rejects_connector_count_drift() -> None:
    bad73 = _json(P73)
    bad73["connector_ready_dialects_count"] = 2
    r = execute_deribit_approved_paper_runtime_heartbeat_execution(bad73, _json(P72), _json(P71))
    assert r.accepted is False
    assert any("connector_ready_dialects_count_invalid" in rc for rc in r.rejection_reasons)
