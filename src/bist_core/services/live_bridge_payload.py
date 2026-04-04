from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _pick(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _as_float(value: Any, digits: int = 2) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def normalize_live_bridge_payload(row: Mapping[str, Any] | dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        return {}

    normalized = dict(row)

    open_v = _as_float(_pick(normalized, "current_open", "last_open", "open"))
    high_v = _as_float(_pick(normalized, "current_high", "last_high", "high"))
    low_v = _as_float(_pick(normalized, "current_low", "last_low", "low"))
    close_v = _as_float(_pick(normalized, "current_price", "last_price", "current_close", "last_close", "close"))

    volume_v = _as_int(_pick(normalized, "current_volume", "last_volume", "volume"))
    turnover_v = _as_int(_pick(normalized, "current_turnover", "last_turnover", "turnover"))
    raw_time_v = _pick(normalized, "last_raw_time_code", "raw_time_code")

    if open_v is not None:
        normalized["current_open"] = open_v
        normalized["last_open"] = open_v
        normalized["open"] = open_v

    if high_v is not None:
        normalized["current_high"] = high_v
        normalized["last_high"] = high_v
        normalized["high"] = high_v

    if low_v is not None:
        normalized["current_low"] = low_v
        normalized["last_low"] = low_v
        normalized["low"] = low_v

    if close_v is not None:
        normalized["current_close"] = close_v
        normalized["last_close"] = close_v
        normalized["close"] = close_v
        normalized["current_price"] = close_v
        normalized["last_price"] = close_v
        normalized["price"] = close_v
        normalized["live_price"] = close_v
        normalized["asof_price"] = close_v

    if volume_v is not None:
        normalized["current_volume"] = volume_v
        normalized["last_volume"] = volume_v
        normalized["volume"] = volume_v

    if turnover_v is not None:
        normalized["current_turnover"] = turnover_v
        normalized["last_turnover"] = turnover_v
        normalized["turnover"] = turnover_v

    if raw_time_v is not None:
        normalized["raw_time_code"] = raw_time_v
        normalized["last_raw_time_code"] = raw_time_v

    for key in ("header_bytes", "record_bytes", "record_count", "valid_count", "anomaly_count"):
        if key in normalized and normalized[key] is not None:
            normalized[key] = _as_int(normalized[key])


    for key in ("anomaly_ratio", "coverage_ratio"):
        if key in normalized and normalized[key] is not None:
            normalized[key] = _as_float(normalized[key], digits=6)

    return normalized
