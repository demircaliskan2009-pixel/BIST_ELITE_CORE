from __future__ import annotations

import json

from tests.crypto_core.venue.test_phase47b_operator_approval_artifact import _approval


def test_phase47e_approval_contains_no_secret_endpoint_or_execution_material() -> None:
    payload = json.dumps(_approval(), sort_keys=True).lower()

    for forbidden in (
        "password",
        "signature",
        "api_key",
        "https://",
        "wss://",
        "exchange_order_id",
        "execution_adapter_call",
        "strategy_signal_payload",
        '"live_enabled": true',
        '"shadow_enabled": true',
        '"auto_loop_enabled": true',
        '"scheduler_enabled": true',
        '"promotion_granted": true',
    ):
        assert forbidden not in payload


def test_phase47e_scope_flags_remain_disabled_and_safety_flags_remain_true() -> None:
    approval = _approval()
    scope = approval["campaign_scope"]
    safety = approval["safety_flags"]

    assert isinstance(scope, dict)
    assert isinstance(safety, dict)
    assert approval["promotion_granted"] is False
    assert approval["campaign_execution_status"] == "NOT_EXECUTED"
    assert approval["session_execution_status"] == "NOT_EXECUTED"
    assert approval["run_execution_status"] == "NOT_EXECUTED"
    assert scope["live_ready"] is False
    assert scope["live_enabled"] is False
    assert scope["shadow_enabled"] is False
    assert scope["auto_loop_enabled"] is False
    assert scope["scheduler_enabled"] is False
    assert safety["no_private_api"] is True
    assert safety["no_credentials"] is True
    assert safety["no_exchange_orders"] is True
    assert safety["no_execution_adapter"] is True
    assert safety["no_strategy_signal"] is True
    assert safety["no_scheduler"] is True
    assert safety["no_automatic_paper_loop"] is True
    assert safety["no_shadow"] is True
    assert safety["no_live"] is True
