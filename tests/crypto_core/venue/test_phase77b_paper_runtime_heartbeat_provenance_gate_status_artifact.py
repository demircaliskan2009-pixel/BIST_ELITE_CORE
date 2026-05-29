from __future__ import annotations

import hashlib
import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_provenance_gate_status import (
    audit_deribit_paper_runtime_heartbeat_provenance_gate_status,
)

ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_STATUS_77B.json")
P76 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_POST_AUDIT_76B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_phase77b_artifact_schema_and_phase() -> None:
    art = _json(ARTIFACT)
    assert art["schema_version"] == "deribit_paper_runtime_heartbeat_provenance_gate_status.v1"
    assert art["phase"] == "77"


def test_phase77b_artifact_hash_matches_helper_output() -> None:
    art = _json(ARTIFACT)
    r = audit_deribit_paper_runtime_heartbeat_provenance_gate_status(_json(P76))
    assert _canonical_sha256(art) == _canonical_sha256(r.artifact_payload)


def test_phase77b_artifact_parity_with_helper() -> None:
    r = audit_deribit_paper_runtime_heartbeat_provenance_gate_status(_json(P76))
    art = _json(ARTIFACT)
    for key in (
        "schema_version",
        "phase",
        "heartbeat_execution_post_audit_status",
        "b5_status",
        "connector_enablement_ready",
        "provenance_reason",
        "next_blocker",
        "reason_code",
    ):
        assert r.artifact_payload[key] == art[key], f"mismatch on {key!r}"
