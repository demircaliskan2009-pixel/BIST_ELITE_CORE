from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat import record_deribit_paper_runtime_heartbeat

PHASE69 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_START_TELEMETRY_AUDIT_69B.json")
PHASE68 = Path("docs/crypto_core/DERIBIT_APPROVED_PAPER_RUNTIME_START_EXECUTION_68B.json")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_OPERATOR_TRIGGERED_HEARTBEAT_70B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact() -> dict[str, object]:
    return _json(ARTIFACT)


def test_phase70b_artifact_matches_runtime_output() -> None:
    runtime = record_deribit_paper_runtime_heartbeat(_json(PHASE69), _json(PHASE68)).artifact_payload

    assert _artifact() == runtime
    assert runtime["phase"] == "70"
    assert runtime["heartbeat_status"] == "RECORDED"
    assert runtime["heartbeat_trigger"] == "OPERATOR_MANUAL"
    assert runtime["next_blocker"] == "PAPER_RUNTIME_HEARTBEAT_TELEMETRY_NOT_READY"
