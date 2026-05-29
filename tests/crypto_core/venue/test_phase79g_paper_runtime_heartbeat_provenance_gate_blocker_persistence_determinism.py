from __future__ import annotations

import hashlib
import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_provenance_gate_blocker_persistence import (
    audit_deribit_paper_runtime_heartbeat_provenance_gate_blocker_persistence,
)

P78 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_CONTINUITY_78B.json")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_BLOCKER_PERSISTENCE_79B.json")
EXPECTED_SHA256 = "60aa85c41971d4d8d6b21562701d75b2538cf3ccf66ceb020b51de9d3ae57a41"


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_phase79g_helper_is_deterministic() -> None:
    r1 = audit_deribit_paper_runtime_heartbeat_provenance_gate_blocker_persistence(_json(P78))
    r2 = audit_deribit_paper_runtime_heartbeat_provenance_gate_blocker_persistence(_json(P78))
    assert r1 == r2


def test_phase79g_artifact_hash_is_stable() -> None:
    assert _canonical_sha256(_json(ARTIFACT)) == EXPECTED_SHA256
