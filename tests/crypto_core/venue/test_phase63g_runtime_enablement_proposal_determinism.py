from __future__ import annotations

import json

from crypto_core.venue.deribit_paper_runtime_enablement_proposal import propose_deribit_paper_runtime_enablement
from tests.crypto_core.venue.test_phase63b_runtime_enablement_proposal_artifact import _phase62_wiring, _proposal


def test_phase63g_runtime_output_is_deterministic() -> None:
    first = propose_deribit_paper_runtime_enablement(_phase62_wiring()).artifact_payload
    second = propose_deribit_paper_runtime_enablement(_phase62_wiring()).artifact_payload

    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_phase63g_committed_artifact_matches_deterministic_runtime_output() -> None:
    runtime = propose_deribit_paper_runtime_enablement(_phase62_wiring()).artifact_payload

    assert _proposal() == runtime
