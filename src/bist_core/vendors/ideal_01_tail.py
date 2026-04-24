from __future__ import annotations

from pathlib import Path
from typing import Any

from bist_core.services.live_bridge_payload import normalize_live_bridge_payload
from bist_core.vendors.ideal_01_layout import audit_ideal_01_file


def _ideal_round_price(value: float | int | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def extract_ideal_01_tail(
    path: str | Path,
    *,
    tail_n: int = 64,
) -> dict[str, Any]:
    audited = audit_ideal_01_file(path, tail_n=max(tail_n, 8))
    best = audited["best"]
    rows = list(best.get("tail_rows") or [])
    if not rows:
        raise ValueError(f"No valid tail rows found in intraday file: {path}")

    last = rows[-1]
    return {
        "path": audited["path"],
        "size": audited["size"],
        "header_bytes": best["header_bytes"],
        "record_bytes": best["record_bytes"],
        "record_count": best["record_count"],
        "valid_count": best["valid_count"],
        "anomaly_count": best["anomaly_count"],
        "anomaly_ratio": best["anomaly_ratio"],
        "coverage_ratio": best.get("coverage_ratio"),
        "tail_count": len(rows),
        "last_raw_time_code": last["raw_time_code"],
        "last_open": last["open"],
        "last_high": last["high"],
        "last_low": last["low"],
        "last_close": last["close"],
        "last_volume": last["volume"],
        "last_turnover": last["turnover"],
        "rows": rows,
    }


def build_ideal_01_bridge_row(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    data = extract_ideal_01_tail(p, tail_n=8)

    symbol = data.get("symbol")
    if not symbol:
        stem = p.name
        if "'" in stem:
            stem = stem.split("'", 1)[1]
        if "." in stem:
            stem = stem.rsplit(".", 1)[0]
        symbol = stem.upper()

    raw_time_code = data.get("last_raw_time_code", data.get("raw_time_code"))
    last_open = _ideal_round_price(data.get("last_open", data.get("current_open")))
    last_high = _ideal_round_price(data.get("last_high", data.get("current_high")))
    last_low = _ideal_round_price(data.get("last_low", data.get("current_low")))
    last_close = _ideal_round_price(data.get("last_close", data.get("current_close")))
    last_volume = data.get("last_volume", data.get("current_volume", data.get("volume")))
    last_turnover = data.get("last_turnover", data.get("current_turnover", data.get("turnover")))

    return normalize_live_bridge_payload(
        {
            "symbol": symbol,
            "source_file": p.name,
            "source_period": "01",
            "current_open": last_open,
            "current_high": last_high,
            "current_low": last_low,
            "current_close": last_close,
            "current_price": last_close,
            "last_price": last_close,
            "last_open": last_open,
            "last_high": last_high,
            "last_low": last_low,
            "last_close": last_close,
            "open": last_open,
            "high": last_high,
            "low": last_low,
            "close": last_close,
            "current_volume": last_volume,
            "current_turnover": last_turnover,
            "volume": last_volume,
            "turnover": last_turnover,
            "raw_time_code": raw_time_code,
            "last_raw_time_code": raw_time_code,
            "record_count": data.get("record_count"),
            "valid_count": data.get("valid_count"),
            "anomaly_count": data.get("anomaly_count"),
            "anomaly_ratio": data.get("anomaly_ratio"),
            "coverage_ratio": data.get("coverage_ratio"),
            "header_bytes": data["header_bytes"],
            "record_bytes": data["record_bytes"],
        }
    )

