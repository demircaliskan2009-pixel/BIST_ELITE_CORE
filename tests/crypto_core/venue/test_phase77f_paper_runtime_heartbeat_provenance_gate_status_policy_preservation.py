from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_provenance_gate_status import (
    DERIBIT_PHASE76_POST_AUDIT_SHA256,
    audit_deribit_paper_runtime_heartbeat_provenance_gate_status,
)

P76 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_POST_AUDIT_76B.json")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_STATUS_77B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase77f_preserves_phase76_provenance_chain() -> None:
    art = _json(ARTIFACT)
    assert art["source_phase76_post_audit_sha256"] == DERIBIT_PHASE76_POST_AUDIT_SHA256


def test_phase77f_rejects_phase76_source_chain_drift() -> None:
    bad76 = _json(P76)
    bad76["heartbeat_count"] = 999
    r = audit_deribit_paper_runtime_heartbeat_provenance_gate_status(bad76)
    assert r.accepted is False
    assert any("phase76_provenance_drift" in rc for rc in r.rejection_reasons)


def test_phase77f_rejects_phase76_wrong_phase_id() -> None:
    bad76 = _json(P76)
    bad76["phase"] = "75"
    r = audit_deribit_paper_runtime_heartbeat_provenance_gate_status(bad76)
    assert r.accepted is False
    assert any("phase76_artifact_malformed" in rc or "phase76_provenance_drift" in rc for rc in r.rejection_reasons)
