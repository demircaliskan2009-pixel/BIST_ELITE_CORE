from __future__ import annotations

import json

from crypto_core.venue.deribit_paper_promotion_telemetry_audit import (
    audit_deribit_paper_promotion_execution_telemetry,
)
from tests.crypto_core.venue.test_phase59b_paper_promotion_execution_telemetry_artifact import (
    _audit,
    _phase55_readiness,
    _phase58_execution,
)


def test_phase59g_runtime_output_is_deterministic() -> None:
    first = audit_deribit_paper_promotion_execution_telemetry(
        _phase58_execution(), _phase55_readiness()
    ).artifact_payload
    second = audit_deribit_paper_promotion_execution_telemetry(
        _phase58_execution(), _phase55_readiness()
    ).artifact_payload

    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_phase59g_committed_artifact_matches_runtime_output() -> None:
    runtime = audit_deribit_paper_promotion_execution_telemetry(
        _phase58_execution(), _phase55_readiness()
    ).artifact_payload

    assert _audit() == runtime
