from __future__ import annotations

import hashlib
import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_execution_telemetry import (
    audit_deribit_paper_runtime_heartbeat_execution_telemetry,
)

P74 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_74B.json")
P73 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_APPROVAL_73B.json")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_TELEMETRY_AUDIT_75B.json")
EXPECTED_SHA256 = "9135d10a57a169886fc35db9542c000579bcab42b60740be26eb6681a389c327"


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_phase75g_helper_is_deterministic() -> None:
    r1 = audit_deribit_paper_runtime_heartbeat_execution_telemetry(_json(P74), _json(P73))
    r2 = audit_deribit_paper_runtime_heartbeat_execution_telemetry(_json(P74), _json(P73))
    assert r1 == r2


def test_phase75g_artifact_hash_is_stable() -> None:
    assert _canonical_sha256(_json(ARTIFACT)) == EXPECTED_SHA256
