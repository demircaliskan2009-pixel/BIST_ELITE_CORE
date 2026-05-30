from __future__ import annotations

import copy

from crypto_core.venue.deribit_approved_execution_telemetry_audit import (
    audit_deribit_approved_execution_telemetry,
)
from tests.crypto_core.venue.test_phase54b_approved_execution_telemetry_artifact import (
    _phase52_approval,
    _phase53_execution,
)


def test_phase54g_telemetry_validation_is_deterministic() -> None:
    result_one = audit_deribit_approved_execution_telemetry(_phase53_execution(), _phase52_approval())
    result_two = audit_deribit_approved_execution_telemetry(copy.deepcopy(_phase53_execution()), _phase52_approval())

    assert result_one.accepted is True
    assert result_one == result_two


def test_phase54g_telemetry_payload_order_independent_for_json_roundtrip() -> None:
    result = audit_deribit_approved_execution_telemetry(_phase53_execution(), _phase52_approval())
    reordered = dict(reversed(list(result.artifact_payload.items())))

    assert sorted(result.artifact_payload.items(), key=lambda item: item[0]) == sorted(
        reordered.items(), key=lambda item: item[0]
    )
