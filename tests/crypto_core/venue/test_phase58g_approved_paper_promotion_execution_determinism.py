from __future__ import annotations

import json

from crypto_core.venue.deribit_approved_paper_promotion_execution import execute_deribit_approved_paper_promotion
from tests.crypto_core.venue.test_phase58b_approved_paper_promotion_execution_artifact import (
    _execution,
    _phase55_readiness,
    _phase57_approval,
)


def test_phase58g_runtime_output_is_deterministic() -> None:
    first = execute_deribit_approved_paper_promotion(_phase57_approval(), _phase55_readiness()).artifact_payload
    second = execute_deribit_approved_paper_promotion(_phase57_approval(), _phase55_readiness()).artifact_payload

    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_phase58g_committed_artifact_matches_deterministic_runtime_output() -> None:
    runtime = execute_deribit_approved_paper_promotion(_phase57_approval(), _phase55_readiness()).artifact_payload

    assert _execution() == runtime
