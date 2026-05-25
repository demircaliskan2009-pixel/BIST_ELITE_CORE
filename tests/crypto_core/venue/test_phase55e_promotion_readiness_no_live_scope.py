from __future__ import annotations

import json

from tests.crypto_core.venue.test_phase55b_promotion_readiness_artifact import _artifact


def test_phase55e_readiness_contains_no_secret_endpoint_or_execution_material() -> None:
    payload = json.dumps(_artifact(), sort_keys=True).lower()

    for forbidden in (
        "password",
        "signature",
        "api_key",
        "https://",
        "wss://",
        "exchange_order_id",
        "execution_adapter_call",
        "strategy_signal_payload",
        '"promotion_granted": true',
        '"live_ready": true',
        '"shadow_ready": true',
        '"campaign_execution_replayed": true',
        '"ledger_mutated": true',
    ):
        assert forbidden not in payload


def test_phase55e_scope_flags_remain_disabled_and_safety_flags_remain_true() -> None:
    artifact = _artifact()

    assert artifact["promotion_granted"] is False
    assert artifact["live_ready"] is False
    assert artifact["shadow_ready"] is False
    assert artifact["scheduler_enabled"] is False
    assert artifact["auto_loop_enabled"] is False
    assert artifact["live_enabled"] is False
    assert artifact["shadow_enabled"] is False
    assert artifact["no_private_api"] is True
    assert artifact["no_credentials"] is True
    assert artifact["no_exchange_orders"] is True
    assert artifact["no_execution_adapter"] is True
    assert artifact["no_strategy_signal"] is True
    assert artifact["no_order_routing"] is True
    assert artifact["no_scheduler"] is True
    assert artifact["no_automatic_paper_loop"] is True
    assert artifact["no_shadow"] is True
    assert artifact["no_live"] is True
