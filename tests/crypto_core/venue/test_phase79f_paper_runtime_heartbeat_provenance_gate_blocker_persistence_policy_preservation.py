from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_provenance_gate_blocker_persistence import (
    DERIBIT_PHASE78_PROVENANCE_GATE_CONTINUITY_SHA256,
    audit_deribit_paper_runtime_heartbeat_provenance_gate_blocker_persistence,
)

P78 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_CONTINUITY_78B.json")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_BLOCKER_PERSISTENCE_79B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase79f_preserves_phase78_provenance_chain() -> None:
    art = _json(ARTIFACT)
    assert art["source_phase78_provenance_gate_continuity_sha256"] == DERIBIT_PHASE78_PROVENANCE_GATE_CONTINUITY_SHA256


def test_phase79f_rejects_phase78_source_chain_drift() -> None:
    bad78 = _json(P78)
    bad78["reason_code"] = "drift"
    r = audit_deribit_paper_runtime_heartbeat_provenance_gate_blocker_persistence(bad78)
    assert r.accepted is False
    assert any("phase78_provenance_drift" in rc for rc in r.rejection_reasons)


def test_phase79f_rejects_phase78_wrong_phase_id() -> None:
    bad78 = _json(P78)
    bad78["phase"] = "77"
    r = audit_deribit_paper_runtime_heartbeat_provenance_gate_blocker_persistence(bad78)
    assert r.accepted is False
    assert any("phase78_artifact_malformed" in rc or "phase78_provenance_drift" in rc for rc in r.rejection_reasons)
