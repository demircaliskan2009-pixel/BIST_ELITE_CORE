from __future__ import annotations

from crypto_core.venue.deribit_operator_runtime_enablement_approval import (
    execute_deribit_operator_runtime_enablement_approval,
)
from tests.crypto_core.venue.test_phase64b_runtime_enablement_approval_artifact import (
    APPROVAL_METADATA,
    _approval,
    _phase62_wiring,
    _phase63_proposal,
)


def test_phase64g_approval_output_is_deterministic_for_fixed_sources_and_timestamp() -> None:
    first = execute_deribit_operator_runtime_enablement_approval(
        _phase63_proposal(),
        _phase62_wiring(),
        reviewed_at_iso=APPROVAL_METADATA["reviewed_at_iso"],
    ).artifact_payload
    second = execute_deribit_operator_runtime_enablement_approval(
        _phase63_proposal(),
        _phase62_wiring(),
        reviewed_at_iso=APPROVAL_METADATA["reviewed_at_iso"],
    ).artifact_payload

    assert first == second == _approval()
