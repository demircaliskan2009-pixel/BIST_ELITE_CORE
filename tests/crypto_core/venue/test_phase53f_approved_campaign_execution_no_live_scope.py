from __future__ import annotations

from tests.crypto_core.venue.test_phase53b_approved_campaign_execution_artifact import _artifact
from tests.crypto_core.venue.test_phase53c_approved_campaign_execution_contract import _run_phase53


def test_phase53f_artifact_preserves_no_live_scope() -> None:
    artifact = _artifact()

    for field in ("live_enabled", "shadow_enabled", "scheduler_enabled", "auto_loop_enabled"):
        assert artifact[field] is False
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
        assert artifact[field] is True


def test_phase53f_runtime_scope_remains_offline_paper_only() -> None:
    result = _run_phase53()

    assert result.accepted is True
    assert result.artifact_payload["execution_mode"] == "OFFLINE_DETERMINISTIC_PAPER_ONLY"
    assert result.artifact_payload["promotion_granted"] is False
    assert result.artifact_payload["live_ready"] is False
    assert result.artifact_payload["shadow_ready"] is False
