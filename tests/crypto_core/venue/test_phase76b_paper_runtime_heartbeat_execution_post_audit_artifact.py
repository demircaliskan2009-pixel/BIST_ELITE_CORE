from __future__ import annotations

import hashlib
import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_execution_post_audit import (
    audit_deribit_paper_runtime_heartbeat_execution_post_audit,
)

ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_POST_AUDIT_76B.json")
P75 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_TELEMETRY_AUDIT_75B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_phase76b_artifact_schema_and_phase() -> None:
    art = _json(ARTIFACT)
    assert art["schema_version"] == "deribit_paper_runtime_heartbeat_execution_post_audit.v1"
    assert art["phase"] == "76"


def test_phase76b_artifact_hash_matches_helper_output() -> None:
    art = _json(ARTIFACT)
    r = audit_deribit_paper_runtime_heartbeat_execution_post_audit(_json(P75))
    assert _canonical_sha256(art) == _canonical_sha256(r.artifact_payload)


def test_phase76b_artifact_parity_with_helper() -> None:
    r = audit_deribit_paper_runtime_heartbeat_execution_post_audit(_json(P75))
    art = _json(ARTIFACT)
    for key in (
        "schema_version",
        "phase",
        "heartbeat_execution_post_audit_status",
        "heartbeat_execution_telemetry_status",
        "heartbeat_execution_status",
        "execution_mode",
        "approval_status",
        "operator_id",
        "approval_scope",
        "next_blocker",
        "reason_code",
    ):
        assert r.artifact_payload[key] == art[key], f"mismatch on {key!r}"
