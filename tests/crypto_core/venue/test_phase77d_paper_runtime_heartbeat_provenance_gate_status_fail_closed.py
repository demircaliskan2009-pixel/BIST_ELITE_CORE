from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_provenance_gate_status import (
    audit_deribit_paper_runtime_heartbeat_provenance_gate_status,
)

P76 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_POST_AUDIT_76B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase77d_rejects_missing_phase76() -> None:
    r = audit_deribit_paper_runtime_heartbeat_provenance_gate_status({})
    assert r.accepted is False
    assert any("phase76_artifact_missing" in rc for rc in r.rejection_reasons)


def test_phase77d_rejects_phase76_wrong_schema() -> None:
    bad76 = _json(P76)
    bad76["schema_version"] = "wrong.v0"
    r = audit_deribit_paper_runtime_heartbeat_provenance_gate_status(bad76)
    assert r.accepted is False
    assert any("phase76_artifact_malformed" in rc for rc in r.rejection_reasons)


def test_phase77d_rejects_phase76_post_audit_status_drift() -> None:
    bad76 = _json(P76)
    bad76["heartbeat_execution_post_audit_status"] = "FAIL"
    r = audit_deribit_paper_runtime_heartbeat_provenance_gate_status(bad76)
    assert r.accepted is False
    assert any("phase76_provenance_drift" in rc or "post_audit_status_invalid" in rc for rc in r.rejection_reasons)


def test_phase77d_rejects_connector_count_drift() -> None:
    bad76 = _json(P76)
    bad76["connector_ready_dialects_count"] = 2
    r = audit_deribit_paper_runtime_heartbeat_provenance_gate_status(bad76)
    assert r.accepted is False
    assert any("connector_ready_dialects_count_invalid" in rc for rc in r.rejection_reasons)
