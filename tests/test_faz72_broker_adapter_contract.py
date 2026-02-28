"""FAZ72: Broker adapter interface (place_orders/cancel/get_fills) with strict schemas and stub that reads fixture responses."""

from __future__ import annotations

import json
from pathlib import Path


from bist_core.execution.broker_adapter import (
    FILL_RECORD_KEYS,
    PLACE_ORDERS_OUTPUT_KEYS,
    CANCEL_OUTPUT_KEYS,
    StubBrokerAdapter,
    _validate_place_orders_input,
    _validate_place_orders_output,
    _validate_cancel_input,
    _validate_cancel_output,
    _validate_get_fills_input,
    _validate_get_fills_output,
    _validate_fill_record,
)
from bist_core.execution.adapters.stub_broker import StubExecutionProvider


ROOT = Path(__file__).resolve().parent
FIXTURE_DIR = ROOT / "fixtures" / "broker_adapter"


def test_place_orders_input_schema_valid() -> None:
    """Valid place_orders input passes validation."""
    payload = {"day": "2025-01-15", "actions": [{"symbol": "THYAO", "side": "BUY", "weight": 0.1}]}
    assert _validate_place_orders_input(payload) is None


def test_place_orders_input_schema_invalid() -> None:
    """Missing day or actions fails validation."""
    assert _validate_place_orders_input({}) is not None
    assert "day" in (_validate_place_orders_input({"actions": []}) or "")
    assert "actions" in (_validate_place_orders_input({"day": "x"}) or "")
    assert _validate_place_orders_input({"day": 1, "actions": []}) is not None
    assert _validate_place_orders_input({"day": "x", "actions": "y"}) is not None


def test_place_orders_output_schema() -> None:
    """Place_orders output must have ok, order_ids, fills, errors."""
    valid = {"ok": True, "order_ids": [], "fills": [], "errors": []}
    assert _validate_place_orders_output(valid) is None
    for k in PLACE_ORDERS_OUTPUT_KEYS:
        bad = dict(valid)
        del bad[k]
        assert _validate_place_orders_output(bad) is not None
    fill = {"order_id": "1", "symbol": "X", "side": "BUY", "qty": 10.0, "price": 1.0, "notional": 10.0}
    assert _validate_place_orders_output({**valid, "fills": [fill]}) is None


def test_cancel_input_output_schema() -> None:
    """Cancel input requires order_id (str or null); output ok, cancelled, errors."""
    assert _validate_cancel_input({"order_id": None}) is None
    assert _validate_cancel_input({"order_id": "ord-1"}) is None
    assert _validate_cancel_input({}) is not None
    assert _validate_cancel_input({"order_id": 1}) is not None
    out = {"ok": True, "cancelled": [], "errors": []}
    assert _validate_cancel_output(out) is None
    for k in CANCEL_OUTPUT_KEYS:
        bad = dict(out)
        del bad[k]
        assert _validate_cancel_output(bad) is not None


def test_get_fills_input_output_schema() -> None:
    """Get_fills input optional day/order_id; output ok, fills, errors."""
    assert _validate_get_fills_input({}) is None
    assert _validate_get_fills_input({"day": "2025-01-15"}) is None
    assert _validate_get_fills_input({"order_id": "ord-1"}) is None
    assert _validate_get_fills_input({"day": 1}) is not None
    out = {"ok": True, "fills": [], "errors": []}
    assert _validate_get_fills_output(out) is None
    fill = {"order_id": "1", "symbol": "X", "side": "BUY", "qty": 10.0, "price": 1.0, "notional": 10.0}
    assert _validate_get_fills_output({**out, "fills": [fill]}) is None


def test_fill_record_schema() -> None:
    """Fill record requires order_id, symbol, side, qty, price, notional."""
    f = {"order_id": "1", "symbol": "X", "side": "BUY", "qty": 10.0, "price": 1.0, "notional": 10.0}
    assert _validate_fill_record(f) is None
    for k in FILL_RECORD_KEYS:
        bad = dict(f)
        del bad[k]
        assert _validate_fill_record(bad) is not None


def test_stub_adapter_invalid_input_returns_errors() -> None:
    """StubBrokerAdapter returns ok=False and errors when input invalid."""
    adapter = StubBrokerAdapter({})
    out = adapter.place_orders({})
    assert out["ok"] is False
    assert out["errors"]
    assert out["order_ids"] == []
    assert out["fills"] == []
    out_cancel = adapter.cancel({})
    assert out_cancel["ok"] is False
    assert out_cancel["errors"]
    out_fills = adapter.get_fills({"day": 1})
    assert out_fills["ok"] is False
    assert out_fills["errors"]


def test_stub_adapter_valid_input_default_response() -> None:
    """StubBrokerAdapter with no fixture returns default ok=True empty response."""
    adapter = StubBrokerAdapter({})
    out = adapter.place_orders({"day": "2025-01-15", "actions": []})
    assert out["ok"] is True
    assert out["order_ids"] == []
    assert out["fills"] == []
    assert out["errors"] == []
    out_cancel = adapter.cancel({"order_id": None})
    assert out_cancel["ok"] is True
    assert out_cancel["cancelled"] == []
    out_fills = adapter.get_fills({})
    assert out_fills["ok"] is True
    assert out_fills["fills"] == []


def test_stub_adapter_reads_fixture_from_dir() -> None:
    """StubBrokerAdapter reads fixture responses from fixture_dir."""
    adapter = StubBrokerAdapter({"fixture_dir": str(FIXTURE_DIR)})
    out = adapter.place_orders({"day": "2025-01-15", "actions": [{"symbol": "X", "side": "BUY"}]})
    assert out["ok"] is True
    assert out["order_ids"] == ["ord-1", "ord-2"]
    assert len(out["fills"]) == 2
    assert out["fills"][0]["symbol"] == "THYAO"
    out_cancel = adapter.cancel({"order_id": "ord-1"})
    assert out_cancel["ok"] is True
    assert out_cancel["cancelled"] == ["ord-1"]
    out_fills = adapter.get_fills({})
    assert out_fills["ok"] is True
    assert len(out_fills["fills"]) == 1
    assert out_fills["fills"][0]["order_id"] == "ord-1"


def test_stub_adapter_config_file_path() -> None:
    """StubBrokerAdapter can be created from config JSON file path."""
    config_path = FIXTURE_DIR.parent / "broker_config_fixture.json"
    config_path.write_text(json.dumps({"fixture_dir": str(FIXTURE_DIR)}, indent=2), encoding="utf-8")
    try:
        adapter = StubBrokerAdapter(config_path)
        out = adapter.place_orders({"day": "2025-01-15", "actions": []})
        assert out["ok"] is True
        assert out["order_ids"] == ["ord-1", "ord-2"]
    finally:
        if config_path.is_file():
            config_path.unlink()


def test_execution_provider_calls_adapter_when_live() -> None:
    """StubExecutionProvider calls broker adapter place_orders when dry_run=False (live)."""
    config = {"fixture_dir": str(FIXTURE_DIR)}
    provider = StubExecutionProvider(config)
    orders_intent = {"day": "2025-01-15", "actions": [{"symbol": "THYAO", "side": "BUY", "weight": 0.1}]}
    result = provider.submit_orders(orders_intent, dry_run=False)
    assert result["ok"] is True
    assert result["broker"] == "stub"
    assert result["sent"] == 2
    assert result["details"].get("order_ids") == ["ord-1", "ord-2"]
    assert len(result["details"].get("fills", [])) == 2


def test_execution_provider_dry_run_does_not_use_adapter_place_orders() -> None:
    """StubExecutionProvider dry_run=True returns ok without calling adapter place_orders (sent=0)."""
    config = {"fixture_dir": str(FIXTURE_DIR)}
    provider = StubExecutionProvider(config)
    orders_intent = {"day": "2025-01-15", "actions": [{"symbol": "X", "side": "BUY"}]}
    result = provider.submit_orders(orders_intent, dry_run=True)
    assert result["ok"] is True
    assert result["broker"] == "stub"
    assert result["sent"] == 0
    assert "fills" not in result.get("details", {})


def test_execution_provider_fixture_failure_returns_errors() -> None:
    """When adapter returns ok=False, execution result reflects it."""
    StubBrokerAdapter({})
    # Return a failing fixture: we need an adapter that returns ok=False. StubBrokerAdapter
    # only returns ok=False on invalid input. So use a custom response file that has ok: false.
    failing_dir = ROOT / "fixtures" / "broker_adapter_failing"
    failing_dir.mkdir(parents=True, exist_ok=True)
    (failing_dir / "place_orders_response.json").write_text(
        json.dumps({"ok": False, "order_ids": [], "fills": [], "errors": ["rejected_by_broker"]}),
        encoding="utf-8",
    )
    try:
        provider = StubExecutionProvider({"fixture_dir": str(failing_dir)})
        result = provider.submit_orders({"day": "2025-01-15", "actions": []}, dry_run=False)
        assert result["ok"] is False
        assert "rejected_by_broker" in result.get("errors", [])
        assert result["sent"] == 0
    finally:
        if (failing_dir / "place_orders_response.json").is_file():
            (failing_dir / "place_orders_response.json").unlink()
        if failing_dir.is_dir():
            failing_dir.rmdir()
