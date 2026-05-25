from __future__ import annotations

import copy

from crypto_core.venue.deribit_operator_promotion_review_proposal import propose_deribit_operator_promotion_review
from tests.crypto_core.venue.test_phase56b_operator_promotion_review_proposal_artifact import (
    _phase54_telemetry,
    _phase55_readiness,
    _proposal,
    _proposal_rejection_reasons,
)


def test_phase56g_proposal_validation_is_deterministic() -> None:
    proposal_one = propose_deribit_operator_promotion_review(
        _phase55_readiness(), _phase54_telemetry()
    ).artifact_payload
    proposal_two = propose_deribit_operator_promotion_review(
        copy.deepcopy(_phase55_readiness()),
        copy.deepcopy(_phase54_telemetry()),
    ).artifact_payload

    assert proposal_one == proposal_two
    assert proposal_one == _proposal()
    assert _proposal_rejection_reasons(_phase55_readiness(), _phase54_telemetry(), proposal_one) == (
        _proposal_rejection_reasons(_phase55_readiness(), _phase54_telemetry(), proposal_two)
    )


def test_phase56g_proposal_payload_order_independent_for_json_roundtrip() -> None:
    proposal = _proposal()
    reordered = dict(reversed(list(proposal.items())))

    assert sorted(proposal.items(), key=lambda item: item[0]) == sorted(reordered.items(), key=lambda item: item[0])


def test_phase56g_proposal_checks_are_copied_per_payload() -> None:
    mutated = propose_deribit_operator_promotion_review(_phase55_readiness(), _phase54_telemetry()).artifact_payload
    mutated["proposal_checks"].append("mutated-check")

    fresh = propose_deribit_operator_promotion_review(_phase55_readiness(), _phase54_telemetry()).artifact_payload

    assert fresh == _proposal()
    assert "mutated-check" not in fresh["proposal_checks"]
