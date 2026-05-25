from __future__ import annotations

from tests.crypto_core.venue.test_phase45b_paper_session_promotion_evaluation_artifact import (
    _evaluation,
    _evaluation_rejection_reasons,
    _mutated,
    _promotion_readiness,
    _report_pack,
)


def test_phase45d_missing_or_malformed_source_fields_fail_closed() -> None:
    missing_source = _mutated(_evaluation(), source_phase44_report_pack="")
    bad_hash = _mutated(_evaluation(), source_phase44_report_pack_sha256="bad")

    assert "evaluation:source_phase44_mismatch" in _evaluation_rejection_reasons(
        _promotion_readiness(), _report_pack(), missing_source
    )
    assert "evaluation:source_phase44_hash_mismatch" in _evaluation_rejection_reasons(
        _promotion_readiness(), _report_pack(), bad_hash
    )


def test_phase45d_insufficient_evidence_fails_closed() -> None:
    insufficient = _mutated(_evaluation(), evaluated_session_count=2)

    assert "evaluation:session_count_mismatch" in _evaluation_rejection_reasons(
        _promotion_readiness(), _report_pack(), insufficient
    )
    assert "evaluation:evidence_count_insufficient" in _evaluation_rejection_reasons(
        _promotion_readiness(), _report_pack(), insufficient
    )


def test_phase45d_live_shadow_loop_scheduler_flags_fail_closed() -> None:
    for field in ("live_enabled", "shadow_enabled", "auto_loop_enabled", "scheduler_enabled"):
        bad_evaluation = _mutated(_evaluation(), **{field: True})
        reasons = _evaluation_rejection_reasons(_promotion_readiness(), _report_pack(), bad_evaluation)

        assert f"evaluation:{field}_not_false" in reasons


def test_phase45d_private_execution_safety_flags_fail_closed() -> None:
    for field in (
        "no_private_api",
        "no_credentials",
        "no_exchange_orders",
        "no_execution_adapter",
        "no_order_routing",
        "no_strategy_signal",
    ):
        bad_evaluation = _mutated(_evaluation(), **{field: False})
        reasons = _evaluation_rejection_reasons(_promotion_readiness(), _report_pack(), bad_evaluation)

        assert f"evaluation:{field}_not_true" in reasons


def test_phase45d_malformed_evaluation_matrix_items_fail_closed() -> None:
    malformed_matrix = _mutated(_evaluation(), evaluation_matrix=[{"status": "PASS"}, "corrupt"])
    bad_status = _mutated(_evaluation(), evaluation_matrix=[{"status": "PASS"}, {"status": "WARN"}])

    assert "evaluation:matrix_item_not_mapping" in _evaluation_rejection_reasons(
        _promotion_readiness(), _report_pack(), malformed_matrix
    )
    assert "evaluation:matrix_status_not_pass" in _evaluation_rejection_reasons(
        _promotion_readiness(), _report_pack(), bad_status
    )


def test_phase45d_automatic_promotion_or_live_ready_fails_closed() -> None:
    promoted = _mutated(_evaluation(), promotion_granted=True)
    live_ready = _mutated(_evaluation(), live_ready=True)
    no_operator_gate = _mutated(_evaluation(), operator_approval_required=False)

    assert "evaluation:promotion_granted_not_false" in _evaluation_rejection_reasons(
        _promotion_readiness(), _report_pack(), promoted
    )
    assert "evaluation:live_ready_not_false" in _evaluation_rejection_reasons(
        _promotion_readiness(), _report_pack(), live_ready
    )
    assert "evaluation:operator_approval_required_not_true" in _evaluation_rejection_reasons(
        _promotion_readiness(), _report_pack(), no_operator_gate
    )
