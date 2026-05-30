from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_provenance_gate_continuity import (
    DERIBIT_PHASE77_PROVENANCE_GATE_STATUS_SHA256,
    audit_deribit_paper_runtime_heartbeat_provenance_gate_continuity,
)

P77 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_STATUS_77B.json")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_CONTINUITY_78B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase78f_preserves_phase77_provenance_chain() -> None:
    art = _json(ARTIFACT)
    assert art["source_phase77_provenance_gate_status_sha256"] == DERIBIT_PHASE77_PROVENANCE_GATE_STATUS_SHA256


def test_phase78f_rejects_phase77_source_chain_drift() -> None:
    bad77 = _json(P77)
    bad77["reason_code"] = "drift"
    r = audit_deribit_paper_runtime_heartbeat_provenance_gate_continuity(bad77)
    assert r.accepted is False
    assert any("phase77_provenance_drift" in rc for rc in r.rejection_reasons)


def test_phase78f_rejects_phase77_wrong_phase_id() -> None:
    bad77 = _json(P77)
    bad77["phase"] = "76"
    r = audit_deribit_paper_runtime_heartbeat_provenance_gate_continuity(bad77)
    assert r.accepted is False
    assert any("phase77_artifact_malformed" in rc or "phase77_provenance_drift" in rc for rc in r.rejection_reasons)
