"""iDeal multi-timeframe binary reader (``.01``, ``.05``, ``.60``, ``.G``, …) — 32-byte bar layout (local files only)."""

from __future__ import annotations

import json
import math
import os
import struct
from pathlib import Path

import numpy as np

from bist_core.data.ideal_binary_parser import (
    RECORD_SIZE,
    OHLCVRecord,
    decode_ideal_binary_bytes,
)
from bist_core.models.ohlcv import OHLCVBar

# Struct layouts for iDeal .01 (try both: signed ts vs unsigned ts + 7 floats).
_STRUCT_SIGNED = struct.Struct("<iffffffi")  # ts(i), o,h,l,c,v,extra(f), flag(i)
_STRUCT_UNSIGNED = struct.Struct("<I7f")  # ts(I), o,h,l,c,v,turnover,reserved
_HEADER_CANDIDATES = (0, 16, 24, 32, 40, 48, 56, 64)

# LOCKED: int32 ts + float32 o,h,l,c,v,extra + int32 flag — see RECORD_SIZE in ideal_binary_parser.

_DECODE_LOCATION_BLOCKED_EMITTED = False


def _emit_decode_location_blocked_once() -> None:
    """Log once: struct timestamp decode is not used here (final ts = int as stored)."""
    global _DECODE_LOCATION_BLOCKED_EMITTED
    if not _DECODE_LOCATION_BLOCKED_EMITTED:
        print({"DECODE_LOCATION_BLOCKED": True}, flush=True)
        _DECODE_LOCATION_BLOCKED_EMITTED = True


def normalize_price(x: float) -> float:
    """Per-bar scale: raw ``< 10`` → ×100; else identity.

    **PRDV3:** Pure function — no randomness, no I/O, no env/globals; identical ``x`` ⇒
    identical ``float`` output (deterministic normalization).
    """
    xf = float(x)
    if xf < 10.0:
        return xf * 100.0
    return xf


def _np_normalize_prices(a: np.ndarray) -> np.ndarray:
    x = a.astype(np.float64).copy()
    m = x < 10.0
    x[m] = x[m] * 100.0
    return x


def _assert_no_repo_data_path(base: Path) -> None:
    """
    Fail-closed: forbid project-style ``...\\data\\...`` roots (fixtures / repo ``data/``).
    Real iDeal layout uses e.g. ``C:\\iDeal\\ChartData\\IMKBH\\01`` (``ChartData`` is allowed).
    """
    try:
        p = base.expanduser().resolve()
    except OSError:
        p = base.expanduser()
    norm = str(p).replace("/", "\\").lower()
    if "\\data\\" in norm or norm.endswith("\\data"):
        raise RuntimeError(
            "FORBIDDEN_IDEAL_PATH: iDeal root must not contain a '\\data\\' folder segment "
            "(no repo data/ or test fixtures). Set BIST_IDEAL_DATA_PATH to your real iDeal path."
        )


def _market_seal_enabled() -> bool:
    """Production market seal (range, variation, reference). BIST_IDEAL_MARKET_SEAL=0 to disable for tiny test buffers."""
    v = os.environ.get("BIST_IDEAL_MARKET_SEAL", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _ideal_feed_debug_enabled() -> bool:
    return os.environ.get("BIST_IDEAL_FEED_DEBUG", "").strip().lower() in ("1", "true", "yes")


def _parse_strict_enabled() -> bool:
    """Production: strict asserts. Set BIST_IDEAL_PARSE_STRICT=0 for tiny unit-test buffers only."""
    v = os.environ.get("BIST_IDEAL_PARSE_STRICT", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def records_to_ohlcv_bars_from_ideal(records: list[OHLCVRecord], symbol: str) -> list[OHLCVBar]:
    """
    Per-bar OHLC normalization via :func:`normalize_price` (no global divisor).
    """
    parse_ideal_01_bytes.last_scale = 1.0  # type: ignore[attr-defined]

    sym = str(symbol).strip().upper()
    if not records:
        return []

    raw_closes = [float(r.close) for r in records]
    print(
        {
            "NORMALIZED_SAMPLE": [normalize_price(x) for x in raw_closes[:20]],
        },
        flush=True,
    )

    prices_norm = [normalize_price(c) for c in raw_closes]
    print(
        {
            "POST_NORMALIZED_RANGE": {
                "min": min(prices_norm) if prices_norm else None,
                "max": max(prices_norm) if prices_norm else None,
            },
        },
        flush=True,
    )
    print(
        {
            "FINAL_SAMPLE": [round(float(x), 2) for x in prices_norm[-20:]],
        },
        flush=True,
    )

    _emit_decode_location_blocked_once()
    bars: list[OHLCVBar] = []
    for r in records:
        try:
            u_ts = int(r.timestamp)
        except (TypeError, ValueError):
            continue
        oc = normalize_price(float(r.open))
        hc = normalize_price(float(r.high))
        lc = normalize_price(float(r.low))
        cc = normalize_price(float(r.close))
        vf = float(r.volume)
        if not all(math.isfinite(x) for x in (oc, hc, lc, cc, vf)):
            continue
        if not (10.0 < cc < 10000.0):
            continue
        bars.append(
            OHLCVBar(
                timestamp=int(u_ts),
                symbol=sym,
                open=oc,
                high=hc,
                low=lc,
                close=cc,
                volume=vf,
                is_dummy=False,
            )
        )
    return bars


def ohlcv_bars_from_ideal_numpy(good: np.ndarray, symbol: str) -> list[OHLCVBar]:
    """
    Per-bar normalization on OHLC (vectorized); no global divisor.
    """
    parse_ideal_01_bytes.last_scale = 1.0  # type: ignore[attr-defined]

    sym = str(symbol).strip().upper()
    if len(good) == 0:
        return []

    c_raw = good["c"]
    print(
        {
            "RAW_SAMPLE": c_raw[:20].tolist(),
            "RAW_MIN": float(np.min(c_raw)),
            "RAW_MAX": float(np.max(c_raw)),
        },
        flush=True,
    )

    raw_closes = good["c"].astype(np.float64).tolist()
    print(
        {
            "NORMALIZED_SAMPLE": [normalize_price(float(x)) for x in raw_closes[:20]],
        },
        flush=True,
    )

    o64 = _np_normalize_prices(good["o"])
    h64 = _np_normalize_prices(good["h"])
    l64 = _np_normalize_prices(good["l"])
    c64 = _np_normalize_prices(good["c"])
    prices_norm = c64.tolist()
    print(
        {
            "POST_NORMALIZED_RANGE": {
                "min": float(np.min(c64)) if len(c64) else None,
                "max": float(np.max(c64)) if len(c64) else None,
            },
        },
        flush=True,
    )
    print(
        {
            "FINAL_SAMPLE": [round(float(x), 2) for x in prices_norm[-20:]],
        },
        flush=True,
    )

    vf = good["v"].astype(np.float64)
    ts = good["ts"].astype(np.int64)
    n = int(len(good))
    _emit_decode_location_blocked_once()
    bars: list[OHLCVBar] = []
    for i in range(n):
        try:
            u_ts = int(ts[i])
        except (TypeError, ValueError):
            continue
        ocf, hcf, lcf, ccf, vff = (
            float(o64[i]),
            float(h64[i]),
            float(l64[i]),
            float(c64[i]),
            float(vf[i]),
        )
        if not all(math.isfinite(x) for x in (ocf, hcf, lcf, ccf, vff)):
            continue
        if not (10.0 < ccf < 10000.0):
            continue
        bars.append(
            OHLCVBar(
                timestamp=int(u_ts),
                symbol=sym,
                open=ocf,
                high=hcf,
                low=lcf,
                close=ccf,
                volume=vff,
                is_dummy=False,
            )
        )
    return bars


def _parse_ideal_01_struct_bytes(
    data: bytes,
    symbol: str,
    path: str,
) -> list[OHLCVBar]:
    """
    Robust struct-only parser: try all offset/layout combinations, score, select best.
    Strict validation: len>=50, min>0, max<10000, unique>=5 per candidate.
    """
    sym = str(symbol).strip().upper()
    layouts = [("signed", _STRUCT_SIGNED), ("unsigned", _STRUCT_UNSIGNED)]
    best_bars: list[OHLCVBar] = []
    best_score = -1
    best_offset = 0
    best_layout = "none"
    os.path.getsize(path) if path and os.path.exists(path) else len(data)

    def _parse_with_layout(
        header: int,
        layout_name: str,
        struct_obj: struct.Struct,
    ) -> list[OHLCVBar]:
        _emit_decode_location_blocked_once()
        parsed: list[OHLCVBar] = []
        n_full = (len(data) - header) // RECORD_SIZE
        if n_full == 0:
            return []
        for i in range(n_full):
            off = header + i * RECORD_SIZE
            chunk = data[off : off + RECORD_SIZE]
            if len(chunk) < RECORD_SIZE:
                break
            try:
                row = struct_obj.unpack(chunk)
                ts = int(row[0])
                o, h, l, c, v = (
                    float(row[1]),
                    float(row[2]),
                    float(row[3]),
                    float(row[4]),
                    float(row[5]),
                )
            except (struct.error, ValueError, IndexError):
                continue
            if not all(math.isfinite(x) for x in (o, h, l, c, v)):
                continue
            if v < 0 or h < l or min(o, h, l, c) <= 0:
                continue
            oc = normalize_price(o)
            hc = normalize_price(h)
            lc = normalize_price(l)
            cc = normalize_price(c)
            if not (10.0 < cc < 10000.0):
                continue
            u_ts = int(ts)
            parsed.append(
                OHLCVBar(
                    timestamp=u_ts,
                    symbol=sym,
                    open=oc,
                    high=hc,
                    low=lc,
                    close=cc,
                    volume=v,
                    is_dummy=False,
                )
            )
        return parsed

    for header in _HEADER_CANDIDATES:
        if len(data) <= header:
            continue
        for layout_name, struct_obj in layouts:
            parsed = _parse_with_layout(header, layout_name, struct_obj)
            if len(parsed) < 50:
                continue
            closes = [float(b.close) for b in parsed]
            min_p = min(closes)
            max_p = max(closes)
            unique_p = len({round(x, 6) for x in closes})
            if min_p <= 0 or max_p >= 10000 or unique_p < 5:
                continue
            score = len(parsed) + unique_p
            if score > best_score:
                best_score = score
                best_bars = parsed
                best_offset = header
                best_layout = layout_name

    out = best_bars[-500:] if len(best_bars) > 500 else best_bars
    unique_prices = len({round(float(b.close), 6) for b in out})

    print(
        {
            "PARSE_FINAL": {
                "symbol": sym,
                "bars": len(out),
                "unique": unique_prices,
                "offset": best_offset,
                "layout": best_layout,
            }
        },
        flush=True,
    )

    if len(data) >= RECORD_SIZE and len(out) == 0:
        raise RuntimeError("IDEAL_PARSE_DETERMINISTIC_FAIL")

    return out


def parse_ideal_01_bytes(
    raw_bytes: bytes,
    symbol: str,
    **_: object,
) -> list[OHLCVBar]:
    """
    Parse iDeal .01 bars: ``<iffffffi`` per record via :mod:`bist_core.data.ideal_binary_parser`,
    per-bar normalized OHLC, ``10 < close < 10000``.
    Falls back to struct-only parser when alignment or decode fails.
    """
    if not raw_bytes:
        return []
    try:
        good = decode_ideal_binary_bytes(raw_bytes)
        return ohlcv_bars_from_ideal_numpy(good, symbol)
    except (ValueError, struct.error, Exception):
        return _parse_ideal_01_struct_bytes(raw_bytes, symbol, "")


def _validate_parse_result(bars: list[OHLCVBar]) -> None:
    """Print tail stats; raise PARSE_FAILED if production gates fail.

    Use up to the last 50 bars for uniqueness when available — real tails can be
    very tight for 20 bars while still valid (fail-closed: still require ≥50 bars
    total and ≥10 unique in the window).
    """
    if not bars:
        if _parse_strict_enabled():
            raise Exception("PARSE_FAILED")
        return
    if len(bars) >= 50:
        sample = bars[-50:]
    elif len(bars) >= 20:
        sample = bars[-20:]
    else:
        sample = bars
    closes = [float(b.close) for b in sample]
    uniq = len({round(x, 6) for x in closes})
    print(
        {
            "MIN": min(closes) if closes else None,
            "MAX": max(closes) if closes else None,
            "UNIQUE": uniq,
        }
    )
    if not _parse_strict_enabled():
        return
    if len(bars) < 50 or uniq < 10:
        raise Exception("PARSE_FAILED")


class IdealDataFeed:
    """Full snapshot read ``IMKBH'<SYM>.<tf>`` each call — fixed 32-byte records (no incremental offsets).

    Timeframes match iDeal suffixes: ``01``, ``05``, ``60``, ``G``, etc. (same binary layout as ``.01``).
    """

    def __init__(self, base_path: str | None = None) -> None:
        _from_arg = (str(base_path).strip() if base_path else "")
        _bist = (os.environ.get("BIST_IDEAL_DATA_PATH") or "").strip()
        _ideal = (os.environ.get("IDEAL_DATA_PATH") or "").strip()
        # Explicit path wins over env so tests can inject tmp dirs while CI has BIST_IDEAL_DATA_PATH.
        resolved = _from_arg or _bist or _ideal
        if not resolved:
            raise RuntimeError(
                "BIST_IDEAL_DATA_PATH (or IDEAL_DATA_PATH) must be set — no default repo data path"
            )
        self.base_path = Path(resolved)
        _assert_no_repo_data_path(self.base_path)
        _cache_off = os.environ.get("BIST_LIVE_FEED_CACHE", "1").strip().lower() in ("0", "false", "no", "off")
        self._use_cache = not _cache_off
        self._bars_cache: dict[str, list[OHLCVBar]] = {}
        self._cache_meta: dict[str, tuple[float, int]] = {}  # cache_key -> (mtime, size)
        if _ideal_feed_debug_enabled():
            print({"debug": "base_path", "path": str(self.base_path)})

    def _data_layer_proof_and_seal(self, sym_u: str, closes: list[float]) -> None:
        """DATA_PROOF print; optional market seal checks (env-gated)."""
        last_price = closes[-1] if closes else None
        print(
            {
                "DATA_PROOF": {
                    "symbol": sym_u,
                    "normalization": "per_bar_lt10_x100",
                    "last_price": round(float(last_price), 2) if last_price is not None else None,
                    "min": round(float(min(closes)), 2) if closes else None,
                    "max": round(float(max(closes)), 2) if closes else None,
                    "unique": len({round(float(x), 2) for x in closes}),
                }
            }
        )

        if not closes or not _market_seal_enabled():
            return

        lp = float(last_price) if last_price is not None else 0.0
        if not (10.0 < lp < 10000.0):
            raise Exception("PRICE_OUT_OF_RANGE")

        uq = len({round(float(x), 2) for x in closes})
        if uq < 10:
            raise Exception("LOW_VARIATION")

        if (max(closes) - min(closes)) < 1.0:
            raise Exception("NO_PRICE_MOVEMENT")

        ref_s = os.environ.get("BIST_LIVE_REFERENCE_PRICE", "").strip()
        if ref_s:
            try:
                ref = float(ref_s)
            except ValueError:
                ref = 0.0
            if ref > 0:
                diff = abs(lp - ref) / ref
                print(
                    {
                        "REFERENCE_CHECK": {
                            "ref": ref,
                            "live": lp,
                            "diff_pct": round(diff * 100.0, 2),
                        }
                    }
                )
                if diff > 0.20:
                    raise Exception("MARKET_MISMATCH")

    def _file_path(self, symbol: str, timeframe: str = "01") -> str:
        sym = str(symbol).strip().upper()
        tf = str(timeframe).strip().lstrip(".") or "01"
        return str(self.base_path / f"IMKBH'{sym}.{tf}")

    def read_new(self, symbol: str, timeframe: str = "01") -> list[OHLCVBar]:
        """Stateless full-file snapshot: decode (guarded) → OHLCV bars → validate → tail slice.

        When BIST_LIVE_FEED_CACHE is enabled (default), decoded tail is cached per symbol so
        repeated reads in the same run avoid full file I/O and decode (deterministic, same data).
        """
        tf = str(timeframe).strip().lstrip(".") or "01"
        sym_u = str(symbol).strip().upper()
        cache_key = f"{sym_u}:{tf}"
        path = self._file_path(symbol, tf)

        if self._use_cache and cache_key in self._bars_cache:
            try:
                st = os.stat(path)
                meta = self._cache_meta.get(cache_key)
                if meta and meta[0] == st.st_mtime and meta[1] == st.st_size:
                    return list(self._bars_cache[cache_key])
            except OSError:
                pass

        if not os.path.exists(path):
            print(
                json.dumps(
                    {
                        "timeframe_validation": {
                            "tf": tf,
                            "bars": 0,
                            "min": None,
                            "max": None,
                        }
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            print({"feed_mode": "FULL_RELOAD", "symbol": sym_u, "bars": 0}, flush=True)
            return []

        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError as e:
            raise RuntimeError(f"NO_DATA_WHILE_FILE_PRESENT: {sym_u} (read error: {e})")

        if not data or len(data) < RECORD_SIZE:
            raise RuntimeError(f"NO_DATA_WHILE_FILE_PRESENT: {sym_u}")

        try:
            good = decode_ideal_binary_bytes(data)
            bars = ohlcv_bars_from_ideal_numpy(good, sym_u)
            closes_all = [float(b.close) for b in bars]
            unique_p = len({round(x, 6) for x in closes_all})
            print(
                {
                    "PARSE_FINAL": {
                        "symbol": sym_u,
                        "bars": len(bars),
                        "unique": unique_p,
                        "offset": 0,
                        "layout": "decode",
                    }
                },
                flush=True,
            )
        except Exception:
            bars = _parse_ideal_01_struct_bytes(data, sym_u, path)

        if not bars:
            raise RuntimeError(f"NO_DATA_WHILE_FILE_PRESENT: {sym_u}")

        closes_all = [float(b.close) for b in bars]
        self._data_layer_proof_and_seal(sym_u, closes_all)

        _validate_parse_result(bars)

        print(
            {
                "REAL_PARSE_RESULT": {
                    "bars": len(bars),
                    "sample_close": float(bars[0].close) if bars else None,
                }
            }
        )

        bars = bars[-500:]

        closes_out = [float(b.close) for b in bars]
        print(
            json.dumps(
                {
                    "timeframe_validation": {
                        "tf": tf,
                        "bars": len(bars),
                        "min": min(closes_out) if closes_out else None,
                        "max": max(closes_out) if closes_out else None,
                    }
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

        if len(bars) < 50:
            print(
                {
                    "feed_warning": "LOW_BAR_COUNT",
                    "symbol": sym_u,
                    "bars": len(bars),
                },
                flush=True,
            )

        print(
            {"feed_mode": "FULL_RELOAD", "symbol": sym_u, "bars": len(bars)},
            flush=True,
        )

        if self._use_cache:
            try:
                st = os.stat(path)
                self._bars_cache[cache_key] = list(bars)
                self._cache_meta[cache_key] = (st.st_mtime, st.st_size)
            except OSError:
                self._bars_cache[cache_key] = list(bars)
                self._cache_meta[cache_key] = (0.0, 0)
        return bars

    def to_jsonable(self) -> dict[str, int]:
        """Offsets removed — snapshot feed has nothing to persist; empty dict for API compatibility."""
        return {}

    def save_offsets(self, path: str | Path) -> None:
        """No-op: incremental offsets removed; full file snapshot each read_new."""

    def load_offsets(self, path: str | Path) -> None:
        """No-op: incremental offsets removed."""


def select_dynamic_scale(_raw_closes: list[float]) -> tuple[float, bool]:
    """Deprecated: global divisor removed — returns ``(1.0, True)`` for API compatibility."""

    return 1.0, True


__all__ = [
    "IdealDataFeed",
    "normalize_price",
    "ohlcv_bars_from_ideal_numpy",
    "parse_ideal_01_bytes",
    "records_to_ohlcv_bars_from_ideal",
    "select_dynamic_scale",
]
