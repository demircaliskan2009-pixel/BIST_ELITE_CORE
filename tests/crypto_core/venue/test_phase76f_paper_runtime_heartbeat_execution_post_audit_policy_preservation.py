from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_execution_post_audit import (
    DERIBIT_PHASE75_HEARTBEAT_EXECUTION_TELEMETRY_SHA256,
    audit_deribit_paper_runtime_heartbeat_execution_post_audit,
)

P75 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_TELEMETRY_AUDIT_75B.json")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_POST_AUDIT_76B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase76f_preserves_phase75_provenance_chain() -> None:
    art = _json(ARTIFACT)
    assert art["source_phase75_heartbeat_execution_telemetry_audit_sha256"] == (
        DERIBIT_PHASE75_HEARTBEAT_EXECUTION_TELEMETRY_SHA256
    )


def test_phase76f_rejects_phase75_source_chain_drift() -> None:
    bad75 = _json(P75)
    bad75["heartbeat_count"] = 2
    r = audit_deribit_paper_runtime_heartbeat_execution_post_audit(bad75)
    assert r.accepted is False
    assert any("phase75_provenance_drift" in rc for rc in r.rejection_reasons)


def test_phase76f_rejects_phase74_source_chain_drift() -> None:
    bad75 = _json(P75)
    bad75["source_phase74_approved_heartbeat_execution"] = "docs/crypto_core/DRIFTED_74B.json"
    r = audit_deribit_paper_runtime_heartbeat_execution_post_audit(bad75)
    assert r.accepted is False
    assert any("phase74_provenance_drift" in rc for rc in r.rejection_reasons)