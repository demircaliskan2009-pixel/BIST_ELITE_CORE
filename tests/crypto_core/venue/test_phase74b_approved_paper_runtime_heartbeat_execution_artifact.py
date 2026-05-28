from __future__ import annotations

import hashlib
import json
from pathlib import Path

from crypto_core.venue.deribit_approved_paper_runtime_heartbeat_execution import (
    execute_deribit_approved_paper_runtime_heartbeat_execution,
)

ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_74B.json")
P73 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_APPROVAL_73B.json")
P72 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_REVIEW_PROPOSAL_72B.json")
P71 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_TELEMETRY_AUDIT_71B.json")
EXPECTED_SHA256 = "233a5e2ebba8c17d3341e1a38ccb0a6af28359a9339f648cdc4ea205bc75e05a"


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_phase74b_artifact_schema_and_phase() -> None:
    art = _json(ARTIFACT)
    assert art["schema_version"] == "deribit_approved_paper_runtime_heartbeat_execution.v1"
    assert art["phase"] == "74"


def test_phase74b_artifact_sha256_stable() -> None:
    art = _json(ARTIFACT)
    assert _canonical_sha256(art) == EXPECTED_SHA256


def test_phase74b_artifact_parity_with_helper() -> None:
    r = execute_deribit_approved_paper_runtime_heartbeat_execution(_json(P73), _json(P72), _json(P71))
    art = _json(ARTIFACT)
    for key in (
        "schema_version",
        "phase",
        "heartbeat_execution_status",
        "execution_mode",
        "approval_status",
        "operator_id",
        "approval_decision",
        "approval_scope",
        "next_blocker",
        "reason_code",
    ):
        assert r.artifact_payload[key] == art[key], f"mismatch on {key!r}"
