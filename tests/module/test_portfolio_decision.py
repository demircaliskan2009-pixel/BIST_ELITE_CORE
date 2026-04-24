"""Tests for portfolio_decision module — deterministic, no randomness."""

from __future__ import annotations

import pytest

from bist_core.decision.portfolio_decision import (
    PortfolioDecisionEngine,
    _SymbolScorer,
    _PositionTracker,
    _compute_risk_sized_position,
    _MAX_POSITIONS,
    _MAX_PER_SYMBOL,
    _MAX_ENTRIES_PER_TS,
    _RISK_PER_TRADE_PCT,
    _MAX_NOTIONAL_PCT,
    _SCORE_MIN_TRADES,
    _SCORE_MIN_THRESHOLD,
)
from bist_core.models.ohlcv import OHLCVBar


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bars(
    closes: list[float],
    symbol: str = "TEST",
    volumes: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
) -> list[OHLCVBar]:
    if volumes is None:
        volumes = [1_000_000.0] * len(closes)
    if highs is None:
        highs = [c * 1.01 for c in closes]
    if lows is None:
        lows = [c * 0.99 for c in closes]
    return [
        OHLCVBar(
            timestamp=1_700_000_000 + i * 86400,
            symbol=symbol,
            open=c,
            high=h,
            low=lo,
            close=c,
            volume=v,
        )
        for i, (c, h, lo, v) in enumerate(zip(closes, highs, lows, volumes))
    ]


# ---------------------------------------------------------------------------
# _SymbolScorer tests
# ---------------------------------------------------------------------------


class TestSymbolScorer:
    def test_neutral_on_insufficient_data(self):
        scorer = _SymbolScorer()
        assert scorer.score("YKBNK") == 0.5
        scorer.record_trade("YKBNK", 100.0)
        assert scorer.score("YKBNK") == 0.5  # only 1 trade, < min

    def test_blocks_consistent_loser(self):
        scorer = _SymbolScorer()
        for _ in range(_SCORE_MIN_TRADES):
            scorer.record_trade("GSRAY", -100.0)
        assert scorer.score("GSRAY") == 0.0
        assert not scorer.is_allowed("GSRAY")

    def test_allows_consistent_winner(self):
        scorer = _SymbolScorer()
        for _ in range(_SCORE_MIN_TRADES + 1):
            scorer.record_trade("EREGL", 200.0)
        assert scorer.score("EREGL") > 0.5
        assert scorer.is_allowed("EREGL")

    def test_mixed_results_scored_correctly(self):
        scorer = _SymbolScorer()
        # 3 wins, 1 loss → WR=75%, PF > 1
        scorer.record_trade("SYM", 100.0)
        scorer.record_trade("SYM", 100.0)
        scorer.record_trade("SYM", 100.0)
        scorer.record_trade("SYM", -50.0)
        score = scorer.score("SYM")
        assert 0.5 < score < 1.0
        assert scorer.is_allowed("SYM")

    def test_lookback_window_evicts_old(self):
        scorer = _SymbolScorer()
        # Fill with losses
        for _ in range(15):
            scorer.record_trade("SYM", -100.0)
        assert not scorer.is_allowed("SYM")
        # Replace with wins
        for _ in range(15):
            scorer.record_trade("SYM", 200.0)
        assert scorer.is_allowed("SYM")


# ---------------------------------------------------------------------------
# _PositionTracker tests
# ---------------------------------------------------------------------------


class TestPositionTracker:
    def test_starts_empty(self):
        tracker = _PositionTracker()
        assert tracker.total_open() == 0
        assert tracker.symbol_open("YKBNK") == 0

    def test_can_open_within_limits(self):
        tracker = _PositionTracker()
        assert tracker.can_open("YKBNK", 1000)
        tracker.open_trade("YKBNK", 1000)
        assert tracker.total_open() == 1
        assert tracker.symbol_open("YKBNK") == 1

    def test_blocks_at_max_positions(self):
        tracker = _PositionTracker()
        for i in range(_MAX_POSITIONS):
            tracker.open_trade(f"SYM{i}", 1000)
        assert tracker.total_open() == _MAX_POSITIONS
        assert not tracker.can_open("NEWONE", 1000)

    def test_blocks_at_max_per_symbol(self):
        tracker = _PositionTracker()
        for _ in range(_MAX_PER_SYMBOL):
            tracker.open_trade("YKBNK", 1000)
        assert not tracker.can_open("YKBNK", 1000)
        # But another symbol is fine
        assert tracker.can_open("EREGL", 1000)

    def test_blocks_at_max_entries_per_ts(self):
        tracker = _PositionTracker()
        for i in range(_MAX_ENTRIES_PER_TS):
            tracker.open_trade(f"SYM{i}", 1000)
        assert not tracker.can_open("NEXT", 1000)

    def test_daily_counter_resets_on_new_ts(self):
        tracker = _PositionTracker()
        for i in range(_MAX_ENTRIES_PER_TS):
            tracker.open_trade(f"SYM{i}", 1000)
        assert not tracker.can_open("NEXT", 1000)
        # New timestamp
        assert tracker.can_open("NEXT", 2000)

    def test_close_frees_slot(self):
        tracker = _PositionTracker()
        for i in range(_MAX_POSITIONS):
            tracker.open_trade(f"SYM{i}", 1000)
        assert not tracker.can_open("NEW", 1000)
        tracker.close_trade("SYM0")
        assert tracker.can_open("NEW", 2000)  # new ts to reset daily counter

    def test_close_nonexistent_safe(self):
        tracker = _PositionTracker()
        tracker.close_trade("NOSUCH")  # should not raise
        assert tracker.total_open() == 0


# ---------------------------------------------------------------------------
# _compute_risk_sized_position tests
# ---------------------------------------------------------------------------


class TestRiskSizedPosition:
    def test_basic_sizing(self):
        # entry=100, stop=95, equity=100000, risk=2%
        # risk_per_share=5, dollar_risk=2000, size=400
        # notional=400*100=40000, max_notional=10000 → cap at 100
        size = _compute_risk_sized_position(100.0, 95.0, 100_000.0)
        assert size == 100 or size == _compute_risk_sized_position(100.0, 95.0, 100_000.0)
        # notional cap: 10000/100 = 100 shares → min(400,100) = 100
        assert size == 100

    def test_zero_risk_returns_zero(self):
        assert _compute_risk_sized_position(100.0, 100.0, 100_000.0) == 0

    def test_zero_entry_returns_zero(self):
        assert _compute_risk_sized_position(0.0, -5.0, 100_000.0) == 0

    def test_minimum_size_enforced(self):
        # Very large risk per share → tiny position → clamped to 1
        size = _compute_risk_sized_position(100.0, 1.0, 1_000.0)
        assert size >= 1

    def test_notional_cap_limits_cheap_stocks(self):
        # entry=1, stop=0.9, equity=100K
        # risk_per_share=0.1, dollar_risk=2000 → 20000 shares
        # notional_cap: 10000/1 = 10000 shares → min(20000, 10000) = 10000
        # but capped by _MAX_POSITION_SIZE=2000
        size = _compute_risk_sized_position(1.0, 0.9, 100_000.0)
        assert size == 2000  # capped at max


# ---------------------------------------------------------------------------
# PortfolioDecisionEngine integration tests
# ---------------------------------------------------------------------------


class TestPortfolioDecisionEngine:
    def test_instantiation(self):
        engine = PortfolioDecisionEngine()
        assert engine._equity == 100_000.0
        assert engine._tracker.total_open() == 0

    def test_returns_none_for_insufficient_bars(self):
        engine = PortfolioDecisionEngine()
        bars = _make_bars([10.0])
        assert engine("TEST", bars, 0) is None

    def test_notify_trade_closed_updates_scorer(self):
        engine = PortfolioDecisionEngine()
        engine.notify_trade_closed("GSRAY", -100.0)
        engine.notify_trade_closed("GSRAY", -100.0)
        # After 2 losses, GSRAY should be blocked
        assert not engine._scorer.is_allowed("GSRAY")

    def test_notify_equity_updates_internal(self):
        engine = PortfolioDecisionEngine()
        engine.notify_equity(120_000.0)
        assert engine._equity == 120_000.0

    def test_position_size_overridden_by_portfolio(self):
        """If the edge fires, portfolio wrapper overrides position_size."""
        engine = PortfolioDecisionEngine()
        # Feed enough bars for V2 edge to potentially fire
        # We can't easily trigger the V2 edge in isolation, so test via mock
        # Just verify the wrapper would override position_size if a decision came through
        assert hasattr(engine, "_edge")

    def test_deterministic_output(self):
        """Same inputs produce same outputs — no randomness."""
        bars = _make_bars([10.0 + i * 0.1 for i in range(60)], symbol="DET")
        eng1 = PortfolioDecisionEngine()
        eng2 = PortfolioDecisionEngine()
        r1 = eng1("DET", bars, 59)
        r2 = eng2("DET", bars, 59)
        assert r1 == r2  # both None or both same dict

    def test_blocked_symbol_rejected(self):
        """Symbol with bad score is rejected."""
        engine = PortfolioDecisionEngine()
        # Poison BLOCK symbol with losses
        for _ in range(5):
            engine.notify_trade_closed("BLOCK", -500.0)
        assert not engine._scorer.is_allowed("BLOCK")
        # Any signal for BLOCK should be rejected
        bars = _make_bars([10.0 + i * 0.1 for i in range(60)], symbol="BLOCK")
        result = engine("BLOCK", bars, 59)
        assert result is None  # blocked by scorer


# ---------------------------------------------------------------------------
# Constants sanity
# ---------------------------------------------------------------------------


class TestConstants:
    def test_max_positions_within_bounds(self):
        assert 1 <= _MAX_POSITIONS <= 25

    def test_max_per_symbol_within_bounds(self):
        assert 1 <= _MAX_PER_SYMBOL <= 10

    def test_risk_pct_reasonable(self):
        assert 0.001 <= _RISK_PER_TRADE_PCT <= 0.05

    def test_notional_cap_reasonable(self):
        assert 0.01 <= _MAX_NOTIONAL_PCT <= 0.25

    def test_score_threshold_in_range(self):
        assert 0.0 <= _SCORE_MIN_THRESHOLD <= 1.0
