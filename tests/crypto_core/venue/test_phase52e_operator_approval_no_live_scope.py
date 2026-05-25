from __future__ import annotations

import json

from tests.crypto_core.venue.test_phase52b_operator_approval_artifact import _approval


def test_phase52e_approval_contains_no_secret_endpoint_or_execution_material() -> None:
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
        '"promotion_granted": true',
        '"campaign_execution": true',
        '"ledger_mutated": true',
        '"live_enabled": true',
        '"shadow_enabled": true',
        '"auto_loop_enabled": true',
        '"scheduler_enabled": true',
    ):
        assert forbidden not in payload


def test_phase52e_scope_flags_remain_disabled_and_safety_flags_remain_true() -> None:
    approval = _approval()
    scope = approval["approval_scope"]

    assert isinstance(scope, dict)
    assert approval["promotion_granted"] is False
    assert approval["campaign_execution"] is False
    assert approval["session_execution"] is False
    assert approval["run_execution"] is False
    assert approval["ledger_mutated"] is False
    assert approval["live_ready"] is False
    assert approval["shadow_ready"] is False
    assert approval["live_enabled"] is False
    assert approval["shadow_enabled"] is False
    assert approval["auto_loop_enabled"] is False
    assert approval["scheduler_enabled"] is False
    assert scope["paper_only"] is True
    assert scope["simulation_only"] is True
    assert scope["deribit_public_market_data_only"] is True
    assert approval["no_private_api"] is True
    assert approval["no_credentials"] is True
    assert approval["no_exchange_orders"] is True
    assert approval["no_execution_adapter"] is True
    assert approval["no_strategy_signal"] is True
    assert approval["no_order_routing"] is True
    assert approval["no_scheduler"] is True
    assert approval["no_automatic_paper_loop"] is True
    assert approval["no_shadow"] is True
    assert approval["no_live"] is True
