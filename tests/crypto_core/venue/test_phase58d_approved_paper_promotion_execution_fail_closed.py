from __future__ import annotations

from crypto_core.venue.deribit_approved_paper_promotion_execution import execute_deribit_approved_paper_promotion
from tests.crypto_core.venue.test_phase58b_approved_paper_promotion_execution_artifact import (
    SAFETY_FLAGS,
    _mutated,
    _mutated_scope,
    _phase55_readiness,
    _phase57_approval,
)


def _run_with(phase57: object, phase55: object):
    return execute_deribit_approved_paper_promotion(phase57, phase55)


def test_phase58d_missing_or_malformed_sources_fail_closed() -> None:
    assert _run_with(None, _phase55_readiness()).rejection_reasons == (
        "deribit_approved_paper_promotion_execution:phase57_artifact_missing",
    )
    assert (
        "deribit_approved_paper_promotion_execution:phase55_artifact_missing"
        in _run_with(_phase57_approval(), []).rejection_reasons
    )


def test_phase58d_phase57_approval_metadata_must_be_exact() -> None:
    for field, value in (
        ("approval_status", "NOT_APPROVED"),
        ("approval_decision", "APPROVE_LIVE_PROMOTION"),
        ("operator_id", "other_operator"),
        ("next_blocker", "OTHER"),
    ):
        result = _run_with(_mutated(_phase57_approval(), **{field: value}), _phase55_readiness())

        assert "deribit_approved_paper_promotion_execution:phase57_metadata_invalid" in result.rejection_reasons


def test_phase58d_phase55_must_be_ready_for_operator_promotion_review() -> None:
    for field, value in (
        ("promotion_readiness_verdict", "FAIL_CLOSED"),
        ("ready_for_operator_promotion_review", False),
    ):
        result = _run_with(_phase57_approval(), _mutated(_phase55_readiness(), **{field: value}))

        assert "deribit_approved_paper_promotion_execution:phase55_metadata_invalid" in result.rejection_reasons


def test_phase58d_execution_or_live_scope_drift_fails_closed() -> None:
    for field in (
        "promotion_granted",
        "campaign_execution",
        "session_execution",
        "run_execution",
        "ledger_mutated",
        "live_ready",
        "shadow_ready",
        "live_enabled",
        "shadow_enabled",
        "auto_loop_enabled",
        "scheduler_enabled",
    ):
        result = _run_with(_mutated(_phase57_approval(), **{field: True}), _phase55_readiness())

        assert "deribit_approved_paper_promotion_execution:phase57_scope_flags_invalid" in result.rejection_reasons


def test_phase58d_approval_scope_and_safety_flags_fail_closed() -> None:
    for field in SAFETY_FLAGS:
        bad_top_level = _run_with(_mutated(_phase57_approval(), **{field: False}), _phase55_readiness())
        bad_scope = _run_with(_mutated_scope(_phase57_approval(), **{field: False}), _phase55_readiness())

        assert (
            "deribit_approved_paper_promotion_execution:phase57_safety_flags_invalid" in bad_top_level.rejection_reasons
        )
        assert (
            "deribit_approved_paper_promotion_execution:phase57_approval_scope_invalid" in bad_scope.rejection_reasons
        )


def test_phase58d_phase55_safety_or_connector_drift_fails_closed() -> None:
    bad_safety = _mutated(_phase55_readiness(), no_private_api=False)
    bad_connector = _mutated(_phase55_readiness(), connector_ready_dialects_count=0)

    assert (
        "deribit_approved_paper_promotion_execution:phase55_safety_flags_invalid"
        in _run_with(_phase57_approval(), bad_safety).rejection_reasons
    )
    assert (
        "deribit_approved_paper_promotion_execution:phase55_connector_ready_dialects_invalid"
        in _run_with(_phase57_approval(), bad_connector).rejection_reasons
    )
