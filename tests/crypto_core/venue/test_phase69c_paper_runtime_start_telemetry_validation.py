from __future__ import annotations

from crypto_core.venue.deribit_paper_runtime_start_telemetry import (
    audit_deribit_paper_runtime_start_telemetry,
)
from tests.crypto_core.venue.test_phase69b_paper_runtime_start_telemetry_artifact import (
    _artifact,
    _phase65_execution,
    _phase67_approval,
    _phase68_execution,
)


def test_phase69c_phase68_source_validates_before_telemetry_audit() -> None:
    phase68 = _phase68_execution()

    assert phase68["runtime_start_execution_status"] == "EXECUTED"
    assert phase68["runtime_enabled"] is True
    assert phase68["runtime_started"] is True
    assert phase68["next_blocker"] == "PAPER_RUNTIME_START_TELEMETRY_NOT_READY"


def test_phase69c_phase67_phase65_provenance_validates_before_audit() -> None:
    phase67 = _phase67_approval()
    phase65 = _phase65_execution()

    assert phase67["approval_status"] == "APPROVED"
    assert phase67["runtime_start_approved"] is True
    assert phase65["runtime_enablement_execution_status"] == "EXECUTED"
    assert phase65["runtime_enabled"] is True


def test_phase69c_audit_accepts_and_emits_pass_artifact() -> None:
    result = audit_deribit_paper_runtime_start_telemetry(
        _phase68_execution(), _phase67_approval(), _phase65_execution()
    )
    artifact = _artifact()

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert artifact["runtime_start_telemetry_status"] == "PASS"
    assert artifact["runtime_loop_started"] is False
    assert artifact["runtime_order_routing_enabled"] is False
