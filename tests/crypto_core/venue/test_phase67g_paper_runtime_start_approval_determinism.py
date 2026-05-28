from __future__ import annotations

import copy

from crypto_core.venue.deribit_paper_runtime_start_approval import (
    DERIBIT_PHASE67_REVIEWED_AT_ISO,
    execute_deribit_paper_runtime_start_approval,
)
from tests.crypto_core.venue.test_phase67b_paper_runtime_start_approval_artifact import (
    _approval,
    _expected_approval,
    _phase65_execution,
    _phase66_proposal,
)


def test_phase67g_runtime_output_is_deterministic() -> None:
    first = execute_deribit_paper_runtime_start_approval(
        copy.deepcopy(_phase66_proposal()),
        copy.deepcopy(_phase65_execution()),
        reviewed_at_iso=DERIBIT_PHASE67_REVIEWED_AT_ISO,
    ).artifact_payload
    second = execute_deribit_paper_runtime_start_approval(
        copy.deepcopy(_phase66_proposal()),
        copy.deepcopy(_phase65_execution()),
        reviewed_at_iso=DERIBIT_PHASE67_REVIEWED_AT_ISO,
    ).artifact_payload

    assert first == second == _expected_approval()


def test_phase67g_checked_in_artifact_is_deterministic_snapshot() -> None:
    assert _approval() == _expected_approval()
