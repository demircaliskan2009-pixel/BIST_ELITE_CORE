"""iDeal binary data decoder — safe, auto-detect, deterministic."""

from __future__ import annotations

import struct

from bist_core.models.ohlcv import OHLCVBar


def _median(values):
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return (s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0)


def _validate_timestamps(ts_list):
    if not ts_list:
        return 0.0

    valid = 0
    prev = None

    for ts in ts_list:
        if not isinstance(ts, int):
            continue

        if ts < 946684800 or ts > 2051222400:
            continue

        if prev is None or ts > prev:
            valid += 1
            prev = ts

    return valid / max(len(ts_list), 1)


def _validate_prices(closes):
    if not closes:
        return 0.0

    med = _median(closes)
    if med <= 0:
        return 0.0

    valid = 0
    for p in closes:
        if not isinstance(p, (int, float)):
            continue
        if p <= 0:
            continue
        if p > med * 10:
            continue
        valid += 1

    return valid / max(len(closes), 1)


def _validate_volumes(vols):
    if not vols:
        return 0.0

    med = _median(vols)
    if med <= 0:
        return 0.0

    valid = 0
    for v in vols:
        if not isinstance(v, (int, float)):
            continue
        if v < 0:
            continue
        if v > med * 20:
            continue
        valid += 1

    return valid / max(len(vols), 1)


def _consistency_score(parsed):
    if not parsed:
        return 0.0

    ts = []
    closes = []
    vols = []

    for b in parsed:
        try:
            ts.append(int(b.timestamp))
            closes.append(float(b.close))
            vols.append(float(b.volume))
        except Exception:
            continue

    ts_score = _validate_timestamps(ts)
    price_score = _validate_prices(closes)
    vol_score = _validate_volumes(vols)

    return 0.4 * ts_score + 0.3 * price_score + 0.3 * vol_score


def _is_valid_ohlcv(o, h, l, c, v) -> bool:
    if not all(isinstance(x, (int, float)) for x in (o, h, l, c, v)):
        return False
    if v < 0:
        return False
    if not (l <= o <= h and l <= c <= h):
        return False
    return True


def _try_parse_records(data: bytes, record_size: int, symbol: str, debug: bool = False):
    n = len(data) // record_size

    formats = [
        "<q5f",
        "<q5d",
        "<i5f",
        "<i5d",
    ]

    best_result = []
    best_score = 0.0
    best_meta = None

    for fmt in formats:
        try:
            size = struct.calcsize(fmt)
            if size > record_size:
                continue

            parsed = []

            for i in range(n):
                chunk = data[i * record_size : i * record_size + size]
                if len(chunk) < size:
                    continue

                vals = struct.unpack(fmt, chunk)

                ts = vals[0]
                o, h, l, c, v = vals[1:6]

                if _is_valid_ohlcv(o, h, l, c, v):
                    parsed.append(
                        OHLCVBar(
                            timestamp=str(int(ts)),
                            symbol=symbol,
                            open=float(o),
                            high=float(h),
                            low=float(l),
                            close=float(c),
                            volume=float(v),
                        )
                    )

            if len(parsed) < 10:
                continue

            score = _consistency_score(parsed)

            if score > best_score:
                best_score = score
                best_result = parsed
                best_meta = (fmt, record_size, len(parsed))

        except Exception:
            continue

    if debug and best_meta:
        fmt, rsize, count = best_meta
        print(f"[IDEAL PARSER] fmt={fmt} record_size={rsize} valid={count} score={best_score:.3f}")

    if best_score > 0.6 and len(best_result) >= 50:
        return best_result

    return []


def parse_ideal_binary(path: str, symbol: str, debug: bool = False) -> list:
    try:
        with open(path, "rb") as f:
            data = f.read()
    except Exception:
        return []

    if not data or len(data) < 32:
        return []

    for record_size in (32, 40, 48):
        parsed = _try_parse_records(data, record_size, symbol, debug=debug)
        if parsed:
            return parsed

    return []


def parse_ideal_file(path: str, symbol: str, debug: bool = False) -> list:
    return parse_ideal_binary(path, symbol, debug=debug)


__all__ = ["parse_ideal_file", "parse_ideal_binary", "_is_valid_ohlcv"]


if __name__ == "__main__":
    path = r"C:\iDeal\ChartData\IMKBH\G\IMKBH'ASELS.G"
    bars = parse_ideal_file(path, "ASELS", debug=True)

    print("parsed:", len(bars))
    for b in bars[:3]:
        print(vars(b))
