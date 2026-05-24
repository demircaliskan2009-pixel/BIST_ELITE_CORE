from __future__ import annotations

import json

from tests.crypto_core.venue.test_phase39b_paper_trade_audit_report_artifact import _proof, _report


def test_phase39e_report_contains_no_secret_or_runtime_endpoint_material() -> None:
    payload = json.dumps({"proof": _proof(), "report": _report()}, sort_keys=True).lower()

    for forbidden in (
        "password",
        "secret",
        "signature",
        "token",
        "api_key",
        "https://",
        "wss://",
        "exchange_order_id",
        "execution_adapter_call",
        "scheduler_enabled",
        "strategy_signal_payload",
    ):
        assert forbidden not in payload


def test_phase39e_report_keeps_all_live_shadow_scheduler_loop_flags_disabled() -> None:
    report = _report()

    assert report["no_scheduler"] is True
    assert report["no_automatic_paper_loop"] is True
    assert report["no_shadow"] is True
    assert report["no_live"] is True
    assert report["live_enabled"] is False
    assert report["shadow_enabled"] is False
    assert report["auto_loop_enabled"] is False
