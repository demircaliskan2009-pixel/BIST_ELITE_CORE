from __future__ import annotations

from crypto_core.venue.deribit_paper_promoted_runtime_wiring import wire_deribit_paper_promoted_runtime
from tests.crypto_core.venue.test_phase62b_paper_promoted_runtime_wiring_artifact import (
    FALSE_RUNTIME_FIELDS,
    SAFETY_FLAGS,
    _mutated,
    _phase61_readiness,
)


def _run_with(phase61: object):
    return wire_deribit_paper_promoted_runtime(phase61)


def test_phase62d_missing_or_malformed_source_fails_closed() -> None:
    assert _run_with(None).rejection_reasons == ("deribit_paper_promoted_runtime_wiring:phase61_artifact_missing",)
    assert _run_with([]).rejection_reasons == ("deribit_paper_promoted_runtime_wiring:phase61_artifact_missing",)


def test_phase62d_phase61_metadata_must_be_exact() -> None:
    for field, value in (
        ("source_phase60_post_audit_sha256", ""),
        ("source_phase60_post_audit_sha256", "0" * 64),
        ("runtime_readiness_verdict", "FAIL_CLOSED"),
        ("ready_for_paper_runtime", False),
        ("paper_promoted", False),
        ("promotion_granted", False),
        ("promotion_scope", "LIVE"),
        ("readiness_checks", []),
        ("next_blocker", "OTHER"),
    ):
        result = _run_with(_mutated(_phase61_readiness(), **{field: value}))

        assert "deribit_paper_promoted_runtime_wiring:phase61_metadata_invalid" in result.rejection_reasons


def test_phase62d_phase61_scope_runtime_or_safety_drift_fails_closed() -> None:
    for field in FALSE_RUNTIME_FIELDS:
        if field == "runtime_started":
            continue
        result = _run_with(_mutated(_phase61_readiness(), **{field: True}))

        assert "deribit_paper_promoted_runtime_wiring:phase61_scope_flags_invalid" in result.rejection_reasons

    for runtime_value in (True, 1, "true"):
        runtime_result = _run_with(_mutated(_phase61_readiness(), runtime_started=runtime_value))
        assert (
            "deribit_paper_promoted_runtime_wiring:phase61_runtime_started_invalid" in runtime_result.rejection_reasons
        )

    connector_result = _run_with(_mutated(_phase61_readiness(), connector_ready_dialects_count=2))
    assert (
        "deribit_paper_promoted_runtime_wiring:phase61_connector_ready_dialects_invalid"
        in connector_result.rejection_reasons
    )

    for field in SAFETY_FLAGS:
        result = _run_with(_mutated(_phase61_readiness(), **{field: False}))

        assert "deribit_paper_promoted_runtime_wiring:phase61_safety_flags_invalid" in result.rejection_reasons


def test_phase62d_rejected_payload_forces_fail_closed_scope_and_safety() -> None:
    result = _run_with(_mutated(_phase61_readiness(), live_enabled=True, no_live=False, runtime_started=True))
    payload = result.artifact_payload

    assert result.accepted is False
    assert "deribit_paper_promoted_runtime_wiring:phase61_scope_flags_invalid" in result.rejection_reasons
    assert "deribit_paper_promoted_runtime_wiring:phase61_runtime_started_invalid" in result.rejection_reasons
    assert "deribit_paper_promoted_runtime_wiring:phase61_safety_flags_invalid" in result.rejection_reasons
    assert payload["runtime_wiring_status"] == "FAIL_CLOSED"
    assert payload["ready_for_paper_runtime"] is False
    assert payload["runtime_enabled"] is False
    assert payload["runtime_started"] is False
    for field in FALSE_RUNTIME_FIELDS:
        assert payload[field] is False
    for field in SAFETY_FLAGS:
        assert payload[field] is True
