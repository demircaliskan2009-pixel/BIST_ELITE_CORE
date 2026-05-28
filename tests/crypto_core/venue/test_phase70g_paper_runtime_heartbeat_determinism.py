from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat import record_deribit_paper_runtime_heartbeat

PHASE69 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_START_TELEMETRY_AUDIT_69B.json")
PHASE68 = Path("docs/crypto_core/DERIBIT_APPROVED_PAPER_RUNTIME_START_EXECUTION_68B.json")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_OPERATOR_TRIGGERED_HEARTBEAT_70B.json")


def test_phase70g_runtime_output_is_deterministic_and_matches_artifact() -> None:
    phase69 = json.loads(PHASE69.read_text(encoding="utf-8"))
    phase68 = json.loads(PHASE68.read_text(encoding="utf-8"))

    first = record_deribit_paper_runtime_heartbeat(phase69, phase68).artifact_payload
    second = record_deribit_paper_runtime_heartbeat(phase69, phase68).artifact_payload

    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert json.loads(ARTIFACT.read_text(encoding="utf-8")) == first
