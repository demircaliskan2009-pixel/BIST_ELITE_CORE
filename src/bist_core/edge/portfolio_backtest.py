from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence

from bist_core.edge.paper_trading import PaperTradingConfig
from bist_core.edge.portfolio import PRDV3PortfolioEngineConfig, run_prdv3_multi_symbol_portfolio_engine
from bist_core.edge.registry import EdgeDefinition
from bist_core.edge.validation import _signal_state
from bist_core.execution.paper_engine import OrderSide, SlippageModel
from bist_core.models.ohlcv import OHLCVBar, normalize_timestamp
from bist_core.portfolio import Ledger
from bist_core.risk.correlation_engine import CorrelationEngine
from bist_core.risk.sector_mapper import get_sector


@dataclass(frozen=True)
class PRDV3PortfolioBacktestConfig:
    portfolio_engine_config: PRDV3PortfolioEngineConfig = field(default_factory=PRDV3PortfolioEngineConfig)
    paper_trading_config: PaperTradingConfig = field(default_factory=PaperTradingConfig)
    take_profit_multiple: float = 2.0


@dataclass(frozen=True)
class PRDV3PortfolioBacktestTrade:
    trade_id: str
    symbol: str
    edge_id: str
    signal_timestamp: int
    entry_bar_index: int
    entry_timestamp: int
    entry_open_price: float
    entry_fill_price: float
    exit_bar_index: int
    exit_timestamp: int
    exit_price: float
    exit_fill_price: float
    share_count: int
    bars_held: int
    allocation_pct: float
    exposure_amount: float
    risk_amount: float
    stop_price: float
    target_price: float
    exit_reason: str
    gross_pnl: float
    net_pnl: float
    return_pct: float
    commission_paid: float
    slippage_paid: float
    total_cost: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "edge_id": self.edge_id,
            "signal_timestamp": self.signal_timestamp,
            "entry_bar_index": self.entry_bar_index,
            "entry_timestamp": self.entry_timestamp,
            "entry_open_price": self.entry_open_price,
            "entry_fill_price": self.entry_fill_price,
            "exit_bar_index": self.exit_bar_index,
            "exit_timestamp": self.exit_timestamp,
            "exit_price": self.exit_price,
            "exit_fill_price": self.exit_fill_price,
            "share_count": self.share_count,
            "bars_held": self.bars_held,
            "allocation_pct": self.allocation_pct,
            "exposure_amount": self.exposure_amount,
            "risk_amount": self.risk_amount,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "exit_reason": self.exit_reason,
            "gross_pnl": self.gross_pnl,
            "net_pnl": self.net_pnl,
            "return_pct": self.return_pct,
            "commission_paid": self.commission_paid,
            "slippage_paid": self.slippage_paid,
            "total_cost": self.total_cost,
        }


@dataclass(frozen=True)
class PRDV3PortfolioBacktestOpenPosition:
    trade_id: str
    symbol: str
    edge_id: str
    entry_bar_index: int
    entry_timestamp: int
    entry_fill_price: float
    share_count: int
    allocation_pct: float
    exposure_amount: float
    risk_amount: float
    stop_price: float
    target_price: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "edge_id": self.edge_id,
            "entry_bar_index": self.entry_bar_index,
            "entry_timestamp": self.entry_timestamp,
            "entry_fill_price": self.entry_fill_price,
            "share_count": self.share_count,
            "allocation_pct": self.allocation_pct,
            "exposure_amount": self.exposure_amount,
            "risk_amount": self.risk_amount,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
        }


@dataclass(frozen=True)
class PRDV3PortfolioBacktestResult:
    valid: bool
    blocked_reason: str | None
    metrics: dict[str, Any]
    trades: tuple[PRDV3PortfolioBacktestTrade, ...]
    open_positions: tuple[PRDV3PortfolioBacktestOpenPosition, ...]
    equity_curve: tuple[dict[str, Any], ...]
    logs: tuple[dict[str, Any], ...]
    skipped_symbols: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "blocked_reason": self.blocked_reason,
            "metrics": dict(self.metrics),
            "trades": [trade.to_dict() for trade in self.trades],
            "open_positions": [position.to_dict() for position in self.open_positions],
            "equity_curve": [dict(point) for point in self.equity_curve],
            "logs": [dict(log) for log in self.logs],
            "skipped_symbols": list(self.skipped_symbols),
        }


@dataclass
class _ScheduledEntry:
    symbol: str
    edge_id: str
    signal_timestamp: int
    execute_bar_index: int
    position_budget: float
    allocation_pct: float
    risk_amount: float


@dataclass
class _ScheduledExit:
    symbol: str
    execute_bar_index: int
    reason: str


@dataclass
class _OpenPosition:
    trade_id: str
    symbol: str
    edge_id: str
    signal_timestamp: int
    entry_bar_index: int
    entry_timestamp: int
    entry_open_price: float
    entry_fill_price: float
    entry_commission: float
    entry_slippage: float
    share_count: int
    allocation_pct: float
    risk_amount: float
    stop_price: float
    target_price: float


def _round_value(value: float) -> float:
    return round(float(value), 6)


def _empty_metrics(initial_equity: float) -> dict[str, Any]:
    return {
        "total_return": 0.0,
        "max_drawdown": 0.0,
        "sharpe_ratio": 0.0,
        "expectancy": 0.0,
        "win_rate": 0.0,
        "trade_count": 0,
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "final_equity": _round_value(initial_equity),
        "open_positions": 0,
    }


def _blocked_result(reason: str, initial_equity: float, logs: Sequence[dict[str, Any]] | None = None, skipped_symbols: Sequence[str] | None = None) -> PRDV3PortfolioBacktestResult:
    return PRDV3PortfolioBacktestResult(
        valid=False,
        blocked_reason=reason,
        metrics=_empty_metrics(initial_equity),
        trades=(),
        open_positions=(),
        equity_curve=(),
        logs=tuple(logs or ()),
        skipped_symbols=tuple(sorted(set(skipped_symbols or ()))),
    )


def _validate_config(config: PRDV3PortfolioBacktestConfig) -> str | None:
    if config.take_profit_multiple <= 0.0:
        return "invalid_config:take_profit_multiple"
    paper_config = config.paper_trading_config
    if paper_config.initial_capital <= 0.0:
        return "invalid_config:non_positive_initial_capital"
    if paper_config.commission_pct < 0.0:
        return "invalid_config:negative_commission_pct"
    if paper_config.slippage_pct < 0.0:
        return "invalid_config:negative_slippage_pct"
    if paper_config.max_fill_share_of_bar_volume <= 0.0 or paper_config.max_fill_share_of_bar_volume > 1.0:
        return "invalid_config:max_fill_share_of_bar_volume"
    return None


def _normalize_symbols(symbols: Sequence[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        normalized = str(symbol or "").strip().upper()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return tuple(ordered)


def _normalize_history(historical_data: Mapping[str, Sequence[OHLCVBar]]) -> dict[str, tuple[OHLCVBar, ...]]:
    normalized: dict[str, tuple[OHLCVBar, ...]] = {}
    for symbol, bars in historical_data.items():
        normalized_symbol = str(symbol or "").strip().upper()
        if not normalized_symbol:
            continue
        normalized[normalized_symbol] = tuple(bars)
    return normalized


def _validate_symbol_bars(symbol: str, bars: Sequence[OHLCVBar]) -> str | None:
    if len(bars) < 2:
        return "invalid_data:insufficient_history"
    previous_timestamp: int | None = None
    for bar in bars:
        timestamp = normalize_timestamp(bar.timestamp)
        if previous_timestamp is not None and timestamp <= previous_timestamp:
            return "invalid_data:non_monotonic_timestamps"
        previous_timestamp = timestamp
        if str(bar.symbol or "").strip().upper() != symbol:
            return "invalid_data:mixed_symbols"
        if any(float(price) <= 0.0 for price in (bar.open, bar.high, bar.low, bar.close)):
            return "invalid_data:non_positive_price"
        if float(bar.volume) < 0.0:
            return "invalid_data:negative_volume"
        if float(bar.high) < max(float(bar.open), float(bar.low), float(bar.close)):
            return "invalid_data:high_below_bar_range"
        if float(bar.low) > min(float(bar.open), float(bar.high), float(bar.close)):
            return "invalid_data:low_above_bar_range"
    return None


def _has_executable_liquidity(bars: Sequence[OHLCVBar], config: PRDV3PortfolioBacktestConfig) -> bool:
    return any(_max_fill_quantity(bar, config) >= 1 for bar in bars)


def _max_fill_quantity(bar: OHLCVBar, config: PRDV3PortfolioBacktestConfig) -> int:
    return int(math.floor(float(bar.volume) * config.paper_trading_config.max_fill_share_of_bar_volume))


def _returns_signature(bars: Sequence[OHLCVBar], lookback: int) -> list[float]:
    closes = [float(bar.close) for bar in bars if float(bar.close) > 0.0]
    if len(closes) < 3:
        return []
    trailing = closes[-(lookback + 1) :]
    output: list[float] = []
    for previous, current in zip(trailing, trailing[1:]):
        if previous <= 0.0:
            return []
        output.append((current / previous) - 1.0)
    return output


def _exposure_amount(position: _OpenPosition, mark_price: float) -> float:
    return _round_value(float(position.share_count) * float(mark_price))


def _risk_fraction(position_budget: float, risk_amount: float, min_stop_pct: float) -> float:
    if position_budget > 0.0 and risk_amount > 0.0:
        return max(float(risk_amount) / float(position_budget), float(min_stop_pct) / 100.0)
    return float(min_stop_pct) / 100.0


def _next_bar_index(current_index: int, bars: Sequence[OHLCVBar]) -> int | None:
    candidate = current_index + 1
    if candidate < len(bars):
        return candidate
    return None


def _close_position(
    position: _OpenPosition,
    *,
    exit_bar_index: int,
    exit_timestamp: int,
    raw_exit_price: float,
    exit_reason: str,
    ledger: Ledger,
    commission_pct: float,
    slippage_model: SlippageModel,
) -> PRDV3PortfolioBacktestTrade:
    exit_fill_price = float(slippage_model.compute(raw_exit_price, OrderSide.SELL))
    ledger.apply_fill(
        {
            "symbol": position.symbol,
            "side": "SELL",
            "qty": position.share_count,
            "price": exit_fill_price,
        }
    )
    exit_commission = _round_value(exit_fill_price * position.share_count * commission_pct)
    exit_slippage = _round_value((raw_exit_price - exit_fill_price) * position.share_count)
    commission_paid = _round_value(position.entry_commission + exit_commission)
    slippage_paid = _round_value(position.entry_slippage + exit_slippage)
    gross_pnl = _round_value((raw_exit_price - position.entry_open_price) * position.share_count)
    net_pnl = _round_value((exit_fill_price - position.entry_fill_price) * position.share_count - commission_paid)
    exposure_amount = _round_value(position.entry_fill_price * position.share_count)
    total_cost = _round_value(commission_paid + slippage_paid)
    return_pct = _round_value(net_pnl / exposure_amount) if exposure_amount > 0.0 else 0.0
    return PRDV3PortfolioBacktestTrade(
        trade_id=position.trade_id,
        symbol=position.symbol,
        edge_id=position.edge_id,
        signal_timestamp=position.signal_timestamp,
        entry_bar_index=position.entry_bar_index,
        entry_timestamp=position.entry_timestamp,
        entry_open_price=_round_value(position.entry_open_price),
        entry_fill_price=_round_value(position.entry_fill_price),
        exit_bar_index=exit_bar_index,
        exit_timestamp=exit_timestamp,
        exit_price=_round_value(raw_exit_price),
        exit_fill_price=_round_value(exit_fill_price),
        share_count=position.share_count,
        bars_held=(exit_bar_index - position.entry_bar_index) + 1,
        allocation_pct=_round_value(position.allocation_pct),
        exposure_amount=exposure_amount,
        risk_amount=_round_value(position.risk_amount),
        stop_price=_round_value(position.stop_price),
        target_price=_round_value(position.target_price),
        exit_reason=exit_reason,
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        return_pct=return_pct,
        commission_paid=commission_paid,
        slippage_paid=slippage_paid,
        total_cost=total_cost,
    )


def _open_position_snapshot(position: _OpenPosition) -> PRDV3PortfolioBacktestOpenPosition:
    return PRDV3PortfolioBacktestOpenPosition(
        trade_id=position.trade_id,
        symbol=position.symbol,
        edge_id=position.edge_id,
        entry_bar_index=position.entry_bar_index,
        entry_timestamp=position.entry_timestamp,
        entry_fill_price=_round_value(position.entry_fill_price),
        share_count=position.share_count,
        allocation_pct=_round_value(position.allocation_pct),
        exposure_amount=_round_value(position.entry_fill_price * position.share_count),
        risk_amount=_round_value(position.risk_amount),
        stop_price=_round_value(position.stop_price),
        target_price=_round_value(position.target_price),
    )


def _build_metrics(
    trades: Sequence[PRDV3PortfolioBacktestTrade],
    equity_curve: Sequence[dict[str, Any]],
    initial_equity: float,
    final_unrealized_pnl: float,
    open_count: int,
) -> dict[str, Any]:
    equities = [float(point["equity"]) for point in equity_curve]
    peak = float(initial_equity)
    max_drawdown = 0.0
    for equity in equities:
        if equity > peak:
            peak = equity
        drawdown = (peak - equity) / peak if peak > 0.0 else 0.0
        if drawdown > max_drawdown:
            max_drawdown = drawdown

    returns: list[float] = []
    for previous, current in zip(equities, equities[1:]):
        if previous > 0.0:
            returns.append((current - previous) / previous)
    if len(returns) >= 2:
        mean_return = sum(returns) / len(returns)
        variance = sum((value - mean_return) ** 2 for value in returns) / len(returns)
        standard_deviation = math.sqrt(variance) if variance > 0.0 else 0.0
        sharpe_ratio = _round_value(mean_return / standard_deviation) if standard_deviation > 0.0 else 0.0
    else:
        sharpe_ratio = 0.0

    wins = [trade for trade in trades if trade.net_pnl > 0.0]
    win_rate = _round_value(len(wins) / len(trades)) if trades else 0.0
    expectancy = _round_value(sum(trade.net_pnl for trade in trades) / len(trades)) if trades else 0.0
    final_equity = equities[-1] if equities else float(initial_equity)
    total_return = _round_value((final_equity - float(initial_equity)) / float(initial_equity)) if initial_equity > 0.0 else 0.0
    realized_pnl = _round_value(sum(trade.net_pnl for trade in trades))
    return {
        "total_return": total_return,
        "max_drawdown": _round_value(max_drawdown),
        "sharpe_ratio": sharpe_ratio,
        "expectancy": expectancy,
        "win_rate": win_rate,
        "trade_count": len(trades),
        "realized_pnl": realized_pnl,
        "unrealized_pnl": _round_value(final_unrealized_pnl),
        "final_equity": _round_value(final_equity),
        "open_positions": int(open_count),
    }


def run_prdv3_portfolio_backtest(
    edges: Sequence[EdgeDefinition],
    symbols: Sequence[str],
    historical_data: Mapping[str, Sequence[OHLCVBar]],
    initial_equity: float,
    config: PRDV3PortfolioBacktestConfig | None = None,
) -> PRDV3PortfolioBacktestResult:
    config = config or PRDV3PortfolioBacktestConfig()
    logs: list[dict[str, Any]] = []
    config_error = _validate_config(config)
    if config_error is not None:
        logs.append({"event": "backtest_blocked", "reason": config_error})
        return _blocked_result(config_error, initial_equity, logs=logs)
    if not math.isfinite(float(initial_equity)) or float(initial_equity) <= 0.0:
        logs.append({"event": "backtest_blocked", "reason": "invalid_initial_equity"})
        return _blocked_result("invalid_initial_equity", initial_equity, logs=logs)

    normalized_symbols = _normalize_symbols(symbols)
    if not normalized_symbols:
        logs.append({"event": "backtest_blocked", "reason": "no_symbols"})
        return _blocked_result("no_symbols", initial_equity, logs=logs)

    edge_map = {edge.edge_id: edge for edge in edges if edge.enabled}
    if not edge_map:
        logs.append({"event": "backtest_blocked", "reason": "invalid_edges:no_enabled_edges"})
        return _blocked_result("invalid_edges:no_enabled_edges", initial_equity, logs=logs)

    normalized_history = _normalize_history(historical_data)
    valid_history: dict[str, tuple[OHLCVBar, ...]] = {}
    skipped_symbols: list[str] = []
    for symbol in normalized_symbols:
        bars = normalized_history.get(symbol)
        if not bars:
            skipped_symbols.append(symbol)
            logs.append({"event": "symbol_skipped", "symbol": symbol, "reason": "missing_symbol_data"})
            continue
        validation_error = _validate_symbol_bars(symbol, bars)
        if validation_error is not None:
            skipped_symbols.append(symbol)
            logs.append({"event": "symbol_skipped", "symbol": symbol, "reason": validation_error})
            continue
        if not _has_executable_liquidity(bars, config):
            skipped_symbols.append(symbol)
            logs.append({"event": "symbol_skipped", "symbol": symbol, "reason": "no_liquidity_history"})
            continue
        valid_history[symbol] = tuple(bars)

    if not valid_history:
        metrics = _empty_metrics(initial_equity)
        return PRDV3PortfolioBacktestResult(
            valid=True,
            blocked_reason=None,
            metrics=metrics,
            trades=(),
            open_positions=(),
            equity_curve=(),
            logs=tuple(logs),
            skipped_symbols=tuple(sorted(set(skipped_symbols))),
        )

    paper_config = replace(config.paper_trading_config, initial_capital=float(initial_equity))
    ledger = Ledger(initial_cash=float(initial_equity), fee_bps=paper_config.commission_pct * 10_000.0, slippage_bps=0.0)
    slippage_model = SlippageModel(base_slippage_bps=paper_config.slippage_pct * 10_000.0)
    correlation_engine = CorrelationEngine()
    timestamp_to_index = {
        symbol: {int(bar.timestamp): index for index, bar in enumerate(bars)}
        for symbol, bars in valid_history.items()
    }
    all_timestamps = sorted({int(bar.timestamp) for bars in valid_history.values() for bar in bars})

    latest_marks: dict[str, float] = {}
    open_positions: dict[str, _OpenPosition] = {}
    pending_entries: dict[str, _ScheduledEntry] = {}
    pending_exits: dict[str, _ScheduledExit] = {}
    closed_trades: list[PRDV3PortfolioBacktestTrade] = []
    equity_curve: list[dict[str, Any]] = []
    trade_counter = 0

    for timestamp in all_timestamps:
        symbols_at_timestamp = sorted(
            symbol for symbol in valid_history if timestamp in timestamp_to_index[symbol]
        )
        for symbol in symbols_at_timestamp:
            current_bar = valid_history[symbol][timestamp_to_index[symbol][timestamp]]
            latest_marks[symbol] = float(current_bar.close)

        closed_symbols_this_step: set[str] = set()

        for symbol in symbols_at_timestamp:
            bar_index = timestamp_to_index[symbol][timestamp]
            bar = valid_history[symbol][bar_index]
            scheduled_exit = pending_exits.get(symbol)
            if scheduled_exit is None or scheduled_exit.execute_bar_index != bar_index:
                continue
            position = open_positions.get(symbol)
            if position is None:
                logs.append({"event": "inconsistent_state", "symbol": symbol, "reason": "pending_exit_without_position"})
                return _blocked_result(
                    "inconsistent_state:pending_exit_without_position",
                    initial_equity,
                    logs=logs,
                    skipped_symbols=skipped_symbols,
                )
            fill_capacity = _max_fill_quantity(bar, config)
            if fill_capacity < position.share_count:
                next_index = _next_bar_index(bar_index, valid_history[symbol])
                if next_index is None:
                    logs.append({"event": "exit_blocked_liquidity", "symbol": symbol, "reason": scheduled_exit.reason})
                    continue
                pending_exits[symbol] = _ScheduledExit(symbol=symbol, execute_bar_index=next_index, reason=scheduled_exit.reason)
                logs.append({"event": "exit_deferred_liquidity", "symbol": symbol, "reason": scheduled_exit.reason})
                continue
            trade = _close_position(
                position,
                exit_bar_index=bar_index,
                exit_timestamp=timestamp,
                raw_exit_price=float(bar.open),
                exit_reason=scheduled_exit.reason,
                ledger=ledger,
                commission_pct=paper_config.commission_pct,
                slippage_model=slippage_model,
            )
            closed_trades.append(trade)
            del open_positions[symbol]
            del pending_exits[symbol]
            closed_symbols_this_step.add(symbol)
            logs.append({"event": "exit_filled", "symbol": symbol, "edge_id": trade.edge_id, "reason": trade.exit_reason})

        for symbol in symbols_at_timestamp:
            bar_index = timestamp_to_index[symbol][timestamp]
            bar = valid_history[symbol][bar_index]
            scheduled_entry = pending_entries.get(symbol)
            if scheduled_entry is None or scheduled_entry.execute_bar_index != bar_index:
                continue
            if symbol in open_positions:
                logs.append({"event": "inconsistent_state", "symbol": symbol, "reason": "pending_entry_with_open_position"})
                return _blocked_result(
                    "inconsistent_state:pending_entry_with_open_position",
                    initial_equity,
                    logs=logs,
                    skipped_symbols=skipped_symbols,
                )
            fill_capacity = _max_fill_quantity(bar, config)
            entry_open_price = float(bar.open)
            entry_fill_price = float(slippage_model.compute(entry_open_price, OrderSide.BUY))
            if entry_fill_price <= 0.0:
                del pending_entries[symbol]
                logs.append({"event": "entry_blocked", "symbol": symbol, "reason": "invalid_entry_fill_price"})
                continue
            share_count = int(math.floor(float(scheduled_entry.position_budget) / entry_fill_price))
            if share_count < 1:
                del pending_entries[symbol]
                logs.append({"event": "entry_blocked", "symbol": symbol, "reason": "position_size_zero"})
                continue
            if fill_capacity < share_count:
                del pending_entries[symbol]
                logs.append({"event": "entry_blocked_liquidity", "symbol": symbol, "requested_shares": share_count, "max_fill_qty": fill_capacity})
                continue
            estimated_cash = (entry_fill_price * share_count) * (1.0 + paper_config.commission_pct)
            if estimated_cash > ledger.cash():
                del pending_entries[symbol]
                logs.append({"event": "entry_blocked_capital", "symbol": symbol, "requested_cash": _round_value(estimated_cash), "available_cash": _round_value(ledger.cash())})
                continue
            ledger.apply_fill({"symbol": symbol, "side": "BUY", "qty": share_count, "price": entry_fill_price})
            entry_commission = _round_value(entry_fill_price * share_count * paper_config.commission_pct)
            entry_slippage = _round_value((entry_fill_price - entry_open_price) * share_count)
            trade_counter += 1
            risk_fraction = _risk_fraction(
                position_budget=float(scheduled_entry.position_budget),
                risk_amount=float(scheduled_entry.risk_amount),
                min_stop_pct=config.portfolio_engine_config.orchestrator_config.allocation_config.min_stop_distance_pct,
            )
            stop_distance = max(entry_fill_price * risk_fraction, entry_fill_price * (config.portfolio_engine_config.orchestrator_config.allocation_config.min_stop_distance_pct / 100.0))
            stop_price = max(entry_fill_price - stop_distance, 0.01)
            target_price = entry_fill_price + (stop_distance * float(config.take_profit_multiple))
            open_positions[symbol] = _OpenPosition(
                trade_id=f"portfolio_trade_{trade_counter:05d}",
                symbol=symbol,
                edge_id=scheduled_entry.edge_id,
                signal_timestamp=scheduled_entry.signal_timestamp,
                entry_bar_index=bar_index,
                entry_timestamp=timestamp,
                entry_open_price=entry_open_price,
                entry_fill_price=entry_fill_price,
                entry_commission=entry_commission,
                entry_slippage=entry_slippage,
                share_count=share_count,
                allocation_pct=float(scheduled_entry.allocation_pct),
                risk_amount=float(scheduled_entry.risk_amount),
                stop_price=_round_value(stop_price),
                target_price=_round_value(target_price),
            )
            del pending_entries[symbol]
            logs.append({"event": "entry_filled", "symbol": symbol, "edge_id": scheduled_entry.edge_id, "share_count": share_count})

        for symbol in list(open_positions):
            if symbol not in symbols_at_timestamp:
                continue
            if symbol in pending_exits:
                continue
            position = open_positions[symbol]
            bar_index = timestamp_to_index[symbol][timestamp]
            bar = valid_history[symbol][bar_index]
            fill_capacity = _max_fill_quantity(bar, config)
            stop_triggered = float(bar.low) <= float(position.stop_price)
            target_triggered = float(bar.high) >= float(position.target_price)
            if stop_triggered or target_triggered:
                exit_reason = "stop_loss" if stop_triggered else "take_profit"
                raw_exit_price = float(position.stop_price) if stop_triggered else float(position.target_price)
                if fill_capacity >= position.share_count:
                    trade = _close_position(
                        position,
                        exit_bar_index=bar_index,
                        exit_timestamp=timestamp,
                        raw_exit_price=raw_exit_price,
                        exit_reason=exit_reason,
                        ledger=ledger,
                        commission_pct=paper_config.commission_pct,
                        slippage_model=slippage_model,
                    )
                    closed_trades.append(trade)
                    del open_positions[symbol]
                    closed_symbols_this_step.add(symbol)
                    logs.append({"event": "exit_filled_intrabar", "symbol": symbol, "edge_id": trade.edge_id, "reason": exit_reason})
                    continue
                next_index = _next_bar_index(bar_index, valid_history[symbol])
                if next_index is not None:
                    pending_exits[symbol] = _ScheduledExit(symbol=symbol, execute_bar_index=next_index, reason=exit_reason)
                    logs.append({"event": "exit_deferred_liquidity", "symbol": symbol, "reason": exit_reason})
                continue

            edge = edge_map.get(position.edge_id)
            if edge is None:
                logs.append({"event": "inconsistent_state", "symbol": symbol, "reason": "missing_edge_definition"})
                return _blocked_result(
                    "inconsistent_state:missing_edge_definition",
                    initial_equity,
                    logs=logs,
                    skipped_symbols=skipped_symbols,
                )
            history = valid_history[symbol][: bar_index + 1]
            signal_state = _signal_state(edge, history)
            bars_held = (bar_index - position.entry_bar_index) + 1
            if signal_state.should_exit or bars_held >= edge.risk_profile.max_holding_bars:
                next_index = _next_bar_index(bar_index, valid_history[symbol])
                if next_index is not None:
                    pending_exits[symbol] = _ScheduledExit(
                        symbol=symbol,
                        execute_bar_index=next_index,
                        reason=signal_state.exit_reason or "max_holding_bars",
                    )
                    logs.append({"event": "exit_scheduled", "symbol": symbol, "reason": signal_state.exit_reason or "max_holding_bars"})

        unrealized_pnl = _round_value(ledger.unrealized_pnl(latest_marks)) if latest_marks else 0.0
        total_exposure = _round_value(sum(_exposure_amount(position, latest_marks.get(symbol, position.entry_fill_price)) for symbol, position in open_positions.items()))
        equity_value = _round_value(ledger.equity(latest_marks)) if latest_marks else _round_value(ledger.cash())
        exposure_pct = _round_value(total_exposure / equity_value) if equity_value > 0.0 else 0.0
        peak_equity = max([float(point["equity"]) for point in equity_curve], default=float(initial_equity))
        drawdown = _round_value((peak_equity - equity_value) / peak_equity) if peak_equity > 0.0 else 0.0
        equity_curve.append(
            {
                "timestamp": timestamp,
                "equity": equity_value,
                "cash": _round_value(ledger.cash()),
                "realized_pnl": _round_value(ledger.realized_pnl()),
                "unrealized_pnl": unrealized_pnl,
                "drawdown": drawdown,
                "open_positions": len(open_positions),
                "total_exposure": total_exposure,
                "total_exposure_pct": exposure_pct,
            }
        )

        remaining_slots = int(config.portfolio_engine_config.max_concurrent_positions) - len(open_positions) - len(pending_entries)
        remaining_exposure_pct = float(config.portfolio_engine_config.max_total_exposure_pct) - exposure_pct
        if remaining_slots < 1 or remaining_exposure_pct <= 0.0:
            continue

        base_sector_counts: dict[str, int] = {}
        for symbol in sorted(set(open_positions) | set(pending_entries)):
            sector = get_sector(symbol)
            if sector != "other":
                base_sector_counts[sector] = base_sector_counts.get(sector, 0) + 1

        eligible_symbols = [
            symbol
            for symbol in symbols_at_timestamp
            if symbol not in open_positions and symbol not in pending_entries and symbol not in closed_symbols_this_step and _next_bar_index(timestamp_to_index[symbol][timestamp], valid_history[symbol]) is not None
        ]
        if not eligible_symbols:
            continue

        portfolio_config = replace(
            config.portfolio_engine_config,
            max_total_exposure_pct=min(remaining_exposure_pct, float(config.portfolio_engine_config.max_total_exposure_pct)),
            max_concurrent_positions=remaining_slots,
        )
        histories = {
            symbol: valid_history[symbol][: timestamp_to_index[symbol][timestamp] + 1]
            for symbol in eligible_symbols
        }
        decision_result = run_prdv3_multi_symbol_portfolio_engine(
            edges,
            eligible_symbols,
            histories,
            equity_value,
            portfolio_config,
        )
        if not decision_result.valid:
            continue

        accepted_this_step: list[str] = []
        for entry in decision_result.trade_plan:
            symbol = entry.symbol
            if symbol in open_positions or symbol in pending_entries:
                continue
            history = histories.get(symbol)
            if history is None:
                continue
            sector = get_sector(symbol)
            if sector != "other" and base_sector_counts.get(sector, 0) >= int(config.portfolio_engine_config.max_sector_positions):
                logs.append({"event": "entry_rejected", "symbol": symbol, "reason": "sector_cluster"})
                continue
            candidate_signature = _returns_signature(history, int(config.portfolio_engine_config.correlation_lookback))
            similar_count = 0
            if len(candidate_signature) >= 2:
                for existing_symbol in sorted(set(open_positions) | set(accepted_this_step)):
                    existing_history = valid_history[existing_symbol][: timestamp_to_index[existing_symbol][timestamp] + 1] if existing_symbol in timestamp_to_index and timestamp in timestamp_to_index[existing_symbol] else valid_history[existing_symbol]
                    existing_signature = _returns_signature(existing_history, int(config.portfolio_engine_config.correlation_lookback))
                    if len(existing_signature) < 2:
                        continue
                    if correlation_engine.correlation(candidate_signature, existing_signature) >= float(config.portfolio_engine_config.correlation_threshold):
                        similar_count += 1
            if similar_count >= int(config.portfolio_engine_config.max_similar_trades):
                logs.append({"event": "entry_rejected", "symbol": symbol, "reason": "correlation_cluster"})
                continue
            next_index = _next_bar_index(timestamp_to_index[symbol][timestamp], valid_history[symbol])
            if next_index is None:
                continue
            pending_entries[symbol] = _ScheduledEntry(
                symbol=symbol,
                edge_id=entry.edge,
                signal_timestamp=timestamp,
                execute_bar_index=next_index,
                position_budget=float(entry.position_size),
                allocation_pct=float(entry.allocation_pct),
                risk_amount=float(entry.risk),
            )
            accepted_this_step.append(symbol)
            if sector != "other":
                base_sector_counts[sector] = base_sector_counts.get(sector, 0) + 1
            logs.append({"event": "entry_scheduled", "symbol": symbol, "edge_id": entry.edge, "allocation_pct": _round_value(float(entry.allocation_pct))})

    for symbol in sorted(open_positions):
        position = open_positions[symbol]
        bars = valid_history[symbol]
        last_index = len(bars) - 1
        last_bar = bars[last_index]
        fill_capacity = _max_fill_quantity(last_bar, config)
        if fill_capacity < position.share_count:
            logs.append({"event": "open_position_end_of_data", "symbol": symbol, "reason": "liquidity"})
            continue
        trade = _close_position(
            position,
            exit_bar_index=last_index,
            exit_timestamp=int(last_bar.timestamp),
            raw_exit_price=float(last_bar.close),
            exit_reason="end_of_data",
            ledger=ledger,
            commission_pct=paper_config.commission_pct,
            slippage_model=slippage_model,
        )
        closed_trades.append(trade)
        logs.append({"event": "exit_filled_end_of_data", "symbol": symbol, "edge_id": trade.edge_id})
    open_positions = {
        symbol: position
        for symbol, position in open_positions.items()
        if all(trade.trade_id != position.trade_id for trade in closed_trades)
    }

    final_unrealized_pnl = _round_value(ledger.unrealized_pnl(latest_marks)) if latest_marks else 0.0
    metrics = _build_metrics(closed_trades, equity_curve, float(initial_equity), final_unrealized_pnl, len(open_positions))
    return PRDV3PortfolioBacktestResult(
        valid=True,
        blocked_reason=None,
        metrics=metrics,
        trades=tuple(closed_trades),
        open_positions=tuple(_open_position_snapshot(position) for _, position in sorted(open_positions.items())),
        equity_curve=tuple(equity_curve),
        logs=tuple(logs),
        skipped_symbols=tuple(sorted(set(skipped_symbols))),
    )


__all__ = [
    "PRDV3PortfolioBacktestConfig",
    "PRDV3PortfolioBacktestOpenPosition",
    "PRDV3PortfolioBacktestResult",
    "PRDV3PortfolioBacktestTrade",
    "run_prdv3_portfolio_backtest",
]
