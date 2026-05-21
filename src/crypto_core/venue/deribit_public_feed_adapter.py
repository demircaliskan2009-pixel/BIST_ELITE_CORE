from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from crypto_core.data.public_feed_dialect import FeedChecksumModel, FeedSequenceModel
from crypto_core.venue.contracts import PublicFeedType, VenueId
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_PUBLIC_FEED_ADAPTER_ID = "deribit_public_book_pre_normalization_adapter_v1"
DERIBIT_PUBLIC_BOOK_DIALECT_ID = "deribit:l2_orderbook:book_instrument_interval"
DERIBIT_PUBLIC_BOOK_CHANNEL = "book.BTC-PERPETUAL.none.10.100ms"
DERIBIT_PUBLIC_PROD_WS_URL = "wss://www.deribit.com/ws/api/v2"
DERIBIT_PUBLIC_TESTNET_WS_URL = "wss://test.deribit.com/ws/api/v2"
PUBLIC_MARKET_DATA_ONLY = "PUBLIC_MARKET_DATA_ONLY"

_NS_PER_MS = 1_000_000
_PUBLIC_BOOK_EVENT_TYPES = frozenset({"snapshot", "change", "delta", "unspecified"})
_PRIVATE_OR_EXECUTION_KEYS = frozenset(
    {
        "api" + "_key",
        "auth",
        "balance",
        "client" + "_secret",
        "credential",
        "deposit",
        "margin",
        "order_id",
        "position",
        "private",
        "secret",
        "signature",
        "token",
        "trade_order",
        "withdraw",
    }
)
_PRIVATE_OR_EXECUTION_METHOD_MARKERS = frozenset(
    {
        "private/",
        "auth",
        "buy",
        "cancel",
        "edit",
        "sell",
        "submit",
        "withdraw",
    }
)


@dataclass(frozen=True)
class DeribitBookLevel:
    price: float
    amount: float


@dataclass(frozen=True)
class DeribitPublicBookObservation:
    adapter_id: str
    dialect_id: str
    venue_id: VenueId
    feed_type: PublicFeedType
    channel: str
    instrument_name: str
    event_type: str
    event_time_ns: int
    received_at_ns: int
    receive_lag_ns: int
    change_id: int
    prev_change_id: int | None
    bids: tuple[DeribitBookLevel, ...]
    asks: tuple[DeribitBookLevel, ...]
    normalized: bool = False


@dataclass(frozen=True)
class DeribitPublicFeedParseResult:
    accepted: bool
    observation: DeribitPublicBookObservation | None
    rejection_reasons: tuple[str, ...]


@dataclass(frozen=True)
class DeribitPublicFeedSmokeRequest:
    ws_url: str
    channel: str
    timeout_seconds: int
    max_events: int
    artifact_path: str
    run_mode: str = PUBLIC_MARKET_DATA_ONLY
    dry_run: bool = True


@dataclass(frozen=True)
class DeribitPublicFeedSmokePlan:
    accepted: bool
    adapter_id: str
    ws_url: str | None
    channel: str | None
    subscription_message: dict[str, object] | None
    timeout_seconds: int | None
    max_events: int | None
    artifact_path: str | None
    network_auto_start: bool
    rejection_reasons: tuple[str, ...]


def deribit_public_book_dialect():
    ready = tuple(spec for spec in connector_ready_dialects() if spec.dialect_id == DERIBIT_PUBLIC_BOOK_DIALECT_ID)
    if len(ready) != 1:
        return None
    return ready[0]


def parse_deribit_public_book_payload(
    payload: str | dict[str, Any],
    *,
    received_at_ns: int,
    prior_change_id: int | None = None,
) -> DeribitPublicFeedParseResult:
    reasons: list[str] = []
    spec = deribit_public_book_dialect()
    if spec is None:
        reasons.append("deribit_public_feed:dialect_not_ready")
        return _parse_result(None, reasons)

    if not _positive_int(received_at_ns):
        reasons.append("deribit_public_feed:received_at_ns_invalid")

    raw_payload = _payload_mapping(payload, reasons)
    if raw_payload is None:
        return _parse_result(None, reasons)

    if _contains_private_or_execution_surface(raw_payload):
        reasons.append("deribit_public_feed:private_or_execution_payload")

    channel, data = _extract_channel_and_data(raw_payload, reasons)
    if not _non_empty(channel) or data is None:
        return _parse_result(None, reasons)

    if not channel.startswith("book."):
        reasons.append("deribit_public_feed:channel_not_public_book")
    if channel != DERIBIT_PUBLIC_BOOK_CHANNEL:
        reasons.append("deribit_public_feed:unexpected_channel")

    instrument_name = _instrument_from_channel(channel)
    if not instrument_name:
        reasons.append("deribit_public_feed:instrument_missing")
    elif data.get("instrument_name") not in {instrument_name, None}:
        reasons.append("deribit_public_feed:instrument_mismatch")

    event_type = data.get("type")
    if event_type is None:
        event_type = "unspecified"
    if event_type not in _PUBLIC_BOOK_EVENT_TYPES:
        reasons.append("deribit_public_feed:event_type_unsupported")

    event_time_ns = _event_time_ns(data.get("timestamp"), reasons)
    receive_lag_ns = (
        received_at_ns - event_time_ns if event_time_ns is not None and _positive_int(received_at_ns) else None
    )
    if receive_lag_ns is None:
        reasons.append("deribit_public_feed:receive_lag_unavailable")
    elif receive_lag_ns < 0:
        reasons.append("deribit_public_feed:received_before_event")
    else:
        if receive_lag_ns > spec.max_receive_lag_ns:
            reasons.append("deribit_public_feed:receive_lag_breach")
        if receive_lag_ns > spec.max_staleness_ns:
            reasons.append("deribit_public_feed:stale_event")

    change_id = _optional_int(data.get("change_id"))
    if change_id is None:
        reasons.append("deribit_public_feed:change_id_missing")
    elif change_id < 0:
        reasons.append("deribit_public_feed:change_id_invalid")
    prev_change_id = _optional_int(data.get("prev_change_id"))
    if prev_change_id is not None and prev_change_id < 0:
        reasons.append("deribit_public_feed:prev_change_id_invalid")

    if prior_change_id is not None:
        if not _non_negative_int(prior_change_id):
            reasons.append("deribit_public_feed:prior_change_id_invalid")
        elif prev_change_id is None:
            reasons.append("deribit_public_feed:sequence_gap_unresolved")
        elif prev_change_id != prior_change_id:
            reasons.append("deribit_public_feed:sequence_gap_detected")

    if spec.max_gap_tolerance != 0:
        reasons.append("deribit_public_feed:gap_policy_not_fail_closed")
    if spec.supports_checksum is not False or spec.checksum_model is not FeedChecksumModel.NONE:
        reasons.append("deribit_public_feed:checksum_policy_mismatch")
    if spec.sequence_model is not FeedSequenceModel.SNAPSHOT_DELTA_RANGE:
        reasons.append("deribit_public_feed:sequence_policy_mismatch")

    bids = _levels(data.get("bids"), "bids", reasons)
    asks = _levels(data.get("asks"), "asks", reasons)

    if reasons:
        return _parse_result(None, reasons)

    observation = DeribitPublicBookObservation(
        adapter_id=DERIBIT_PUBLIC_FEED_ADAPTER_ID,
        dialect_id=spec.dialect_id,
        venue_id=VenueId.DERIBIT,
        feed_type=PublicFeedType.L2_ORDERBOOK,
        channel=channel,
        instrument_name=instrument_name,
        event_type=str(event_type),
        event_time_ns=event_time_ns or 0,
        received_at_ns=received_at_ns,
        receive_lag_ns=receive_lag_ns or 0,
        change_id=change_id or 0,
        prev_change_id=prev_change_id,
        bids=tuple(bids),
        asks=tuple(asks),
    )
    return _parse_result(observation, ())


def build_deribit_public_feed_smoke_plan(request: DeribitPublicFeedSmokeRequest) -> DeribitPublicFeedSmokePlan:
    reasons: list[str] = []
    spec = deribit_public_book_dialect()
    if spec is None:
        reasons.append("deribit_public_feed:dialect_not_ready")
    if request.run_mode != PUBLIC_MARKET_DATA_ONLY:
        reasons.append("deribit_public_feed:run_mode_not_public_market_data_only")
    if request.dry_run is not True:
        reasons.append("deribit_public_feed:dry_run_required")
    if request.ws_url not in {DERIBIT_PUBLIC_PROD_WS_URL, DERIBIT_PUBLIC_TESTNET_WS_URL}:
        reasons.append("deribit_public_feed:ws_url_not_approved_public")
    if request.channel != DERIBIT_PUBLIC_BOOK_CHANNEL:
        reasons.append("deribit_public_feed:unexpected_channel")
    if not isinstance(request.timeout_seconds, int) or isinstance(request.timeout_seconds, bool):
        reasons.append("deribit_public_feed:timeout_invalid")
    elif request.timeout_seconds <= 0 or request.timeout_seconds > 60:
        reasons.append("deribit_public_feed:timeout_invalid")
    if not isinstance(request.max_events, int) or isinstance(request.max_events, bool):
        reasons.append("deribit_public_feed:max_events_invalid")
    elif request.max_events <= 0 or request.max_events > 100:
        reasons.append("deribit_public_feed:max_events_invalid")
    if not _non_empty(request.artifact_path):
        reasons.append("deribit_public_feed:artifact_path_required")
    elif Path(request.artifact_path).is_absolute() is False:
        reasons.append("deribit_public_feed:artifact_path_must_be_explicit")

    accepted = not reasons
    return DeribitPublicFeedSmokePlan(
        accepted=accepted,
        adapter_id=DERIBIT_PUBLIC_FEED_ADAPTER_ID,
        ws_url=request.ws_url if accepted else None,
        channel=request.channel if accepted else None,
        subscription_message=(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "public/subscribe",
                "params": {"channels": [request.channel]},
            }
            if accepted
            else None
        ),
        timeout_seconds=request.timeout_seconds if accepted else None,
        max_events=request.max_events if accepted else None,
        artifact_path=request.artifact_path if accepted else None,
        network_auto_start=False,
        rejection_reasons=tuple(dict.fromkeys(reasons)),
    )


def deribit_public_book_observation_to_dict(observation: DeribitPublicBookObservation) -> dict[str, object]:
    return {
        "adapter_id": observation.adapter_id,
        "dialect_id": observation.dialect_id,
        "venue_id": observation.venue_id.value,
        "feed_type": observation.feed_type.value,
        "channel": observation.channel,
        "instrument_name": observation.instrument_name,
        "event_type": observation.event_type,
        "event_time_ns": observation.event_time_ns,
        "received_at_ns": observation.received_at_ns,
        "receive_lag_ns": observation.receive_lag_ns,
        "change_id": observation.change_id,
        "prev_change_id": observation.prev_change_id,
        "bids": [{"price": level.price, "amount": level.amount} for level in observation.bids],
        "asks": [{"price": level.price, "amount": level.amount} for level in observation.asks],
        "normalized": observation.normalized,
    }


def _parse_result(
    observation: DeribitPublicBookObservation | None,
    reasons: tuple[str, ...] | list[str],
) -> DeribitPublicFeedParseResult:
    normalized_reasons = tuple(dict.fromkeys(reasons))
    return DeribitPublicFeedParseResult(
        accepted=observation is not None and normalized_reasons == (),
        observation=observation,
        rejection_reasons=normalized_reasons,
    )


def _payload_mapping(payload: str | dict[str, Any], reasons: list[str]) -> dict[str, Any] | None:
    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            reasons.append("deribit_public_feed:json_malformed")
            return None
        if not isinstance(decoded, dict):
            reasons.append("deribit_public_feed:payload_not_mapping")
            return None
        return decoded
    if isinstance(payload, dict):
        return payload
    reasons.append("deribit_public_feed:payload_not_mapping")
    return None


def _extract_channel_and_data(
    payload: dict[str, Any],
    reasons: list[str],
) -> tuple[str, dict[str, Any] | None]:
    params = payload.get("params")
    if isinstance(params, dict):
        channel = params.get("channel")
        data = params.get("data")
        if isinstance(channel, str) and isinstance(data, dict):
            return channel, data

    channel = payload.get("channel")
    data = payload.get("data", payload)
    if isinstance(channel, str) and isinstance(data, dict):
        return channel, data

    reasons.append("deribit_public_feed:subscription_envelope_malformed")
    return "", None


def _contains_private_or_execution_surface(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).lower()
            item_text = str(item).lower() if isinstance(item, str) else ""
            if key_text in _PRIVATE_OR_EXECUTION_KEYS:
                return True
            if key_text == "method" and any(marker in item_text for marker in _PRIVATE_OR_EXECUTION_METHOD_MARKERS):
                return True
            if _contains_private_or_execution_surface(item):
                return True
    elif isinstance(value, list | tuple):
        return any(_contains_private_or_execution_surface(item) for item in value)
    return False


def _instrument_from_channel(channel: str) -> str:
    parts = channel.split(".")
    if len(parts) < 2:
        return ""
    return parts[1]


def _event_time_ns(value: object, reasons: list[str]) -> int | None:
    timestamp_ms = _optional_int(value)
    if timestamp_ms is None or timestamp_ms <= 0:
        reasons.append("deribit_public_feed:event_timestamp_missing")
        return None
    return timestamp_ms * _NS_PER_MS


def _levels(value: object, field_name: str, reasons: list[str]) -> tuple[DeribitBookLevel, ...]:
    if not isinstance(value, list | tuple) or not value:
        reasons.append(f"deribit_public_feed:{field_name}_missing")
        return ()
    result: list[DeribitBookLevel] = []
    for item in value:
        if not isinstance(item, list | tuple) or len(item) < 2:
            reasons.append(f"deribit_public_feed:{field_name}_malformed")
            return ()
        price_index = 1 if isinstance(item[0], str) and len(item) >= 3 else 0
        amount_index = price_index + 1
        price = _finite_positive_float(item[price_index])
        amount = _finite_non_negative_float(item[amount_index])
        if price is None or amount is None:
            reasons.append(f"deribit_public_feed:{field_name}_malformed")
            return ()
        result.append(DeribitBookLevel(price=price, amount=amount))
    return tuple(result)


def _optional_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _finite_positive_float(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        result = float(value)
        if result > 0.0 and result < float("inf"):
            return result
    return None


def _finite_non_negative_float(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        result = float(value)
        if result >= 0.0 and result < float("inf"):
            return result
    return None


__all__ = [
    "DERIBIT_PUBLIC_BOOK_CHANNEL",
    "DERIBIT_PUBLIC_BOOK_DIALECT_ID",
    "DERIBIT_PUBLIC_FEED_ADAPTER_ID",
    "DERIBIT_PUBLIC_PROD_WS_URL",
    "DERIBIT_PUBLIC_TESTNET_WS_URL",
    "PUBLIC_MARKET_DATA_ONLY",
    "DeribitBookLevel",
    "DeribitPublicBookObservation",
    "DeribitPublicFeedParseResult",
    "DeribitPublicFeedSmokePlan",
    "DeribitPublicFeedSmokeRequest",
    "build_deribit_public_feed_smoke_plan",
    "deribit_public_book_dialect",
    "deribit_public_book_observation_to_dict",
    "parse_deribit_public_book_payload",
]
