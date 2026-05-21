from __future__ import annotations

from copy import deepcopy

from crypto_core.venue.deribit_public_feed_adapter import DERIBIT_PUBLIC_BOOK_CHANNEL, parse_deribit_public_book_payload

EVENT_TIME_NS = 1_700_000_000_000_000_000
RECEIVED_AT_NS = EVENT_TIME_NS + 500_000_000


def _payload() -> dict[str, object]:
    return {
        "method": "subscription",
        "params": {
            "channel": DERIBIT_PUBLIC_BOOK_CHANNEL,
            "data": {
                "type": "change",
                "timestamp": 1_700_000_000_000,
                "instrument_name": "BTC-PERPETUAL",
                "change_id": 102,
                "prev_change_id": 101,
                "bids": [["change", 50_000.0, 1.0]],
                "asks": [["change", 50_010.0, 0.5]],
            },
        },
    }


def test_phase28c_private_or_execution_like_payload_fails_closed() -> None:
    payload = _payload()
    payload["method"] = "private/buy"
    result = parse_deribit_public_book_payload(payload, received_at_ns=RECEIVED_AT_NS)

    assert result.accepted is False
    assert "deribit_public_feed:private_or_execution_payload" in result.rejection_reasons


def test_phase28c_missing_channel_or_instrument_fails_closed() -> None:
    payload = _payload()
    params = payload["params"]
    assert isinstance(params, dict)
    params["channel"] = "ticker.BTC-PERPETUAL.raw"
    result = parse_deribit_public_book_payload(payload, received_at_ns=RECEIVED_AT_NS)

    assert result.accepted is False
    assert "deribit_public_feed:channel_not_public_book" in result.rejection_reasons
    assert "deribit_public_feed:unexpected_channel" in result.rejection_reasons


def test_phase28c_receive_lag_and_stale_event_fail_closed() -> None:
    result = parse_deribit_public_book_payload(_payload(), received_at_ns=EVENT_TIME_NS + 2_500_000_000)

    assert result.accepted is False
    assert "deribit_public_feed:receive_lag_breach" in result.rejection_reasons
    assert "deribit_public_feed:stale_event" in result.rejection_reasons


def test_phase28c_detectable_gap_fails_closed_with_zero_tolerance() -> None:
    result = parse_deribit_public_book_payload(_payload(), received_at_ns=RECEIVED_AT_NS, prior_change_id=100)

    assert result.accepted is False
    assert "deribit_public_feed:sequence_gap_detected" in result.rejection_reasons


def test_phase28c_missing_prev_change_id_with_prior_sequence_fails_closed() -> None:
    payload = deepcopy(_payload())
    params = payload["params"]
    assert isinstance(params, dict)
    data = params["data"]
    assert isinstance(data, dict)
    data["prev_change_id"] = None

    result = parse_deribit_public_book_payload(payload, received_at_ns=RECEIVED_AT_NS, prior_change_id=101)

    assert result.accepted is False
    assert "deribit_public_feed:sequence_gap_unresolved" in result.rejection_reasons
