from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_blocker_chain_continuity_103 import (
    DERIBIT_PHASE102_BLOCKER_CHAIN_CONTINUITY_SHA256,
    DERIBIT_PHASE103_NEXT_BLOCKER,
    audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_103,
)

P102 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_102B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase103c_valid_phase102_artifact_accepted() -> None:
    result = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_103(_json(P102))
    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert result.artifact_payload["blocker_chain_continuity"] == "PASS"
    assert result.artifact_payload["b5_status"] == "BLOCKED"
    assert result.artifact_payload["connector_enablement_ready"] is False
    assert result.artifact_payload["next_blocker"] == DERIBIT_PHASE103_NEXT_BLOCKER


def test_phase103c_missing_artifact_rejected() -> None:
    result = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_103(None)
    assert result.accepted is False
    assert any("phase102_artifact_missing" in reason for reason in result.rejection_reasons)
    assert result.artifact_payload["blocker_chain_continuity"] == "FAIL_CLOSED"


def test_phase103c_wrong_phase102_schema_rejected() -> None:
    bad = dict(_json(P102))
    bad["schema_version"] = "wrong.v1"
    result = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_103(bad)
    assert result.accepted is False
    assert any("phase102_artifact_malformed" in reason for reason in result.rejection_reasons)


def test_phase103c_drift_in_phase102_sha256_rejected() -> None:
    bad = dict(_json(P102))
    bad["b5_status"] = "OPEN"
    result = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_103(bad)
    assert result.accepted is False
    assert any("phase102_blocker_chain_continuity_drift" in reason for reason in result.rejection_reasons)


def test_phase103c_phase102_sha256_constant_is_correct() -> None:
    import hashlib

    art = _json(P102)
    canonical = json.dumps(art, sort_keys=True, separators=(",", ":"))
    actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert actual == DERIBIT_PHASE102_BLOCKER_CHAIN_CONTINUITY_SHA256
