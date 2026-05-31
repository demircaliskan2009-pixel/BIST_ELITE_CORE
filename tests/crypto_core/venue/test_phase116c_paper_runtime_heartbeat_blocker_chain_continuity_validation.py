from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_blocker_chain_continuity_116 import (
    DERIBIT_PHASE115_BLOCKER_CHAIN_CONTINUITY_SHA256,
    DERIBIT_PHASE116_NEXT_BLOCKER,
    audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_116,
)

P115 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_115B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase116c_valid_phase115_artifact_accepted() -> None:
    result = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_116(_json(P115))
    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert result.artifact_payload["blocker_chain_continuity"] == "PASS"
    assert result.artifact_payload["b5_status"] == "BLOCKED"
    assert result.artifact_payload["connector_enablement_ready"] is False
    assert result.artifact_payload["next_blocker"] == DERIBIT_PHASE116_NEXT_BLOCKER


def test_phase116c_missing_artifact_rejected() -> None:
    result = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_116(None)
    assert result.accepted is False
    assert any("phase115_artifact_missing" in reason for reason in result.rejection_reasons)
    assert result.artifact_payload["blocker_chain_continuity"] == "FAIL_CLOSED"


def test_phase116c_wrong_phase115_schema_rejected() -> None:
    bad = dict(_json(P115))
    bad["schema_version"] = "wrong.v1"
    result = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_116(bad)
    assert result.accepted is False
    assert any("phase115_artifact_malformed" in reason for reason in result.rejection_reasons)


def test_phase116c_drift_in_phase115_sha256_rejected() -> None:
    bad = dict(_json(P115))
    bad["b5_status"] = "OPEN"
    result = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_116(bad)
    assert result.accepted is False
    assert any("phase115_blocker_chain_continuity_drift" in reason for reason in result.rejection_reasons)


def test_phase116c_phase115_sha256_constant_is_correct() -> None:
    import hashlib

    art = _json(P115)
    canonical = json.dumps(art, sort_keys=True, separators=(",", ":"))
    actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert actual == DERIBIT_PHASE115_BLOCKER_CHAIN_CONTINUITY_SHA256
