from __future__ import annotations

import copy
import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat import record_deribit_paper_runtime_heartbeat

PHASE69 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_START_TELEMETRY_AUDIT_69B.json")
PHASE68 = Path("docs/crypto_core/DERIBIT_APPROVED_PAPER_RUNTIME_START_EXECUTION_68B.json")


def _j(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _m(payload: dict[str, object], **updates: object) -> dict[str, object]:
    nxt = copy.deepcopy(payload)
    nxt.update(updates)
    return nxt


def test_phase70d_missing_or_malformed_sources_fail_closed() -> None:
    assert record_deribit_paper_runtime_heartbeat(None, _j(PHASE68)).accepted is False
    assert record_deribit_paper_runtime_heartbeat(_j(PHASE69), None).accepted is False


def test_phase70d_runtime_scope_and_safety_drift_fail_closed() -> None:
    phase69 = _j(PHASE69)
    phase68 = _j(PHASE68)

    runtime_enabled = record_deribit_paper_runtime_heartbeat(_m(phase69, runtime_enabled=False), phase68)
    assert runtime_enabled.accepted is False
    assert "deribit_paper_runtime_heartbeat:phase69_runtime_state_invalid" in runtime_enabled.rejection_reasons

    runtime_started = record_deribit_paper_runtime_heartbeat(_m(phase69, runtime_started=False), phase68)
    assert runtime_started.accepted is False
    assert "deribit_paper_runtime_heartbeat:phase69_runtime_state_invalid" in runtime_started.rejection_reasons

    loop_started = record_deribit_paper_runtime_heartbeat(_m(phase69, runtime_loop_started=True), phase68)
    assert loop_started.accepted is False
    assert "deribit_paper_runtime_heartbeat:runtime_loop_started_invalid" in loop_started.rejection_reasons

    order_routing = record_deribit_paper_runtime_heartbeat(_m(phase69, runtime_order_routing_enabled=True), phase68)
    assert order_routing.accepted is False
    assert "deribit_paper_runtime_heartbeat:runtime_order_routing_enabled_invalid" in order_routing.rejection_reasons

    live_ready = record_deribit_paper_runtime_heartbeat(_m(phase69, live_ready=True), phase68)
    assert live_ready.accepted is False
    assert "deribit_paper_runtime_heartbeat:live_ready_invalid" in live_ready.rejection_reasons

    no_live = record_deribit_paper_runtime_heartbeat(_m(phase69, no_live=False), phase68)
    assert no_live.accepted is False
    assert "deribit_paper_runtime_heartbeat:no_live_invalid" in no_live.rejection_reasons

    connector_count = record_deribit_paper_runtime_heartbeat(_m(phase69, connector_ready_dialects_count=2), phase68)
    assert connector_count.accepted is False
    assert "deribit_paper_runtime_heartbeat:connector_ready_dialects_count_invalid" in connector_count.rejection_reasons


def test_phase70d_phase69_or_phase68_provenance_drift_fail_closed() -> None:
    phase69 = _j(PHASE69)
    phase68 = _j(PHASE68)

    assert record_deribit_paper_runtime_heartbeat(_m(phase69, source="drift"), phase68).accepted is False
    assert record_deribit_paper_runtime_heartbeat(phase69, _m(phase68, source="drift")).accepted is False
