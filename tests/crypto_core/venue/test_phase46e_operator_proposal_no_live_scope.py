from __future__ import annotations

import json

from tests.crypto_core.venue.test_phase46b_operator_proposal_artifact import _proposal


def test_phase46e_proposal_contains_no_secret_endpoint_or_execution_material() -> None:
    payload = json.dumps(_proposal(), sort_keys=True).lower()

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
        '"approval_status": "approved"',
        '"promotion_granted": true',
        '"live_enabled": true',
        '"shadow_enabled": true',
        '"auto_loop_enabled": true',
        '"scheduler_enabled": true',
    ):
        assert forbidden not in payload


def test_phase46e_scope_flags_remain_disabled_and_safety_flags_remain_true() -> None:
    proposal = _proposal()
    scope = proposal["campaign_scope"]
    safety = proposal["safety_flags"]

    assert proposal["approval_status"] == "NOT_APPROVED"
    assert proposal["promotion_granted"] is False
    assert scope["public_market_data_only"] is True
    assert scope["paper_only"] is True
    assert scope["simulation_only"] is True
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
