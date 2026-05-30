from __future__ import annotations

import json

from tests.crypto_core.venue.test_phase54b_approved_execution_telemetry_artifact import _artifact


def test_phase54e_telemetry_contains_no_secret_endpoint_or_execution_material() -> None:
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
        '"ready_for_live": true',
        '"ready_for_shadow": true',
        '"campaign_execution_replayed": true',
        '"ledger_mutated": true',
    ):
        assert forbidden not in payload


def test_phase54e_safety_metrics_and_scope_flags_remain_blocked() -> None:
    artifact = _artifact()
    safety = artifact["safety_metrics"]

    assert isinstance(safety, dict)
    assert safety["live_scope"] is False
    assert safety["shadow_scope"] is False
    assert safety["scheduler_scope"] is False
    assert safety["auto_loop_scope"] is False
    assert safety["private_api_scope"] is False
    assert safety["execution_adapter_scope"] is False
    assert safety["strategy_scope"] is False
    assert artifact["promotion_granted"] is False
    assert artifact["ready_for_live"] is False
    assert artifact["ready_for_shadow"] is False
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
