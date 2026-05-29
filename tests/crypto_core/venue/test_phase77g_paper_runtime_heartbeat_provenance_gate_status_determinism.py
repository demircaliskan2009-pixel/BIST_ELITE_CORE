from __future__ import annotations

import hashlib
import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_provenance_gate_status import (
    audit_deribit_paper_runtime_heartbeat_provenance_gate_status,
)

P76 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_POST_AUDIT_76B.json")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_STATUS_77B.json")
EXPECTED_SHA256 = "e1747b03ce6e966de84e8d165aac4be1f37c4cf06369688c8cf5a2aad09f62ed"


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_phase77g_helper_is_deterministic() -> None:
    r1 = audit_deribit_paper_runtime_heartbeat_provenance_gate_status(_json(P76))
    r2 = audit_deribit_paper_runtime_heartbeat_provenance_gate_status(_json(P76))
    assert r1 == r2


def test_phase77g_artifact_hash_is_stable() -> None:
    assert _canonical_sha256(_json(ARTIFACT)) == EXPECTED_SHA256
