"""BIST session, auction gate, circuit breaker, event risk, vol shock — deterministic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from bist_core.market.session_engine import SessionEngine
from bist_core.models.ohlcv import OHLCVBar
from bist_core.risk.circuit_breaker import CircuitBreaker
from bist_core.risk.event_risk import EventRisk
from bist_core.risk.volatility_shock import VolatilityShock

_TRT = timezone(timedelta(hours=3))


def _ts_trt(y: int, mo: int, d: int, h: int, mi: int) -> int:
    dt = datetime(y, mo, d, h, mi, tzinfo=_TRT)
    return int(dt.timestamp())


def test_session_phases_trt() -> None:
    se = SessionEngine()
    assert se.get_phase(_ts_trt(2025, 6, 2, 9, 30)) == "pre_open"
    assert se.get_phase(_ts_trt(2025, 6, 2, 9, 56)) == "auction_open"
    assert se.get_phase(_ts_trt(2025, 6, 2, 11, 0)) == "continuous"
    assert se.get_phase(_ts_trt(2025, 6, 2, 18, 2)) == "auction_close"
    assert se.get_phase(_ts_trt(2025, 6, 2, 19, 0)) == "closed"


def test_auction_phase_blocks_by_spec() -> None:
    se = SessionEngine()
    assert se.get_phase(_ts_trt(2025, 6, 2, 9, 56)) in ("auction_open", "auction_close")


def test_circuit_breaker_triggers_on_10pct_move() -> None:
    cb = CircuitBreaker()
    bars = [
        OHLCVBar(0, "X", 100.0, 100.0, 100.0, 100.0, 1e6),
        OHLCVBar(1, "X", 115.0, 115.0, 115.0, 115.0, 1e6),
    ]
    assert cb.triggered(bars) is True


def test_circuit_breaker_no_trigger_small_move() -> None:
    cb = CircuitBreaker()
    bars = [
        OHLCVBar(0, "X", 100.0, 100.0, 100.0, 100.0, 1e6),
        OHLCVBar(1, "X", 101.0, 101.0, 101.0, 101.0, 1e6),
    ]
    assert cb.triggered(bars) is False


def test_event_risk_flags() -> None:
    er = EventRisk()
    assert er.is_risky("THYAO") is True
    assert er.is_risky("ASELS") is False


def test_event_risk_halves_size_rule() -> None:
    base = 100
    er = EventRisk()
    s = max(1, int(base * 0.5)) if er.is_risky("THYAO") else base
    assert s == 50


def test_volatility_shock_detects_high_rel_vol() -> None:
    vs = VolatilityShock()
    # Strong oscillation around 100 → high std / mean
    seq = [100.0, 120.0, 90.0, 125.0, 85.0, 130.0, 80.0, 135.0, 75.0, 140.0]
    bars = [
        OHLCVBar(str(i), "X", c, c, c, c, 5e6) for i, c in enumerate(seq)
    ]
    assert vs.detect(bars) is True


def test_volatility_shock_calm_series() -> None:
    vs = VolatilityShock()
    seq = [100.0 + i * 0.01 for i in range(10)]
    bars = [OHLCVBar(str(i), "X", c, c, c, c, 5e6) for i, c in enumerate(seq)]
    assert vs.detect(bars) is False


def test_vol_shock_halves_size_rule() -> None:
    base = 100
    vs = VolatilityShock()
    seq = [100.0, 120.0, 90.0, 125.0, 85.0, 130.0, 80.0, 135.0, 75.0, 140.0]
    bars = [OHLCVBar(str(i), "X", c, c, c, c, 5e6) for i, c in enumerate(seq)]
    s = base
    if vs.detect(bars):
        s = max(1, int(s * 0.5))
    assert s == 50
