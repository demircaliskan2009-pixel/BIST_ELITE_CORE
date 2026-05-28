from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import crypto_core.venue.deribit_paper_runtime_start_telemetry as telemetry_module
from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_paper_runtime_start_telemetry import (
    audit_deribit_paper_runtime_start_telemetry,
)
from tests.crypto_core.venue.test_phase69b_paper_runtime_start_telemetry_artifact import (
    _mutated,
    _phase65_execution,
    _phase67_approval,
    _phase68_execution,
)


def _run_with(phase68: object, phase67: object, phase65: object):
    return audit_deribit_paper_runtime_start_telemetry(phase68, phase67, phase65)


def test_phase69d_missing_or_malformed_sources_fail_closed() -> None:
    assert _run_with(None, _phase67_approval(), _phase65_execution()).rejection_reasons == (
        "deribit_paper_runtime_start_telemetry:phase68_artifact_missing",
    )
    assert (
        "deribit_paper_runtime_start_telemetry:phase67_artifact_missing"
        in _run_with(
            _phase68_execution(),
            None,
            _phase65_execution(),
        ).rejection_reasons
    )
    assert (
        "deribit_paper_runtime_start_telemetry:phase65_artifact_missing"
        in _run_with(
            _phase68_execution(),
            _phase67_approval(),
            None,
        ).rejection_reasons
    )


def test_phase69d_runtime_start_or_scope_drift_fails_closed() -> None:
    bad_status = _run_with(
        _mutated(_phase68_execution(), runtime_start_execution_status="FAIL_CLOSED"),
        _phase67_approval(),
        _phase65_execution(),
    )
    assert "deribit_paper_runtime_start_telemetry:phase68_metadata_invalid" in bad_status.rejection_reasons

    bad_safety = _run_with(
        _mutated(_phase68_execution(), no_live=False),
        _phase67_approval(),
        _phase65_execution(),
    )
    assert "deribit_paper_runtime_start_telemetry:phase68_safety_flags_invalid" in bad_safety.rejection_reasons

    bad_connector = _run_with(
        _mutated(_phase68_execution(), connector_ready_dialects_count=2),
        _phase67_approval(),
        _phase65_execution(),
    )
    assert (
        "deribit_paper_runtime_start_telemetry:phase68_connector_ready_dialects_invalid"
        in bad_connector.rejection_reasons
    )


def test_phase69d_runtime_loop_or_order_routing_enablement_is_rejected() -> None:
    loop_enabled = _run_with(
        _mutated(_phase68_execution(), runtime_loop_started=True),
        _phase67_approval(),
        _phase65_execution(),
    )
    assert "deribit_paper_runtime_start_telemetry:runtime_loop_started_true" in loop_enabled.rejection_reasons

    routing_enabled = _run_with(
        _mutated(_phase68_execution(), runtime_order_routing_enabled=True),
        _phase67_approval(),
        _phase65_execution(),
    )
    assert (
        "deribit_paper_runtime_start_telemetry:runtime_order_routing_enabled_true" in routing_enabled.rejection_reasons
    )


def test_phase69d_phase67_or_phase65_provenance_drift_fails_closed() -> None:
    drift67 = _run_with(
        _phase68_execution(),
        _mutated(_phase67_approval(), operator_id="other_operator"),
        _phase65_execution(),
    )
    assert "deribit_paper_runtime_start_telemetry:phase67_provenance_drift" in drift67.rejection_reasons

    drift65 = _run_with(
        _phase68_execution(),
        _phase67_approval(),
        _mutated(_phase65_execution(), operator_id="other_operator"),
    )
    assert "deribit_paper_runtime_start_telemetry:phase65_provenance_drift" in drift65.rejection_reasons


def test_phase69d_connector_ready_dialect_must_be_deribit_verified(monkeypatch) -> None:
    monkeypatch.setattr(
        telemetry_module,
        "connector_ready_dialects",
        lambda: (
            SimpleNamespace(
                venue_id=VenueId.BINANCE_USDM,
                dialect_id="binance_usdm:l2_orderbook:placeholder",
            ),
        ),
    )
    result = _run_with(_phase68_execution(), _phase67_approval(), _phase65_execution())

    assert "deribit_paper_runtime_start_telemetry:connector_ready_dialects_mismatch" in result.rejection_reasons


def test_phase69d_rejected_payload_forces_fail_closed_status() -> None:
    phase68 = deepcopy(_phase68_execution())
    phase68["runtime_start_execution_status"] = "FAIL_CLOSED"

    result = _run_with(phase68, _phase67_approval(), _phase65_execution())
    payload = result.artifact_payload

    assert result.accepted is False
    assert payload["runtime_start_telemetry_status"] == "FAIL_CLOSED"
    assert payload["source_phase68_runtime_start_execution_status"] == "FAIL_CLOSED"
    assert payload["runtime_enabled"] is False
    assert payload["runtime_started"] is False
    assert payload["runtime_mode"] == "FAIL_CLOSED"
    assert payload["next_blocker"] == "PAPER_RUNTIME_START_TELEMETRY_NOT_READY"
