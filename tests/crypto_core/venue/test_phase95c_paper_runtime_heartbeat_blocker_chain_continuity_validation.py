from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_blocker_chain_continuity_95 import (
    DERIBIT_PHASE94_BLOCKER_CHAIN_CONTINUITY_SHA256,
    DERIBIT_PHASE95_NEXT_BLOCKER,
    audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_95,
)

P94 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_94B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase95c_valid_phase94_artifact_accepted() -> None:
    r = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_95(_json(P94))
    assert r.accepted is True
    assert r.rejection_reasons == ()
    assert r.artifact_payload["blocker_chain_continuity"] == "PASS"
    assert r.artifact_payload["b5_status"] == "BLOCKED"
    assert r.artifact_payload["connector_enablement_ready"] is False
    assert r.artifact_payload["next_blocker"] == DERIBIT_PHASE95_NEXT_BLOCKER


def test_phase95c_missing_artifact_rejected() -> None:
    r = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_95(None)
    assert r.accepted is False
    assert any("phase94_artifact_missing" in reason for reason in r.rejection_reasons)
    assert r.artifact_payload["blocker_chain_continuity"] == "FAIL_CLOSED"


def test_phase95c_wrong_phase94_schema_rejected() -> None:
    bad = dict(_json(P94))
    bad["schema_version"] = "wrong.v1"
    r = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_95(bad)
    assert r.accepted is False
    assert any("phase94_artifact_malformed" in reason for reason in r.rejection_reasons)


def test_phase95c_drift_in_phase94_sha256_rejected() -> None:
    bad = dict(_json(P94))
    bad["b5_status"] = "OPEN"
    r = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_95(bad)
    assert r.accepted is False
    assert any("phase94_blocker_chain_continuity_drift" in reason for reason in r.rejection_reasons)


def test_phase95c_phase94_sha256_constant_is_correct() -> None:
    import hashlib

    art = _json(P94)
    canonical = json.dumps(art, sort_keys=True, separators=(",", ":"))
    actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert actual == DERIBIT_PHASE94_BLOCKER_CHAIN_CONTINUITY_SHA256
