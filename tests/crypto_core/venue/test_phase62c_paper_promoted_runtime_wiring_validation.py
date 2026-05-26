from __future__ import annotations

from crypto_core.venue.deribit_paper_promoted_runtime_wiring import wire_deribit_paper_promoted_runtime
from tests.crypto_core.venue.test_phase62b_paper_promoted_runtime_wiring_artifact import (
    FALSE_RUNTIME_FIELDS,
    SAFETY_FLAGS,
    _phase61_readiness,
)


def test_phase62c_source_validates_before_runtime_wiring() -> None:
    phase61 = _phase61_readiness()

    assert phase61["runtime_readiness_verdict"] == "PASS"
    assert phase61["ready_for_paper_runtime"] is True
    assert phase61["paper_promoted"] is True
    assert phase61["promotion_granted"] is True
    assert phase61["promotion_scope"] == "PAPER_ONLY_SIMULATION_ONLY"
    assert phase61["runtime_enabled"] is False
    assert phase61["next_blocker"] == "PAPER_PROMOTED_RUNTIME_WIRING_NOT_READY"


def test_phase62c_runtime_wiring_accepts_without_runtime_enablement() -> None:
    result = wire_deribit_paper_promoted_runtime(_phase61_readiness())
    artifact = result.artifact_payload

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert artifact["runtime_wiring_status"] == "WIRED"
    assert artifact["ready_for_paper_runtime"] is True
    assert artifact["runtime_enabled"] is False
    assert artifact["runtime_started"] is False
    for field in FALSE_RUNTIME_FIELDS:
        assert artifact[field] is False
    for field in SAFETY_FLAGS:
        assert artifact[field] is True
