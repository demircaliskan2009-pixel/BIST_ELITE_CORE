from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_telemetry import audit_deribit_paper_runtime_heartbeat_telemetry

PHASE70 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_OPERATOR_TRIGGERED_HEARTBEAT_70B.json")
PHASE69 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_START_TELEMETRY_AUDIT_69B.json")


def test_phase71c_validation_accepts_runtime_heartbeat_telemetry() -> None:
    result = audit_deribit_paper_runtime_heartbeat_telemetry(
        json.loads(PHASE70.read_text(encoding="utf-8")),
        json.loads(PHASE69.read_text(encoding="utf-8")),
    )

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert result.artifact_payload["heartbeat_telemetry_status"] == "PASS"
