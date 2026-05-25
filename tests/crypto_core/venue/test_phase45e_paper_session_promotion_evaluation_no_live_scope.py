from __future__ import annotations

import json

from tests.crypto_core.venue.test_phase45b_paper_session_promotion_evaluation_artifact import _evaluation


def test_phase45e_evaluation_contains_no_secret_endpoint_or_execution_material() -> None:
    payload = json.dumps(_evaluation(), sort_keys=True).lower()

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
        '"promotion_granted": true',
        '"live_ready": true',
        '"live_enabled": true',
        '"shadow_enabled": true',
        '"auto_loop_enabled": true',
        '"scheduler_enabled": true',
    ):
        assert forbidden not in payload


def test_phase45e_scope_flags_remain_disabled_and_safety_flags_remain_true() -> None:
    evaluation = _evaluation()

    assert evaluation["promotion_granted"] is False
    assert evaluation["operator_approval_required"] is True
    assert evaluation["live_ready"] is False
    assert evaluation["live_enabled"] is False
    assert evaluation["shadow_enabled"] is False
    assert evaluation["auto_loop_enabled"] is False
    assert evaluation["scheduler_enabled"] is False
    assert evaluation["no_private_api"] is True
    assert evaluation["no_credentials"] is True
    assert evaluation["no_exchange_orders"] is True
    assert evaluation["no_execution_adapter"] is True
    assert evaluation["no_strategy_signal"] is True
    assert evaluation["no_scheduler"] is True
    assert evaluation["no_automatic_paper_loop"] is True
    assert evaluation["no_shadow"] is True
    assert evaluation["no_live"] is True
