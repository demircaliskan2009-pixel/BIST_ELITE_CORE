"""
Load full iDeal binary files into OHLCVBar (registry + env path resolution).
"""

from __future__ import annotations

import os
import glob
import struct
from datetime import datetime, timezone
from pathlib import Path
import math
import statistics
from typing import TYPE_CHECKING, Any, Optional

from bist_core.data.ideal_binary_parser import emit_parser_ready_report
from bist_core.data.ideal_timestamp_codec import decode_ideal_struct_timestamp
from bist_core.models.ohlcv import OHLCVBar

if TYPE_CHECKING:
    from bist_core.data.registry import DatasetRegistry


def _normalize_ts(ts: int) -> int:
    """
    Normalize timestamp to seconds.
    Handles ns / us / ms / s automatically.
    """
    if ts > 1e18:  # nanoseconds
        return ts // 1_000_000_000
    if ts > 1e15:  # microseconds
        return ts // 1_000_000
    if ts > 1e12:  # milliseconds
        return ts // 1_000
    return ts


def _filter_recent_bars(bars: list[OHLCVBar], *, max_days: int = 1200) -> list[OHLCVBar]:
    """
    Keep only recent bars based on latest timestamp.
    This guarantees all TFs are aligned in the same era.
    """
    if not bars:
        return bars

    latest_ts = max(_normalize_ts(int(b.timestamp)) for b in bars)
    cutoff = latest_ts - (max_days * 86400)

    filtered = [
        b for b in bars if _normalize_ts(int(b.timestamp)) >= cutoff
    ]

    # ensure strictly increasing timestamps
    filtered = sorted(
        filtered,
        key=lambda x: _normalize_ts(int(x.timestamp)),
    )

    if len(filtered) >= 2:
        assert all(
            _normalize_ts(int(filtered[i].timestamp))
            <= _normalize_ts(int(filtered[i + 1].timestamp))
            for i in range(len(filtered) - 1)
        ), "TIMESTAMP_ORDER_BROKEN"

    print(
        {
            "TF_FILTER": {
                "input": len(bars),
                "output": len(filtered),
                "cutoff_ts": cutoff,
                "latest_ts": latest_ts,
                "normalized": True,
            }
        },
        flush=True,
    )

    return filtered


def _ideal_chart_root_from_env() -> Path:
    root = os.environ.get("BIST_IDEAL_CHART_ROOT", "").strip()
    if root:
        return Path(root).expanduser()
    data_path = os.environ.get("BIST_IDEAL_DATA_PATH", "").strip()
    if not data_path:
        raise RuntimeError(
            "BIST_IDEAL_CHART_ROOT or BIST_IDEAL_DATA_PATH must be set for load_ideal_dataset"
        )
    p = Path(data_path).expanduser()
    # .../IMKBH/01 -> .../IMKBH
    if p.name in ("01", "05", "60", "G", "D", "W", "M"):
        return p.parent
    return p


def resolve_ideal_symbol_path(
    symbol: str,
    timeframe: str,
    *,
    chart_root: Optional[Path] = None,
) -> Path:
    """
    ``<chart_root>/<tf>/IMKBH'<SYMBOL>.<tf>`` (e.g. IMKBH\\01\\IMKBH'ASELS.01).
    """
    sym = str(symbol).strip().upper()
    tf = str(timeframe).strip().lstrip(".")
    root = chart_root if chart_root is not None else _ideal_chart_root_from_env()
    p = resolve_ideal_file(root, sym, tf)
    if p is not None:
        return p
    return root / tf / f"IMKBH'{sym}.{tf}"


def resolve_ideal_file(base_path: Path | str, symbol: str, tf: str) -> Optional[Path]:
    tf_path = Path(base_path) / str(tf).strip().lstrip(".")
    sym = str(symbol).strip().upper()
    tf_s = str(tf).strip().lstrip(".")

    # exact match (fast path)
    direct = tf_path / f"{sym}.{tf_s}"
    if direct.exists():
        return direct

    # IMKBH' prefix match (CRITICAL)
    prefixed = tf_path / f"IMKBH'{sym}.{tf_s}"
    if prefixed.exists():
        return prefixed

    # wildcard fallback (future-proof)
    pattern = str(tf_path / f"*{sym}.{tf_s}")
    matches = glob.glob(pattern)
    if matches:
        return Path(matches[0])

    return None


def _detected_multiplier(raw_close: float) -> float:
    """Single scale factor per bar from raw close (iDeal <10 → ×100), deterministic."""
    xf = float(raw_close)
    if not math.isfinite(xf):
        return 1.0
    if xf < 10.0:
        return 100.0
    return 1.0


_STRUCT_A = "<Ifffff"  # ts uint32, o,h,l,c,v
_STRUCT_B = "<Qfffff"  # ts uint64, o,h,l,c,v
_STRUCT_C = "<iffffffi"  # locked iDeal 32B: ts(i), o,h,l,c,v,extra(f), flag(i)
_STRUCT_A_SIZE = struct.calcsize(_STRUCT_A)
_STRUCT_B_SIZE = struct.calcsize(_STRUCT_B)
_STRUCT_C_SIZE = struct.calcsize(_STRUCT_C)


def _record_valid_ohlc(o: float, h: float, l: float, c: float) -> bool:
    if not all(math.isfinite(x) for x in (o, h, l, c)):
        return False
    return bool(l <= o <= h and l <= c <= h)


def _scan_struct_format(
    data: bytes, fmt: str, rec_size: int, timeframe: str
) -> tuple[int, int, list[tuple[int, float, float, float, float, float]]]:
    """
    Return (total_records, valid_count, valid_rows).

    Timestamp rule: ``decode_ideal_struct_timestamp`` runs ONLY here (or index-based
    reconstruction). Each returned row's ``row[0]`` is **final Unix seconds** — downstream
    must treat it as immutable (no second decode).
    """
    if rec_size <= 0 or len(data) < rec_size:
        return (0, 0, [])
    total = len(data) // rec_size
    rows: list[tuple[int, float, float, float, float, float, str]] = []
    ts_pipeline_emitted = False
    for i in range(total):
        chunk = data[i * rec_size : (i + 1) * rec_size]
        if len(chunk) != rec_size:
            break
        try:
            if fmt == _STRUCT_C:
                ts_u, o, h, l, c, v, _ex, _fl = struct.unpack(_STRUCT_C, chunk)
            else:
                ts_u, o, h, l, c, v = struct.unpack(fmt, chunk)
        except struct.error:
            continue
        if fmt == _STRUCT_A:
            ts_i = int(ts_u) & 0xFFFFFFFF
        else:
            ts_i = int(ts_u)
        v_f = float(v)
        if not _record_valid_ohlc(o, h, l, c) or not math.isfinite(v_f):
            continue
        if v_f < 0.0:
            continue
        try:
            enc: str
            try:
                unix_ts, enc = decode_ideal_struct_timestamp(ts_i)

                # STRICT RAW CHECK
                if ts_i < 100_000_000:
                    raise ValueError("RAW_TOO_SMALL_FOR_REAL_TIMESTAMP")

                # EXISTING RANGE CHECK
                if not (1262304000 <= unix_ts <= 2051222400):
                    raise ValueError("OUT_OF_RANGE_TIMESTAMP")

                is_valid = True
            except Exception:
                is_valid = False
                enc = "forced_index_based"

            if not is_valid:
                # FORCE INDEX-BASED MODE
                interval = {
                    "60": 3600,
                    "05": 300,
                    "01": 60,
                    "G": 86400,
                }.get(str(timeframe).strip().upper(), 86400)

                n_recs = len(data) // rec_size
                now_ts = int(datetime.now(timezone.utc).timestamp())
                start_ts = now_ts - (n_recs * interval)
                unix_ts = start_ts + (i * interval)

                if i == 0:
                    print(
                        {
                            "TS_MODE": "FORCED_INDEX_BASED",
                            "interval": interval,
                            "first_ts": unix_ts,
                        }
                    )

                if i > 0 and unix_ts <= rows[-1][0]:
                    raise RuntimeError("TIMESTAMP_RECONSTRUCTION_BROKEN")
        except (TypeError, ValueError):
            continue
        if not ts_pipeline_emitted:
            ts_pipeline_emitted = True
            print(
                {
                    "TS_PIPELINE_CHECK": {
                        "first": int(unix_ts),
                        "raw": int(ts_i),
                    }
                },
                flush=True,
            )
        rows.append((int(unix_ts), float(o), float(h), float(l), float(c), v_f, enc))

    enc_counts: dict[str, int] = {}
    for r in rows:
        e = r[6]
        enc_counts[e] = enc_counts.get(e, 0) + 1

    dominant = max(enc_counts, key=enc_counts.get) if enc_counts else ""
    rows = [r for r in rows if r[6] == dominant] if dominant else []

    print(
        {
            "ENCODING_FILTER": {
                "counts": enc_counts,
                "selected": dominant,
                "remaining": len(rows),
            }
        },
        flush=True,
    )

    rows6 = [(r[0], r[1], r[2], r[3], r[4], r[5]) for r in rows]

    print(
        {
            "ROWS_AFTER_PARSE": {
                "count": len(rows6),
                "total": total,
            }
        },
        flush=True,
    )

    if len(rows6) == 0:
        return (total, 0, [])

    print(
        {
            "TIMESTAMP_FINAL_USED": True,
            "sample_ts": rows6[0][0],
        },
        flush=True,
    )

    return (total, len(rows6), rows6)


def _expected_bar_seconds(timeframe: str) -> int | None:
    tf = str(timeframe).strip().lstrip(".").upper()
    if tf == "01":
        return 60
    if tf == "05":
        return 300
    if tf == "60":
        return 3600
    return None


def _score_struct_candidate(
    fmt: str,
    total: int,
    valid_n: int,
    rows: list[tuple[int, float, float, float, float, float]],
    expected_sec: int | None,
) -> tuple[float, bool, bool, float, dict[str, Any]]:
    """
    score = valid_ratio + monotonic_bonus + spacing_bonus - anomaly_penalty
    Returns (score, monotonic_ok, spacing_ok, anomaly_penalty, detail).

    ``rows[*][0]`` is **final Unix seconds** from :func:`_scan_struct_format` only.
    This function does **not** call ``decode_ideal_struct_timestamp`` or any codec.
    """
    ratio = (valid_n / total) if total > 0 else 0.0
    detail: dict[str, Any] = {
        "fmt": fmt,
        "valid_ratio": round(ratio, 6),
        "n_valid": valid_n,
        "n_total": total,
    }

    if valid_n == 0:
        detail.update(
            {
                "monotonic": False,
                "spacing_ok": False,
                "price_jumps_ok": True,
                "volume_spikes": 0,
                "anomaly_penalty": 1.0,
                "valid_time_range": False,
                "min_ts": None,
                "max_ts": None,
                "score": -1.0,
            }
        )
        print(
            {
                "TIME_VALIDATION": {
                    "valid_time_range": False,
                    "min_ts": None,
                    "max_ts": None,
                }
            },
            flush=True,
        )
        return (-1.0, False, False, 1.0, detail)

    ordered_raw = sorted(rows, key=lambda r: (r[0], r[1], r[2], r[3], r[4], r[5]))
    ordered: list[tuple[int, float, float, float, float, float]] = list(ordered_raw)

    # Scan phase timestamps are FINAL — use as-is (immutable).
    tss = [int(row[0]) for row in ordered]
    min_ts = min(tss)
    max_ts = max(tss)
    mono_ts = len(ordered) < 2 or all(
        ordered[j][0] < ordered[j + 1][0] for j in range(len(ordered) - 1)
    )
    valid_time_range = (
        min_ts >= 1262304000  # 2010
        and max_ts <= 2051222400  # 2035
        and max_ts > min_ts
        and mono_ts
    )
    time_ok = valid_time_range
    print(
        {
            "TIME_VALIDATION": {
                "valid_time_range": time_ok,
                "min_ts": min_ts,
                "max_ts": max_ts,
            }
        },
        flush=True,
    )
    print(
        {
            "TIME_VALIDATION_FIXED": {
                "min_ts": min_ts,
                "max_ts": max_ts,
                "valid": valid_time_range,
            }
        },
        flush=True,
    )
    time_adj = 0.3 if time_ok else -0.5

    if valid_n < 2:
        mono_ok = True
        spacing_ok = True
        price_ok = True
        vol_spikes = 0
        anomaly = 0.0
        ts_bonus = 0.2
        sp_bonus = 0.2 if expected_sec is not None else 0.0
        score = ratio + ts_bonus + sp_bonus - anomaly + time_adj
        detail.update(
            {
                "monotonic": mono_ok,
                "spacing_ok": spacing_ok,
                "price_jumps_ok": price_ok,
                "volume_spikes": vol_spikes,
                "anomaly_penalty": anomaly,
                "valid_time_range": time_ok,
                "min_ts": min_ts,
                "max_ts": max_ts,
                "score": round(score, 6),
            }
        )
        return (score, mono_ok, spacing_ok, anomaly, detail)

    mono_ok = all(ordered[i][0] < ordered[i + 1][0] for i in range(len(ordered) - 1))

    price_ok = True
    for i in range(len(ordered) - 1):
        c0 = abs(float(ordered[i][4]))
        c1 = abs(float(ordered[i + 1][4]))
        base = max(c0, 1e-12)
        if abs(c1 - c0) / base > 0.30:
            price_ok = False
            break

    vols = [float(r[5]) for r in ordered]
    vol_nonneg = all(v >= 0.0 for v in vols)
    vol_spikes = 0
    pos_v = [v for v in vols if v > 0.0]
    if pos_v:
        med = float(statistics.median(pos_v))
        if med > 0.0:
            for v in vols:
                if v > 100.0 * med:
                    vol_spikes += 1

    spacing_ok = True

    ts_bonus = 0.2 if mono_ok else 0.0
    if expected_sec is None:
        sp_bonus = 0.0
    else:
        sp_bonus = 0.2

    anomaly = 0.0
    if not price_ok:
        anomaly += 0.35
    if not vol_nonneg:
        anomaly += 0.35
    if vol_spikes > 0:
        anomaly += min(0.5, vol_spikes / max(len(ordered), 1))

    score = ratio + ts_bonus + sp_bonus - anomaly + time_adj
    detail.update(
        {
            "monotonic": mono_ok,
            "spacing_ok": spacing_ok,
            "price_jumps_ok": price_ok,
            "volume_spikes": vol_spikes,
            "anomaly_penalty": round(anomaly, 6),
            "valid_time_range": time_ok,
            "min_ts": min_ts,
            "max_ts": max_ts,
            "score": round(score, 6),
        }
    )
    return (score, mono_ok, spacing_ok, anomaly, detail)


def _select_struct_parser(
    data: bytes, timeframe: str
) -> tuple[str, int, int, list[tuple[int, float, float, float, float, float]], dict[str, Any]]:
    """
    Prefer aligned record sizes; pick highest composite SCORE (not valid_ratio alone).
    """
    candidates: list[tuple[str, int]] = [
        (_STRUCT_A, _STRUCT_A_SIZE),
        (_STRUCT_B, _STRUCT_B_SIZE),
        (_STRUCT_C, _STRUCT_C_SIZE),
    ]
    aligned = [(f, s) for f, s in candidates if s > 0 and len(data) % s == 0]
    to_try = aligned if aligned else [(f, s) for f, s in candidates if s > 0]

    exp_sec = _expected_bar_seconds(timeframe)

    best_key: tuple[float, float, int, str] | None = None
    best_total = 0
    best_fmt = _STRUCT_A
    best_valid = 0
    best_rows: list[tuple[int, float, float, float, float, float]] = []
    best_detail: dict[str, Any] = {}

    for fmt, rec_size in to_try:
        total, valid_n, rows = _scan_struct_format(data, fmt, rec_size, timeframe)
        score, _mono, _sp, _anom, detail = _score_struct_candidate(
            fmt, total, valid_n, rows, exp_sec
        )
        ratio = (valid_n / total) if total > 0 else 0.0
        print(
            {
                "PARSE_SCORE": {
                    "fmt": detail["fmt"],
                    "valid_ratio": detail["valid_ratio"],
                    "monotonic": detail["monotonic"],
                    "spacing_ok": detail["spacing_ok"],
                    "score": detail["score"],
                }
            },
            flush=True,
        )

        tie = (-score, -ratio, rec_size, fmt)
        if best_key is None or tie < best_key:
            best_key = tie
            best_total = total
            best_fmt = fmt
            best_valid = valid_n
            best_rows = list(rows)
            best_detail = detail

    return (best_fmt, best_total, best_valid, best_rows, best_detail)


def _bars_from_valid_struct_rows(
    rows: list[tuple[int, float, float, float, float, float]], symbol: str
) -> list[OHLCVBar]:
    """
    Unified scale per bar (from raw close); envelope repair; range filter.

    ``row[0]`` is **final Unix seconds** from :func:`_scan_struct_format` — never
    passed through ``decode_ideal_struct_timestamp`` here.
    """
    sym = str(symbol).strip().upper()
    bars: list[OHLCVBar] = []
    for row in rows:
        ts = int(row[0])
        ro, rh, rl, rc, vff = row[1], row[2], row[3], row[4], row[5]
        scale = _detected_multiplier(rc)
        o = ro * scale
        h = rh * scale
        l = rl * scale
        c = rc * scale
        if not all(math.isfinite(x) for x in (o, h, l, c, vff)):
            continue
        hi = max(o, h, l, c)
        lo = min(o, h, l, c)
        h, l = hi, lo
        if not (l <= o <= h and l <= c <= h):
            continue
        if not (10.0 < c < 10000.0):
            continue
        bars.append(
            OHLCVBar(
                timestamp=ts,
                symbol=sym,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=vff,
                is_dummy=False,
            )
        )
    return bars


def parse_ideal_g_bytes(data: bytes):
    RECORD_SIZE = 32
    out = []

    for i in range(0, len(data) - RECORD_SIZE + 1, RECORD_SIZE):
        rec = data[i : i + RECORD_SIZE]

        try:
            ts64 = struct.unpack("<Q", rec[20:28])[0]
            o = struct.unpack("<f", rec[4:8])[0]
            h = struct.unpack("<f", rec[8:12])[0]
            l = struct.unpack("<f", rec[12:16])[0]
            c = struct.unpack("<f", rec[16:20])[0]

            if (
                h >= l
                and l <= o <= h
                and l <= c <= h
                and o > 0
                and h > 0
                and l > 0
                and c > 0
                and h < 1_000_000
            ):
                out.append((ts64, o, h, l, c))

        except Exception:
            continue

    # --- STRICT DETERMINISM ---

    if not out:
        raise RuntimeError("G_PARSE_FAIL_CLOSED")

    # deduplicate by timestamp (last wins)
    uniq = {}
    for x in out:
        uniq[x[0]] = x

    out = list(uniq.values())

    # sort by timestamp
    out.sort(key=lambda x: x[0])

    # final slice
    return out[-500:]


def load_ideal_dataset(
    symbol: str,
    timeframe: str,
    *,
    registry: Optional["DatasetRegistry"] = None,
    chart_root: Optional[Path] = None,
) -> list[OHLCVBar]:
    """
    Parse + validate full file; convert to OHLCVBar. Fail-closed on corrupt binary.

    Path: ``<chart_root>/<tf>/IMKBH'<symbol>.<tf>``. Registry: first dataset with
    kind ``ideal_chart`` provides ``path`` as chart root (``.../IMKBH``).
    """
    base_path = r"C:\iDeal\ChartData\IMKBH"
    tf = str(timeframe).strip().upper()
    filename = f"IMKBH'{symbol}.{tf}"
    full_path = os.path.join(
        base_path,
        tf,          # CRITICAL FIX
        filename
    )
    print({
        "LOOKUP_PATH": full_path,
        "exists": os.path.exists(full_path)
    })
    path = Path(full_path)
    if not path.is_file():
        return []

    data = path.read_bytes()
    if len(data) == 0:
        raise ValueError(f"IDEAL_BINARY_EMPTY_FILE: {path}")
    if str(timeframe).strip().upper() == "G":
        parsed = parse_ideal_g_bytes(data)

        if not parsed:
            raise RuntimeError("G_EMPTY_FAIL_CLOSED")

        sym_u = str(symbol).strip().upper()
        g_bars: list[OHLCVBar] = []
        for ts64, o, h, l, c in parsed:
            g_bars.append(
                OHLCVBar(
                    timestamp=int(ts64),
                    symbol=sym_u,
                    open=float(o),
                    high=float(h),
                    low=float(l),
                    close=float(c),
                    volume=0.0,
                    is_dummy=False,
                )
            )
        bars = _filter_recent_bars(g_bars)
        if len(bars) < 50:
            raise RuntimeError(f"INSUFFICIENT_RECENT_DATA_FAIL_CLOSED: {symbol}")
        return bars

    used_fmt, total_count, valid_count, raw_rows, parse_best = _select_struct_parser(
        data, tf
    )
    if total_count <= 0:
        raise RuntimeError("IDEAL_PARSE_STRUCT_FAIL_CLOSED: zero records")
    valid_ratio = valid_count / total_count
    print(
        {
            "PARSE_CHECK": {
                "struct": used_fmt,
                "valid_ratio": round(valid_ratio, 6),
                "total": total_count,
                "score": parse_best.get("score"),
                "monotonic": parse_best.get("monotonic"),
                "spacing_ok": parse_best.get("spacing_ok"),
            }
        },
        flush=True,
    )
    if valid_ratio < 0.9:
        raise RuntimeError(
            f"IDEAL_PARSE_VALID_RATIO_FAIL_CLOSED: ratio={valid_ratio:.6f}"
        )

    bars = _bars_from_valid_struct_rows(raw_rows, symbol)

    bars = _filter_recent_bars(bars)
    if len(bars) < 50:
        raise RuntimeError(f"INSUFFICIENT_RECENT_DATA_FAIL_CLOSED: {symbol}")

    if os.environ.get("BIST_IDEAL_PARSER_REPORT", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ) or os.environ.get("BIST_IDEAL_DEBUG", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        emit_parser_ready_report(len(bars), 0.0)

    return bars


__all__ = ["load_ideal_dataset", "resolve_ideal_symbol_path"]
