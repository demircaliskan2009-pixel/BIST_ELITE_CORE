from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

DERIBIT_PUBLIC_WS_OPERATOR_AUTHORIZATION = "PUBLIC_MARKET_DATA_ONLY"
DERIBIT_OFFICIAL_PUBLIC_WS_URL = "wss://www.deribit.com/ws/api/v2"
DERIBIT_DEFAULT_PUBLIC_CHANNEL = "book.BTC-PERPETUAL.none.10.100ms"
DERIBIT_PUBLIC_WS_MAX_DURATION_SECONDS = 30.0
DERIBIT_PUBLIC_WS_MAX_MESSAGES = 100
DERIBIT_PUBLIC_WS_DEFAULT_SAMPLE_EVENTS = 5
DERIBIT_PUBLIC_WS_MAX_SAMPLE_EVENTS = 100
DERIBIT_PUBLIC_WS_MAX_RECEIVE_LAG_MS = 60_000

_FORBIDDEN_CHANNEL_TOKENS = (
    "user",
    "private",
    "auth",
    "raw",
    "order",
    "portfolio",
    "position",
    "account",
)
_INSTRUMENT_PATTERN = r"[A-Z0-9]+(?:-[A-Z0-9]+)*"
_AGGREGATED_CHANNEL_PATTERNS = (
    re.compile(rf"^book\.{_INSTRUMENT_PATTERN}\.none\.(?:1|10|20|50|100)\.100ms$"),
    re.compile(rf"^trades\.{_INSTRUMENT_PATTERN}\.100ms$"),
    re.compile(rf"^ticker\.{_INSTRUMENT_PATTERN}\.100ms$"),
)


class DeribitPublicWsSmokeError(ValueError):
    """Raised when Deribit public WebSocket smoke payloads are malformed."""


@dataclass(frozen=True)
class DeribitPublicWsSmokeConfig:
    ws_url: str = DERIBIT_OFFICIAL_PUBLIC_WS_URL
    channels: tuple[str, ...] = (DERIBIT_DEFAULT_PUBLIC_CHANNEL,)
    operator_authorization: str = ""
    dry_run: bool = True
    duration_seconds: float = 5.0
    max_messages: int = 10
    max_receive_lag_ms: int = 5_000
    sample_limit: int = DERIBIT_PUBLIC_WS_DEFAULT_SAMPLE_EVENTS
    request_id: int = 1


@dataclass(frozen=True)
class DeribitPublicWsSmokeEvent:
    channel: str | None
    received_at_ns: int
    event_time_ms: int | None
    receive_lag_ms: int | None
    sequence_id: int | None
    prev_sequence_id: int | None
    payload_kind: str
    payload_sample: dict[str, object]
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class DeribitPublicWsSmokeResult:
    accepted: bool
    ws_url: str | None
    channels: tuple[str, ...]
    operator_authorization: str | None
    dry_run: bool
    duration_seconds: float | None
    max_messages: int | None
    message_count: int
    sample_events: tuple[DeribitPublicWsSmokeEvent, ...]
    started_at_ns: int | None
    completed_at_ns: int | None
    rejection_reasons: tuple[str, ...]


class _DeribitPublicWsRuntimeRejected(RuntimeError):
    def __init__(self, reasons: tuple[str, ...]) -> None:
        super().__init__(";".join(reasons))
        self.reasons = reasons


def validate_deribit_public_ws_smoke_config(config: object) -> tuple[str, ...]:
    if not isinstance(config, DeribitPublicWsSmokeConfig):
        return ("deribit_ws:config_malformed",)

    reasons: list[str] = []
    if not config.operator_authorization:
        reasons.append("deribit_ws:authorization_missing")
    elif config.operator_authorization != DERIBIT_PUBLIC_WS_OPERATOR_AUTHORIZATION:
        reasons.append("deribit_ws:authorization_invalid")
    if config.dry_run is not True:
        reasons.append("deribit_ws:dry_run_required")
    if config.ws_url != DERIBIT_OFFICIAL_PUBLIC_WS_URL:
        reasons.append("deribit_ws:url_not_allowed")
    if not isinstance(config.duration_seconds, int | float) or isinstance(config.duration_seconds, bool):
        reasons.append("deribit_ws:duration_unbounded")
    elif not (0.0 < float(config.duration_seconds) <= DERIBIT_PUBLIC_WS_MAX_DURATION_SECONDS):
        reasons.append("deribit_ws:duration_unbounded")
    if not _bounded_int(config.max_messages, minimum=1, maximum=DERIBIT_PUBLIC_WS_MAX_MESSAGES):
        reasons.append("deribit_ws:max_messages_unbounded")
    if not _bounded_int(config.max_receive_lag_ms, minimum=1, maximum=DERIBIT_PUBLIC_WS_MAX_RECEIVE_LAG_MS):
        reasons.append("deribit_ws:receive_lag_budget_invalid")
    if not _bounded_int(config.sample_limit, minimum=1, maximum=DERIBIT_PUBLIC_WS_MAX_SAMPLE_EVENTS):
        reasons.append("deribit_ws:sample_limit_invalid")
    if not _bounded_int(config.request_id, minimum=1, maximum=1_000_000):
        reasons.append("deribit_ws:request_id_invalid")
    if not isinstance(config.channels, tuple) or not config.channels:
        reasons.append("deribit_ws:channel_forbidden")
    else:
        for channel in config.channels:
            if not _channel_allowed(channel):
                reasons.append("deribit_ws:channel_forbidden")
    return tuple(dict.fromkeys(reasons))


def run_deribit_public_ws_smoke_test(config: DeribitPublicWsSmokeConfig) -> DeribitPublicWsSmokeResult:
    config_reasons = validate_deribit_public_ws_smoke_config(config)
    started_at_ns = time.time_ns()
    if config_reasons:
        return _result_from_events(
            config=config,
            events=(),
            started_at_ns=started_at_ns,
            completed_at_ns=time.time_ns(),
            rejection_reasons=config_reasons,
        )

    try:
        received_messages = _receive_deribit_public_ws_messages(config)
    except _DeribitPublicWsRuntimeRejected as exc:
        return _result_from_events(
            config=config,
            events=(),
            started_at_ns=started_at_ns,
            completed_at_ns=time.time_ns(),
            rejection_reasons=exc.reasons,
        )
    except Exception:
        return _result_from_events(
            config=config,
            events=(),
            started_at_ns=started_at_ns,
            completed_at_ns=time.time_ns(),
            rejection_reasons=("deribit_ws:runtime_error",),
        )

    events, event_reasons = _events_from_received_messages(config, received_messages)
    reasons = list(event_reasons)
    if not events:
        reasons.append("deribit_ws:no_messages")
    return _result_from_events(
        config=config,
        events=events,
        started_at_ns=started_at_ns,
        completed_at_ns=time.time_ns(),
        rejection_reasons=tuple(reasons),
    )


def deribit_public_ws_smoke_result_to_dict(result: DeribitPublicWsSmokeResult) -> dict[str, object]:
    return {
        "accepted": result.accepted,
        "ws_url": result.ws_url,
        "channels": list(result.channels),
        "operator_authorization": result.operator_authorization,
        "dry_run": result.dry_run,
        "duration_seconds": result.duration_seconds,
        "max_messages": result.max_messages,
        "message_count": result.message_count,
        "sample_events": [_event_to_dict(event) for event in result.sample_events],
        "started_at_ns": result.started_at_ns,
        "completed_at_ns": result.completed_at_ns,
        "rejection_reasons": list(result.rejection_reasons),
    }


def deribit_public_ws_smoke_result_from_dict(payload: object) -> DeribitPublicWsSmokeResult:
    data = _mapping(payload, "Deribit public WebSocket smoke result")
    return DeribitPublicWsSmokeResult(
        accepted=_bool(data.get("accepted"), "accepted"),
        ws_url=_optional_string(data.get("ws_url"), "ws_url"),
        channels=_string_tuple(data.get("channels"), "channels"),
        operator_authorization=_optional_string(data.get("operator_authorization"), "operator_authorization"),
        dry_run=_bool(data.get("dry_run"), "dry_run"),
        duration_seconds=_optional_positive_float(data.get("duration_seconds"), "duration_seconds"),
        max_messages=_optional_positive_int(data.get("max_messages"), "max_messages"),
        message_count=_non_negative_int(data.get("message_count"), "message_count"),
        sample_events=tuple(_event_from_dict(item) for item in _sequence(data.get("sample_events"), "sample_events")),
        started_at_ns=_optional_positive_int(data.get("started_at_ns"), "started_at_ns"),
        completed_at_ns=_optional_positive_int(data.get("completed_at_ns"), "completed_at_ns"),
        rejection_reasons=_string_tuple(data.get("rejection_reasons"), "rejection_reasons"),
    )


def _receive_deribit_public_ws_messages(config: DeribitPublicWsSmokeConfig) -> tuple[tuple[object, int], ...]:
    try:
        import websocket  # type: ignore[import-not-found]
    except Exception as exc:
        raise _DeribitPublicWsRuntimeRejected(("deribit_ws:client_unavailable",)) from exc

    request = {
        "jsonrpc": "2.0",
        "id": config.request_id,
        "method": "public/subscribe",
        "params": {"channels": list(config.channels)},
    }
    received: list[tuple[object, int]] = []
    deadline = time.monotonic() + float(config.duration_seconds)
    try:
        ws = websocket.create_connection(config.ws_url, timeout=min(float(config.duration_seconds), 5.0))
        try:
            ws.send(json.dumps(request, sort_keys=True))
            while len(received) < config.max_messages and time.monotonic() < deadline:
                remaining = max(0.1, min(1.0, deadline - time.monotonic()))
                ws.settimeout(remaining)
                try:
                    raw = ws.recv()
                except Exception as exc:
                    if "timeout" in exc.__class__.__name__.lower():
                        raise _DeribitPublicWsRuntimeRejected(("deribit_ws:timeout",)) from exc
                    raise
                received.append((json.loads(raw), time.time_ns()))
        finally:
            ws.close()
    except _DeribitPublicWsRuntimeRejected:
        raise
    except json.JSONDecodeError as exc:
        raise _DeribitPublicWsRuntimeRejected(("deribit_ws:message_malformed",)) from exc
    except Exception as exc:
        raise _DeribitPublicWsRuntimeRejected(("deribit_ws:runtime_error",)) from exc
    return tuple(received)


def _events_from_received_messages(
    config: DeribitPublicWsSmokeConfig,
    received_messages: tuple[tuple[object, int], ...],
) -> tuple[tuple[DeribitPublicWsSmokeEvent, ...], tuple[str, ...]]:
    events: list[DeribitPublicWsSmokeEvent] = []
    reasons: list[str] = []
    last_sequence_by_channel: dict[str, int] = {}
    for payload, received_at_ns in received_messages:
        event = _event_from_payload(
            config,
            payload,
            received_at_ns=received_at_ns,
            last_sequence_by_channel=last_sequence_by_channel,
        )
        if event is None:
            continue
        events.append(event)
        reasons.extend(event.rejection_reasons)
        if event.channel is not None and event.sequence_id is not None:
            last_sequence_by_channel[event.channel] = event.sequence_id
    return tuple(events), tuple(dict.fromkeys(reasons))


def _event_from_payload(
    config: DeribitPublicWsSmokeConfig,
    payload: object,
    *,
    received_at_ns: int,
    last_sequence_by_channel: dict[str, int],
) -> DeribitPublicWsSmokeEvent | None:
    if _is_control_payload(config, payload):
        return None
    if not isinstance(payload, dict):
        return _malformed_event(received_at_ns)
    if payload.get("method") != "subscription":
        return _malformed_event(received_at_ns)
    params = payload.get("params")
    if not isinstance(params, dict):
        return _malformed_event(received_at_ns)
    channel = params.get("channel")
    data = params.get("data")
    if not isinstance(channel, str) or not _channel_allowed(channel) or not isinstance(data, dict):
        return _malformed_event(received_at_ns, channel=channel if isinstance(channel, str) else None)

    event_time_ms = _optional_int(data.get("timestamp"))
    sequence_id = _sequence_id_from_data(data)
    prev_sequence_id = _prev_sequence_id_from_data(data)
    receive_lag_ms = None
    reasons: list[str] = []
    if event_time_ms is not None:
        receive_lag_ms = received_at_ns // 1_000_000 - event_time_ms
        if receive_lag_ms > config.max_receive_lag_ms:
            reasons.append("deribit_ws:receive_lag_stale")
    previous_sequence_id = last_sequence_by_channel.get(channel)
    if previous_sequence_id is not None and sequence_id is not None:
        if prev_sequence_id is not None and prev_sequence_id != previous_sequence_id:
            reasons.append("deribit_ws:sequence_gap")
        elif prev_sequence_id is None and sequence_id <= previous_sequence_id:
            reasons.append("deribit_ws:sequence_gap")

    return DeribitPublicWsSmokeEvent(
        channel=channel,
        received_at_ns=received_at_ns,
        event_time_ms=event_time_ms,
        receive_lag_ms=receive_lag_ms,
        sequence_id=sequence_id,
        prev_sequence_id=prev_sequence_id,
        payload_kind=_payload_kind(data),
        payload_sample=_payload_sample(data),
        rejection_reasons=tuple(dict.fromkeys(reasons)),
    )


def _is_control_payload(config: DeribitPublicWsSmokeConfig, payload: object) -> bool:
    return isinstance(payload, dict) and (
        payload.get("id") == config.request_id or payload.get("method") in {"heartbeat", "test_request"}
    )


def _malformed_event(received_at_ns: int, *, channel: str | None = None) -> DeribitPublicWsSmokeEvent:
    return DeribitPublicWsSmokeEvent(
        channel=channel,
        received_at_ns=received_at_ns,
        event_time_ms=None,
        receive_lag_ms=None,
        sequence_id=None,
        prev_sequence_id=None,
        payload_kind="malformed",
        payload_sample={},
        rejection_reasons=("deribit_ws:message_malformed",),
    )


def _result_from_events(
    *,
    config: object,
    events: tuple[DeribitPublicWsSmokeEvent, ...],
    started_at_ns: int | None,
    completed_at_ns: int | None,
    rejection_reasons: tuple[str, ...],
) -> DeribitPublicWsSmokeResult:
    if isinstance(config, DeribitPublicWsSmokeConfig):
        sample_limit = config.sample_limit if _bounded_int(config.sample_limit, minimum=1, maximum=10_000) else 1
        reasons = tuple(dict.fromkeys(rejection_reasons))
        return DeribitPublicWsSmokeResult(
            accepted=bool(events) and reasons == (),
            ws_url=config.ws_url,
            channels=config.channels,
            operator_authorization=config.operator_authorization,
            dry_run=config.dry_run,
            duration_seconds=float(config.duration_seconds)
            if isinstance(config.duration_seconds, int | float) and not isinstance(config.duration_seconds, bool)
            else None,
            max_messages=config.max_messages if isinstance(config.max_messages, int) else None,
            message_count=len(events),
            sample_events=tuple(events[:sample_limit]),
            started_at_ns=started_at_ns,
            completed_at_ns=completed_at_ns,
            rejection_reasons=reasons,
        )
    reasons = tuple(dict.fromkeys(("deribit_ws:config_malformed", *rejection_reasons)))
    return DeribitPublicWsSmokeResult(
        accepted=False,
        ws_url=None,
        channels=(),
        operator_authorization=None,
        dry_run=False,
        duration_seconds=None,
        max_messages=None,
        message_count=0,
        sample_events=(),
        started_at_ns=started_at_ns,
        completed_at_ns=completed_at_ns,
        rejection_reasons=reasons,
    )


def _event_to_dict(event: DeribitPublicWsSmokeEvent) -> dict[str, object]:
    return {
        "channel": event.channel,
        "received_at_ns": event.received_at_ns,
        "event_time_ms": event.event_time_ms,
        "receive_lag_ms": event.receive_lag_ms,
        "sequence_id": event.sequence_id,
        "prev_sequence_id": event.prev_sequence_id,
        "payload_kind": event.payload_kind,
        "payload_sample": event.payload_sample,
        "rejection_reasons": list(event.rejection_reasons),
    }


def _event_from_dict(payload: object) -> DeribitPublicWsSmokeEvent:
    data = _mapping(payload, "Deribit public WebSocket smoke event")
    return DeribitPublicWsSmokeEvent(
        channel=_optional_string(data.get("channel"), "channel"),
        received_at_ns=_positive_int(data.get("received_at_ns"), "received_at_ns"),
        event_time_ms=_optional_non_negative_int(data.get("event_time_ms"), "event_time_ms"),
        receive_lag_ms=_optional_int_field(data.get("receive_lag_ms"), "receive_lag_ms"),
        sequence_id=_optional_non_negative_int(data.get("sequence_id"), "sequence_id"),
        prev_sequence_id=_optional_non_negative_int(data.get("prev_sequence_id"), "prev_sequence_id"),
        payload_kind=_non_empty_string(data.get("payload_kind"), "payload_kind"),
        payload_sample=_plain_dict(data.get("payload_sample"), "payload_sample"),
        rejection_reasons=_string_tuple(data.get("rejection_reasons"), "rejection_reasons"),
    )


def _channel_allowed(channel: object) -> bool:
    if not isinstance(channel, str) or not channel:
        return False
    lowered = channel.lower()
    if any(token in lowered for token in _FORBIDDEN_CHANNEL_TOKENS):
        return False
    return any(pattern.match(channel) is not None for pattern in _AGGREGATED_CHANNEL_PATTERNS)


def _payload_kind(data: dict[str, object]) -> str:
    kind = data.get("type")
    if isinstance(kind, str) and kind:
        return kind
    return "market_data"


def _sequence_id_from_data(data: dict[str, object]) -> int | None:
    for field_name in ("change_id", "sequence", "seq"):
        value = _optional_int(data.get(field_name))
        if value is not None and value >= 0:
            return value
    return None


def _prev_sequence_id_from_data(data: dict[str, object]) -> int | None:
    for field_name in ("prev_change_id", "prev_sequence", "prev_seq"):
        value = _optional_int(data.get(field_name))
        if value is not None and value >= 0:
            return value
    return None


def _payload_sample(data: dict[str, object]) -> dict[str, object]:
    sample: dict[str, object] = {}
    for key in ("type", "instrument_name", "timestamp", "change_id", "prev_change_id"):
        value = data.get(key)
        if isinstance(value, str | int | float | bool) or value is None:
            sample[key] = value
    for side in ("bids", "asks", "trades"):
        value = data.get(side)
        if isinstance(value, list | tuple):
            sample[f"{side}_count"] = len(value)
    return sample


def _bounded_int(value: object, *, minimum: int, maximum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum


def _optional_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _mapping(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise DeribitPublicWsSmokeError(f"{field_name} must be a mapping")
    return value


def _plain_dict(value: object, field_name: str) -> dict[str, object]:
    payload = _mapping(value, field_name)
    if any(not isinstance(key, str) for key in payload):
        raise DeribitPublicWsSmokeError(f"{field_name} keys must be strings")
    for item in payload.values():
        if not isinstance(item, str | int | float | bool | type(None)):
            raise DeribitPublicWsSmokeError(f"{field_name} values must be JSON scalars")
    return payload


def _sequence(value: object, field_name: str) -> tuple[object, ...]:
    if not isinstance(value, tuple | list):
        raise DeribitPublicWsSmokeError(f"{field_name} must be a sequence")
    return tuple(value)


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        raise DeribitPublicWsSmokeError(f"{field_name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(item, str) or not item for item in result):
        raise DeribitPublicWsSmokeError(f"{field_name} must contain non-empty strings")
    return result


def _non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise DeribitPublicWsSmokeError(f"{field_name} must be a non-empty string")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _non_empty_string(value, field_name)


def _bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise DeribitPublicWsSmokeError(f"{field_name} must be a boolean")
    return value


def _positive_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise DeribitPublicWsSmokeError(f"{field_name} must be a positive integer")
    return value


def _non_negative_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DeribitPublicWsSmokeError(f"{field_name} must be a non-negative integer")
    return value


def _optional_positive_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    return _positive_int(value, field_name)


def _optional_non_negative_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    return _non_negative_int(value, field_name)


def _optional_int_field(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise DeribitPublicWsSmokeError(f"{field_name} must be an integer")
    return value


def _optional_positive_float(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, int | float) or isinstance(value, bool) or float(value) <= 0.0:
        raise DeribitPublicWsSmokeError(f"{field_name} must be a positive number")
    return float(value)


__all__ = [
    "DERIBIT_DEFAULT_PUBLIC_CHANNEL",
    "DERIBIT_OFFICIAL_PUBLIC_WS_URL",
    "DERIBIT_PUBLIC_WS_DEFAULT_SAMPLE_EVENTS",
    "DERIBIT_PUBLIC_WS_MAX_SAMPLE_EVENTS",
    "DERIBIT_PUBLIC_WS_OPERATOR_AUTHORIZATION",
    "DeribitPublicWsSmokeConfig",
    "DeribitPublicWsSmokeError",
    "DeribitPublicWsSmokeEvent",
    "DeribitPublicWsSmokeResult",
    "deribit_public_ws_smoke_result_from_dict",
    "deribit_public_ws_smoke_result_to_dict",
    "run_deribit_public_ws_smoke_test",
    "validate_deribit_public_ws_smoke_config",
]
