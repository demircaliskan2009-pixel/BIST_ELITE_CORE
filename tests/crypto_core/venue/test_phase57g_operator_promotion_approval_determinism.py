from __future__ import annotations

import copy

from crypto_core.venue.deribit_operator_promotion_approval import (
    DERIBIT_PHASE57_MERGE_POLICY_NOTE,
    execute_deribit_operator_promotion_approval,
)
from tests.crypto_core.venue.test_phase57b_operator_promotion_approval_artifact import (
    APPROVAL_METADATA,
    _approval,
    _approval_rejection_reasons,
    _phase55_readiness,
    _phase56_proposal,
)


def test_phase57g_approval_validation_is_deterministic() -> None:
    approval_one = execute_deribit_operator_promotion_approval(
        _phase56_proposal(),
        _phase55_readiness(),
        reviewed_at_iso=APPROVAL_METADATA["reviewed_at_iso"],
        merge_policy_note=DERIBIT_PHASE57_MERGE_POLICY_NOTE,
    ).artifact_payload
    approval_two = execute_deribit_operator_promotion_approval(
        copy.deepcopy(_phase56_proposal()),
        copy.deepcopy(_phase55_readiness()),
        reviewed_at_iso=APPROVAL_METADATA["reviewed_at_iso"],
        merge_policy_note=DERIBIT_PHASE57_MERGE_POLICY_NOTE,
    ).artifact_payload

    assert approval_one == approval_two
    assert approval_one == _approval()
    assert _approval_rejection_reasons(_phase56_proposal(), _phase55_readiness(), approval_one) == (
        _approval_rejection_reasons(_phase56_proposal(), _phase55_readiness(), approval_two)
    )


def test_phase57g_approval_payload_order_independent_for_json_roundtrip() -> None:
    approval = _approval()
    reordered = dict(reversed(list(approval.items())))

    assert sorted(approval.items(), key=lambda item: item[0]) == sorted(reordered.items(), key=lambda item: item[0])


def test_phase57g_approval_checks_are_copied_per_payload() -> None:
    mutated = execute_deribit_operator_promotion_approval(
        _phase56_proposal(),
        _phase55_readiness(),
        reviewed_at_iso=APPROVAL_METADATA["reviewed_at_iso"],
        merge_policy_note=DERIBIT_PHASE57_MERGE_POLICY_NOTE,
    ).artifact_payload
    mutated["approval_checks"].append("mutated-check")

    fresh = execute_deribit_operator_promotion_approval(
        _phase56_proposal(),
        _phase55_readiness(),
        reviewed_at_iso=APPROVAL_METADATA["reviewed_at_iso"],
        merge_policy_note=DERIBIT_PHASE57_MERGE_POLICY_NOTE,
    ).artifact_payload

    assert fresh == _approval()
    assert "mutated-check" not in fresh["approval_checks"]


def test_phase57g_approval_scope_is_copied_per_payload() -> None:
    mutated = execute_deribit_operator_promotion_approval(
        _phase56_proposal(),
        _phase55_readiness(),
        reviewed_at_iso=APPROVAL_METADATA["reviewed_at_iso"],
        merge_policy_note=DERIBIT_PHASE57_MERGE_POLICY_NOTE,
    ).artifact_payload
    mutated["approval_scope"]["paper_only"] = False

    fresh = execute_deribit_operator_promotion_approval(
        _phase56_proposal(),
        _phase55_readiness(),
        reviewed_at_iso=APPROVAL_METADATA["reviewed_at_iso"],
        merge_policy_note=DERIBIT_PHASE57_MERGE_POLICY_NOTE,
    ).artifact_payload

    assert fresh == _approval()
    assert fresh["approval_scope"]["paper_only"] is True
