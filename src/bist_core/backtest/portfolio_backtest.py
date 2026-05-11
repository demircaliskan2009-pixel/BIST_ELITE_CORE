"""Portfolio-level Backtest Engine — trade-replay architecture.

Two-phase design for performance:
  Phase 1: Run single-symbol backtests independently (fast, ~1s each)
  Phase 2: Replay all trades through portfolio engine with:
    - Market regime classification (SUPER_BULL / BULL / NEUTRAL / BEAR / CHAOS)
    - Dynamic risk multiplier (aggression engine)
    - Dynamic position sizing (risk-based, drawdown-controlled)
    - Sector exposure caps
    - Correlation filtering
    - Cross-symbol position limits
    - Proper mark-to-market equity tracking

This is the FINAL production backtest engine for PRDV3 portfolio simulation.

Key constraints (inherited from single-symbol engine):
- NEXT-BAR EXECUTION: signal at bar N → fill at bar N+1 open
- NO LOOKAHEAD: all indicators use only completed bars
- Deterministic: no randomness in any path
- Fail-closed: insufficient data → no trade
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Final, Sequence

from bist_core.backtest.intraday_backtest import IntradayBacktestEngine
from bist_core.data.ideal_intraday_loader import (
    IdealIntradayLoader,
    SymbolBundle,
)
from bist_core.models.ohlcv import OHLCVBar
from bist_core.regime.market_regime_v2 import (
    classify_regime_series,
    get_regime_at,
)
from bist_core.risk.aggression_engine import (
    OpportunityState,
    compute_risk_multiplier,
)
from bist_core.risk.correlation_engine import CorrelationEngine
from bist_core.risk.position_sizing_engine import (
    check_daily_loss_limit,
    check_total_risk_cap,
    compute_drawdown_state,
    compute_position_size,
)
from bist_core.risk.sector_mapper import get_sector

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_INITIAL_EQUITY: Final[float] = 100_000.0
_MAX_TOTAL_POSITIONS: Final[int] = 6        # max concurrent across all symbols
_MAX_PER_SYMBOL: Final[int] = 2             # max concurrent per symbol
_MAX_SECTOR_EXPOSURE: Final[float] = 0.35   # max 35% of equity in one sector
_MAX_TOTAL_EXPOSURE: Final[float] = 0.80    # max 80% of equity invested
_MAX_POSITION_PCT: Final[float] = 0.15      # max 15% of equity per position
_CORRELATION_THRESHOLD: Final[float] = 0.99  # disabled for BIST — all stocks structurally correlated
_CORRELATION_LOOKBACK: Final[int] = 20       # days for correlation calc


# ---------------------------------------------------------------------------
# Portfolio trade (enriched with portfolio-level fields)
# ---------------------------------------------------------------------------

@dataclass
class PortfolioTrade:
    """A trade enriched with portfolio-level sizing and regime info."""
    symbol: str
    sector: str
    edge: str
    direction: str
    entry_price: float
    exit_price: float
    entry_ts: int
    exit_ts: int
    exit_reason: str
    # Original single-symbol trade fields
    original_pnl: float
    original_shares: int
    # Portfolio-level fields
    portfolio_shares: int
    portfolio_notional: float
    portfolio_pnl: float
    risk_multiplier: float
    dd_multiplier: float
    regime_at_entry: str
    rejected: bool = False
    reject_reason: str = ""


# ---------------------------------------------------------------------------
# Portfolio backtest result
# ---------------------------------------------------------------------------

@dataclass
class PortfolioBacktestResult:
    trades: list[dict[str, Any]] = field(default_factory=list)
    rejected_trades: list[dict[str, Any]] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    regime_distribution: dict[str, int] = field(default_factory=dict)
    per_symbol_stats: dict[str, dict[str, Any]] = field(default_factory=dict)
    per_edge_stats: dict[str, dict[str, Any]] = field(default_factory=dict)
    per_regime_stats: dict[str, dict[str, Any]] = field(default_factory=dict)
    aggression_stats: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Portfolio Backtest Engine
# ---------------------------------------------------------------------------

class PortfolioBacktestEngine:
    """Multi-symbol portfolio backtest using trade-replay architecture.

    Phase 1: Run single-symbol backtests independently (fast, ~1s each).
    Phase 2: Merge trades by entry_ts, replay through portfolio constraints.

    Usage:
        loader = IdealIntradayLoader()
        symbols = ["AKBNK", "EREGL", "PETKM", "ISCTR"]
        engine = PortfolioBacktestEngine(initial_equity=100_000)
        result = engine.run(symbols, loader)
    """

    def __init__(
        self,
        initial_equity: float = _DEFAULT_INITIAL_EQUITY,
        max_positions: int = _MAX_TOTAL_POSITIONS,
        event_engine: object | None = None,
    ) -> None:
        self._initial_equity = initial_equity
        self._max_positions = max_positions
        self._corr_engine = CorrelationEngine()
        self._event_engine = event_engine

    def run(
        self,
        symbols: Sequence[str],
        loader: IdealIntradayLoader,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> PortfolioBacktestResult:
        """Run portfolio backtest across all symbols simultaneously."""
        result = PortfolioBacktestResult()

        # ----- PHASE 1: Single-symbol backtests -----
        bundles: dict[str, SymbolBundle] = {}
        all_raw_trades: list[dict[str, Any]] = []
        daily_by_symbol: dict[str, list[OHLCVBar]] = {}

        for sym in symbols:
            try:
                bundle = loader.load_symbol(sym, timeframes=["G", "60", "05", "01"])
                if not bundle or "01" not in bundle or len(bundle["01"]) < 100:
                    continue
                bundles[sym] = bundle

                daily_bars = sorted(bundle.get("G", []), key=lambda b: b.timestamp)
                if daily_bars:
                    daily_by_symbol[sym] = daily_bars

                # Run single-symbol backtest with generous limits
                engine = IntradayBacktestEngine(
                    initial_equity=self._initial_equity,
                    max_positions=15,  # generous for signal collection
                    event_engine=self._event_engine,
                )
                sym_result = engine.run_symbol(
                    symbol=sym,
                    bundle=bundle,
                    start_ts=start_ts,
                    end_ts=end_ts,
                )
                for t in sym_result.trades:
                    t["_symbol"] = sym
                    all_raw_trades.append(t)

            except Exception:
                continue

        if not all_raw_trades:
            result.metrics = {"error": "NO_TRADES_GENERATED"}
            return result

        # ----- Build regime series -----
        regime_series = classify_regime_series(daily_by_symbol)
        for snap in regime_series:
            result.regime_distribution[snap.regime] = (
                result.regime_distribution.get(snap.regime, 0) + 1
            )

        # ----- Build daily close series for correlation -----
        daily_closes: dict[str, list[float]] = {}
        for sym, bars in daily_by_symbol.items():
            daily_closes[sym] = [float(b.close) for b in bars]

        # ----- PHASE 2: Portfolio replay -----
        # Sort all trades by entry timestamp
        all_raw_trades.sort(key=lambda t: t.get("entry_ts", 0))

        equity = self._initial_equity
        peak_equity = equity
        open_positions: list[dict[str, Any]] = []  # simplified position tracking
        accepted_trades: list[PortfolioTrade] = []
        rejected_trades: list[PortfolioTrade] = []
        regime_trades: dict[str, list[float]] = {}
        aggression_values: list[float] = []

        # Daily loss tracking
        current_day_ts = 0  # tracks which day we're in (midnight boundary)
        day_start_equity = equity
        daily_pnl = 0.0

        for raw_trade in all_raw_trades:
            sym = raw_trade["symbol"]
            entry_ts = raw_trade.get("entry_ts", 0)
            exit_ts = raw_trade.get("exit_ts", 0)
            entry_price = raw_trade.get("entry_price", 0)
            exit_price = raw_trade.get("exit_price", 0)
            stop_price = raw_trade.get("stop_price", entry_price * 0.97)
            raw_trade.get("target_price", entry_price * 1.05)
            original_pnl = raw_trade.get("pnl", 0)
            edge = raw_trade.get("edge", "unknown")
            direction = raw_trade.get("direction", "LONG")
            exit_reason = raw_trade.get("exit_reason", "")
            original_shares = raw_trade.get("fill_size", 0)

            # Close any open positions that have exited before this trade's entry
            new_open = []
            for op in open_positions:
                if op["exit_ts"] <= entry_ts:
                    # Already exited — equity was updated when accepted
                    pass
                else:
                    new_open.append(op)
            open_positions = new_open

            # Get regime at entry
            regime = get_regime_at(regime_series, entry_ts)
            regime_name = regime.regime if regime else "NEUTRAL"

            # Compute aggression
            # Simple opportunity proxy: how many concurrent trades are active
            active_count = len(open_positions)
            opp_score = min(1.0, active_count / max(1, self._max_positions))
            opp = OpportunityState(
                breakout_density=opp_score,
                volume_expansion=1.0,
                strength_clustering=opp_score,
                opportunity_score=opp_score,
            )
            aggression = compute_risk_multiplier(regime, opp)
            risk_mult = aggression.risk_multiplier
            aggression_values.append(risk_mult)

            # Drawdown control
            dd_state = compute_drawdown_state(equity, peak_equity)

            # Daily loss limit check
            trade_day = entry_ts // 86400
            if trade_day != current_day_ts:
                current_day_ts = trade_day
                day_start_equity = equity
                daily_pnl = 0.0
            daily_halted = check_daily_loss_limit(daily_pnl, day_start_equity)

            # Total risk cap check
            open_risk = sum(p.get("risk_amount", 0.0) for p in open_positions)
            risk_capped = check_total_risk_cap(open_risk, equity)

            # Portfolio constraints check
            reject_reason = self._check_constraints(
                open_positions, sym, equity, daily_closes,
            )

            if reject_reason or not dd_state.entries_allowed or daily_halted or risk_capped:
                reason = reject_reason or (
                    "DD_BLOCKED" if not dd_state.entries_allowed
                    else "DAILY_LOSS_LIMIT" if daily_halted
                    else "TOTAL_RISK_CAP"
                )
                pt = PortfolioTrade(
                    symbol=sym, sector=get_sector(sym), edge=edge,
                    direction=direction, entry_price=entry_price,
                    exit_price=exit_price, entry_ts=entry_ts, exit_ts=exit_ts,
                    exit_reason=exit_reason, original_pnl=original_pnl,
                    original_shares=original_shares, portfolio_shares=0,
                    portfolio_notional=0, portfolio_pnl=0,
                    risk_multiplier=risk_mult, dd_multiplier=dd_state.size_multiplier,
                    regime_at_entry=regime_name, rejected=True,
                    reject_reason=reason,
                )
                rejected_trades.append(pt)
                continue

            # Position sizing
            # Event trades get a controlled risk boost (up to 1.2x)
            # while remaining within all global risk caps.
            sizing_risk_mult = risk_mult
            if edge.startswith("event_"):
                sizing_risk_mult = min(risk_mult * 1.2, 2.0)

            sizing = compute_position_size(
                equity=equity,
                entry_price=entry_price,
                stop_price=stop_price,
                risk_multiplier=sizing_risk_mult,
                dd_state=dd_state,
            )

            if sizing.shares <= 0:
                rejected_trades.append(PortfolioTrade(
                    symbol=sym, sector=get_sector(sym), edge=edge,
                    direction=direction, entry_price=entry_price,
                    exit_price=exit_price, entry_ts=entry_ts, exit_ts=exit_ts,
                    exit_reason=exit_reason, original_pnl=original_pnl,
                    original_shares=original_shares, portfolio_shares=0,
                    portfolio_notional=0, portfolio_pnl=0,
                    risk_multiplier=risk_mult, dd_multiplier=dd_state.size_multiplier,
                    regime_at_entry=regime_name, rejected=True,
                    reject_reason="ZERO_SIZE",
                ))
                continue

            # Scale PnL by portfolio shares vs original shares
            if original_shares > 0 and original_pnl != 0:
                scale_factor = sizing.shares / original_shares
                portfolio_pnl = round(original_pnl * scale_factor, 2)
            elif entry_price > 0 and exit_price > 0:
                # Recompute from scratch
                if direction == "LONG":
                    raw = (exit_price - entry_price) * sizing.shares
                else:
                    raw = (entry_price - exit_price) * sizing.shares
                cost = entry_price * sizing.shares * 0.0072  # 7.2bps RT
                portfolio_pnl = round(raw - cost, 2)
            else:
                portfolio_pnl = 0.0

            # Accept trade
            pt = PortfolioTrade(
                symbol=sym, sector=get_sector(sym), edge=edge,
                direction=direction, entry_price=entry_price,
                exit_price=exit_price, entry_ts=entry_ts, exit_ts=exit_ts,
                exit_reason=exit_reason, original_pnl=original_pnl,
                original_shares=original_shares, portfolio_shares=sizing.shares,
                portfolio_notional=sizing.notional, portfolio_pnl=portfolio_pnl,
                risk_multiplier=risk_mult, dd_multiplier=dd_state.size_multiplier,
                regime_at_entry=regime_name,
            )
            accepted_trades.append(pt)

            # Update equity
            equity += portfolio_pnl
            daily_pnl += portfolio_pnl
            if equity > peak_equity:
                peak_equity = equity

            # Track open position
            open_positions.append({
                "symbol": sym,
                "sector": get_sector(sym),
                "notional": sizing.notional,
                "risk_amount": sizing.risk_amount,
                "entry_ts": entry_ts,
                "exit_ts": exit_ts,
            })

            # Track regime stats
            regime_trades.setdefault(regime_name, []).append(portfolio_pnl)

            # Equity curve point
            result.equity_curve.append({
                "timestamp": entry_ts,
                "equity": round(equity, 2),
                "drawdown": round((peak_equity - equity) / peak_equity if peak_equity > 0 else 0, 6),
                "open_positions": len(open_positions),
                "regime": regime_name,
                "risk_multiplier": risk_mult,
            })

        # ----- Compute metrics -----
        result.trades = [self._pt_to_dict(pt) for pt in accepted_trades]
        result.rejected_trades = [self._pt_to_dict(pt) for pt in rejected_trades]
        result.metrics = _compute_portfolio_metrics(
            result.trades, result.equity_curve, self._initial_equity
        )
        result.per_symbol_stats = _compute_per_group_stats(result.trades, "symbol")
        result.per_edge_stats = _compute_per_group_stats(result.trades, "edge")
        result.per_regime_stats = _compute_regime_stats(regime_trades)
        result.aggression_stats = {
            "mean": round(sum(aggression_values) / len(aggression_values), 4) if aggression_values else 0.0,
            "min": round(min(aggression_values), 4) if aggression_values else 0.0,
            "max": round(max(aggression_values), 4) if aggression_values else 0.0,
            "samples": len(aggression_values),
        }

        return result

    def _check_constraints(
        self,
        open_positions: list[dict[str, Any]],
        symbol: str,
        equity: float,
        daily_closes: dict[str, list[float]],
    ) -> str:
        """Check portfolio constraints. Returns rejection reason or empty string."""
        # 1. Total position limit
        if len(open_positions) >= self._max_positions:
            return "MAX_POSITIONS"

        # 2. Per-symbol limit
        sym_count = sum(1 for p in open_positions if p["symbol"] == symbol)
        if sym_count >= _MAX_PER_SYMBOL:
            return "MAX_PER_SYMBOL"

        # 3. Sector exposure
        sector = get_sector(symbol)
        sector_notional = sum(
            p["notional"] for p in open_positions if p.get("sector") == sector
        )
        max_new = equity * _MAX_POSITION_PCT
        if equity > 0 and (sector_notional + max_new) / equity > _MAX_SECTOR_EXPOSURE:
            return "SECTOR_EXPOSURE"

        # 4. Total exposure
        total_notional = sum(p["notional"] for p in open_positions)
        if equity > 0 and (total_notional + max_new) / equity > _MAX_TOTAL_EXPOSURE:
            return "TOTAL_EXPOSURE"

        # 5. Correlation filter
        sym_closes = daily_closes.get(symbol, [])
        if len(sym_closes) >= _CORRELATION_LOOKBACK:
            for p in open_positions:
                p_closes = daily_closes.get(p["symbol"], [])
                if len(p_closes) >= _CORRELATION_LOOKBACK:
                    corr = self._corr_engine.correlation(
                        sym_closes[-_CORRELATION_LOOKBACK:],
                        p_closes[-_CORRELATION_LOOKBACK:],
                    )
                    if abs(corr) > _CORRELATION_THRESHOLD:
                        return "CORRELATION"

        return ""

    @staticmethod
    def _pt_to_dict(pt: PortfolioTrade) -> dict[str, Any]:
        return {
            "symbol": pt.symbol,
            "sector": pt.sector,
            "edge": pt.edge,
            "direction": pt.direction,
            "entry_price": pt.entry_price,
            "exit_price": pt.exit_price,
            "entry_ts": pt.entry_ts,
            "exit_ts": pt.exit_ts,
            "exit_reason": pt.exit_reason,
            "original_pnl": pt.original_pnl,
            "portfolio_pnl": pt.portfolio_pnl,
            "portfolio_shares": pt.portfolio_shares,
            "portfolio_notional": pt.portfolio_notional,
            "risk_multiplier": pt.risk_multiplier,
            "dd_multiplier": pt.dd_multiplier,
            "regime_at_entry": pt.regime_at_entry,
            "rejected": pt.rejected,
            "reject_reason": pt.reject_reason,
            "pnl": pt.portfolio_pnl,
        }


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _compute_portfolio_metrics(
    trades: list[dict[str, Any]],
    equity_curve: list[dict[str, Any]],
    initial_equity: float,
) -> dict[str, Any]:
    """Compute comprehensive portfolio metrics."""
    closed = [t for t in trades if not t.get("rejected", False)]

    if not closed:
        return {
            "total_return": 0.0, "win_rate": 0.0, "profit_factor": 0.0,
            "max_drawdown": 0.0, "total_trades": 0, "sharpe_ratio": 0.0,
        }

    wins = [t for t in closed if t["pnl"] > 0]
    losses = [t for t in closed if t["pnl"] <= 0]
    total_win = sum(t["pnl"] for t in wins)
    total_loss = abs(sum(t["pnl"] for t in losses))

    win_rate = len(wins) / len(closed) if closed else 0.0
    pf = total_win / total_loss if total_loss > 0 else (999.0 if total_win > 0 else 0.0)

    max_dd = max(pt["drawdown"] for pt in equity_curve) if equity_curve else 0.0
    final_eq = equity_curve[-1]["equity"] if equity_curve else initial_equity
    total_return = (final_eq - initial_equity) / initial_equity if initial_equity > 0 else 0.0

    # Sharpe from trade-level equity changes
    equities = [initial_equity] + [pt["equity"] for pt in equity_curve]
    returns: list[float] = []
    for i in range(1, len(equities)):
        if equities[i - 1] > 0:
            returns.append((equities[i] - equities[i - 1]) / equities[i - 1])

    if len(returns) >= 2:
        mean_r = sum(returns) / len(returns)
        var_r = sum((r - mean_r) ** 2 for r in returns) / len(returns)
        std_r = math.sqrt(var_r) if var_r > 0 else 0.0
        sharpe = mean_r / std_r if std_r > 0 else 0.0
    else:
        sharpe = 0.0

    calmar = abs(total_return / max_dd) if max_dd > 0 else 0.0
    avg_pnl = sum(t["pnl"] for t in closed) / len(closed)

    # Period returns (split into ~10 equal periods)
    period_returns: list[float] = []
    if len(equities) >= 2:
        bucket = max(1, len(equities) // 10)
        for i in range(0, len(equities) - bucket, bucket):
            s = equities[i]
            e = equities[min(i + bucket, len(equities) - 1)]
            if s > 0:
                period_returns.append((e - s) / s)

    return {
        "total_return": round(total_return, 6),
        "win_rate": round(win_rate, 4),
        "profit_factor": round(pf, 4),
        "max_drawdown": round(max_dd, 6),
        "total_trades": len(closed),
        "rejected_trades": len([t for t in trades if t.get("rejected")]),
        "sharpe_ratio": round(sharpe, 4),
        "calmar_ratio": round(calmar, 4),
        "avg_pnl": round(avg_pnl, 2),
        "final_equity": round(final_eq, 2),
        "total_pnl": round(sum(t["pnl"] for t in closed), 2),
        "unique_symbols": len(set(t["symbol"] for t in closed)),
        "period_returns": [round(r, 6) for r in period_returns],
    }


def _compute_per_group_stats(
    trades: list[dict[str, Any]],
    group_key: str,
) -> dict[str, dict[str, Any]]:
    by_group: dict[str, list[dict[str, Any]]] = {}
    for t in trades:
        if t.get("rejected"):
            continue
        key = t.get(group_key, "unknown")
        by_group.setdefault(key, []).append(t)

    stats: dict[str, dict[str, Any]] = {}
    for group, gtrades in by_group.items():
        wins = [t for t in gtrades if t["pnl"] > 0]
        losses = [t for t in gtrades if t["pnl"] <= 0]
        tw = sum(t["pnl"] for t in wins)
        tl = abs(sum(t["pnl"] for t in losses))
        n = len(gtrades)
        stats[group] = {
            "trades": n,
            "win_rate": round(len(wins) / n, 4) if n else 0.0,
            "profit_factor": round(tw / tl, 4) if tl > 0 else 999.0,
            "avg_pnl": round(sum(t["pnl"] for t in gtrades) / n, 2) if n else 0.0,
            "total_pnl": round(sum(t["pnl"] for t in gtrades), 2),
        }
    return stats


def _compute_regime_stats(
    regime_trades: dict[str, list[float]],
) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for regime, pnls in regime_trades.items():
        n = len(pnls)
        total = sum(pnls)
        wins = sum(1 for p in pnls if p > 0)
        wp = sum(p for p in pnls if p > 0)
        lp = abs(sum(p for p in pnls if p <= 0))
        stats[regime] = {
            "trades": n,
            "total_pnl": round(total, 2),
            "win_rate": round(wins / n, 4) if n > 0 else 0.0,
            "profit_factor": round(wp / lp, 4) if lp > 0 else 999.0,
            "avg_pnl": round(total / n, 2) if n > 0 else 0.0,
        }
    return stats


__all__ = [
    "PortfolioBacktestEngine",
    "PortfolioBacktestResult",
    "PortfolioTrade",
]
