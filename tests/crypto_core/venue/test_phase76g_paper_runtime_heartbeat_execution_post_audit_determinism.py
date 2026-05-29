from __future__ import annotations

import hashlib
import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_execution_post_audit import (
    audit_deribit_paper_runtime_heartbeat_execution_post_audit,
)

P75 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_TELEMETRY_AUDIT_75B.json")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_EXECUTION_POST_AUDIT_76B.json")
EXPECTED_SHA256 = "3a227d33d72fbdda557ef6c7bc2f2e83f0550e19853acb07ebf439024d07d043"


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_phase76g_helper_is_deterministic() -> None:
    r1 = audit_deribit_paper_runtime_heartbeat_execution_post_audit(_json(P75))
    r2 = audit_deribit_paper_runtime_heartbeat_execution_post_audit(_json(P75))
    assert r1 == r2


def test_phase76g_artifact_hash_is_stable() -> None:
    assert _canonical_sha256(_json(ARTIFACT)) == EXPECTED_SHA256
