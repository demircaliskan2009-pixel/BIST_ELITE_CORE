"""DataHardeningEngine — deterministic validation, fail-closed."""

from __future__ import annotations

from bist_core.live.data_hardening import DataHardeningEngine
from bist_core.models.ohlcv import OHLCVBar


def _bar(
    ts: int,
    o: float,
    h: float,
    low: float,
    c: float,
    v: float = 1000.0,
    sym: str = "X",
    *,
    is_dummy: bool = False,
) -> OHLCVBar:
    return OHLCVBar(
        timestamp=ts,
        symbol=sym,
        open=o,
        high=h,
        low=low,
        close=c,
        volume=v,
        is_dummy=is_dummy,
    )


def test_empty_input_invalid() -> None:
    eng = DataHardeningEngine()
    out, ok = eng.process([], "X", None)
    assert out == [] and ok is False


def test_valid_sorted_dedupe_last_wins() -> None:
    eng = DataHardeningEngine()
    b1 = _bar(100, 10.0, 10.5, 9.5, 10.0)
    b2 = _bar(200, 10.0, 10.2, 9.8, 10.1)
    b2d = _bar(200, 11.0, 11.2, 10.8, 11.0)
    out, ok = eng.process([b1, b2, b2d], "X", None)
    assert ok is True
    assert len(out) == 2
    assert out[-1].close == 11.0


def test_negative_price_fail_closed() -> None:
    eng = DataHardeningEngine()
    b = _bar(1, -1.0, 1.0, 0.5, 1.0)
    out, ok = eng.process([b], "X", None)
    assert out == [] and ok is False


def test_ohlc_inconsistent_fail_closed() -> None:
    eng = DataHardeningEngine()
    b = _bar(1, 10.0, 9.0, 8.0, 9.5)
    out, ok = eng.process([b], "X", None)
    assert out == [] and ok is False


def test_dummy_flag_batch_bypasses_hardening() -> None:
    """Bars with is_dummy=True skip volume/gap/Matriks checks; real data still validated below."""
    eng = DataHardeningEngine(price_threshold=0.02)
    b = _bar(1_700_000_000, 100.0, 101.0, 99.0, 100.0, is_dummy=True)
    out, ok = eng.process([b], "X", 110.0)
    assert ok is True
    assert len(out) == 1 and out[0].close == 100.0 and out[0].is_dummy is True


def test_matriks_cross_source_rejects_wide_deviation() -> None:
    eng = DataHardeningEngine(price_threshold=0.02)
    b = _bar(1_700_000_000, 100.0, 101.0, 99.0, 100.0)
    out, ok = eng.process([b], "X", 110.0)
    assert out == [] and ok is False


def test_matriks_cross_source_accepts_close_match() -> None:
    eng = DataHardeningEngine(price_threshold=0.02)
    b = _bar(1_700_000_000, 100.0, 101.0, 99.0, 100.0)
    out, ok = eng.process([b], "X", 100.5)
    assert ok is True
    assert len(out) == 1


def test_unix_gap_truncates_prefix_only() -> None:
    eng = DataHardeningEngine(unix_gap_skip_multiplier=12.0)
    t0 = 1_700_000_000
    b0 = _bar(t0, 10.0, 10.1, 9.9, 10.0)
    b1 = _bar(t0 + 60, 10.0, 10.1, 9.9, 10.0)
    b2 = _bar(t0 + 120, 10.0, 10.1, 9.9, 10.0)
    b3 = _bar(t0 + 120 + 7 * 24 * 3600, 10.0, 10.1, 9.9, 10.0)
    out, ok = eng.process([b0, b1, b2, b3], "X", None)
    assert ok is True
    assert len(out) == 3

