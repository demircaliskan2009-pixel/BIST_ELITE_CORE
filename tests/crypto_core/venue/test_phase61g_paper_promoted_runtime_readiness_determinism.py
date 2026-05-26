from __future__ import annotations

import copy

from crypto_core.venue.deribit_paper_promoted_runtime_readiness import (
    evaluate_deribit_paper_promoted_runtime_readiness,
)
from tests.crypto_core.venue.test_phase61b_paper_promoted_runtime_readiness_artifact import (
    _expected_runtime_readiness,
    _phase60_post_audit,
    _runtime_readiness,
)


def test_phase61g_runtime_output_is_deterministic() -> None:
    first = evaluate_deribit_paper_promoted_runtime_readiness(copy.deepcopy(_phase60_post_audit())).artifact_payload
    second = evaluate_deribit_paper_promoted_runtime_readiness(copy.deepcopy(_phase60_post_audit())).artifact_payload

    assert first == second == _expected_runtime_readiness()


def test_phase61g_checked_in_artifact_is_deterministic_snapshot() -> None:
    assert _runtime_readiness() == _expected_runtime_readiness()
