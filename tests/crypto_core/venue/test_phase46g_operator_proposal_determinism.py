from __future__ import annotations

import json

from tests.crypto_core.venue.test_phase46b_operator_proposal_artifact import (
    _phase44_report_pack,
    _phase45_evaluation,
    _proposal,
    _proposal_rejection_reasons,
)


def test_phase46g_proposal_validation_is_deterministic() -> None:
    evaluation = _phase45_evaluation()
    report_pack = _phase44_report_pack()
    proposal = _proposal()

    first = _proposal_rejection_reasons(evaluation, report_pack, proposal)
    second = _proposal_rejection_reasons(evaluation, report_pack, proposal)

    assert first == second == ()


def test_phase46g_proposal_json_round_trip_is_deterministic() -> None:
    proposal = _proposal()

    first = json.dumps(proposal, sort_keys=True, separators=(",", ":"))
    second = json.dumps(json.loads(first), sort_keys=True, separators=(",", ":"))

    assert first == second
