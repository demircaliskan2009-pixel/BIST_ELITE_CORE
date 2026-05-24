from __future__ import annotations

import json

from tests.crypto_core.venue.test_phase44b_repeated_session_report_pack_artifact import _report_pack


def test_phase44e_report_pack_contains_no_secret_endpoint_or_execution_material() -> None:
    payload = json.dumps(_report_pack(), sort_keys=True).lower()

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


def test_phase44e_scope_flags_remain_disabled_and_safety_flags_remain_true() -> None:
    pack = _report_pack()

    assert pack["all_sessions_simulation_only"] is True
    assert pack["live_enabled"] is False
    assert pack["shadow_enabled"] is False
    assert pack["auto_loop_enabled"] is False
    assert pack["scheduler_enabled"] is False
    assert pack["no_private_api"] is True
    assert pack["no_credentials"] is True
    assert pack["no_exchange_orders"] is True
    assert pack["no_execution_adapter"] is True
    assert pack["no_strategy_signal"] is True
    assert pack["no_scheduler"] is True
    assert pack["no_automatic_paper_loop"] is True
    assert pack["no_shadow"] is True
    assert pack["no_live"] is True
