from __future__ import annotations

from crypto_core.venue.deribit_approved_paper_runtime_enablement import (
    execute_deribit_approved_paper_runtime_enablement,
)
from tests.crypto_core.venue.test_phase65b_approved_paper_runtime_enablement_artifact import (
    FALSE_EXECUTION_DISABLED_FIELDS,
    SAFETY_FLAGS,
    _execution,
    _phase62_wiring,
    _phase64_approval,
)


def test_phase65c_phase64_approval_validates_before_execution() -> None:
    approval = _phase64_approval()

    assert approval["approval_status"] == "APPROVED"
    assert approval["runtime_enablement_approved"] is True
    assert approval["runtime_enabled"] is False
    assert approval["runtime_started"] is False
    assert approval["next_blocker"] == "APPROVED_PAPER_RUNTIME_ENABLEMENT_EXECUTION_NOT_READY"


def test_phase65c_phase62_wiring_validates_before_execution() -> None:
    wiring = _phase62_wiring()

    assert wiring["runtime_wiring_status"] == "WIRED"
    assert wiring["ready_for_paper_runtime"] is True
    assert wiring["runtime_enabled"] is False
    assert wiring["runtime_started"] is False


def test_phase65c_execution_accepts_without_runtime_start_or_scope_widening() -> None:
    result = execute_deribit_approved_paper_runtime_enablement(_phase64_approval(), _phase62_wiring())
    artifact = _execution()

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert artifact["runtime_enablement_execution_status"] == "EXECUTED"
    assert artifact["runtime_enabled"] is True
    assert artifact["runtime_started"] is False
    for field in FALSE_EXECUTION_DISABLED_FIELDS:
        assert artifact[field] is False
    for field in SAFETY_FLAGS:
        assert artifact[field] is True
