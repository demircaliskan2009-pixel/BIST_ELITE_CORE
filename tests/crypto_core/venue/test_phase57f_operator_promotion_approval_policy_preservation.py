from __future__ import annotations

from tests.crypto_core.venue.test_phase57b_operator_promotion_approval_artifact import (
    APPROVAL_METADATA,
    _approval,
    _phase55_readiness,
    _phase56_proposal,
)


def test_phase57f_approval_preserves_pre_execution_chain_and_next_blocker() -> None:
    phase56 = _phase56_proposal()
    phase55 = _phase55_readiness()
    approval = _approval()

    assert phase55["promotion_granted"] is False
    assert phase56["promotion_granted"] is False
    assert phase56["next_blocker"] == "OPERATOR_PROMOTION_APPROVAL_NOT_READY"
    assert approval["source_phase56_proposal_status"] == phase56["proposal_status"]
    assert approval["source_phase56_approval_status"] == phase56["approval_status"]
    assert approval["source_phase55_promotion_readiness_verdict"] == phase55["promotion_readiness_verdict"]
    assert approval["next_blocker"] == "APPROVED_PROMOTION_EXECUTION_NOT_READY"


def test_phase57f_merge_policy_violation_is_recorded_without_widening_scope() -> None:
    approval = _approval()
    scope = approval["approval_scope"]

    assert approval["merge_policy_note"] == APPROVAL_METADATA["merge_policy_note"]
    assert approval["promotion_granted"] is False
    assert approval["campaign_execution"] is False
    assert approval["ledger_mutated"] is False
    assert scope["no_private_api"] is True
    assert scope["no_shadow"] is True
    assert scope["no_live"] is True
