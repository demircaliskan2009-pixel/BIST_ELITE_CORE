"""Tests for edges 5-7: RS momentum, sector rotation, momentum continuation."""

from __future__ import annotations

import pytest

from bist_core.decision.bist_edge_v2 import (
    _BIST_SECTORS,
    _momentum_continuation_signal,
    _relative_strength_signal,
    _rsi,
    _sector_rotation_signal,
    _sma,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uptrend(start: float, n: int, pct: float = 0.01) -> list[float]:
    """Generate an uptrending close series."""
    return [start * (1 + pct) ** i for i in range(n)]


def _flat(val: float, n: int) -> list[float]:
    return [val] * n


def _vols(n: int, base: float = 1_000_000.0) -> list[float]:
    return [base] * n


def _build_universe(
    symbols: list[str],
    closes_map: dict[str, list[float]],
) -> dict[str, list[float]]:
    """Build universe_closes dict from a mapping."""
    return {s: closes_map[s] for s in symbols if s in closes_map}


# ---------------------------------------------------------------------------
# BIST_SECTORS sanity
# ---------------------------------------------------------------------------

class TestBistSectors:
    def test_all_15_symbols_mapped(self) -> None:
        expected = {
            "AKBNK", "YKBNK", "ISCTR",
            "PEKGY", "EKGYO", "PSGYO",
            "EREGL", "PETKM", "SASA",
            "ADESE", "HEKTS", "KATMR",
            "GSRAY", "TSPOR", "CANTE",
        }
        assert set(_BIST_SECTORS.keys()) == expected

    def test_sector_names(self) -> None:
        sectors = set(_BIST_SECTORS.values())
        assert sectors == {"banks", "holdings", "industrial", "consumer", "other"}

    def test_banks(self) -> None:
        banks = {s for s, v in _BIST_SECTORS.items() if v == "banks"}
        assert banks == {"AKBNK", "YKBNK", "ISCTR"}


# ---------------------------------------------------------------------------
# Edge 5: Relative Strength Momentum
# ---------------------------------------------------------------------------

class TestRelativeStrengthSignal:
    """_relative_strength_signal tests."""

    def test_insufficient_closes(self) -> None:
        """Too few closes → False."""
        assert _relative_strength_signal("AKBNK", [100.0] * 3, {}) is False

    def test_empty_universe(self) -> None:
        closes = _uptrend(100.0, 60)
        assert _relative_strength_signal("AKBNK", closes, {}) is False

    def test_universe_too_small(self) -> None:
        """Fewer than 5 symbols → False."""
        closes = _uptrend(100.0, 60)
        universe = {
            "AKBNK": closes,
            "YKBNK": _flat(100.0, 60),
            "ISCTR": _flat(100.0, 60),
        }
        assert _relative_strength_signal("AKBNK", closes, universe) is False

    def test_top_performer_fires(self) -> None:
        """Symbol with highest 5-day return in top 20% → True (if above SMA50)."""
        n = 60
        # AKBNK strong uptrend → highest RS
        akbnk = _uptrend(100.0, n, pct=0.02)
        # Others flat/weak
        universe = {
            "AKBNK": akbnk,
            "YKBNK": _flat(100.0, n),
            "ISCTR": _flat(100.0, n),
            "PEKGY": _flat(100.0, n),
            "EKGYO": _flat(100.0, n),
            "PSGYO": _flat(100.0, n),
        }
        result = _relative_strength_signal("AKBNK", akbnk, universe)
        assert result is True

    def test_bottom_performer_rejected(self) -> None:
        """Flat symbol while others trend up → not in top 20%."""
        n = 60
        flat = _flat(100.0, n)
        up = _uptrend(100.0, n, pct=0.02)
        universe = {
            "AKBNK": flat,  # weakest
            "YKBNK": up,
            "ISCTR": up,
            "PEKGY": up,
            "EKGYO": up,
            "PSGYO": up,
        }
        assert _relative_strength_signal("AKBNK", flat, universe) is False

    def test_negative_return_rejected(self) -> None:
        """Even if 'top' by rank, negative return → False."""
        n = 60
        # All declining, one less so (-0.5% vs -2%)
        mild_down = [100.0 * (0.995**i) for i in range(n)]
        hard_down = [100.0 * (0.98**i) for i in range(n)]
        universe = {
            "AKBNK": mild_down,
            "YKBNK": hard_down,
            "ISCTR": hard_down,
            "PEKGY": hard_down,
            "EKGYO": hard_down,
            "PSGYO": hard_down,
        }
        # AKBNK is top but return is negative
        assert _relative_strength_signal("AKBNK", mild_down, universe) is False

    def test_below_sma50_rejected(self) -> None:
        """Symbol in top RS but last close below SMA50 → False."""
        n = 60
        # Build uptrend then drop price below SMA50 on last bar
        closes = _uptrend(100.0, n, pct=0.02)
        sma50 = sum(closes[-50:]) / 50
        closes[-1] = sma50 * 0.95  # drop below SMA50
        flat = _flat(100.0, n)
        universe = {
            "AKBNK": closes,
            "YKBNK": flat,
            "ISCTR": flat,
            "PEKGY": flat,
            "EKGYO": flat,
            "PSGYO": flat,
        }
        assert _relative_strength_signal("AKBNK", closes, universe) is False

    def test_symbol_not_in_universe(self) -> None:
        """Symbol missing from universe_closes → False."""
        closes = _uptrend(100.0, 60)
        universe = {
            "YKBNK": _flat(100.0, 60),
            "ISCTR": _flat(100.0, 60),
            "PEKGY": _flat(100.0, 60),
            "EKGYO": _flat(100.0, 60),
            "PSGYO": _flat(100.0, 60),
        }
        assert _relative_strength_signal("AKBNK", closes, universe) is False

    def test_deterministic(self) -> None:
        """Same input → same output."""
        n = 60
        akbnk = _uptrend(100.0, n, pct=0.02)
        universe = {
            "AKBNK": akbnk,
            "YKBNK": _flat(100.0, n),
            "ISCTR": _flat(100.0, n),
            "PEKGY": _flat(100.0, n),
            "EKGYO": _flat(100.0, n),
            "PSGYO": _flat(100.0, n),
        }
        r1 = _relative_strength_signal("AKBNK", akbnk, universe)
        r2 = _relative_strength_signal("AKBNK", akbnk, universe)
        assert r1 == r2


# ---------------------------------------------------------------------------
# Edge 6: Sector Rotation
# ---------------------------------------------------------------------------

class TestSectorRotationSignal:
    """_sector_rotation_signal tests."""

    def test_unknown_symbol_rejected(self) -> None:
        """Symbol not in _BIST_SECTORS → False."""
        closes = _uptrend(100.0, 60)
        assert _sector_rotation_signal("UNKNOWN", closes, {}) is False

    def test_insufficient_closes(self) -> None:
        assert _sector_rotation_signal("AKBNK", [100.0] * 3, {}) is False

    def test_empty_universe(self) -> None:
        closes = _uptrend(100.0, 60)
        assert _sector_rotation_signal("AKBNK", closes, {}) is False

    def test_banks_outperforming_fires(self) -> None:
        """Banks sector up while others flat → sector rotation fires for a bank."""
        n = 60
        bank_up = _uptrend(100.0, n, pct=0.02)
        flat = _flat(100.0, n)
        universe = {
            "AKBNK": bank_up,
            "YKBNK": bank_up,
            "ISCTR": bank_up,
            "PEKGY": flat,
            "EKGYO": flat,
            "PSGYO": flat,
            "EREGL": flat,
            "PETKM": flat,
            "SASA": flat,
            "ADESE": flat,
            "HEKTS": flat,
            "KATMR": flat,
            "GSRAY": flat,
            "TSPOR": flat,
            "CANTE": flat,
        }
        result = _sector_rotation_signal("AKBNK", bank_up, universe)
        assert result is True

    def test_lagging_sector_rejected(self) -> None:
        """Banks flat while others up → bank stock rejected."""
        n = 60
        flat = _flat(100.0, n)
        up = _uptrend(100.0, n, pct=0.02)
        universe = {
            "AKBNK": flat,
            "YKBNK": flat,
            "ISCTR": flat,
            "PEKGY": up,
            "EKGYO": up,
            "PSGYO": up,
            "EREGL": up,
            "PETKM": up,
            "SASA": up,
            "ADESE": up,
            "HEKTS": up,
            "KATMR": up,
            "GSRAY": up,
            "TSPOR": up,
            "CANTE": up,
        }
        assert _sector_rotation_signal("AKBNK", flat, universe) is False

    def test_below_sma20_rejected(self) -> None:
        """Sector outperforms but individual stock below SMA20 → False."""
        n = 60
        bank_up = _uptrend(100.0, n, pct=0.02)
        flat = _flat(100.0, n)
        # AKBNK is a laggard in its own sector — drop below SMA20
        akbnk = list(bank_up)
        sma20 = sum(akbnk[-20:]) / 20
        akbnk[-1] = sma20 * 0.90
        universe = {
            "AKBNK": akbnk,
            "YKBNK": bank_up,
            "ISCTR": bank_up,
            "PEKGY": flat,
            "EKGYO": flat,
            "PSGYO": flat,
            "EREGL": flat,
            "PETKM": flat,
            "SASA": flat,
            "ADESE": flat,
            "HEKTS": flat,
            "KATMR": flat,
            "GSRAY": flat,
            "TSPOR": flat,
            "CANTE": flat,
        }
        assert _sector_rotation_signal("AKBNK", akbnk, universe) is False

    def test_spread_below_threshold_rejected(self) -> None:
        """Sector barely outperforms (< 2% spread) → False."""
        n = 60
        # All similar uptrends → spread near zero
        up = _uptrend(100.0, n, pct=0.01)
        universe = {
            "AKBNK": up,
            "YKBNK": up,
            "ISCTR": up,
            "PEKGY": up,
            "EKGYO": up,
            "PSGYO": up,
            "EREGL": up,
            "PETKM": up,
            "SASA": up,
            "ADESE": up,
            "HEKTS": up,
            "KATMR": up,
            "GSRAY": up,
            "TSPOR": up,
            "CANTE": up,
        }
        assert _sector_rotation_signal("AKBNK", up, universe) is False

    def test_deterministic(self) -> None:
        n = 60
        bank_up = _uptrend(100.0, n, pct=0.02)
        flat = _flat(100.0, n)
        universe = {
            "AKBNK": bank_up, "YKBNK": bank_up, "ISCTR": bank_up,
            "PEKGY": flat, "EKGYO": flat, "PSGYO": flat,
            "EREGL": flat, "PETKM": flat, "SASA": flat,
            "ADESE": flat, "HEKTS": flat, "KATMR": flat,
            "GSRAY": flat, "TSPOR": flat, "CANTE": flat,
        }
        r1 = _sector_rotation_signal("AKBNK", bank_up, universe)
        r2 = _sector_rotation_signal("AKBNK", bank_up, universe)
        assert r1 == r2


# ---------------------------------------------------------------------------
# Edge 7: Momentum Continuation
# ---------------------------------------------------------------------------

class TestMomentumContinuationSignal:
    """_momentum_continuation_signal tests."""

    def test_insufficient_closes(self) -> None:
        assert _momentum_continuation_signal([100.0] * 10, _vols(10)) is False

    def test_new_high_fires(self) -> None:
        """Price above prior 20-bar max with volume + RSI ok → True."""
        # Build a series with moderate RSI: alternating small gains and losses
        # ending with a breakout to new 20-day high
        closes = [100.0]
        for i in range(1, 35):
            # Alternate: +0.5% then -0.3% → slow net drift up, RSI ~55-65
            change = 0.005 if i % 2 == 1 else -0.003
            closes.append(closes[-1] * (1 + change))
        # Final bar: push above 20-bar max
        prev_high = max(closes[-21:])
        closes.append(prev_high * 1.012)

        # Volume above 1.1x average
        volumes = _vols(len(closes), base=1_000_000.0)
        volumes[-1] = 1_500_000.0

        # Sanity: RSI must be below 75 for signal to fire
        rsi = _rsi(closes, 14)
        assert rsi < 75.0, f"Test data broken: RSI={rsi}"

        result = _momentum_continuation_signal(closes, volumes)
        assert result is True

    def test_no_new_high_rejected(self) -> None:
        """Close below prior 20-bar max → False."""
        n = 30
        closes = _uptrend(100.0, n, pct=0.005)
        closes[-1] = closes[-2] * 0.99  # below prior max
        volumes = _vols(n, base=1_000_000.0)
        volumes[-1] = 1_500_000.0
        assert _momentum_continuation_signal(closes, volumes) is False

    def test_exhausted_rsi_rejected(self) -> None:
        """RSI >= 75 → False (overbought)."""
        n = 30
        # Strong uptrend → RSI very high
        closes = _uptrend(100.0, n, pct=0.04)
        prev_high = max(closes[:-1])
        closes[-1] = prev_high * 1.01
        volumes = _vols(n, base=1_000_000.0)
        volumes[-1] = 1_500_000.0
        # With 4% daily gains, RSI should be near 100
        rsi = _rsi(closes, 14)
        if rsi >= 75.0:
            assert _momentum_continuation_signal(closes, volumes) is False

    def test_low_volume_rejected(self) -> None:
        """Volume below 1.1x average → False."""
        n = 30
        closes = _uptrend(100.0, n, pct=0.005)
        prev_high = max(closes[:-1])
        closes[-1] = prev_high * 1.02
        # Low volume on last bar
        volumes = _vols(n, base=1_000_000.0)
        volumes[-1] = 500_000.0  # well below average
        assert _momentum_continuation_signal(closes, volumes) is False

    def test_insufficient_volume_data(self) -> None:
        """Fewer than VOLUME_LOOKBACK bars → False."""
        closes = _uptrend(100.0, 25, pct=0.005)
        volumes = _vols(5, base=1_000_000.0)  # too few
        assert _momentum_continuation_signal(closes, volumes) is False

    def test_deterministic(self) -> None:
        n = 30
        closes = _uptrend(100.0, n, pct=0.005)
        prev_high = max(closes[:-1])
        closes[-1] = prev_high * 1.02
        volumes = _vols(n, base=1_000_000.0)
        volumes[-1] = 1_500_000.0
        r1 = _momentum_continuation_signal(closes, volumes)
        r2 = _momentum_continuation_signal(closes, volumes)
        assert r1 == r2

    def test_flat_market_rejected(self) -> None:
        """All same close → no new high → False."""
        n = 30
        closes = _flat(100.0, n)
        volumes = _vols(n)
        assert _momentum_continuation_signal(closes, volumes) is False


# ---------------------------------------------------------------------------
# Integration: BistEdgeV2Decision with universe tracking
# ---------------------------------------------------------------------------

class TestUniverseTracking:
    """Verify _universe_closes is populated by __call__."""

    def test_universe_closes_populated(self) -> None:
        from bist_core.decision.bist_edge_v2 import BistEdgeV2Decision
        from bist_core.models.ohlcv import OHLCVBar

        engine = BistEdgeV2Decision()
        n = 60

        def make_bars(sym: str, closes: list[float]) -> list[OHLCVBar]:
            return [
                OHLCVBar(
                    timestamp=1_700_000_000 + i * 86400,
                    symbol=sym,
                    open=c,
                    high=c * 1.01,
                    low=c * 0.99,
                    close=c,
                    volume=1_000_000.0,
                )
                for i, c in enumerate(closes)
            ]

        # Call engine for two symbols
        bars_a = make_bars("AKBNK", _uptrend(100.0, n))
        bars_b = make_bars("YKBNK", _flat(100.0, n))
        engine("AKBNK", bars_a, n - 1)
        engine("YKBNK", bars_b, n - 1)

        assert "AKBNK" in engine._universe_closes
        assert "YKBNK" in engine._universe_closes
        assert len(engine._universe_closes["AKBNK"]) == n
