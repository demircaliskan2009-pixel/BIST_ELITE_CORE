from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_blocker_chain_continuity_103 import (
    _FALSE_SCOPE,
    _TRUE_FLAGS,
    audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_103,
)

P102 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_102B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase103d_artifact_scope_flags_are_false() -> None:
    result = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_103(_json(P102))
    art = result.artifact_payload
    for field in _FALSE_SCOPE:
        assert art[field] is False, f"expected {field} to be False"


def test_phase103d_artifact_safety_flags_are_true() -> None:
    result = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_103(_json(P102))
    art = result.artifact_payload
    for field in _TRUE_FLAGS:
        assert art[field] is True, f"expected {field} to be True"


def test_phase103d_b5_remains_blocked() -> None:
    result = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_103(_json(P102))
    assert result.artifact_payload["b5_status"] == "BLOCKED"


def test_phase103d_connector_enablement_is_false() -> None:
    result = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_103(_json(P102))
    assert result.artifact_payload["connector_enablement_ready"] is False


def test_phase103d_connector_ready_dialects_count_is_one() -> None:
    result = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_103(_json(P102))
    assert result.artifact_payload["connector_ready_dialects_count"] == 1
