from __future__ import annotations

from crypto_core.venue.deribit_approved_paper_runtime_start import execute_deribit_approved_paper_runtime_start
from tests.crypto_core.venue.test_phase68b_approved_paper_runtime_start_artifact import (
    FALSE_EXECUTION_DISABLED_FIELDS,
    SAFETY_FLAGS,
    _execution,
    _phase65_execution,
    _phase67_approval,
)


def test_phase68c_phase67_approval_validates_before_runtime_start_execution() -> None:
    approval = _phase67_approval()

    assert approval["approval_status"] == "APPROVED"
    assert approval["runtime_start_approved"] is True
    assert approval["runtime_enabled"] is True
    assert approval["runtime_started"] is False
    assert approval["next_blocker"] == "APPROVED_PAPER_RUNTIME_START_EXECUTION_NOT_READY"


def test_phase68c_phase65_execution_validates_before_runtime_start_execution() -> None:
    execution = _phase65_execution()

    assert execution["runtime_enablement_execution_status"] == "EXECUTED"
    assert execution["runtime_enabled"] is True
    assert execution["runtime_started"] is False
    assert execution["next_blocker"] == "PAPER_RUNTIME_START_PROPOSAL_NOT_READY"


def test_phase68c_execution_accepts_and_starts_runtime_without_scope_widening() -> None:
    result = execute_deribit_approved_paper_runtime_start(_phase67_approval(), _phase65_execution())
    artifact = _execution()

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert artifact["runtime_start_execution_status"] == "EXECUTED"
    assert artifact["runtime_enabled"] is True
    assert artifact["runtime_started"] is True
    for field in FALSE_EXECUTION_DISABLED_FIELDS:
        assert artifact[field] is False
    for field in SAFETY_FLAGS:
        assert artifact[field] is True
