from __future__ import annotations

import json

from tests.crypto_core.venue.test_phase43b_paper_session_promotion_artifact import _promotion_report


def test_phase43e_artifact_contains_no_secret_endpoint_or_execution_material() -> None:
    payload = json.dumps(_promotion_report(), sort_keys=True).lower()

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


def test_phase43e_scope_flags_remain_disabled_and_safety_flags_remain_true() -> None:
    report = _promotion_report()

    assert report["simulation_only"] is True
    assert report["live_enabled"] is False
    assert report["shadow_enabled"] is False
    assert report["auto_loop_enabled"] is False
    assert report["scheduler_enabled"] is False
    assert report["no_private_api"] is True
    assert report["no_credentials"] is True
    assert report["no_exchange_orders"] is True
    assert report["no_execution_adapter"] is True
    assert report["no_strategy_signal"] is True
    assert report["no_scheduler"] is True
    assert report["no_automatic_paper_loop"] is True
    assert report["no_shadow"] is True
    assert report["no_live"] is True
