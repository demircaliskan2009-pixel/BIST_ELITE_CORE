from __future__ import annotations

import json

from tests.crypto_core.venue.test_phase41b_paper_run_telemetry_report_artifact import _report


def test_phase41e_report_contains_no_secret_endpoint_or_execution_material() -> None:
    payload = json.dumps(_report(), sort_keys=True).lower()

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


def test_phase41e_report_keeps_all_live_shadow_scheduler_loop_flags_disabled() -> None:
    report = _report()

    assert report["simulation_only"] is True
    assert report["live_enabled"] is False
    assert report["shadow_enabled"] is False
    assert report["auto_loop_enabled"] is False
    assert report["scheduler_enabled"] is False
    assert report["no_scheduler"] is True
    assert report["no_automatic_paper_loop"] is True
    assert report["no_shadow"] is True
    assert report["no_live"] is True
