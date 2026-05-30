from __future__ import annotations

from crypto_core.venue.deribit_paper_runtime_enablement_proposal import propose_deribit_paper_runtime_enablement
from tests.crypto_core.venue.test_phase63b_runtime_enablement_proposal_artifact import (
    FALSE_RUNTIME_FIELDS,
    SAFETY_FLAGS,
    _phase62_wiring,
)


def test_phase63c_source_validates_before_runtime_enablement_proposal() -> None:
    phase62 = _phase62_wiring()

    assert phase62["runtime_wiring_status"] == "WIRED"
    assert phase62["ready_for_paper_runtime"] is True
    assert phase62["paper_promoted"] is True
    assert phase62["promotion_granted"] is True
    assert phase62["promotion_scope"] == "PAPER_ONLY_SIMULATION_ONLY"
    assert phase62["runtime_enabled"] is False
    assert phase62["runtime_started"] is False


def test_phase63c_runtime_enablement_proposal_accepts_without_approval_or_start() -> None:
    result = propose_deribit_paper_runtime_enablement(_phase62_wiring())
    artifact = result.artifact_payload

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert artifact["proposal_status"] == "READY_FOR_OPERATOR_REVIEW"
    assert artifact["approval_status"] == "NOT_APPROVED"
    for field in FALSE_RUNTIME_FIELDS:
        assert artifact[field] is False
    for field in SAFETY_FLAGS:
        assert artifact[field] is True
