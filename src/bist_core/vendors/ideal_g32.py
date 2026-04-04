from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from struct import Struct
from typing import Any

_RECORD = Struct("<I7f")


@dataclass(frozen=True)
class IdealG32Bar:
    raw_date_code: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float
    reserved: float


def _plausibility_reason(rec: IdealG32Bar) -> str | None:
    if min(rec.open, rec.high, rec.low, rec.close) < 0:
        return "negative_price"
    if rec.high < rec.low:
        return "high_below_low"
    if rec.high < max(rec.open, rec.close):
        return "high_below_open_or_close"
    if rec.low > min(rec.open, rec.close):
        return "low_above_open_or_close"
    if rec.volume < 0:
        return "negative_volume"
    if rec.turnover < 0:
        return "negative_turnover"
    return None


def parse_g32_file(path: str | Path, strict: bool = True) -> dict[str, Any]:
    p = Path(path)
    raw = p.read_bytes()
    if len(raw) % _RECORD.size != 0:
        raise ValueError(f"Unexpected .G size for 32-byte layout: {len(raw)}")

    rows: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []

    for off in range(0, len(raw), _RECORD.size):
        rec = IdealG32Bar(*_RECORD.unpack_from(raw, off))
        reason = _plausibility_reason(rec)
        if reason is not None:
            item = {
                "offset": off,
                "reason": reason,
                "raw_date_code": rec.raw_date_code,
                "open": rec.open,
                "high": rec.high,
                "low": rec.low,
                "close": rec.close,
                "volume": rec.volume,
                "turnover": rec.turnover,
                "reserved": rec.reserved,
            }
            anomalies.append(item)
            if strict:
                raise ValueError(f"Implausible bar at offset={off}: {reason}: {rec}")
            continue

        rows.append(asdict(rec))

    return {
        "path": str(p),
        "record_bytes": _RECORD.size,
        "record_count": len(raw) // _RECORD.size,
        "valid_count": len(rows),
        "anomaly_count": len(anomalies),
        "rows": rows,
        "anomalies": anomalies,
    }


def tail_g32_file(path: str | Path, n: int = 5, strict: bool = False) -> list[dict[str, Any]]:
    got = parse_g32_file(path, strict=strict)
    return got["rows"][-n:]


def audit_g32_file(path: str | Path, tail_n: int = 8) -> dict[str, Any]:
    got = parse_g32_file(path, strict=False)
    return {
        "path": got["path"],
        "record_bytes": got["record_bytes"],
        "record_count": got["record_count"],
        "valid_count": got["valid_count"],
        "anomaly_count": got["anomaly_count"],
        "anomaly_ratio": round(
            (got["anomaly_count"] / got["record_count"]) if got["record_count"] else 0.0, 6
        ),
        "first_anomalies": got["anomalies"][:8],
        "tail_rows": got["rows"][-tail_n:],
    }
