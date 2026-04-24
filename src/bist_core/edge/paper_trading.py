from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from bist_core.brain.regime_engine import RegimeEngine
from bist_core.edge.allocation import (
    CapitalAllocationConfig,
    CapitalAllocationResult,
    allocate_capital_to_edge,
)
from bist_core.edge.registry import EdgeDefinition
from bist_core.edge.selection import select_best_edge
from bist_core.edge.validation import EdgeValidationResult, _signal_state
from bist_core.execution.paper_engine import OrderSide, SlippageModel
from bist_core.models.ohlcv import OHLCVBar, normalize_timestamp
from bist_core.portfolio import Ledger


@dataclass(frozen=True)
class PaperTradingConfig:
    initial_capital: float = 100_000.0
    commission_pct: float = 0.001
    slippage_pct: float = 0.0005
    max_fill_share_of_bar_volume: float = 0.01
    allocation_config: CapitalAllocationConfig = field(default_factory=CapitalAllocationConfig)


@dataclass(frozen=True)
class PaperTradingTrade:
    trade_id: str
    edge_id: str
    symbol: str
    signal_bar_index: int
    signal_timestamp: int
    entry_bar_index: int
    entry_timestamp: int
    entry_open_price: float
    entry_fill_price: float
    exit_bar_index: int
    exit_timestamp: int
    exit_open_price: float
    exit_fill_price: float
    share_count: int
    bars_held: int
    score: float
    position_size_pct: float
    exposure_amount: float
    risk_amount: float
    exit_reason: str
    gross_pnl: float
    net_pnl: float
    return_pct: float
    commission_paid: float
    slippage_paid: float
    total_cost: float
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "edge_id": self.edge_id,
            "symbol": self.symbol,
            "signal_bar_index": self.signal_bar_index,
            "signal_timestamp": self.signal_timestamp,
            "entry_bar_index": self.entry_bar_index,
            "entry_timestamp": self.entry_timestamp,
            "entry_open_price": self.entry_open_price,
            "entry_fill_price": self.entry_fill_price,
            "exit_bar_index": self.exit_bar_index,
            "exit_timestamp": self.exit_timestamp,
            "exit_open_price": self.exit_open_price,
            "exit_fill_price": self.exit_fill_price,
            "share_count": self.share_count,
            "bars_held": self.bars_held,
            "score": self.score,
            "position_size_pct": self.position_size_pct,
            "exposure_amount": self.exposure_amount,
            "risk_amount": self.risk_amount,
            "exit_reason": self.exit_reason,
            "gross_pnl": self.gross_pnl,
            "net_pnl": self.net_pnl,
            "return_pct": self.return_pct,
            "commission_paid": self.commission_paid,
            "slippage_paid": self.slippage_paid,
            "total_cost": self.total_cost,
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class PaperOpenPosition:
    trade_id: str
    edge_id: str
    symbol: str
    entry_bar_index: int
    entry_timestamp: int
    entry_fill_price: float
    share_count: int
    score: float
    position_size_pct: float
    exposure_amount: float
    risk_amount: float
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "edge_id": self.edge_id,
            "symbol": self.symbol,
            "entry_bar_index": self.entry_bar_index,
            "entry_timestamp": self.entry_timestamp,
            "entry_fill_price": self.entry_fill_price,
            "share_count": self.share_count,
            "score": self.score,
            "position_size_pct": self.position_size_pct,
            "exposure_amount": self.exposure_amount,
            "risk_amount": self.risk_amount,
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class PaperTradingResult:
    valid: bool
    blocked_reason: str | None
    metrics: dict[str, Any]
    trades: tuple[PaperTradingTrade, ...]
    open_positions: tuple[PaperOpenPosition, ...]
    equity_curve: tuple[dict[str, Any], ...]
    logs: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "blocked_reason": self.blocked_reason,
            "metrics": dict(self.metrics),
            "trades": [trade.to_dict() for trade in self.trades],
            "open_positions": [position.to_dict() for position in self.open_positions],
            "equity_curve": [dict(point) for point in self.equity_curve],
            "logs": [dict(log) for log in self.logs],
        }


@dataclass
class _PendingEntry:
    edge_id: str
    signal_bar_index: int
    signal_timestamp: int
    execute_bar_index: int
    score: float
    allocation: CapitalAllocationResult


@dataclass
class _ScheduledExit:
    execute_bar_index: int
    reason: str


@dataclass
class _OpenPosition:
    trade_id: str
    edge_id: str
    symbol: str
    signal_bar_index: int
    signal_timestamp: int
    entry_bar_index: int
    entry_timestamp: int
    entry_open_price: float
    entry_fill_price: float
    entry_commission: float
    entry_slippage: float
    share_count: int
    score: float
    allocation: CapitalAllocationResult


def _round_money(value: float) -> float:
    return round(float(value), 6)


def _empty_metrics(initial_capital: float) -> dict[str, Any]:
    return {
        "total_return": 0.0,
        "win_rate": 0.0,
        "expectancy": 0.0,
        "max_drawdown": 0.0,
        "entries_filled": 0,
        "closed_trades": 0,
        "open_positions": 0,
        "total_cost": 0.0,
        "final_equity": _round_money(initial_capital),
    }


def _blocked_result(reason: str, initial_capital: float) -> PaperTradingResult:
    return PaperTradingResult(
        valid=False,
        blocked_reason=reason,
        metrics=_empty_metrics(initial_capital),
        trades=(),
        open_positions=(),
        equity_curve=(),
        logs=(),
    )


def _validate_config(config: PaperTradingConfig) -> str | None:
    if config.initial_capital <= 0.0:
        return "invalid_config:non_positive_initial_capital"
    if config.commission_pct < 0.0:
        return "invalid_config:negative_commission_pct"
    if config.slippage_pct < 0.0:
        return "invalid_config:negative_slippage_pct"
    if config.max_fill_share_of_bar_volume <= 0.0 or config.max_fill_share_of_bar_volume > 1.0:
        return "invalid_config:max_fill_share_of_bar_volume"
    return None


def _validate_bars(bars: Sequence[OHLCVBar]) -> str | None:
    if not bars:
        return "invalid_data:empty_bars"
    symbol = str(bars[0].symbol or "").strip()
    if not symbol:
        return "invalid_data:empty_symbol"
    previous_timestamp: int | None = None
    for bar in bars:
        timestamp = normalize_timestamp(bar.timestamp)
        if previous_timestamp is not None and timestamp <= previous_timestamp:
            return "invalid_data:non_monotonic_timestamps"
        previous_timestamp = timestamp
        if str(bar.symbol or "").strip() != symbol:
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


def _index_validations(
    validation_results: Sequence[EdgeValidationResult],
) -> tuple[dict[str, EdgeValidationResult], str | None]:
    validation_map: dict[str, EdgeValidationResult] = {}
    for result in validation_results:
        if result.edge_id in validation_map:
            return {}, f"invalid_validation_results:duplicate_edge_id:{result.edge_id}"
        if result.valid is not True or result.blocked_reason is not None:
            return {}, f"invalid_validation_results:invalid:{result.edge_id}"
        validation_map[result.edge_id] = result
    return validation_map, None


def _log(logs: list[dict[str, Any]], bar_index: int, timestamp: int, event: str, **fields: Any) -> None:
    record = {"bar_index": int(bar_index), "timestamp": int(timestamp), "event": event}
    for key, value in fields.items():
        record[key] = value
    logs.append(record)


def _max_fill_quantity(bar: OHLCVBar, config: PaperTradingConfig) -> int:
    return int(math.floor(float(bar.volume) * config.max_fill_share_of_bar_volume))


def _max_drawdown(equity_curve: Sequence[dict[str, Any]]) -> float:
    if not equity_curve:
        return 0.0
    peak = float(equity_curve[0]["equity"])
    max_drawdown = 0.0
    for point in equity_curve:
        equity = float(point["equity"])
        if equity > peak:
            peak = equity
        drawdown = (peak - equity) / peak if peak > 0.0 else 0.0
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    return _round_money(max_drawdown)


def _build_metrics(
    trades: Sequence[PaperTradingTrade],
    open_positions: Sequence[PaperOpenPosition],
    equity_curve: Sequence[dict[str, Any]],
    total_cost: float,
    initial_capital: float,
) -> dict[str, Any]:
    metrics = _empty_metrics(initial_capital)
    if equity_curve:
        final_equity = float(equity_curve[-1]["equity"])
        metrics["final_equity"] = _round_money(final_equity)
        metrics["total_return"] = _round_money((final_equity - initial_capital) / initial_capital)
        metrics["max_drawdown"] = _max_drawdown(equity_curve)
    metrics["entries_filled"] = len(trades) + len(open_positions)
    metrics["closed_trades"] = len(trades)
    metrics["open_positions"] = len(open_positions)
    metrics["total_cost"] = _round_money(total_cost)
    if trades:
        net_pnls = [trade.net_pnl for trade in trades]
        wins = [pnl for pnl in net_pnls if pnl > 0.0]
        metrics["win_rate"] = _round_money(len(wins) / len(trades))
        metrics["expectancy"] = _round_money(sum(net_pnls) / len(trades))
    return metrics


def _open_position_snapshot(position: _OpenPosition) -> PaperOpenPosition:
    return PaperOpenPosition(
        trade_id=position.trade_id,
        edge_id=position.edge_id,
        symbol=position.symbol,
        entry_bar_index=position.entry_bar_index,
        entry_timestamp=position.entry_timestamp,
        entry_fill_price=_round_money(position.entry_fill_price),
        share_count=position.share_count,
        score=_round_money(position.score),
        position_size_pct=_round_money(position.allocation.position_size_pct),
        exposure_amount=_round_money(position.allocation.exposure_amount),
        risk_amount=_round_money(position.allocation.risk_amount),
        explanation=position.allocation.explanation,
    )


def run_edge_paper_trading(
    edges: Sequence[EdgeDefinition],
    validation_results: Sequence[EdgeValidationResult] | Mapping[str, EdgeValidationResult],
    bars: Sequence[OHLCVBar],
    config: PaperTradingConfig | None = None,
    edge_states: Mapping[str, Any] | None = None,
) -> PaperTradingResult:
    config = config or PaperTradingConfig()
    config_error = _validate_config(config)
    if config_error is not None:
        return _blocked_result(config_error, config.initial_capital)

    bar_error = _validate_bars(bars)
    if bar_error is not None:
        return _blocked_result(bar_error, config.initial_capital)

    active_edges = [edge for edge in edges if edge.enabled]
    if not active_edges:
        return _blocked_result("invalid_edges:no_enabled_edges", config.initial_capital)

    edge_map = {edge.edge_id: edge for edge in active_edges}
    if len(edge_map) != len(active_edges):
        return _blocked_result("invalid_edges:duplicate_edge_id", config.initial_capital)

    if isinstance(validation_results, Mapping):
        validation_map = dict(validation_results)
        validation_error = None
    else:
        validation_map, validation_error = _index_validations(validation_results)
    if validation_error is not None:
        return _blocked_result(validation_error, config.initial_capital)

    for edge in active_edges:
        validation_result = validation_map.get(edge.edge_id)
        if validation_result is None:
            return _blocked_result(f"invalid_validation_results:missing:{edge.edge_id}", config.initial_capital)
        if validation_result.valid is not True or validation_result.blocked_reason is not None:
            return _blocked_result(f"invalid_validation_results:invalid:{edge.edge_id}", config.initial_capital)

    slippage_model = SlippageModel(base_slippage_bps=config.slippage_pct * 10_000.0)
    ledger = Ledger(initial_cash=config.initial_capital, fee_bps=config.commission_pct * 10_000.0, slippage_bps=0.0)
    regime_engine = RegimeEngine()
    trades: list[PaperTradingTrade] = []
    equity_curve: list[dict[str, Any]] = []
    logs: list[dict[str, Any]] = []
    total_cost = 0.0
    pending_entry: _PendingEntry | None = None
    pending_exit: _ScheduledExit | None = None
    open_position: _OpenPosition | None = None
    symbol = str(bars[0].symbol or "").strip()

    for bar_index, bar in enumerate(bars):
        timestamp = int(bar.timestamp)

        if pending_entry is not None and pending_entry.execute_bar_index == bar_index and open_position is None:
            fill_capacity = _max_fill_quantity(bar, config)
            if fill_capacity < pending_entry.allocation.share_count:
                _log(
                    logs,
                    bar_index,
                    timestamp,
                    "entry_blocked_liquidity",
                    edge_id=pending_entry.edge_id,
                    requested_shares=pending_entry.allocation.share_count,
                    max_fill_qty=fill_capacity,
                )
                pending_entry = None
            else:
                entry_open_price = float(bar.open)
                entry_fill_price = float(slippage_model.compute(entry_open_price, OrderSide.BUY))
                estimated_cash = (entry_fill_price * pending_entry.allocation.share_count) * (1.0 + config.commission_pct)
                if estimated_cash > ledger.cash():
                    _log(
                        logs,
                        bar_index,
                        timestamp,
                        "entry_blocked_capital",
                        edge_id=pending_entry.edge_id,
                        requested_cash=_round_money(estimated_cash),
                        available_cash=_round_money(ledger.cash()),
                    )
                    pending_entry = None
                else:
                    ledger.apply_fill(
                        {
                            "symbol": symbol,
                            "side": "BUY",
                            "qty": pending_entry.allocation.share_count,
                            "price": entry_fill_price,
                        }
                    )
                    entry_commission = _round_money(entry_fill_price * pending_entry.allocation.share_count * config.commission_pct)
                    entry_slippage = _round_money((entry_fill_price - entry_open_price) * pending_entry.allocation.share_count)
                    total_cost = _round_money(total_cost + entry_commission + entry_slippage)
                    trade_id = f"paper_trade_{len(trades) + 1:04d}"
                    open_position = _OpenPosition(
                        trade_id=trade_id,
                        edge_id=pending_entry.edge_id,
                        symbol=symbol,
                        signal_bar_index=pending_entry.signal_bar_index,
                        signal_timestamp=pending_entry.signal_timestamp,
                        entry_bar_index=bar_index,
                        entry_timestamp=timestamp,
                        entry_open_price=entry_open_price,
                        entry_fill_price=entry_fill_price,
                        entry_commission=entry_commission,
                        entry_slippage=entry_slippage,
                        share_count=pending_entry.allocation.share_count,
                        score=pending_entry.score,
                        allocation=pending_entry.allocation,
                    )
                    _log(
                        logs,
                        bar_index,
                        timestamp,
                        "entry_filled",
                        trade_id=trade_id,
                        edge_id=pending_entry.edge_id,
                        share_count=pending_entry.allocation.share_count,
                        entry_fill_price=_round_money(entry_fill_price),
                    )
                    pending_entry = None

        if pending_exit is not None and pending_exit.execute_bar_index == bar_index and open_position is not None:
            fill_capacity = _max_fill_quantity(bar, config)
            if fill_capacity < open_position.share_count:
                next_index = bar_index + 1
                _log(
                    logs,
                    bar_index,
                    timestamp,
                    "exit_deferred_liquidity",
                    trade_id=open_position.trade_id,
                    edge_id=open_position.edge_id,
                    requested_shares=open_position.share_count,
                    max_fill_qty=fill_capacity,
                )
                pending_exit = _ScheduledExit(next_index, pending_exit.reason) if next_index < len(bars) else pending_exit
            else:
                raw_exit_price = float(bar.open)
                exit_fill_price = float(slippage_model.compute(raw_exit_price, OrderSide.SELL))
                ledger.apply_fill(
                    {
                        "symbol": symbol,
                        "side": "SELL",
                        "qty": open_position.share_count,
                        "price": exit_fill_price,
                    }
                )
                exit_commission = _round_money(exit_fill_price * open_position.share_count * config.commission_pct)
                exit_slippage = _round_money((raw_exit_price - exit_fill_price) * open_position.share_count)
                commission_paid = _round_money(open_position.entry_commission + exit_commission)
                slippage_paid = _round_money(open_position.entry_slippage + exit_slippage)
                total_cost = _round_money(total_cost + exit_commission + exit_slippage)
                gross_pnl = _round_money((raw_exit_price - open_position.entry_open_price) * open_position.share_count)
                net_pnl = _round_money((exit_fill_price - open_position.entry_fill_price) * open_position.share_count - commission_paid)
                trades.append(
                    PaperTradingTrade(
                        trade_id=open_position.trade_id,
                        edge_id=open_position.edge_id,
                        symbol=symbol,
                        signal_bar_index=open_position.signal_bar_index,
                        signal_timestamp=open_position.signal_timestamp,
                        entry_bar_index=open_position.entry_bar_index,
                        entry_timestamp=open_position.entry_timestamp,
                        entry_open_price=_round_money(open_position.entry_open_price),
                        entry_fill_price=_round_money(open_position.entry_fill_price),
                        exit_bar_index=bar_index,
                        exit_timestamp=timestamp,
                        exit_open_price=_round_money(raw_exit_price),
                        exit_fill_price=_round_money(exit_fill_price),
                        share_count=open_position.share_count,
                        bars_held=(bar_index - open_position.entry_bar_index) + 1,
                        score=_round_money(open_position.score),
                        position_size_pct=_round_money(open_position.allocation.position_size_pct),
                        exposure_amount=_round_money(open_position.allocation.exposure_amount),
                        risk_amount=_round_money(open_position.allocation.risk_amount),
                        exit_reason=pending_exit.reason,
                        gross_pnl=gross_pnl,
                        net_pnl=net_pnl,
                        return_pct=_round_money(net_pnl / (open_position.entry_fill_price * open_position.share_count)),
                        commission_paid=commission_paid,
                        slippage_paid=slippage_paid,
                        total_cost=_round_money(commission_paid + slippage_paid),
                        explanation=open_position.allocation.explanation,
                    )
                )
                _log(
                    logs,
                    bar_index,
                    timestamp,
                    "exit_filled",
                    trade_id=open_position.trade_id,
                    edge_id=open_position.edge_id,
                    exit_reason=pending_exit.reason,
                    exit_fill_price=_round_money(exit_fill_price),
                )
                open_position = None
                pending_exit = None

        equity_curve.append(
            {
                "timestamp": timestamp,
                "equity": _round_money(ledger.equity({symbol: float(bar.close)})),
                "cash": _round_money(ledger.cash()),
                "close": _round_money(float(bar.close)),
                "position_qty": int(open_position.share_count) if open_position is not None else 0,
            }
        )

        if bar_index == len(bars) - 1:
            continue

        history = bars[: bar_index + 1]
        regime = regime_engine.detect_regime(history)
        selection = select_best_edge(active_edges, regime, history, edge_states=edge_states)

        if open_position is None and pending_entry is None and selection.selected_edge_id is not None:
            selected_edge = edge_map[selection.selected_edge_id]
            selected_edge_state = None if edge_states is None else edge_states.get(selection.selected_edge_id)
            allocation = allocate_capital_to_edge(
                selected_edge=selected_edge,
                edge_score=selection.score,
                validation_result=validation_map[selection.selected_edge_id],
                current_equity=ledger.equity({symbol: float(bar.close)}),
                bars=history,
                config=config.allocation_config,
                edge_state=selected_edge_state,
            )
            if allocation.approved:
                pending_entry = _PendingEntry(
                    edge_id=selection.selected_edge_id,
                    signal_bar_index=bar_index,
                    signal_timestamp=timestamp,
                    execute_bar_index=bar_index + 1,
                    score=selection.score,
                    allocation=allocation,
                )
                _log(
                    logs,
                    bar_index,
                    timestamp,
                    "entry_scheduled",
                    edge_id=selection.selected_edge_id,
                    score=_round_money(selection.score),
                    share_count=allocation.share_count,
                    position_size_pct=_round_money(allocation.position_size_pct),
                )
            else:
                _log(
                    logs,
                    bar_index,
                    timestamp,
                    "allocation_blocked",
                    edge_id=selection.selected_edge_id,
                    blocked_reason=allocation.blocked_reason,
                )
        elif open_position is not None and selection.selected_edge_id is not None:
            _log(
                logs,
                bar_index,
                timestamp,
                "selection_blocked_open_position",
                active_trade_id=open_position.trade_id,
                candidate_edge_id=selection.selected_edge_id,
            )

        if open_position is None or pending_exit is not None:
            continue

        signal_state = _signal_state(edge_map[open_position.edge_id], history)
        bars_held = (bar_index - open_position.entry_bar_index) + 1
        if signal_state.should_exit:
            pending_exit = _ScheduledExit(bar_index + 1, signal_state.exit_reason or "exit_signal_active")
            _log(
                logs,
                bar_index,
                timestamp,
                "exit_scheduled",
                trade_id=open_position.trade_id,
                edge_id=open_position.edge_id,
                exit_reason=pending_exit.reason,
            )
        elif bars_held >= edge_map[open_position.edge_id].risk_profile.max_holding_bars:
            pending_exit = _ScheduledExit(bar_index + 1, "max_holding_bars")
            _log(
                logs,
                bar_index,
                timestamp,
                "exit_scheduled",
                trade_id=open_position.trade_id,
                edge_id=open_position.edge_id,
                exit_reason="max_holding_bars",
            )

    if open_position is not None:
        last_bar = bars[-1]
        last_timestamp = int(last_bar.timestamp)
        fill_capacity = _max_fill_quantity(last_bar, config)
        if fill_capacity >= open_position.share_count:
            raw_exit_price = float(last_bar.close)
            exit_fill_price = float(slippage_model.compute(raw_exit_price, OrderSide.SELL))
            ledger.apply_fill(
                {
                    "symbol": symbol,
                    "side": "SELL",
                    "qty": open_position.share_count,
                    "price": exit_fill_price,
                }
            )
            exit_commission = _round_money(exit_fill_price * open_position.share_count * config.commission_pct)
            exit_slippage = _round_money((raw_exit_price - exit_fill_price) * open_position.share_count)
            commission_paid = _round_money(open_position.entry_commission + exit_commission)
            slippage_paid = _round_money(open_position.entry_slippage + exit_slippage)
            total_cost = _round_money(total_cost + exit_commission + exit_slippage)
            exit_reason = pending_exit.reason if pending_exit is not None else "end_of_data"
            net_pnl = _round_money((exit_fill_price - open_position.entry_fill_price) * open_position.share_count - commission_paid)
            trades.append(
                PaperTradingTrade(
                    trade_id=open_position.trade_id,
                    edge_id=open_position.edge_id,
                    symbol=symbol,
                    signal_bar_index=open_position.signal_bar_index,
                    signal_timestamp=open_position.signal_timestamp,
                    entry_bar_index=open_position.entry_bar_index,
                    entry_timestamp=open_position.entry_timestamp,
                    entry_open_price=_round_money(open_position.entry_open_price),
                    entry_fill_price=_round_money(open_position.entry_fill_price),
                    exit_bar_index=len(bars) - 1,
                    exit_timestamp=last_timestamp,
                    exit_open_price=_round_money(raw_exit_price),
                    exit_fill_price=_round_money(exit_fill_price),
                    share_count=open_position.share_count,
                    bars_held=(len(bars) - 1 - open_position.entry_bar_index) + 1,
                    score=_round_money(open_position.score),
                    position_size_pct=_round_money(open_position.allocation.position_size_pct),
                    exposure_amount=_round_money(open_position.allocation.exposure_amount),
                    risk_amount=_round_money(open_position.allocation.risk_amount),
                    exit_reason=exit_reason,
                    gross_pnl=_round_money((raw_exit_price - open_position.entry_open_price) * open_position.share_count),
                    net_pnl=net_pnl,
                    return_pct=_round_money(net_pnl / (open_position.entry_fill_price * open_position.share_count)),
                    commission_paid=commission_paid,
                    slippage_paid=slippage_paid,
                    total_cost=_round_money(commission_paid + slippage_paid),
                    explanation=open_position.allocation.explanation,
                )
            )
            _log(
                logs,
                len(bars) - 1,
                last_timestamp,
                "exit_filled_end_of_data",
                trade_id=open_position.trade_id,
                edge_id=open_position.edge_id,
                exit_reason=exit_reason,
                exit_fill_price=_round_money(exit_fill_price),
            )
            open_position = None
            equity_curve[-1]["cash"] = _round_money(ledger.cash())
            equity_curve[-1]["equity"] = _round_money(ledger.equity({symbol: float(last_bar.close)}))
            equity_curve[-1]["position_qty"] = 0
        else:
            _log(
                logs,
                len(bars) - 1,
                last_timestamp,
                "open_position_end_of_data",
                trade_id=open_position.trade_id,
                edge_id=open_position.edge_id,
                requested_shares=open_position.share_count,
                max_fill_qty=fill_capacity,
            )

    open_positions: tuple[PaperOpenPosition, ...] = ()
    if open_position is not None:
        open_positions = (_open_position_snapshot(open_position),)

    return PaperTradingResult(
        valid=True,
        blocked_reason=None,
        metrics=_build_metrics(trades, open_positions, equity_curve, total_cost, config.initial_capital),
        trades=tuple(trades),
        open_positions=open_positions,
        equity_curve=tuple(equity_curve),
        logs=tuple(logs),
    )


__all__ = [
    "PaperOpenPosition",
    "PaperTradingConfig",
    "PaperTradingResult",
    "PaperTradingTrade",
    "run_edge_paper_trading",
]
