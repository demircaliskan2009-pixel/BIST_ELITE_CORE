from __future__ import annotations

import copy
import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_telemetry import (
    audit_deribit_paper_runtime_heartbeat_telemetry,
)

PHASE70 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_OPERATOR_TRIGGERED_HEARTBEAT_70B.json")
PHASE69 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_START_TELEMETRY_AUDIT_69B.json")


def _j(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _m(payload: dict[str, object], **updates: object) -> dict[str, object]:
    nxt = copy.deepcopy(payload)
    nxt.update(updates)
    return nxt


def test_phase71d_missing_or_malformed_sources_fail_closed() -> None:
    assert audit_deribit_paper_runtime_heartbeat_telemetry(None, _j(PHASE69)).accepted is False
    assert audit_deribit_paper_runtime_heartbeat_telemetry(_j(PHASE70), None).accepted is False


def test_phase71d_runtime_scope_and_safety_drift_fail_closed() -> None:
    phase70 = _j(PHASE70)
    phase69 = _j(PHASE69)

    heartbeat_status = audit_deribit_paper_runtime_heartbeat_telemetry(
        _m(phase70, heartbeat_status="FAIL_CLOSED"),
        phase69,
    )
    assert heartbeat_status.accepted is False
    assert "deribit_paper_runtime_heartbeat_telemetry:heartbeat_status_invalid" in heartbeat_status.rejection_reasons

    heartbeat_mode = audit_deribit_paper_runtime_heartbeat_telemetry(
        _m(phase70, heartbeat_mode="WRONG_MODE"),
        phase69,
    )
    assert heartbeat_mode.accepted is False
    assert "deribit_paper_runtime_heartbeat_telemetry:heartbeat_mode_invalid" in heartbeat_mode.rejection_reasons

    loop_started = audit_deribit_paper_runtime_heartbeat_telemetry(
        _m(phase70, runtime_loop_started=True),
        phase69,
    )
    assert loop_started.accepted is False
    assert "deribit_paper_runtime_heartbeat_telemetry:runtime_loop_started_invalid" in loop_started.rejection_reasons

    no_live = audit_deribit_paper_runtime_heartbeat_telemetry(
        _m(phase70, no_live=False),
        phase69,
    )
    assert no_live.accepted is False
    assert "deribit_paper_runtime_heartbeat_telemetry:no_live_invalid" in no_live.rejection_reasons

    connector_count = audit_deribit_paper_runtime_heartbeat_telemetry(
        _m(phase70, connector_ready_dialects_count=2),
        phase69,
    )
    assert connector_count.accepted is False
    assert (
        "deribit_paper_runtime_heartbeat_telemetry:connector_ready_dialects_count_invalid"
        in connector_count.rejection_reasons
    )


def test_phase71d_phase70_or_phase69_provenance_drift_fail_closed() -> None:
    phase70 = _j(PHASE70)
    phase69 = _j(PHASE69)

    phase70_drift = audit_deribit_paper_runtime_heartbeat_telemetry(_m(phase70, source="drift"), phase69)
    assert phase70_drift.accepted is False
    assert "deribit_paper_runtime_heartbeat_telemetry:phase70_provenance_drift" in phase70_drift.rejection_reasons

    phase69_drift = audit_deribit_paper_runtime_heartbeat_telemetry(phase70, _m(phase69, source="drift"))
    assert phase69_drift.accepted is False
    assert "deribit_paper_runtime_heartbeat_telemetry:phase69_provenance_drift" in phase69_drift.rejection_reasons
