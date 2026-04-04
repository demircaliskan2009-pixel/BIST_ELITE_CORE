from __future__ import annotations

from bist_core.services.live_bridge_payload import normalize_live_bridge_payload


def test_normalize_live_bridge_payload_from_last_aliases() -> None:
    row = {
        "symbol": "AKBNK",
        "source_period": "01",
        "last_open": 72.55,
        "last_high": 72.65,
        "last_low": 72.55,
        "last_close": 72.6500015258789,
        "volume": 732956.0,
        "turnover": 53204712.0,
        "last_raw_time_code": 20018519,
        "header_bytes": 0.0,
        "record_bytes": 32.0,
    }

    got = normalize_live_bridge_payload(row)

    assert got["current_open"] == got["last_open"] == got["open"] == 72.55
    assert got["current_high"] == got["last_high"] == got["high"] == 72.65
    assert got["current_low"] == got["last_low"] == got["low"] == 72.55
    assert got["current_close"] == got["current_price"] == got["last_price"] == got["last_close"] == got["close"] == 72.65
    assert got["current_volume"] == got["last_volume"] == got["volume"] == 732956
    assert got["current_turnover"] == got["last_turnover"] == got["turnover"] == 53204712
    assert got["raw_time_code"] == got["last_raw_time_code"] == 20018519
    assert got["header_bytes"] == 0
    assert got["record_bytes"] == 32


def test_normalize_live_bridge_payload_from_current_fields() -> None:
    row = {
        "symbol": "ASELS",
        "source_period": "01",
        "current_open": 322.750001,
        "current_high": 323.000001,
        "current_low": 322.500001,
        "current_close": 322.500001,
        "current_volume": 192703.0,
        "current_turnover": 62160624.0,
        "raw_time_code": 20018519,
    }

    got = normalize_live_bridge_payload(row)

    assert got["current_open"] == got["last_open"] == got["open"] == 322.75
    assert got["current_high"] == got["last_high"] == got["high"] == 323.0
    assert got["current_low"] == got["last_low"] == got["low"] == 322.5
    assert got["current_close"] == got["current_price"] == got["last_price"] == got["last_close"] == got["close"] == 322.5
    assert got["current_volume"] == got["last_volume"] == got["volume"] == 192703
    assert got["current_turnover"] == got["last_turnover"] == got["turnover"] == 62160624
    assert got["raw_time_code"] == got["last_raw_time_code"] == 20018519


def test_normalize_live_bridge_payload_sets_generic_price_aliases() -> None:
    row = {
        "symbol": "AKBNK",
        "source_period": "01",
        "last_close": 72.6500015258789,
        "last_raw_time_code": 20018519,
    }

    got = normalize_live_bridge_payload(row)

    assert got["price"] == 72.65
    assert got["live_price"] == 72.65
    assert got["asof_price"] == 72.65
    assert got["price"] == got["live_price"] == got["asof_price"] == got["current_price"] == got["last_price"] == got["close"]
