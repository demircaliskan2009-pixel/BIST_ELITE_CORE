from __future__ import annotations

from crypto_core.venue.deribit_paper_runtime_start_proposal import propose_deribit_paper_runtime_start
from tests.crypto_core.venue.test_phase66b_paper_runtime_start_proposal_artifact import (
    FALSE_PROPOSAL_DISABLED_FIELDS,
    SAFETY_FLAGS,
    _phase64_approval,
    _phase65_execution,
    _proposal,
)


def test_phase66c_phase65_execution_validates_before_start_proposal() -> None:
    execution = _phase65_execution()

    assert execution["runtime_enablement_execution_status"] == "EXECUTED"
    assert execution["runtime_enabled"] is True
    assert execution["runtime_started"] is False
    assert execution["next_blocker"] == "PAPER_RUNTIME_START_PROPOSAL_NOT_READY"


def test_phase66c_phase64_approval_validates_before_start_proposal() -> None:
    approval = _phase64_approval()

    assert approval["approval_status"] == "APPROVED"
    assert approval["runtime_enablement_approved"] is True
    assert approval["runtime_enabled"] is False
    assert approval["runtime_started"] is False
    assert approval["next_blocker"] == "APPROVED_PAPER_RUNTIME_ENABLEMENT_EXECUTION_NOT_READY"


def test_phase66c_proposal_accepts_without_runtime_start_or_scope_widening() -> None:
    result = propose_deribit_paper_runtime_start(_phase65_execution(), _phase64_approval())
    artifact = _proposal()

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert artifact["proposal_status"] == "READY_FOR_OPERATOR_REVIEW"
    assert artifact["runtime_start_approved"] is False
    assert artifact["runtime_enabled"] is True
    assert artifact["runtime_started"] is False
    for field in FALSE_PROPOSAL_DISABLED_FIELDS:
        assert artifact[field] is False
    for field in SAFETY_FLAGS:
        assert artifact[field] is True
