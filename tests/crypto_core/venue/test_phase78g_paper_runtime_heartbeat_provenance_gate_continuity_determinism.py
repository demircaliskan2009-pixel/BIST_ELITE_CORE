from __future__ import annotations

import hashlib
import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_provenance_gate_continuity import (
    audit_deribit_paper_runtime_heartbeat_provenance_gate_continuity,
)

P77 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_STATUS_77B.json")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_PROVENANCE_GATE_CONTINUITY_78B.json")
EXPECTED_SHA256 = "1c3142ff8d37a122f97556862c3626cef579e5c20c06b00274131dbfce953d07"


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_phase78g_helper_is_deterministic() -> None:
    r1 = audit_deribit_paper_runtime_heartbeat_provenance_gate_continuity(_json(P77))
    r2 = audit_deribit_paper_runtime_heartbeat_provenance_gate_continuity(_json(P77))
    assert r1 == r2


def test_phase78g_artifact_hash_is_stable() -> None:
    assert _canonical_sha256(_json(ARTIFACT)) == EXPECTED_SHA256
