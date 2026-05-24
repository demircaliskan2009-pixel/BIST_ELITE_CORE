from __future__ import annotations

from tests.crypto_core.venue.test_phase43b_paper_session_promotion_artifact import (
    _mutated,
    _phase41_report,
    _promotion_rejection_reasons,
    _promotion_report,
    _session_artifact,
)


def test_phase43d_missing_session_id_fails_closed() -> None:
    session = _mutated(_session_artifact(), session_id="")
    reasons = _promotion_rejection_reasons(session, _phase41_report(), _promotion_report())

    assert "promotion:session_id_missing" in reasons
    assert "promotion:session_id_mismatch" in reasons


def test_phase43d_live_shadow_loop_scheduler_flags_fail_closed() -> None:
    session = _session_artifact()
    phase41 = _phase41_report()

    for field in ("live_enabled", "shadow_enabled", "auto_loop_enabled", "scheduler_enabled"):
        bad_report = _mutated(_promotion_report(), **{field: True})
        reasons = _promotion_rejection_reasons(session, phase41, bad_report)

        assert f"promotion:{field}_not_false" in reasons


def test_phase43d_private_execution_safety_flags_fail_closed() -> None:
    session = _session_artifact()
    phase41 = _phase41_report()

    for field in (
        "no_private_api",
        "no_credentials",
        "no_exchange_orders",
        "no_execution_adapter",
        "no_order_routing",
        "no_strategy_signal",
    ):
        bad_report = _mutated(_promotion_report(), **{field: False})
        reasons = _promotion_rejection_reasons(session, phase41, bad_report)

        assert f"promotion:{field}_not_true" in reasons


def test_phase43d_automatic_promotion_or_campaign_ready_fails_closed() -> None:
    session = _session_artifact()
    phase41 = _phase41_report()

    promoted = _mutated(_promotion_report(), promotion_verdict="READY")
    campaign_ready = _mutated(_promotion_report(), repeated_session_campaign_ready=True)

    assert "promotion:verdict_not_not_ready" in _promotion_rejection_reasons(session, phase41, promoted)
    assert "promotion:campaign_ready_not_false" in _promotion_rejection_reasons(session, phase41, campaign_ready)
