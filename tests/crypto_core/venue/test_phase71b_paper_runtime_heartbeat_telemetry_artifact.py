from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_telemetry import (
    audit_deribit_paper_runtime_heartbeat_telemetry,
)

PHASE70 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_OPERATOR_TRIGGERED_HEARTBEAT_70B.json")
PHASE69 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_START_TELEMETRY_AUDIT_69B.json")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_TELEMETRY_AUDIT_71B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_phase71b_artifact_matches_runtime_output() -> None:
    runtime = audit_deribit_paper_runtime_heartbeat_telemetry(_json(PHASE70), _json(PHASE69)).artifact_payload

    assert _json(ARTIFACT) == runtime
    assert runtime["phase"] == "71"
    assert runtime["heartbeat_telemetry_status"] == "PASS"
    assert runtime["next_blocker"] == "PAPER_RUNTIME_HEARTBEAT_OPERATOR_REVIEW_NOT_READY"
