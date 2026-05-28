from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_execution_telemetry import (
    audit_deribit_paper_runtime_heartbeat_execution_telemetry,
)

P74 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_74B.json")
P73 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_APPROVAL_73B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase75d_rejects_missing_phase74() -> None:
    r = audit_deribit_paper_runtime_heartbeat_execution_telemetry({}, _json(P73))
    assert r.accepted is False
    assert any("phase74_artifact_missing" in rc for rc in r.rejection_reasons)


def test_phase75d_rejects_missing_phase73() -> None:
    r = audit_deribit_paper_runtime_heartbeat_execution_telemetry(_json(P74), {})
    assert r.accepted is False
    assert any("phase73_artifact_missing" in rc for rc in r.rejection_reasons)


def test_phase75d_rejects_phase74_execution_status_drift() -> None:
    bad74 = _json(P74)
    bad74["heartbeat_execution_status"] = "NOT_EXECUTED"
    r = audit_deribit_paper_runtime_heartbeat_execution_telemetry(bad74, _json(P73))
    assert r.accepted is False
    assert any("heartbeat_execution_status_invalid" in rc for rc in r.rejection_reasons)


def test_phase75d_rejects_connector_count_drift() -> None:
    bad74 = _json(P74)
    bad74["connector_ready_dialects_count"] = 2
    r = audit_deribit_paper_runtime_heartbeat_execution_telemetry(bad74, _json(P73))
    assert r.accepted is False
    assert any("connector_ready_dialects_count_invalid" in rc for rc in r.rejection_reasons)
