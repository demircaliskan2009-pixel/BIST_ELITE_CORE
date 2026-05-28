from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_execution_telemetry import (
    DERIBIT_PHASE73_HEARTBEAT_OPERATOR_APPROVAL_SHA256,
    DERIBIT_PHASE74_APPROVED_HEARTBEAT_EXECUTION_SHA256,
    audit_deribit_paper_runtime_heartbeat_execution_telemetry,
)

P74 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_74B.json")
P73 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_APPROVAL_73B.json")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_TELEMETRY_AUDIT_75B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase75f_preserves_source_provenance_chain() -> None:
    art = _json(ARTIFACT)
    assert (
        art["source_phase74_approved_heartbeat_execution_sha256"] == DERIBIT_PHASE74_APPROVED_HEARTBEAT_EXECUTION_SHA256
    )
    assert (
        art["source_phase73_heartbeat_operator_approval_sha256"] == DERIBIT_PHASE73_HEARTBEAT_OPERATOR_APPROVAL_SHA256
    )


def test_phase75f_rejects_phase74_source_chain_drift() -> None:
    bad74 = _json(P74)
    bad74["heartbeat_count"] = 2
    r = audit_deribit_paper_runtime_heartbeat_execution_telemetry(bad74, _json(P73))
    assert r.accepted is False
    assert any("phase74_provenance_drift" in rc for rc in r.rejection_reasons)


def test_phase75f_rejects_phase73_source_chain_drift() -> None:
    bad73 = _json(P73)
    bad73["heartbeat_count"] = 2
    r = audit_deribit_paper_runtime_heartbeat_execution_telemetry(_json(P74), bad73)
    assert r.accepted is False
    assert any("phase73_provenance_drift" in rc for rc in r.rejection_reasons)
