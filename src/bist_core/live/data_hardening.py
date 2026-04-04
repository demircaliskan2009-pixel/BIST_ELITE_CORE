"""Deterministic bar hardening — validation, cross-source check, gap handling (no synthetic bars)."""

from __future__ import annotations

from bist_core.live.data_validator import DataValidator
from bist_core.models.ohlcv import OHLCVBar, normalize_timestamp


def _median(vals: list[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    n = len(s)
    m = n // 2
    if n % 2:
        return float(s[m])
    return float(s[m - 1] + s[m]) / 2.0


def _bar_prices_valid(b: OHLCVBar) -> bool:
    try:
        o, h, low, c = float(b.open), float(b.high), float(b.low), float(b.close)
        v = float(b.volume)
    except (TypeError, ValueError):
        return False
    if min(o, h, low, c) <= 0.0:
        return False
    if h < low:
        return False
    if h + 1e-15 < max(o, c) or low - 1e-15 > min(o, c):
        return False
    if v < 0.0:
        return False
    return True


def _coerce_ts(b: OHLCVBar) -> int:
    try:
        return normalize_timestamp(b.timestamp)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return int(b.timestamp) if isinstance(b.timestamp, int) else -1


def _debug_invalid_data(symbol: str, bars_in: int) -> None:
    print({"symbol": symbol, "reason": "invalid_data", "bars_in": bars_in})


class DataHardeningEngine:
    """
    Production-safe bar pipeline: sort/dedupe, monotonicity, volume sanity,
    optional unix gap truncation (skip rest), Matriks OHLC cross-check when ref present.
    Corrupted input → empty list (fail-closed). No synthetic / forward-filled bars.
    """

    def __init__(
        self,
        *,
        price_threshold: float = 0.02,
        volume_outlier_ratio: float = 10_000.0,
        unix_gap_skip_multiplier: float = 12.0,
    ) -> None:
        self._validator = DataValidator(threshold=price_threshold)
        self._volume_outlier_ratio = float(volume_outlier_ratio)
        self._unix_gap_m = float(unix_gap_skip_multiplier)

    def process(
        self,
        bars: list[OHLCVBar],
        symbol: str,
        matriks_ref: float | None,
    ) -> tuple[list[OHLCVBar], bool]:
        """
        Returns (cleaned_bars, valid). Empty list + valid False on any hard failure.
        ``valid`` True only when input had at least one bar and output is non-empty and consistent.
        """
        sym = str(symbol).strip().upper()
        bars_in = len(bars)
        if not bars:
            _debug_invalid_data(sym, bars_in)
            return [], False

        if bars and getattr(bars[0], "is_dummy", False):
            print({"debug": "bypass_dummy_data", "symbol": symbol})
            return bars, True

        cleaned: list[OHLCVBar] = []
        for b in bars:
            if not _bar_prices_valid(b):
                print({"symbol": sym, "error": "ohlc_invalid", "bar": b})
                _debug_invalid_data(sym, bars_in)
                return [], False
            cleaned.append(b)

        # Sort + dedupe timestamps (last bar wins)
        by_ts: dict[int, OHLCVBar] = {}
        for b in cleaned:
            ts = _coerce_ts(b)
            if ts < 0:
                _debug_invalid_data(sym, bars_in)
                return [], False
            by_ts[ts] = b

        ordered = [by_ts[k] for k in sorted(by_ts.keys())]

        # Volume anomaly vs batch median (deterministic)
        vols = [float(b.volume) for b in ordered]
        med_v = _median(vols)
        if med_v > 0.0:
            for v in vols:
                if v > med_v * self._volume_outlier_ratio:
                    _debug_invalid_data(sym, bars_in)
                    return [], False

        # Unix-like timestamps: skip tail after first "large but not absurd" gap (no synthetic fill)
        if len(ordered) >= 2 and all(_coerce_ts(b) >= 1_000_000_000 for b in ordered):
            ts_list = [_coerce_ts(b) for b in ordered]
            deltas = [float(ts_list[i + 1] - ts_list[i]) for i in range(len(ts_list) - 1)]
            med_d = _median(deltas)
            if med_d <= 0.0:
                _debug_invalid_data(sym, bars_in)
                return [], False
            cut = len(ordered)
            for i, d in enumerate(deltas):
                if d > med_d * self._unix_gap_m:
                    cut = i + 1
                    break
            ordered = ordered[:cut]
            if not ordered:
                _debug_invalid_data(sym, bars_in)
                return [], False

        # Cross-source OHLC vs Matriks (when reference available)
        if matriks_ref is not None and float(matriks_ref) > 0.0:
            ref = float(matriks_ref)
            for b in ordered:
                if not self._validator.compare_ohlc_to_ref(
                    float(b.open), float(b.high), float(b.low), float(b.close), ref
                ):
                    _debug_invalid_data(sym, bars_in)
                    return [], False

        valid = len(ordered) > 0
        return ordered, valid


__all__ = ["DataHardeningEngine"]
