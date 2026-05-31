from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_blocker_chain_continuity_104 import (
    DERIBIT_PHASE103_BLOCKER_CHAIN_CONTINUITY_SHA256,
    DERIBIT_PHASE104_NEXT_BLOCKER,
    audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_104,
)

P103 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_103B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase104c_valid_phase103_artifact_accepted() -> None:
    result = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_104(_json(P103))
    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert result.artifact_payload["blocker_chain_continuity"] == "PASS"
    assert result.artifact_payload["b5_status"] == "BLOCKED"
    assert result.artifact_payload["connector_enablement_ready"] is False
    assert result.artifact_payload["next_blocker"] == DERIBIT_PHASE104_NEXT_BLOCKER


def test_phase104c_missing_artifact_rejected() -> None:
    result = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_104(None)
    assert result.accepted is False
    assert any("phase103_artifact_missing" in reason for reason in result.rejection_reasons)
    assert result.artifact_payload["blocker_chain_continuity"] == "FAIL_CLOSED"


def test_phase104c_wrong_phase103_schema_rejected() -> None:
    bad = dict(_json(P103))
    bad["schema_version"] = "wrong.v1"
    result = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_104(bad)
    assert result.accepted is False
    assert any("phase103_artifact_malformed" in reason for reason in result.rejection_reasons)


def test_phase104c_drift_in_phase103_sha256_rejected() -> None:
    bad = dict(_json(P103))
    bad["b5_status"] = "OPEN"
    result = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_104(bad)
    assert result.accepted is False
    assert any("phase103_blocker_chain_continuity_drift" in reason for reason in result.rejection_reasons)


def test_phase104c_phase103_sha256_constant_is_correct() -> None:
    import hashlib

    art = _json(P103)
    canonical = json.dumps(art, sort_keys=True, separators=(",", ":"))
    actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert actual == DERIBIT_PHASE103_BLOCKER_CHAIN_CONTINUITY_SHA256
