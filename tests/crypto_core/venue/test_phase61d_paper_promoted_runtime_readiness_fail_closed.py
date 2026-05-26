from __future__ import annotations

from crypto_core.venue.deribit_paper_promoted_runtime_readiness import (
    evaluate_deribit_paper_promoted_runtime_readiness,
)
from tests.crypto_core.venue.test_phase61b_paper_promoted_runtime_readiness_artifact import (
    FALSE_EXECUTION_FLAGS,
    SAFETY_FLAGS,
    _mutated,
    _phase60_post_audit,
)


def _run_with(phase60: object):
    return evaluate_deribit_paper_promoted_runtime_readiness(phase60)


def test_phase61d_missing_or_malformed_source_fails_closed() -> None:
    assert _run_with(None).rejection_reasons == ("deribit_paper_promoted_runtime_readiness:phase60_artifact_missing",)


def test_phase61d_phase60_metadata_must_be_exact() -> None:
    for field, value in (
        ("source_phase59_telemetry_audit", "docs/crypto_core/TAMPERED_59B.json"),
        ("source_phase58_promotion_execution", "docs/crypto_core/TAMPERED_58B.json"),
        ("post_audit_verdict", "FAIL_CLOSED"),
        ("promotion_granted", False),
        ("promotion_scope", "LIVE"),
        ("paper_promoted", False),
        ("next_blocker", "OTHER"),
    ):
        result = _run_with(_mutated(_phase60_post_audit(), **{field: value}))

        assert "deribit_paper_promoted_runtime_readiness:phase60_metadata_invalid" in result.rejection_reasons


def test_phase61d_phase60_scope_runtime_or_safety_drift_fails_closed() -> None:
    for field in FALSE_EXECUTION_FLAGS:
        result = _run_with(_mutated(_phase60_post_audit(), **{field: True}))

        assert "deribit_paper_promoted_runtime_readiness:phase60_scope_flags_invalid" in result.rejection_reasons

    runtime_result = _run_with(_mutated(_phase60_post_audit(), runtime_enabled=True))
    assert "deribit_paper_promoted_runtime_readiness:phase60_runtime_flag_invalid" in runtime_result.rejection_reasons

    connector_result = _run_with(_mutated(_phase60_post_audit(), connector_ready_dialects_count=2))
    assert (
        "deribit_paper_promoted_runtime_readiness:phase60_connector_ready_dialects_invalid"
        in connector_result.rejection_reasons
    )

    for field in SAFETY_FLAGS:
        result = _run_with(_mutated(_phase60_post_audit(), **{field: False}))

        assert "deribit_paper_promoted_runtime_readiness:phase60_safety_flags_invalid" in result.rejection_reasons


def test_phase61d_rejected_payload_forces_fail_closed_scope_and_safety() -> None:
    result = _run_with(_mutated(_phase60_post_audit(), live_enabled=True, no_live=False, runtime_enabled=True))
    payload = result.artifact_payload

    assert result.accepted is False
    assert "deribit_paper_promoted_runtime_readiness:phase60_scope_flags_invalid" in result.rejection_reasons
    assert "deribit_paper_promoted_runtime_readiness:phase60_runtime_flag_invalid" in result.rejection_reasons
    assert "deribit_paper_promoted_runtime_readiness:phase60_safety_flags_invalid" in result.rejection_reasons
    assert payload["promotion_scope"] == "PAPER_ONLY_SIMULATION_ONLY"
    assert payload["ready_for_paper_runtime"] is False
    assert payload["runtime_enabled"] is False
    for field in FALSE_EXECUTION_FLAGS:
        assert payload[field] is False
    for field in SAFETY_FLAGS:
        assert payload[field] is True
