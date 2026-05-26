from __future__ import annotations

from crypto_core.venue.deribit_paper_runtime_enablement_proposal import propose_deribit_paper_runtime_enablement
from tests.crypto_core.venue.test_phase63b_runtime_enablement_proposal_artifact import (
    FALSE_RUNTIME_FIELDS,
    SAFETY_FLAGS,
    _mutated,
    _phase62_wiring,
)


def _run_with(phase62: object):
    return propose_deribit_paper_runtime_enablement(phase62)


def test_phase63d_missing_or_malformed_source_fails_closed() -> None:
    assert _run_with(None).rejection_reasons == ("deribit_paper_runtime_enablement_proposal:phase62_artifact_missing",)
    assert _run_with([]).rejection_reasons == ("deribit_paper_runtime_enablement_proposal:phase62_artifact_missing",)


def test_phase63d_phase62_metadata_must_be_exact() -> None:
    for field, value in (
        ("source_phase61_runtime_readiness_sha256", ""),
        ("source_phase61_runtime_readiness_sha256", "0" * 64),
        ("runtime_wiring_status", "FAIL_CLOSED"),
        ("ready_for_paper_runtime", False),
        ("paper_promoted", False),
        ("promotion_granted", False),
        ("promotion_scope", "LIVE"),
        ("wiring_checks", []),
        ("next_blocker", "OTHER"),
    ):
        result = _run_with(_mutated(_phase62_wiring(), **{field: value}))

        assert "deribit_paper_runtime_enablement_proposal:phase62_metadata_invalid" in result.rejection_reasons


def test_phase63d_phase62_scope_or_safety_drift_fails_closed() -> None:
    for field in FALSE_RUNTIME_FIELDS:
        if field == "runtime_enablement_approved":
            continue
        result = _run_with(_mutated(_phase62_wiring(), **{field: True}))

        assert "deribit_paper_runtime_enablement_proposal:phase62_scope_flags_invalid" in result.rejection_reasons

    connector_result = _run_with(_mutated(_phase62_wiring(), connector_ready_dialects_count=2))
    assert (
        "deribit_paper_runtime_enablement_proposal:phase62_connector_ready_dialects_invalid"
        in connector_result.rejection_reasons
    )

    for field in SAFETY_FLAGS:
        result = _run_with(_mutated(_phase62_wiring(), **{field: False}))

        assert "deribit_paper_runtime_enablement_proposal:phase62_safety_flags_invalid" in result.rejection_reasons


def test_phase63d_rejected_payload_forces_fail_closed_scope_and_safety() -> None:
    result = _run_with(_mutated(_phase62_wiring(), live_enabled=True, no_live=False, runtime_started=True))
    payload = result.artifact_payload

    assert result.accepted is False
    assert "deribit_paper_runtime_enablement_proposal:phase62_scope_flags_invalid" in result.rejection_reasons
    assert "deribit_paper_runtime_enablement_proposal:phase62_safety_flags_invalid" in result.rejection_reasons
    assert payload["proposal_status"] == "FAIL_CLOSED"
    assert payload["approval_status"] == "NOT_APPROVED"
    assert payload["runtime_enablement_approved"] is False
    for field in FALSE_RUNTIME_FIELDS:
        assert payload[field] is False
    for field in SAFETY_FLAGS:
        assert payload[field] is True
