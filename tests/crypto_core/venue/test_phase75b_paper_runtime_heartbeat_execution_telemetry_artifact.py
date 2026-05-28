from __future__ import annotations

import hashlib
import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_execution_telemetry import (
    audit_deribit_paper_runtime_heartbeat_execution_telemetry,
)

ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_TELEMETRY_AUDIT_75B.json")
P74 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_74B.json")
P73 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_APPROVAL_73B.json")
EXPECTED_SHA256 = "9135d10a57a169886fc35db9542c000579bcab42b60740be26eb6681a389c327"


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_phase75b_artifact_schema_and_phase() -> None:
    art = _json(ARTIFACT)
    assert art["schema_version"] == "deribit_paper_runtime_heartbeat_execution_telemetry_audit.v1"
    assert art["phase"] == "75"


def test_phase75b_artifact_sha256_stable() -> None:
    art = _json(ARTIFACT)
    assert _canonical_sha256(art) == EXPECTED_SHA256


def test_phase75b_artifact_parity_with_helper() -> None:
    r = audit_deribit_paper_runtime_heartbeat_execution_telemetry(_json(P74), _json(P73))
    art = _json(ARTIFACT)
    for key in (
        "schema_version",
        "phase",
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
