from __future__ import annotations

import hashlib
import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_blocker_chain_continuity_103 import (
    audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_103,
)

ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_103B.json")
P102 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_BLOCKER_CHAIN_CONTINUITY_102B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_phase103b_artifact_schema_and_phase() -> None:
    art = _json(ARTIFACT)
    assert art["schema_version"] == "deribit_paper_runtime_heartbeat_blocker_chain_continuity.v1"
    assert art["phase"] == "103"


def test_phase103b_artifact_hash_matches_helper_output() -> None:
    art = _json(ARTIFACT)
    result = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_103(_json(P102))
    assert _canonical_sha256(art) == _canonical_sha256(result.artifact_payload)


def test_phase103b_artifact_parity_with_helper() -> None:
    result = audit_deribit_paper_runtime_heartbeat_blocker_chain_continuity_103(_json(P102))
    art = _json(ARTIFACT)
    for key in (
        "schema_version",
        "phase",
        "blocker_chain_continuity",
        "b5_status",
        "connector_enablement_ready",
        "provenance_reason",
        "next_blocker",
        "reason_code",
    ):
        assert result.artifact_payload[key] == art[key], f"mismatch on {key!r}"
