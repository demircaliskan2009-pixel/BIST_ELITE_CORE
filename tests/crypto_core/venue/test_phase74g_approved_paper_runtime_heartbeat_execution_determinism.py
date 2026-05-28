from __future__ import annotations

import hashlib
import json
from pathlib import Path

from crypto_core.venue.deribit_approved_paper_runtime_heartbeat_execution import (
    execute_deribit_approved_paper_runtime_heartbeat_execution,
)

P73 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_APPROVAL_73B.json")
P72 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_REVIEW_PROPOSAL_72B.json")
P71 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_TELEMETRY_AUDIT_71B.json")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_74B.json")
EXPECTED_SHA256 = "233a5e2ebba8c17d3341e1a38ccb0a6af28359a9339f648cdc4ea205bc75e05a"


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_phase74g_helper_is_deterministic() -> None:
    r1 = execute_deribit_approved_paper_runtime_heartbeat_execution(_json(P73), _json(P72), _json(P71))
    r2 = execute_deribit_approved_paper_runtime_heartbeat_execution(_json(P73), _json(P72), _json(P71))
    assert r1 == r2


def test_phase74g_artifact_hash_is_stable() -> None:
    assert _canonical_sha256(_json(ARTIFACT)) == EXPECTED_SHA256
