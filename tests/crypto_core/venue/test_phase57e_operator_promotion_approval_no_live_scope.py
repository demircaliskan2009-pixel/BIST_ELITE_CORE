from __future__ import annotations

from tests.crypto_core.venue.test_phase57b_operator_promotion_approval_artifact import _approval


def test_phase57e_approval_artifact_keeps_all_execution_and_live_flags_false() -> None:
    approval = _approval()

    for field in (
        "promotion_granted",
        "campaign_execution",
        "session_execution",
        "run_execution",
        "ledger_mutated",
        "live_ready",
        "shadow_ready",
        "scheduler_enabled",
        "auto_loop_enabled",
        "live_enabled",
        "shadow_enabled",
    ):
        assert approval[field] is False


def test_phase57e_approval_artifact_keeps_safety_and_scope_flags_true() -> None:
    approval = _approval()
    scope = approval["approval_scope"]

    for field in (
        "no_private_api",
        "no_credentials",
        "no_exchange_orders",
        "no_execution_adapter",
        "no_strategy_signal",
        "no_order_routing",
        "no_scheduler",
        "no_automatic_paper_loop",
        "no_shadow",
        "no_live",
    ):
        assert approval[field] is True
    for field in (
        "paper_only",
        "simulation_only",
        "deribit_public_market_data_only",
        "no_private_api",
        "no_credentials",
        "no_exchange_orders",
        "no_execution_adapter",
        "no_order_routing",
        "no_scheduler",
        "no_automatic_paper_loop",
        "no_strategy_signal",
        "no_shadow",
        "no_live",
    ):
        assert scope[field] is True
