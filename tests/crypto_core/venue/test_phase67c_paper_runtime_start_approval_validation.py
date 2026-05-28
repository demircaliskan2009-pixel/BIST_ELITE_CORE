from __future__ import annotations

from crypto_core.venue.deribit_paper_runtime_start_approval import execute_deribit_paper_runtime_start_approval
from tests.crypto_core.venue.test_phase67b_paper_runtime_start_approval_artifact import (
    APPROVAL_METADATA,
    APPROVAL_SCOPE_TRUE_FIELDS,
    FALSE_APPROVAL_DISABLED_FIELDS,
    SAFETY_FLAGS,
    _approval,
    _phase65_execution,
    _phase66_proposal,
)


def test_phase67c_phase66_proposal_validates_before_approval() -> None:
    proposal = _phase66_proposal()

    assert proposal["proposal_status"] == "READY_FOR_OPERATOR_REVIEW"
    assert proposal["approval_status"] == "NOT_APPROVED"
    assert proposal["runtime_start_approved"] is False
    assert proposal["runtime_enabled"] is True
    assert proposal["runtime_started"] is False
    assert proposal["next_blocker"] == "OPERATOR_PAPER_RUNTIME_START_APPROVAL_NOT_READY"


def test_phase67c_phase65_execution_validates_before_approval() -> None:
    execution = _phase65_execution()

    assert execution["runtime_enablement_execution_status"] == "EXECUTED"
    assert execution["runtime_enabled"] is True
    assert execution["runtime_started"] is False
    assert execution["next_blocker"] == "PAPER_RUNTIME_START_PROPOSAL_NOT_READY"


def test_phase67c_approval_accepts_without_runtime_start_or_scope_widening() -> None:
    result = execute_deribit_paper_runtime_start_approval(
        _phase66_proposal(),
        _phase65_execution(),
        reviewed_at_iso=APPROVAL_METADATA["reviewed_at_iso"],
    )
    artifact = _approval()

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert artifact["approval_status"] == "APPROVED"
    assert artifact["runtime_start_approved"] is True
    assert artifact["runtime_enabled"] is True
    assert artifact["runtime_started"] is False
    for field in FALSE_APPROVAL_DISABLED_FIELDS:
        assert artifact[field] is False
    for field in SAFETY_FLAGS:
        assert artifact[field] is True
    for field in APPROVAL_SCOPE_TRUE_FIELDS:
        assert artifact["approval_scope"][field] is True
