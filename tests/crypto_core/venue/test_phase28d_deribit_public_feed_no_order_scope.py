from __future__ import annotations

import inspect

import crypto_core.venue.deribit_public_feed_adapter as adapter
from crypto_core.venue.public_feed_dialects import connector_ready_dialects


def test_phase28d_adapter_exposes_no_order_or_auth_methods() -> None:
    names = {name.lower() for name, value in inspect.getmembers(adapter) if inspect.isfunction(value)}

    forbidden_function_names = {
        "authenticate",
        "cancel_order",
        "create_order",
        "login",
        "place_order",
        "sign_request",
        "submit_order",
    }
    assert names.isdisjoint(forbidden_function_names)


def test_phase28d_source_does_not_introduce_credentials_or_trading_runtime() -> None:
    source = inspect.getsource(adapter).lower()

    for forbidden in (
        "api_secret",
        "executionmode.live",
        "paper_execution",
        "shadow_execution",
        "place_order",
        "submit_order",
        "cancel_order",
    ):
        assert forbidden not in source
    assert "os.environ" not in source
    assert "getenv" not in source


def test_phase28d_connector_ready_dialect_count_remains_one() -> None:
    ready = connector_ready_dialects()

    assert len(ready) == 1
    assert ready[0].dialect_id == "deribit:l2_orderbook:book_instrument_interval"
