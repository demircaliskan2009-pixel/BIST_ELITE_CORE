from __future__ import annotations

import copy

from crypto_core.venue.deribit_campaign_performance_evaluation import evaluate_deribit_campaign_performance
from tests.crypto_core.venue.test_phase50b_campaign_performance_evaluation_artifact import (
    _artifact,
    _phase49_audit,
)


def test_phase50g_evaluation_output_is_deterministic() -> None:
    source_one = _phase49_audit()
    source_two = copy.deepcopy(_phase49_audit())

    result_one = evaluate_deribit_campaign_performance(source_one)
    result_two = evaluate_deribit_campaign_performance(source_two)

    assert result_one == result_two
    assert result_one.artifact_payload == _artifact()


def test_phase50g_artifact_payload_order_independent_for_json_roundtrip() -> None:
    artifact = _artifact()
    reordered = dict(reversed(list(artifact.items())))

    assert sorted(artifact.items(), key=lambda item: item[0]) == sorted(reordered.items(), key=lambda item: item[0])
