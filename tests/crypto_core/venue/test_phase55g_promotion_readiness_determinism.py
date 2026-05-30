from __future__ import annotations

import copy

from crypto_core.venue.deribit_paper_promotion_readiness import evaluate_deribit_paper_promotion_readiness
from tests.crypto_core.venue.test_phase55b_promotion_readiness_artifact import _phase54_audit


def test_phase55g_promotion_readiness_validation_is_deterministic() -> None:
    result_one = evaluate_deribit_paper_promotion_readiness(_phase54_audit())
    result_two = evaluate_deribit_paper_promotion_readiness(copy.deepcopy(_phase54_audit()))

    assert result_one.accepted is True
    assert result_one == result_two


def test_phase55g_readiness_payload_order_independent_for_json_roundtrip() -> None:
    result = evaluate_deribit_paper_promotion_readiness(_phase54_audit())
    reordered = dict(reversed(list(result.artifact_payload.items())))

    assert sorted(result.artifact_payload.items(), key=lambda item: item[0]) == sorted(
        reordered.items(), key=lambda item: item[0]
    )
