from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_blocker_chain_continuity_91 import (
    DERIBIT_PHASE90_BLOCKER_CHAIN_CONTINUITY_SHA256,
    DERIBIT_PHASE91_NEXT_BLOCKER,
    audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_91,
)

P90 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_90B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase91c_valid_phase90_artifact_accepted() -> None:
    r = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_91(_json(P90))
    assert r.accepted is True
    assert r.rejection_reasons == ()
    assert r.artifact_payload["blocker_chain_continuity"] == "PASS"
    assert r.artifact_payload["b5_status"] == "BLOCKED"
    assert r.artifact_payload["connector_enablement_ready"] is False
    assert r.artifact_payload["next_blocker"] == DERIBIT_PHASE91_NEXT_BLOCKER


def test_phase91c_missing_artifact_rejected() -> None:
    r = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_91(None)
    assert r.accepted is False
    assert any("phase90_artifact_missing" in reason for reason in r.rejection_reasons)
    assert r.artifact_payload["blocker_chain_continuity"] == "FAIL_CLOSED"


def test_phase91c_wrong_phase90_schema_rejected() -> None:
    bad = dict(_json(P90))
    bad["schema_version"] = "wrong.v1"
    r = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_91(bad)
    assert r.accepted is False
    assert any("phase90_artifact_malformed" in reason for reason in r.rejection_reasons)


def test_phase91c_drift_in_phase90_sha256_rejected() -> None:
    bad = dict(_json(P90))
    bad["b5_status"] = "OPEN"
    r = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_91(bad)
    assert r.accepted is False
    assert any("phase90_blocker_chain_continuity_drift" in reason for reason in r.rejection_reasons)


def test_phase91c_phase90_sha256_constant_is_correct() -> None:
    import hashlib

    art = _json(P90)
    canonical = json.dumps(art, sort_keys=True, separators=(",", ":"))
    actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert actual == DERIBIT_PHASE90_BLOCKER_CHAIN_CONTINUITY_SHA256
