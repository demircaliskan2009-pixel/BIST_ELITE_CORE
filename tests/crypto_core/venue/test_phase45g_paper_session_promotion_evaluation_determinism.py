from __future__ import annotations

import json

from tests.crypto_core.venue.test_phase45b_paper_session_promotion_evaluation_artifact import (
    _evaluation,
    _evaluation_rejection_reasons,
    _promotion_readiness,
    _report_pack,
)


def test_phase45g_evaluation_validation_is_deterministic() -> None:
    promotion = _promotion_readiness()
    pack = _report_pack()
    evaluation = _evaluation()

    first = _evaluation_rejection_reasons(promotion, pack, evaluation)
    second = _evaluation_rejection_reasons(promotion, pack, evaluation)

    assert first == second == ()


def test_phase45g_evaluation_json_round_trip_is_deterministic() -> None:
    evaluation = _evaluation()

    first = json.dumps(evaluation, sort_keys=True, separators=(",", ":"))
    second = json.dumps(json.loads(first), sort_keys=True, separators=(",", ":"))

    assert first == second
