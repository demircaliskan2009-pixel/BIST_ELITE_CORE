from __future__ import annotations

import json

from crypto_core.venue.deribit_paper_promoted_runtime_wiring import wire_deribit_paper_promoted_runtime
from tests.crypto_core.venue.test_phase62b_paper_promoted_runtime_wiring_artifact import (
    _phase61_readiness,
    _runtime_wiring,
)


def test_phase62g_runtime_output_is_deterministic() -> None:
    first = wire_deribit_paper_promoted_runtime(_phase61_readiness()).artifact_payload
    second = wire_deribit_paper_promoted_runtime(_phase61_readiness()).artifact_payload

    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_phase62g_committed_artifact_matches_deterministic_runtime_output() -> None:
    runtime = wire_deribit_paper_promoted_runtime(_phase61_readiness()).artifact_payload

    assert _runtime_wiring() == runtime
