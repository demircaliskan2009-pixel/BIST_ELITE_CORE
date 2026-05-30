from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat import record_deribit_paper_runtime_heartbeat

PHASE69 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_START_TELEMETRY_AUDIT_69B.json")
PHASE68 = Path("docs/crypto_core/DERIBIT_APPROVED_PAPER_RUNTIME_START_EXECUTION_68B.json")


def test_phase70c_validation_accepts_operator_triggered_heartbeat() -> None:
    result = record_deribit_paper_runtime_heartbeat(
        json.loads(PHASE69.read_text(encoding="utf-8")),
        json.loads(PHASE68.read_text(encoding="utf-8")),
    )

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert result.artifact_payload["heartbeat_status"] == "RECORDED"
