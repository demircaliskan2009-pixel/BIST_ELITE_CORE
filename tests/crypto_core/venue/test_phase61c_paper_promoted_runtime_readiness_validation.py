from __future__ import annotations

from crypto_core.venue.deribit_paper_promoted_runtime_readiness import (
    evaluate_deribit_paper_promoted_runtime_readiness,
)
from tests.crypto_core.venue.test_phase61b_paper_promoted_runtime_readiness_artifact import (
    FALSE_EXECUTION_FLAGS,
    SAFETY_FLAGS,
    _phase60_post_audit,
)


def test_phase61c_source_validates_before_runtime_readiness() -> None:
    phase60 = _phase60_post_audit()

    assert phase60["post_audit_verdict"] == "PASS"
    assert phase60["promotion_granted"] is True
    assert phase60["promotion_scope"] == "PAPER_ONLY_SIMULATION_ONLY"
    assert phase60["paper_promoted"] is True
    assert phase60["next_blocker"] == "PAPER_PROMOTED_RUNTIME_READINESS_NOT_READY"


def test_phase61c_runtime_readiness_accepts_without_runtime_enablement() -> None:
    result = evaluate_deribit_paper_promoted_runtime_readiness(_phase60_post_audit())
    artifact = result.artifact_payload

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert artifact["runtime_readiness_verdict"] == "PASS"
    assert artifact["ready_for_paper_runtime"] is True
    assert artifact["runtime_enabled"] is False
    for field in FALSE_EXECUTION_FLAGS:
        assert artifact[field] is False
    for field in SAFETY_FLAGS:
        assert artifact[field] is True
