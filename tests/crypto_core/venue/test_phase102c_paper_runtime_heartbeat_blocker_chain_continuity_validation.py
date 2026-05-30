from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_blocker_chain_continuity_102 import (
    DERIBIT_PHASE101_BLOCKER_CHAIN_CONTINUITY_SHA256,
    DERIBIT_PHASE102_NEXT_BLOCKER,
    audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_102,
)

P101 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_101B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase102c_valid_phase101_artifact_accepted() -> None:
    r = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_102(_json(P101))
    assert r.accepted is True
    assert r.rejection_reasons == ()
    assert r.artifact_payload["blocker_chain_continuity"] == "PASS"
    assert r.artifact_payload["b5_status"] == "BLOCKED"
    assert r.artifact_payload["connector_enablement_ready"] is False
    assert r.artifact_payload["next_blocker"] == DERIBIT_PHASE102_NEXT_BLOCKER


def test_phase102c_missing_artifact_rejected() -> None:
    r = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_102(None)
    assert r.accepted is False
    assert any("phase101_artifact_missing" in reason for reason in r.rejection_reasons)
    assert r.artifact_payload["blocker_chain_continuity"] == "FAIL_CLOSED"


def test_phase102c_wrong_phase101_schema_rejected() -> None:
    bad = dict(_json(P101))
    bad["schema_version"] = "wrong.v1"
    r = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_102(bad)
    assert r.accepted is False
    assert any("phase101_artifact_malformed" in reason for reason in r.rejection_reasons)


def test_phase102c_drift_in_phase101_sha256_rejected() -> None:
    bad = dict(_json(P101))
    bad["b5_status"] = "OPEN"
    r = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_102(bad)
    assert r.accepted is False
    assert any("phase101_blocker_chain_continuity_drift" in reason for reason in r.rejection_reasons)


def test_phase102c_phase101_sha256_constant_is_correct() -> None:
    import hashlib

    art = _json(P101)
    canonical = json.dumps(art, sort_keys=True, separators=(",", ":"))
    actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert actual == DERIBIT_PHASE101_BLOCKER_CHAIN_CONTINUITY_SHA256
