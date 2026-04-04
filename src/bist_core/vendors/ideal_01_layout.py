from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from struct import Struct
from typing import Any

_REC32 = Struct("<I7f")


@dataclass(frozen=True)
class IdealIntraday32Bar:
    raw_time_code: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float
    reserved: float


def _plausibility_reason(rec: IdealIntraday32Bar) -> str | None:
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
    if rec.raw_time_code <= 0:
        return "non_positive_time_code"
    return None


def _audit_with_header(raw: bytes, header_bytes: int, tail_n: int) -> dict[str, Any]:
    payload = raw[header_bytes:]
    if len(payload) <= 0 or len(payload) % _REC32.size != 0:
        raise ValueError(
            f"header={header_bytes} leaves non-divisible payload: {len(payload)} for rec={_REC32.size}"
        )

    rows: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []

    for i in range(0, len(payload), _REC32.size):
        rec = IdealIntraday32Bar(*_REC32.unpack_from(payload, i))
        reason = _plausibility_reason(rec)
        if reason is not None:
            anomalies.append(
                {
                    "offset": header_bytes + i,
                    "reason": reason,
                    "raw_time_code": rec.raw_time_code,
                    "open": rec.open,
                    "high": rec.high,
                    "low": rec.low,
                    "close": rec.close,
                    "volume": rec.volume,
                    "turnover": rec.turnover,
                    "reserved": rec.reserved,
                }
            )
            continue
        rows.append(asdict(rec))

    record_count = len(payload) // _REC32.size
    anomaly_count = len(anomalies)
    valid_count = len(rows)
    anomaly_ratio = (anomaly_count / record_count) if record_count else 1.0

    return {
        "header_bytes": header_bytes,
        "record_bytes": _REC32.size,
        "record_count": record_count,
        "valid_count": valid_count,
        "anomaly_count": anomaly_count,
        "anomaly_ratio": round(anomaly_ratio, 6),
        "first_anomalies": anomalies[:8],
        "tail_rows": rows[-tail_n:],
    }


def find_best_ideal_01_layout(
    path: str | Path,
    *,
    header_candidates: list[int] | None = None,
    tail_n: int = 8,
) -> dict[str, Any]:
    p = Path(path)
    raw = p.read_bytes()

    if header_candidates is None:
        header_candidates = [0, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 256]

    candidates: list[dict[str, Any]] = []
    for header in header_candidates:
        if len(raw) <= header:
            continue
        payload = len(raw) - header
        if payload % _REC32.size != 0:
            continue
        try:
            audited = _audit_with_header(raw, header, tail_n)
            candidates.append(audited)
        except Exception:
            continue

    if not candidates:
        raise ValueError(f"No valid 32-byte intraday layout candidates for file: {p}")

    max_record_count = max(x["record_count"] for x in candidates)
    min_record_count = max(1, int(max_record_count * 0.95))

    narrowed = [x for x in candidates if x["record_count"] >= min_record_count]
    for item in narrowed:
        item["coverage_ratio"] = round(
            (item["record_count"] / max_record_count) if max_record_count else 0.0,
            6,
        )

    narrowed.sort(
        key=lambda x: (
            x["anomaly_ratio"],
            -x["record_count"],
            -x["valid_count"],
            x["header_bytes"],
        )
    )
    best = narrowed[0]

    return {
        "path": str(p),
        "size": len(raw),
        "candidate_count": len(candidates),
        "narrowed_candidate_count": len(narrowed),
        "best": best,
        "top_candidates": narrowed[:10],
    }


def audit_ideal_01_file(path: str | Path, tail_n: int = 8) -> dict[str, Any]:
    return find_best_ideal_01_layout(path, tail_n=tail_n)
