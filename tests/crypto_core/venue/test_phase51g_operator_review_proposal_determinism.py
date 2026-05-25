from __future__ import annotations

import copy

from tests.crypto_core.venue.test_phase51b_operator_review_proposal_artifact import (
    _phase50_evaluation,
    _proposal,
    _proposal_rejection_reasons,
)


def test_phase51g_proposal_validation_is_deterministic() -> None:
    proposal_one = _proposal()
    proposal_two = copy.deepcopy(_proposal())

    assert proposal_one == proposal_two
    assert _proposal_rejection_reasons(_phase50_evaluation(), proposal_one) == _proposal_rejection_reasons(
        _phase50_evaluation(), proposal_two
    )


def test_phase51g_proposal_payload_order_independent_for_json_roundtrip() -> None:
    proposal = _proposal()
    reordered = dict(reversed(list(proposal.items())))

    assert sorted(proposal.items(), key=lambda item: item[0]) == sorted(reordered.items(), key=lambda item: item[0])
