from __future__ import annotations

from crypto_core.venue.deribit_operator_runtime_enablement_approval import (
    execute_deribit_operator_runtime_enablement_approval,
)
from tests.crypto_core.venue.test_phase64b_runtime_enablement_approval_artifact import (
    APPROVAL_METADATA,
    _approval,
    _approval_rejection_reasons,
    _phase62_wiring,
    _phase63_proposal,
)


def test_phase64c_phase63_proposal_validates_before_approval() -> None:
    proposal = _phase63_proposal()

    assert proposal["proposal_status"] == "READY_FOR_OPERATOR_REVIEW"
    assert proposal["approval_status"] == "NOT_APPROVED"
    assert proposal["operator_metadata_required"] is True
    assert proposal["runtime_enablement_approved"] is False
    assert proposal["runtime_enabled"] is False
    assert proposal["runtime_started"] is False


def test_phase64c_phase62_wiring_validates_before_approval() -> None:
    wiring = _phase62_wiring()

    assert wiring["runtime_wiring_status"] == "WIRED"
    assert wiring["ready_for_paper_runtime"] is True
    assert wiring["runtime_enabled"] is False
    assert wiring["runtime_started"] is False


def test_phase64c_approval_validates_without_runtime_start() -> None:
    result = execute_deribit_operator_runtime_enablement_approval(
        _phase63_proposal(),
        _phase62_wiring(),
        reviewed_at_iso=APPROVAL_METADATA["reviewed_at_iso"],
    )
    approval = _approval()

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert _approval_rejection_reasons(_phase63_proposal(), _phase62_wiring(), approval) == ()
    assert approval["runtime_enablement_approved"] is True
    assert approval["runtime_enabled"] is False
    assert approval["runtime_started"] is False
