from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_telemetry import (
    audit_deribit_paper_runtime_heartbeat_telemetry,
)

PHASE70 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_OPERATOR_TRIGGERED_HEARTBEAT_70B.json")
PHASE69 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_START_TELEMETRY_AUDIT_69B.json")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_TELEMETRY_AUDIT_71B.json")


def test_phase71g_runtime_output_is_deterministic_and_matches_artifact() -> None:
    phase70 = json.loads(PHASE70.read_text(encoding="utf-8"))
    phase69 = json.loads(PHASE69.read_text(encoding="utf-8"))

    first = audit_deribit_paper_runtime_heartbeat_telemetry(phase70, phase69).artifact_payload
    second = audit_deribit_paper_runtime_heartbeat_telemetry(phase70, phase69).artifact_payload

    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert json.loads(ARTIFACT.read_text(encoding="utf-8")) == first
