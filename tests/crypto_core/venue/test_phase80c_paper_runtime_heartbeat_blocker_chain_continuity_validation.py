from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_blocker_chain_continuity import (
    DERIBIT_PHASE79_BLOCKER_PERSISTENCE_SHA256,
    DERIBIT_PHASE80_NEXT_BLOCKER,
    audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity,
)

P79 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_BLOCKER_PERSISTENCE_79B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase80c_valid_phase79_artifact_accepted() -> None:
    r = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity(_json(P79))
    assert r.accepted is True
    assert r.rejection_reasons == ()
    assert r.artifact_payload["blocker_chain_continuity"] == "PASS"
    assert r.artifact_payload["b5_status"] == "BLOCKED"
    assert r.artifact_payload["connector_enablement_ready"] is False
    assert r.artifact_payload["next_blocker"] == DERIBIT_PHASE80_NEXT_BLOCKER


def test_phase80c_missing_artifact_rejected() -> None:
    r = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity(None)
    assert r.accepted is False
    assert any("phase79_artifact_missing" in reason for reason in r.rejection_reasons)
    assert r.artifact_payload["blocker_chain_continuity"] == "FAIL_CLOSED"


def test_phase80c_wrong_phase79_schema_rejected() -> None:
    bad = dict(_json(P79))
    bad["schema_version"] = "wrong.v1"
    r = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity(bad)
    assert r.accepted is False
    assert any("phase79_artifact_malformed" in reason for reason in r.rejection_reasons)


def test_phase80c_drift_in_phase79_sha256_rejected() -> None:
    bad = dict(_json(P79))
    bad["b5_status"] = "OPEN"  # mutate to trigger drift
    r = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity(bad)
    assert r.accepted is False
    assert any("phase79_blocker_persistence_drift" in reason for reason in r.rejection_reasons)


def test_phase80c_phase79_sha256_constant_is_correct() -> None:
    import hashlib

    art = _json(P79)
    canonical = json.dumps(art, sort_keys=True, separators=(",", ":"))
    actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert actual == DERIBIT_PHASE79_BLOCKER_PERSISTENCE_SHA256
