from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_review_proposal import (
    DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT,
    evaluate_deribit_paper_runtime_heartbeat_review_proposal,
)

_FALSE_SCOPE = (
    "runtime_loop_started",
    "runtime_order_routing_enabled",
    "live_ready",
    "shadow_ready",
    "scheduler_enabled",
    "auto_loop_enabled",
    "live_enabled",
    "shadow_enabled",
    "campaign_execution",
    "session_execution",
    "run_execution",
    "ledger_mutation",
    "strategy_signal_generated",
    "order_intent_generated",
)


def _load_phase71() -> dict[str, object]:
    return json.loads(Path(DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT).read_text(encoding="utf-8"))


def test_phase72d_fail_closed_on_missing_phase71() -> None:
    r = evaluate_deribit_paper_runtime_heartbeat_review_proposal({})
    assert r.accepted is False
    assert any("phase71_artifact_missing" in rc for rc in r.rejection_reasons)


def test_phase72d_fail_closed_on_none_phase71() -> None:
    r = evaluate_deribit_paper_runtime_heartbeat_review_proposal(None)
    assert r.accepted is False
    assert any("phase71_artifact_missing" in rc for rc in r.rejection_reasons)


def test_phase72d_fail_closed_on_phase71_provenance_drift() -> None:
    bad = dict(_load_phase71())
    bad["heartbeat_sequence"] = 99
    r = evaluate_deribit_paper_runtime_heartbeat_review_proposal(bad)
    assert r.accepted is False
    assert any("phase71_provenance_drift" in rc for rc in r.rejection_reasons)


def test_phase72d_artifact_scope_flags_are_false() -> None:
    r = evaluate_deribit_paper_runtime_heartbeat_review_proposal(_load_phase71())
    for field in _FALSE_SCOPE:
        assert r.artifact_payload[field] is False, f"{field} must be False"


def test_phase72d_fail_closed_on_heartbeat_telemetry_not_pass() -> None:
    bad = dict(_load_phase71())
    bad["heartbeat_telemetry_status"] = "FAIL_CLOSED"
    r = evaluate_deribit_paper_runtime_heartbeat_review_proposal(bad)
    assert r.accepted is False
    assert any("provenance_drift" in rc or "heartbeat_telemetry_not_pass" in rc for rc in r.rejection_reasons)
