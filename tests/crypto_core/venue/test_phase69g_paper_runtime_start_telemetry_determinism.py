from __future__ import annotations

import copy

from crypto_core.venue.deribit_paper_runtime_start_telemetry import (
    audit_deribit_paper_runtime_start_telemetry,
)
from tests.crypto_core.venue.test_phase69b_paper_runtime_start_telemetry_artifact import (
    _phase65_execution,
    _phase67_approval,
    _phase68_execution,
)


def test_phase69g_result_is_deterministic_for_same_inputs() -> None:
    phase68 = _phase68_execution()
    phase67 = _phase67_approval()
    phase65 = _phase65_execution()

    first = audit_deribit_paper_runtime_start_telemetry(
        copy.deepcopy(phase68),
        copy.deepcopy(phase67),
        copy.deepcopy(phase65),
    )
    second = audit_deribit_paper_runtime_start_telemetry(
        copy.deepcopy(phase68),
        copy.deepcopy(phase67),
        copy.deepcopy(phase65),
    )

    assert first.accepted is True
    assert second.accepted is True
    assert first.reason_code == second.reason_code
    assert first.rejection_reasons == second.rejection_reasons
    assert first.artifact_payload == second.artifact_payload
