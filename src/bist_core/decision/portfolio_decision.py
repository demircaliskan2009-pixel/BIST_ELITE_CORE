"""BIST Portfolio Decision Wrapper — portfolio-aware layer over Edge V2.

This module wraps BistEdgeV2Decision with portfolio-level intelligence:

1. MAX CONCURRENT POSITIONS: caps open positions to limit clustering risk
   and idle capital. At any moment, at most _MAX_POSITIONS trades open.

2. SYMBOL QUALITY SCORING: rolling window score per symbol based on
   recent win rate and profit factor. Symbols below threshold are blocked.
   Score is computed from the wrapper's own trade history — no manual
   exclusion, no lookahead, fully adaptive.

3. INVERSE-ATR POSITION SIZING: position size = risk_budget / ATR,
   equalizing dollar risk per trade across symbols. Replaces the
   fixed-notional sizing in V2 for portfolio-level risk balancing.

4. PER-SYMBOL CONCENTRATION CAP: max N open trades per symbol at any
   time, preventing one symbol from dominating the portfolio.

5. MAX DAILY ENTRIES: limits new entries per timestamp to avoid cluster
   entries on regime-shift days.

All state is deterministic and replayable. No randomness.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from bist_core.decision.meta_engine import MetaDecisionEngine, classify_regime, _REGIME_CAPITAL_MULT
from bist_core.decision.universe_selector import UniverseSelector
from bist_core.events.event_policy import (
    EventEdgeVerdict,
    get_event_size_multiplier,
    get_event_verdict,
)
from bist_core.models.ohlcv import OHLCVBar

# Try loading centralized config
try:
    from bist_core.config.bist_prod_config import BIST_CONFIG

    _cfg = BIST_CONFIG
except Exception:  # pragma: no cover
    _cfg = None

# ---------------------------------------------------------------------------
# Portfolio constants — from centralized config when available
# ---------------------------------------------------------------------------

if _cfg is not None:
    _MAX_POSITIONS = _cfg.portfolio.max_positions
    _MAX_PER_SYMBOL = _cfg.portfolio.max_per_symbol
    _MAX_ENTRIES_PER_TS = _cfg.portfolio.max_entries_per_ts
    _RISK_PER_TRADE_PCT = _cfg.portfolio.risk_per_trade_pct
    _MAX_NOTIONAL_PCT = _cfg.portfolio.max_notional_pct
    _INITIAL_EQUITY = _cfg.portfolio.initial_equity
    _DAILY_LOSS_LIMIT_PCT = _cfg.portfolio.daily_loss_limit_pct
    _MAX_DRAWDOWN_KILL_PCT = _cfg.portfolio.max_drawdown_kill_pct
    _MIN_POSITION_SIZE = _cfg.portfolio.min_position_size
    _MAX_POSITION_SIZE = _cfg.portfolio.max_position_size
    _SCORE_LOOKBACK = _cfg.scoring.lookback
    _SCORE_MIN_TRADES = _cfg.scoring.min_trades
    _SCORE_MIN_THRESHOLD = _cfg.scoring.min_threshold
    _EVENT_STOP_PCT = _cfg.event_policy.event_entry.stop_pct
    _EVENT_RR_MIN = _cfg.event_policy.event_entry.min_rr
    _EVENT_ATR_PERIOD = _cfg.event_policy.event_entry.atr_period
    _EVENT_SWING_LOOKBACK = _cfg.event_policy.event_entry.swing_lookback
    _EVENT_ENTRY_KINDS = _cfg.event_policy.entry_kinds
else:
    _MAX_POSITIONS = 18
    _MAX_PER_SYMBOL = 4
    _MAX_ENTRIES_PER_TS = 10
    _RISK_PER_TRADE_PCT = 0.01
    _MAX_NOTIONAL_PCT = 0.10
    _INITIAL_EQUITY = 100_000.0
    _DAILY_LOSS_LIMIT_PCT = 0.03
    _MAX_DRAWDOWN_KILL_PCT = 0.10
    _MIN_POSITION_SIZE = 1
    _MAX_POSITION_SIZE = 2000
    _SCORE_LOOKBACK = 15
    _SCORE_MIN_TRADES = 2
    _SCORE_MIN_THRESHOLD = 0.15
    _EVENT_STOP_PCT = 0.03
    _EVENT_RR_MIN = 2.0
    _EVENT_ATR_PERIOD = 14
    _EVENT_SWING_LOOKBACK = 10
    _EVENT_ENTRY_KINDS = frozenset({"partnership"})


# ---------------------------------------------------------------------------
# Symbol scorer — rolling quality assessment
# ---------------------------------------------------------------------------

class _SymbolScorer:
    """Tracks per-symbol trade outcomes and computes rolling quality score."""

    def __init__(self) -> None:
        self._history: dict[str, list[float]] = {}  # symbol -> recent PnLs

    def record_trade(self, symbol: str, pnl: float) -> None:
        if symbol not in self._history:
            self._history[symbol] = []
        self._history[symbol].append(pnl)
        # Keep only last N
        if len(self._history[symbol]) > _SCORE_LOOKBACK:
            self._history[symbol] = self._history[symbol][-_SCORE_LOOKBACK:]

    def score(self, symbol: str) -> float:
        """Return quality score in [0, 1]. Higher = better.

        Returns 0.5 if insufficient data (benefit of the doubt).
        """
        history = self._history.get(symbol, [])
        if len(history) < _SCORE_MIN_TRADES:
            return 0.5  # neutral — allow trading

        wins = sum(1 for p in history if p > 0)
        losses_val = abs(sum(p for p in history if p <= 0))
        wins_val = sum(p for p in history if p > 0)

        wr = wins / len(history)
        pf = wins_val / losses_val if losses_val > 0 else 2.0

        # Composite: 50% WR + 50% PF (normalized)
        pf_norm = min(pf, 3.0) / 3.0
        return 0.5 * wr + 0.5 * pf_norm

    def is_allowed(self, symbol: str) -> bool:
        return self.score(symbol) >= _SCORE_MIN_THRESHOLD


# ---------------------------------------------------------------------------
# Portfolio position tracker
# ---------------------------------------------------------------------------

class _PositionTracker:
    """Tracks open positions by symbol. Deterministic."""

    def __init__(self) -> None:
        self._open: dict[str, int] = {}  # symbol -> count of open trades
        self._total_open: int = 0
        self._entries_this_ts: int = 0
        self._current_ts: int = -1

    def total_open(self) -> int:
        return self._total_open

    def symbol_open(self, symbol: str) -> int:
        return self._open.get(symbol, 0)

    def can_open(self, symbol: str, timestamp: int) -> bool:
        """Check all portfolio-level gates."""
        # Reset daily counter on new timestamp
        if timestamp != self._current_ts:
            self._entries_this_ts = 0
            self._current_ts = timestamp

        if self._total_open >= _MAX_POSITIONS:
            return False
        if self._open.get(symbol, 0) >= _MAX_PER_SYMBOL:
            return False
        if self._entries_this_ts >= _MAX_ENTRIES_PER_TS:
            return False
        return True

    def open_trade(self, symbol: str, timestamp: int) -> None:
        if timestamp != self._current_ts:
            self._entries_this_ts = 0
            self._current_ts = timestamp

        self._open[symbol] = self._open.get(symbol, 0) + 1
        self._total_open += 1
        self._entries_this_ts += 1

    def close_trade(self, symbol: str) -> None:
        if symbol in self._open and self._open[symbol] > 0:
            self._open[symbol] -= 1
            self._total_open = max(0, self._total_open - 1)


# ---------------------------------------------------------------------------
# Inverse-ATR position sizing
# ---------------------------------------------------------------------------

def _compute_risk_sized_position(
    entry: float,
    stop: float,
    equity: float,
) -> int:
    """Size position so that a full stop-out loses exactly _RISK_PER_TRADE_PCT of equity.

    Also caps notional exposure at _MAX_NOTIONAL_PCT of equity to prevent
    overleveraged positions when stops are tight.
    """
    risk_per_share = abs(entry - stop)
    if risk_per_share <= 0 or entry <= 0:
        return 0
    dollar_risk = equity * _RISK_PER_TRADE_PCT
    max_notional = equity * _MAX_NOTIONAL_PCT
    size_by_risk = dollar_risk / risk_per_share
    size_by_notional = max_notional / entry
    size = int(min(size_by_risk, size_by_notional))
    return max(_MIN_POSITION_SIZE, min(size, _MAX_POSITION_SIZE))


# ---------------------------------------------------------------------------
# Portfolio decision wrapper
# ---------------------------------------------------------------------------

class PortfolioDecisionEngine:
    """Portfolio-aware wrapper over MetaDecisionEngine.

    Callable matching DecisionFunction protocol:
        (symbol, bars, bar_index) -> Optional[Dict]

    Adds:
    - dynamic universe selection (scores + ranks symbols)
    - max concurrent position cap
    - per-symbol concentration cap
    - daily entry throttle
    - rolling symbol quality scoring
    - risk-budget position sizing with regime capital multiplier
    """

    def __init__(self, equity: float = _INITIAL_EQUITY, event_filter_enabled: bool = False) -> None:
        self._edge = MetaDecisionEngine()
        self._tracker = _PositionTracker()
        self._scorer = _SymbolScorer()
        self._universe = UniverseSelector()
        self._equity = equity
        self._peak_equity = equity
        self._daily_start_equity = equity
        self._daily_pnl = 0.0
        self._current_day_ts: int = -1
        self._kill_switch = False
        self._pending_closes: dict[str, list[dict]] = {}
        self._open_entries: dict[str, list[dict]] = {}
        # Event policy filter
        self._event_filter_enabled = event_filter_enabled
        self._event_index: dict[tuple[str, str], list[str]] = {}  # (date, symbol) → [kind]
        self._event_boost_log: dict[str, str] = {}  # symbol → reason (last)
        self._event_log: list[dict] = []  # traceability: per-trade event sizing audit
        self._event_fired: dict[tuple[str, int], bool] = {}  # (symbol, ts) → already fired

    def load_event_index(self, event_index: dict[tuple[str, str], list[str]]) -> None:
        """Load pre-built event index: (date_str, symbol) → [event_kind].

        Used for daily-level event policy filtering.
        """
        self._event_index = event_index

    def _check_event_policy(
        self, symbol: str, timestamp: int
    ) -> tuple[bool, float, str, str]:
        """Check event policy for a symbol on a given day.

        Returns (allowed, size_multiplier, event_kind, reason).
        Priority: NEGATIVE (block) > POSITIVE (boost size) > SOFT_NEGATIVE (reduce size).
        POSITIVE events have a 5-day lookback window (alpha builds over time).
        """
        if not self._event_filter_enabled or not self._event_index:
            return (True, 1.0, "", "")

        from datetime import datetime, timedelta, timezone

        date_str = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime(
            "%Y-%m-%d"
        )

        best_pos_mult = 0.0
        best_pos_kind = ""
        soft_neg_mult = 1.0
        soft_neg_kind = ""

        # Day-of events: NEGATIVE blocks, collect POSITIVE/SOFT_NEGATIVE multipliers
        kinds = self._event_index.get((date_str, symbol), [])
        for kind in kinds:
            verdict = get_event_verdict(kind)
            if verdict == EventEdgeVerdict.NEGATIVE:
                return (False, 0.0, kind, f"BLOCKED: {kind} on {date_str}")
            mult = get_event_size_multiplier(kind)
            if verdict == EventEdgeVerdict.POSITIVE and mult > best_pos_mult:
                best_pos_mult = mult
                best_pos_kind = kind
            elif verdict == EventEdgeVerdict.SOFT_NEGATIVE and mult < soft_neg_mult:
                soft_neg_mult = mult
                soft_neg_kind = kind

        # 5-day lookback for POSITIVE events (alpha builds over time)
        if best_pos_mult == 0.0:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            for offset in range(1, 5):
                check_date = (dt - timedelta(days=offset)).strftime("%Y-%m-%d")
                pos_kinds = self._event_index.get((check_date, symbol), [])
                for kind in pos_kinds:
                    if get_event_verdict(kind) == EventEdgeVerdict.POSITIVE:
                        mult = get_event_size_multiplier(kind)
                        if mult > best_pos_mult:
                            best_pos_mult = mult
                            best_pos_kind = kind

        # Priority: POSITIVE > SOFT_NEGATIVE > NEUTRAL
        if best_pos_mult > 1.0:
            return (
                True,
                best_pos_mult,
                best_pos_kind,
                f"BOOSTED: {best_pos_kind} (×{best_pos_mult})",
            )
        if soft_neg_mult < 1.0:
            return (
                True,
                soft_neg_mult,
                soft_neg_kind,
                f"PENALIZED: {soft_neg_kind} (×{soft_neg_mult})",
            )
        return (True, 1.0, "", "")

    def _generate_event_entry(
        self,
        symbol: str,
        bars: List[OHLCVBar],
        bar_index: int,
        event_kind: str,
        event_mult: float,
    ) -> Optional[Dict[str, Any]]:
        """Generate event-driven LONG entry when POSITIVE event fires.

        Rules:
        - Entry = current bar close (fills at next bar open via backtest)
        - Stop = max(swing low over lookback, entry × (1 - 3%))
        - Target = entry + 2R minimum
        - One event entry per (symbol, timestamp) — no duplicates
        """
        if bar_index < _EVENT_ATR_PERIOD + 1:
            return None

        bar = bars[bar_index]
        entry = float(bar.close)
        if entry <= 0:
            return None

        # Deduplicate: one event entry per symbol per day
        ts = bar.timestamp
        key = (symbol, ts)
        if self._event_fired.get(key, False):
            return None

        # Stop: recent swing low or fixed 3%
        lookback_start = max(0, bar_index - _EVENT_SWING_LOOKBACK)
        swing_low = min(float(b.low) for b in bars[lookback_start : bar_index + 1])
        fixed_stop = entry * (1.0 - _EVENT_STOP_PCT)
        stop = max(swing_low, fixed_stop)  # tighter of the two

        # Ensure stop is below entry
        if stop >= entry:
            stop = fixed_stop
        if stop >= entry:
            return None

        # Target: 2R minimum
        risk = entry - stop
        target = round(entry + risk * _EVENT_RR_MIN, 4)
        stop = round(stop, 4)

        # Regime-based capital multiplier (same logic as meta engine)
        window = bars[: bar_index + 1]
        closes = [float(b.close) for b in window]
        regime = classify_regime(closes)
        capital_mult = _REGIME_CAPITAL_MULT.get(regime, 1.0)

        self._event_fired[key] = True

        return {
            "symbol": symbol,
            "entry": entry,
            "stop": stop,
            "target": target,
            "position_size": 0,  # will be computed by caller
            "edge": f"event_{event_kind}",
            "regime": regime.value,
            "capital_mult": capital_mult,
            "source": "event",
            "event_kind": event_kind,
        }

    def notify_fill_failed(self, symbol: str) -> None:
        """Called by backtest engine when a queued decision fails to fill.

        Releases the tracker slot that was incremented in __call__ at
        decision time. Without this, unfilled decisions (rejected orders,
        end-of-data pending) permanently consume tracker slots until
        _MAX_POSITIONS is hit and all subsequent entries are blocked.
        """
        self._tracker.close_trade(symbol)

    def notify_trade_closed(self, symbol: str, pnl: float) -> None:
        """Called by the backtest engine when a trade closes.

        Feedback loop for symbol quality scoring and daily PnL tracking.
        """
        self._scorer.record_trade(symbol, pnl)
        self._tracker.close_trade(symbol)
        self._daily_pnl += pnl

    def notify_equity(self, equity: float) -> None:
        """Update equity for risk-budget sizing and drawdown tracking."""
        self._equity = equity
        if equity > self._peak_equity:
            self._peak_equity = equity

    def __call__(
        self,
        symbol: str,
        bars: List[OHLCVBar],
        bar_index: int,
    ) -> Optional[Dict[str, Any]]:
        if bar_index < 1 or not bars:
            return None

        timestamp = bars[bar_index].timestamp if bar_index < len(bars) else 0

        # --- Daily reset + kill switch checks ---
        if timestamp != self._current_day_ts:
            self._daily_pnl = 0.0
            self._daily_start_equity = self._equity
            self._current_day_ts = timestamp

        # Kill switch: max drawdown from peak breached
        if self._peak_equity > 0:
            dd = (self._peak_equity - self._equity) / self._peak_equity
            if dd >= _MAX_DRAWDOWN_KILL_PCT:
                self._kill_switch = True
        if self._kill_switch:
            return None

        # Daily loss limit: halt new entries when daily loss exceeds threshold
        if self._daily_start_equity > 0:
            daily_loss_pct = abs(min(0.0, self._daily_pnl)) / self._daily_start_equity
            if daily_loss_pct >= _DAILY_LOSS_LIMIT_PCT:
                return None

        # --- Universe selection gate ---
        if bar_index < len(bars):
            _bar = bars[bar_index]
            self._universe.update_bar(symbol, _bar.close, _bar.volume, timestamp)
        if not self._universe.is_allowed(symbol):
            return None

        # --- Portfolio gates ---

        # 1. Max positions
        if not self._tracker.can_open(symbol, timestamp):
            return None

        # 2. Symbol quality
        if not self._scorer.is_allowed(symbol):
            return None

        # 3. Event policy gate (evidence-based, Phase 2 alpha study)
        allowed, event_mult, event_kind, event_reason = self._check_event_policy(
            symbol, timestamp
        )
        if not allowed:
            return None

        # --- Meta engine signal ---
        decision = self._edge(symbol, bars, bar_index)

        # --- Event-driven entry fallback ---
        # When POSITIVE event fires and no technical signal, generate event entry
        if decision is None and self._event_filter_enabled:
            if event_kind in _EVENT_ENTRY_KINDS:
                decision = self._generate_event_entry(
                    symbol, bars, bar_index, event_kind, event_mult
                )

        if decision is None:
            return None

        # Tag source for traceability
        if "source" not in decision:
            decision["source"] = "technical"
        if "event_kind" not in decision:
            decision["event_kind"] = event_kind or ""

        # --- Risk-budget position sizing with regime capital multiplier ---
        entry = decision["entry"]
        stop = decision["stop"]
        capital_mult = decision.get("capital_mult", 1.0)
        adjusted_equity = self._equity * capital_mult
        base_size = _compute_risk_sized_position(entry, stop, adjusted_equity)

        # Apply event multiplier to position size (evidence-based)
        position_size = base_size
        if event_mult != 1.0:
            position_size = max(
                _MIN_POSITION_SIZE,
                min(int(base_size * event_mult), _MAX_POSITION_SIZE),
            )

        if position_size < _MIN_POSITION_SIZE:
            return None

        # Record the open
        self._tracker.open_trade(symbol, timestamp)

        decision["position_size"] = position_size
        # Traceability (event sizing audit trail)
        decision["event_kind"] = event_kind or decision.get("event_kind", "")
        decision["event_multiplier"] = event_mult
        decision["final_position_size"] = position_size
        if self._event_filter_enabled:
            self._event_log.append({
                "symbol": symbol,
                "timestamp": timestamp,
                "source": decision.get("source", "technical"),
                "event_kind": event_kind or "none",
                "event_multiplier": event_mult,
                "base_size": base_size,
                "final_size": position_size,
                "reason": event_reason,
            })
        return decision


__all__ = ["PortfolioDecisionEngine"]
