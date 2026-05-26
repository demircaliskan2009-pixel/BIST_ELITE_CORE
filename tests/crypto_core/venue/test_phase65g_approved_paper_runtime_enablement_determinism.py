from __future__ import annotations

import copy

from crypto_core.venue.deribit_approved_paper_runtime_enablement import (
    execute_deribit_approved_paper_runtime_enablement,
)
from tests.crypto_core.venue.test_phase65b_approved_paper_runtime_enablement_artifact import (
    _execution,
    _expected_execution,
    _phase62_wiring,
    _phase64_approval,
)


def test_phase65g_runtime_output_is_deterministic() -> None:
    first = execute_deribit_approved_paper_runtime_enablement(
        copy.deepcopy(_phase64_approval()),
        copy.deepcopy(_phase62_wiring()),
    ).artifact_payload
    second = execute_deribit_approved_paper_runtime_enablement(
        copy.deepcopy(_phase64_approval()),
        copy.deepcopy(_phase62_wiring()),
    ).artifact_payload

    assert first == second == _expected_execution()


def test_phase65g_checked_in_artifact_is_deterministic_snapshot() -> None:
    assert _execution() == _expected_execution()
