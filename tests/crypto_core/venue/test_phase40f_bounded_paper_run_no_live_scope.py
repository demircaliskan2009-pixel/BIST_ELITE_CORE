from __future__ import annotations

import json

from tests.crypto_core.venue.test_phase40b_bounded_paper_run_artifact import _artifact, _run_phase40_harness


def test_phase40f_artifact_contains_no_secret_endpoint_or_execution_material() -> None:
    payload = json.dumps(
        {"artifact": _artifact(), "result": _run_phase40_harness().artifact_payload}, sort_keys=True
    ).lower()

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


def test_phase40f_scope_flags_remain_disabled_and_safety_flags_remain_true() -> None:
    artifact = _artifact()
    invariants = artifact["safety_invariants"]
    assert isinstance(invariants, dict)

    assert artifact["simulation_only"] is True
    assert artifact["live_enabled"] is False
    assert artifact["shadow_enabled"] is False
    assert artifact["auto_loop_enabled"] is False
    assert artifact["scheduler_enabled"] is False
    assert invariants["no_private_api"] is True
    assert invariants["no_credentials"] is True
    assert invariants["no_exchange_orders"] is True
    assert invariants["no_execution_adapter"] is True
    assert invariants["no_strategy_signal"] is True
    assert invariants["no_scheduler"] is True
    assert invariants["no_automatic_paper_loop"] is True
    assert invariants["no_shadow"] is True
    assert invariants["no_live"] is True
