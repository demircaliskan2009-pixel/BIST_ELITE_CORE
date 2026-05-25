from __future__ import annotations

import json

from tests.crypto_core.venue.test_phase48b_campaign_execution_artifact import _artifact


def test_phase48f_artifact_contains_no_secret_endpoint_or_execution_material() -> None:
    payload = json.dumps(_artifact(), sort_keys=True).lower()

    for forbidden in (
        "password",
        "secret",
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
    ):
        assert forbidden not in payload


def test_phase48f_scope_flags_remain_disabled_and_safety_flags_remain_true() -> None:
    artifact = _artifact()

    assert artifact["simulation_only"] is True
    assert artifact["live_enabled"] is False
    assert artifact["shadow_enabled"] is False
    assert artifact["auto_loop_enabled"] is False
    assert artifact["scheduler_enabled"] is False
    assert artifact["no_private_api"] is True
    assert artifact["no_credentials"] is True
    assert artifact["no_exchange_orders"] is True
    assert artifact["no_execution_adapter"] is True
    assert artifact["no_strategy_signal"] is True
    assert artifact["no_scheduler"] is True
    assert artifact["no_automatic_paper_loop"] is True
    assert artifact["no_shadow"] is True
    assert artifact["no_live"] is True
