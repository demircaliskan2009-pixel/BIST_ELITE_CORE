from __future__ import annotations

import copy

from tests.crypto_core.venue.test_phase52b_operator_approval_artifact import (
    _approval,
    _approval_rejection_reasons,
    _phase49_audit,
    _phase50_evaluation,
    _phase51_proposal,
)


def test_phase52g_approval_validation_is_deterministic() -> None:
    approval_one = _approval()
    approval_two = copy.deepcopy(_approval())

    assert approval_one == approval_two
    assert _approval_rejection_reasons(
        _phase51_proposal(), _phase50_evaluation(), _phase49_audit(), approval_one
    ) == _approval_rejection_reasons(_phase51_proposal(), _phase50_evaluation(), _phase49_audit(), approval_two)


def test_phase52g_approval_payload_order_independent_for_json_roundtrip() -> None:
    approval = _approval()
    reordered = dict(reversed(list(approval.items())))

    assert sorted(approval.items(), key=lambda item: item[0]) == sorted(reordered.items(), key=lambda item: item[0])
