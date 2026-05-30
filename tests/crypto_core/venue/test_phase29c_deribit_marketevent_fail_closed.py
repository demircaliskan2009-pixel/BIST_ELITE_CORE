from __future__ import annotations

from dataclasses import replace

from crypto_core.venue.deribit_marketevent_normalizer import (
    normalize_deribit_public_book_observation,
    normalize_deribit_public_book_parse_result,
)
from crypto_core.venue.deribit_public_feed_adapter import (
    DERIBIT_PUBLIC_BOOK_CHANNEL,
    DeribitBookLevel,
    parse_deribit_public_book_payload,
)

EVENT_TIME_NS = 1_700_000_000_000_000_000
RECEIVED_AT_NS = EVENT_TIME_NS + 500_000_000


def test_phase29c_rejected_private_like_parse_result_fails_closed() -> None:
    payload = _payload()
    payload["method"] = "private/buy"
    parsed = parse_deribit_public_book_payload(payload, received_at_ns=RECEIVED_AT_NS)
    result = normalize_deribit_public_book_parse_result(parsed)

    assert result.accepted is False
    assert "deribit_marketevent:pre_normalization_not_accepted" in result.rejection_reasons
    assert "deribit_public_feed:private_or_execution_payload" in result.rejection_reasons


def test_phase29c_stale_and_receive_lag_breach_fail_closed() -> None:
    parsed = parse_deribit_public_book_payload(_payload(), received_at_ns=RECEIVED_AT_NS)
    assert parsed.observation is not None
    stale = replace(parsed.observation, received_at_ns=EVENT_TIME_NS + 2_500_000_000, receive_lag_ns=2_500_000_000)

    result = normalize_deribit_public_book_observation(stale)

    assert result.accepted is False
    assert "deribit_marketevent:receive_lag_breach" in result.rejection_reasons
    assert "deribit_marketevent:stale_event" in result.rejection_reasons


def test_phase29c_detectable_sequence_gap_fails_closed() -> None:
    parsed = parse_deribit_public_book_payload(_payload(), received_at_ns=RECEIVED_AT_NS)
    assert parsed.observation is not None
    gapped = replace(parsed.observation, prev_change_id=99)

    result = normalize_deribit_public_book_observation(gapped, prior_change_id=100)

    assert result.accepted is False
    assert "deribit_marketevent:sequence_gap_detected" in result.rejection_reasons


def test_phase29c_negative_sequence_ids_fail_closed() -> None:
    parsed = parse_deribit_public_book_payload(_payload(), received_at_ns=RECEIVED_AT_NS)
    assert parsed.observation is not None
    invalid = replace(parsed.observation, change_id=-1, prev_change_id=-2)

    result = normalize_deribit_public_book_observation(invalid)

    assert result.accepted is False
    assert "deribit_marketevent:change_id_invalid" in result.rejection_reasons
    assert "deribit_marketevent:prev_change_id_invalid" in result.rejection_reasons


def test_phase29c_malformed_identity_and_crossed_book_fail_closed() -> None:
    parsed = parse_deribit_public_book_payload(_payload(), received_at_ns=RECEIVED_AT_NS)
    assert parsed.observation is not None
    invalid = replace(
        parsed.observation,
        channel="book.ETH-PERPETUAL.none.10.100ms",
        instrument_name="",
        bids=(DeribitBookLevel(price=50_020.0, amount=1.0),),
        asks=(DeribitBookLevel(price=50_010.0, amount=1.0),),
    )

    result = normalize_deribit_public_book_observation(invalid)

    assert result.accepted is False
    assert "deribit_marketevent:channel_mismatch" in result.rejection_reasons
    assert "deribit_marketevent:instrument_missing" in result.rejection_reasons
    assert "deribit_marketevent:book_crossed" in result.rejection_reasons


def _payload() -> dict[str, object]:
    return {
        "method": "subscription",
        "params": {
            "channel": DERIBIT_PUBLIC_BOOK_CHANNEL,
            "data": {
                "type": "change",
                "timestamp": 1_700_000_000_000,
                "instrument_name": "BTC-PERPETUAL",
                "change_id": 101,
                "prev_change_id": 100,
                "bids": [["change", 50_000.0, 1.25]],
                "asks": [["change", 50_010.0, 0.75]],
            },
        },
    }
