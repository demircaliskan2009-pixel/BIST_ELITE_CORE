from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_execution_post_audit import (
    audit_deribit_paper_runtime_heartbeat_execution_post_audit,
)

P75 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_TELEMETRY_AUDIT_75B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase76d_rejects_missing_phase75() -> None:
    r = audit_deribit_paper_runtime_heartbeat_execution_post_audit({})
    assert r.accepted is False
    assert any("phase75_artifact_missing" in rc for rc in r.rejection_reasons)


def test_phase76d_rejects_phase75_telemetry_status_drift() -> None:
    bad75 = _json(P75)
    bad75["heartbeat_execution_telemetry_status"] = "FAIL"
    r = audit_deribit_paper_runtime_heartbeat_execution_post_audit(bad75)
    assert r.accepted is False
    assert any("heartbeat_execution_telemetry_status_invalid" in rc for rc in r.rejection_reasons)


def test_phase76d_rejects_phase75_execution_status_drift() -> None:
    bad75 = _json(P75)
    bad75["heartbeat_execution_status"] = "NOT_EXECUTED"
    r = audit_deribit_paper_runtime_heartbeat_execution_post_audit(bad75)
    assert r.accepted is False
    assert any("heartbeat_execution_status_invalid" in rc for rc in r.rejection_reasons)


def test_phase76d_rejects_connector_count_drift() -> None:
    bad75 = _json(P75)
    bad75["connector_ready_dialects_count"] = 2
    r = audit_deribit_paper_runtime_heartbeat_execution_post_audit(bad75)
    assert r.accepted is False
    assert any("connector_ready_dialects_count_invalid" in rc for rc in r.rejection_reasons)