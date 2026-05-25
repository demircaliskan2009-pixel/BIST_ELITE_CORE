from __future__ import annotations

import json

from tests.crypto_core.venue.test_phase51b_operator_review_proposal_artifact import _proposal


def test_phase51e_proposal_contains_no_secret_endpoint_or_execution_material() -> None:
    payload = json.dumps(_proposal(), sort_keys=True).lower()

    for forbidden in (
        "password",
        "signature",
        "api_key",
        "https://",
        "wss://",
        "exchange_order_id",
        "execution_adapter_call",
        "strategy_signal_payload",
        '"approval_status": "approved"',
        '"promotion_granted": true',
        '"live_ready": true',
        '"shadow_ready": true',
        '"live_enabled": true',
        '"shadow_enabled": true',
        '"scheduler_enabled": true',
        '"auto_loop_enabled": true',
    ):
        assert forbidden not in payload


def test_phase51e_scope_flags_remain_disabled_and_safety_flags_remain_true() -> None:
    proposal = _proposal()

    assert proposal["approval_status"] == "NOT_APPROVED"
    assert proposal["promotion_granted"] is False
    assert proposal["live_ready"] is False
    assert proposal["shadow_ready"] is False
    assert proposal["scheduler_enabled"] is False
    assert proposal["auto_loop_enabled"] is False
    assert proposal["live_enabled"] is False
    assert proposal["shadow_enabled"] is False
    assert proposal["no_private_api"] is True
    assert proposal["no_credentials"] is True
    assert proposal["no_exchange_orders"] is True
    assert proposal["no_execution_adapter"] is True
    assert proposal["no_strategy_signal"] is True
    assert proposal["no_order_routing"] is True
    assert proposal["no_scheduler"] is True
    assert proposal["no_automatic_paper_loop"] is True
    assert proposal["no_shadow"] is True
    assert proposal["no_live"] is True
