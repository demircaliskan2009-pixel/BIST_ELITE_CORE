from __future__ import annotations

import copy

from crypto_core.venue.deribit_approved_paper_runtime_start import execute_deribit_approved_paper_runtime_start
from tests.crypto_core.venue.test_phase68b_approved_paper_runtime_start_artifact import (
    _execution,
    _expected_execution,
    _phase65_execution,
    _phase67_approval,
)


def test_phase68g_runtime_output_is_deterministic() -> None:
    first = execute_deribit_approved_paper_runtime_start(
        copy.deepcopy(_phase67_approval()),
        copy.deepcopy(_phase65_execution()),
    ).artifact_payload
    second = execute_deribit_approved_paper_runtime_start(
        copy.deepcopy(_phase67_approval()),
        copy.deepcopy(_phase65_execution()),
    ).artifact_payload

    assert first == second == _expected_execution()


def test_phase68g_checked_in_artifact_is_deterministic_snapshot() -> None:
    assert _execution() == _expected_execution()
