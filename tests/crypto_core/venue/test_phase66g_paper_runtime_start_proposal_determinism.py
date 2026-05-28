from __future__ import annotations

import copy

from crypto_core.venue.deribit_paper_runtime_start_proposal import propose_deribit_paper_runtime_start
from tests.crypto_core.venue.test_phase66b_paper_runtime_start_proposal_artifact import (
    _expected_proposal,
    _phase64_approval,
    _phase65_execution,
    _proposal,
)


def test_phase66g_runtime_output_is_deterministic() -> None:
    first = propose_deribit_paper_runtime_start(
        copy.deepcopy(_phase65_execution()),
        copy.deepcopy(_phase64_approval()),
    ).artifact_payload
    second = propose_deribit_paper_runtime_start(
        copy.deepcopy(_phase65_execution()),
        copy.deepcopy(_phase64_approval()),
    ).artifact_payload

    assert first == second == _expected_proposal()


def test_phase66g_checked_in_artifact_is_deterministic_snapshot() -> None:
    assert _proposal() == _expected_proposal()
