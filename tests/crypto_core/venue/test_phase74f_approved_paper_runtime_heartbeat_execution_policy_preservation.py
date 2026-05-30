from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_approved_paper_runtime_heartbeat_execution import (
    DERIBIT_PHASE73_HEARTBEAT_OPERATOR_APPROVAL_SHA256,
    execute_deribit_approved_paper_runtime_heartbeat_execution,
)
from crypto_core.venue.deribit_paper_runtime_heartbeat_approval import (
    DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT_SHA256,
    DERIBIT_PHASE72_HEARTBEAT_REVIEW_PROPOSAL_SHA256,
)

P73 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_APPROVAL_73B.json")
P72 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_REVIEW_PROPOSAL_72B.json")
P71 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_TELEMETRY_AUDIT_71B.json")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_74B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase74f_preserves_source_provenance_chain() -> None:
    art = _json(ARTIFACT)
    assert (
        art["source_phase73_heartbeat_operator_approval_sha256"] == DERIBIT_PHASE73_HEARTBEAT_OPERATOR_APPROVAL_SHA256
    )
    assert art["source_phase72_heartbeat_review_proposal_sha256"] == DERIBIT_PHASE72_HEARTBEAT_REVIEW_PROPOSAL_SHA256
    assert art["source_phase71_heartbeat_telemetry_sha256"] == DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT_SHA256


def test_phase74f_rejects_phase73_source_chain_drift() -> None:
    bad73 = _json(P73)
    bad73["heartbeat_count"] = 2
    r = execute_deribit_approved_paper_runtime_heartbeat_execution(bad73, _json(P72), _json(P71))
    assert r.accepted is False
    assert any("phase73_provenance_drift" in rc for rc in r.rejection_reasons)


def test_phase74f_rejects_phase72_source_chain_drift() -> None:
    bad72 = _json(P72)
    bad72["heartbeat_count"] = 2
    r = execute_deribit_approved_paper_runtime_heartbeat_execution(_json(P73), bad72, _json(P71))
    assert r.accepted is False
    assert any("phase72_provenance_drift" in rc for rc in r.rejection_reasons)
