from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from bist_core.brain.regime_engine import NO_REGIME, RegimeEngine
from bist_core.brain.scoring_engine import (
    _compute_feature_snapshot,
    _evaluate_logic,
    _is_regime_compatible,
)
from bist_core.edge.registry import EdgeDefinition
from bist_core.execution.paper_engine import OrderSide, SlippageModel
from bist_core.models.ohlcv import OHLCVBar, normalize_timestamp


@dataclass(frozen=True)
class EdgeValidationConfig:
    commission_pct: float = 0.001
    slippage_pct: float = 0.0005
    initial_capital: float = 100_000.0
    position_size: int = 1


@dataclass(frozen=True)
class EdgeValidationTrade:
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
    bars_held: int
    exit_reason: str
    gross_pnl: float
    net_pnl: float
    return_pct: float
    commission_paid: float
    slippage_paid: float
    total_cost: float

    def to_dict(self) -> dict[str, Any]:
        return {
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
            "bars_held": self.bars_held,
            "exit_reason": self.exit_reason,
            "gross_pnl": self.gross_pnl,
            "net_pnl": self.net_pnl,
            "return_pct": self.return_pct,
            "commission_paid": self.commission_paid,
            "slippage_paid": self.slippage_paid,
            "total_cost": self.total_cost,
        }


@dataclass(frozen=True)
class EdgeValidationResult:
    valid: bool
    edge_id: str
    blocked_reason: str | None
    metrics: dict[str, Any]
    trades: tuple[EdgeValidationTrade, ...]
    equity_curve: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "edge_id": self.edge_id,
            "blocked_reason": self.blocked_reason,
            "metrics": dict(self.metrics),
            "trades": [trade.to_dict() for trade in self.trades],
            "equity_curve": [dict(point) for point in self.equity_curve],
        }


@dataclass(frozen=True)
class EdgeWalkForwardWindow:
    train_start_index: int
    train_end_index: int
    test_start_index: int
    test_end_index: int
    train_result: EdgeValidationResult
    test_result: EdgeValidationResult
    expectancy_gap: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "train_start_index": self.train_start_index,
            "train_end_index": self.train_end_index,
            "test_start_index": self.test_start_index,
            "test_end_index": self.test_end_index,
            "train_result": self.train_result.to_dict(),
            "test_result": self.test_result.to_dict(),
            "expectancy_gap": self.expectancy_gap,
        }


@dataclass(frozen=True)
class EdgeStressScenarioResult:
    scenario_name: str
    validation_result: EdgeValidationResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_name": self.scenario_name,
            "validation_result": self.validation_result.to_dict(),
        }


@dataclass(frozen=True)
class EdgeRobustnessConfig:
    train_bars: int = 120
    test_bars: int = 80
    step_bars: int = 40
    min_walk_forward_windows: int = 2
    min_trade_count: int = 3
    min_expectancy_threshold: float = 0.0
    max_avg_train_test_expectancy_gap: float = 2.5
    min_positive_test_window_ratio: float = 0.5
    max_test_expectancy_range: float = 5.0
    high_volatility_return_multiplier: float = 1.5
    high_volatility_range_multiplier: float = 2.0
    high_volatility_slippage_multiplier: float = 1.5
    low_liquidity_volume_multiplier: float = 0.1
    low_liquidity_slippage_multiplier: float = 2.0
    gap_open_pct: float = 0.03
    gap_slippage_multiplier: float = 2.0


@dataclass(frozen=True)
class EdgeRobustnessResult:
    valid: bool
    edge_id: str
    blocked_reason: str | None
    base_result: EdgeValidationResult
    walk_forward_windows: tuple[EdgeWalkForwardWindow, ...]
    stress_results: tuple[EdgeStressScenarioResult, ...]
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "edge_id": self.edge_id,
            "blocked_reason": self.blocked_reason,
            "base_result": self.base_result.to_dict(),
            "walk_forward_windows": [window.to_dict() for window in self.walk_forward_windows],
            "stress_results": [result.to_dict() for result in self.stress_results],
            "metrics": dict(self.metrics),
        }


@dataclass
class _ScheduledEntry:
    signal_bar_index: int
    signal_timestamp: int
    execute_bar_index: int


@dataclass
class _ScheduledExit:
    execute_bar_index: int
    reason: str


@dataclass
class _OpenPosition:
    signal_bar_index: int
    signal_timestamp: int
    entry_bar_index: int
    entry_timestamp: int
    entry_open_price: float
    entry_fill_price: float
    entry_commission: float
    entry_slippage: float
    size: int


@dataclass(frozen=True)
class _SignalState:
    can_enter: bool
    should_exit: bool
    exit_reason: str | None = None


def _round_money(value: float) -> float:
    return round(float(value), 6)


def _empty_metrics(initial_capital: float) -> dict[str, Any]:
    return {
        "total_return": 0.0,
        "win_rate": 0.0,
        "avg_win": 0.0,
        "avg_loss": 0.0,
        "expectancy": 0.0,
        "max_drawdown": 0.0,
        "total_trades": 0,
        "total_cost": 0.0,
        "final_equity": _round_money(initial_capital),
    }


def _blocked_result(edge: EdgeDefinition, reason: str, initial_capital: float) -> EdgeValidationResult:
    return EdgeValidationResult(
        valid=False,
        edge_id=edge.edge_id,
        blocked_reason=reason,
        metrics=_empty_metrics(initial_capital),
        trades=(),
        equity_curve=(),
    )


def _validate_config(config: EdgeValidationConfig) -> str | None:
    if config.commission_pct < 0.0:
        return "invalid_config:negative_commission_pct"
    if config.slippage_pct < 0.0:
        return "invalid_config:negative_slippage_pct"
    if config.initial_capital <= 0.0:
        return "invalid_config:non_positive_initial_capital"
    if int(config.position_size) < 1:
        return "invalid_config:invalid_position_size"
    return None


def _validate_bars(edge: EdgeDefinition, bars: Sequence[OHLCVBar]) -> str | None:
    if not bars:
        return "invalid_data:empty_bars"
    if len(bars) <= edge.required_data.min_history_bars:
        return "invalid_data:insufficient_history"

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


def _signal_state(edge: EdgeDefinition, bars: Sequence[OHLCVBar]) -> _SignalState:
    regime = RegimeEngine().detect_regime(bars)
    feature_values, feature_error = _compute_feature_snapshot(edge, bars, regime.regime)
    if feature_error is not None:
        return _SignalState(can_enter=False, should_exit=True, exit_reason=feature_error)

    entry_logic = _evaluate_logic(edge.entry_logic, feature_values)
    exit_logic = _evaluate_logic(edge.exit_logic, feature_values)
    invalidation_logic = _evaluate_logic(edge.invalidation_conditions, feature_values)
    if entry_logic.error is not None:
        return _SignalState(can_enter=False, should_exit=True, exit_reason=entry_logic.error)
    if exit_logic.error is not None:
        return _SignalState(can_enter=False, should_exit=True, exit_reason=exit_logic.error)
    if invalidation_logic.error is not None:
        return _SignalState(can_enter=False, should_exit=True, exit_reason=invalidation_logic.error)

    if regime.regime == NO_REGIME:
        return _SignalState(can_enter=False, should_exit=True, exit_reason="no_regime")

    can_enter = (
        _is_regime_compatible(edge, regime.regime)
        and entry_logic.satisfied
        and not exit_logic.satisfied
        and not invalidation_logic.satisfied
    )
    should_exit = invalidation_logic.satisfied or exit_logic.satisfied
    exit_reason = None
    if invalidation_logic.satisfied:
        exit_reason = "invalidation_active"
    elif exit_logic.satisfied:
        exit_reason = "exit_signal_active"
    return _SignalState(can_enter=can_enter, should_exit=should_exit, exit_reason=exit_reason)


def _max_drawdown(equity_curve: Sequence[dict[str, Any]]) -> float:
    if not equity_curve:
        return 0.0
    peak = float(equity_curve[0]["equity"])
    max_dd = 0.0
    for point in equity_curve:
        equity = float(point["equity"])
        if equity > peak:
            peak = equity
        drawdown = (peak - equity) / peak if peak > 0.0 else 0.0
        if drawdown > max_dd:
            max_dd = drawdown
    return _round_money(max_dd)


def _metrics(trades: Sequence[EdgeValidationTrade], equity_curve: Sequence[dict[str, Any]], initial_capital: float) -> dict[str, Any]:
    if not trades:
        empty = _empty_metrics(initial_capital)
        empty["max_drawdown"] = _max_drawdown(equity_curve)
        if equity_curve:
            empty["final_equity"] = _round_money(float(equity_curve[-1]["equity"]))
            empty["total_return"] = _round_money((float(equity_curve[-1]["equity"]) - initial_capital) / initial_capital)
        return empty

    net_pnls = [trade.net_pnl for trade in trades]
    wins = [pnl for pnl in net_pnls if pnl > 0.0]
    losses = [pnl for pnl in net_pnls if pnl <= 0.0]
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    final_equity = float(equity_curve[-1]["equity"]) if equity_curve else initial_capital
    return {
        "total_return": _round_money((final_equity - initial_capital) / initial_capital),
        "win_rate": _round_money(len(wins) / len(trades)),
        "avg_win": _round_money(avg_win),
        "avg_loss": _round_money(avg_loss),
        "expectancy": _round_money(sum(net_pnls) / len(net_pnls)),
        "max_drawdown": _round_money(_max_drawdown(equity_curve)),
        "total_trades": len(trades),
        "total_cost": _round_money(sum(trade.total_cost for trade in trades)),
        "final_equity": _round_money(final_equity),
    }


def _validate_robustness_config(edge: EdgeDefinition, config: EdgeRobustnessConfig) -> str | None:
    minimum_window = edge.required_data.min_history_bars + 1
    if config.train_bars < minimum_window:
        return "invalid_robustness_config:train_bars"
    if config.test_bars < minimum_window:
        return "invalid_robustness_config:test_bars"
    if config.step_bars <= 0:
        return "invalid_robustness_config:step_bars"
    if config.min_walk_forward_windows < 1:
        return "invalid_robustness_config:min_walk_forward_windows"
    if config.min_trade_count < 1:
        return "invalid_robustness_config:min_trade_count"
    if not math.isfinite(float(config.min_expectancy_threshold)):
        return "invalid_robustness_config:min_expectancy_threshold"
    if config.max_avg_train_test_expectancy_gap < 0.0:
        return "invalid_robustness_config:max_avg_train_test_expectancy_gap"
    if config.min_positive_test_window_ratio < 0.0 or config.min_positive_test_window_ratio > 1.0:
        return "invalid_robustness_config:min_positive_test_window_ratio"
    if config.max_test_expectancy_range < 0.0:
        return "invalid_robustness_config:max_test_expectancy_range"
    if config.high_volatility_return_multiplier < 1.0:
        return "invalid_robustness_config:high_volatility_return_multiplier"
    if config.high_volatility_range_multiplier < 1.0:
        return "invalid_robustness_config:high_volatility_range_multiplier"
    if config.high_volatility_slippage_multiplier < 1.0:
        return "invalid_robustness_config:high_volatility_slippage_multiplier"
    if config.low_liquidity_volume_multiplier <= 0.0 or config.low_liquidity_volume_multiplier > 1.0:
        return "invalid_robustness_config:low_liquidity_volume_multiplier"
    if config.low_liquidity_slippage_multiplier < 1.0:
        return "invalid_robustness_config:low_liquidity_slippage_multiplier"
    if config.gap_open_pct <= 0.0:
        return "invalid_robustness_config:gap_open_pct"
    if config.gap_slippage_multiplier < 1.0:
        return "invalid_robustness_config:gap_slippage_multiplier"
    return None


def _empty_robustness_metrics(base_result: EdgeValidationResult) -> dict[str, Any]:
    return {
        "base_total_trades": int(base_result.metrics.get("total_trades", 0)),
        "base_expectancy": _round_money(float(base_result.metrics.get("expectancy", 0.0))),
        "walk_forward_windows": 0,
        "walk_forward_total_test_trades": 0,
        "walk_forward_avg_train_expectancy": 0.0,
        "walk_forward_avg_test_expectancy": 0.0,
        "walk_forward_avg_expectancy_gap": 0.0,
        "walk_forward_positive_test_window_ratio": 0.0,
        "walk_forward_test_expectancy_range": 0.0,
        "stress_pass_count": 0,
        "stress_total_count": 0,
    }


def _scenario_config(config: EdgeValidationConfig, slippage_multiplier: float) -> EdgeValidationConfig:
    return EdgeValidationConfig(
        commission_pct=config.commission_pct,
        slippage_pct=config.slippage_pct * slippage_multiplier,
        initial_capital=config.initial_capital,
        position_size=config.position_size,
    )


def _stress_high_volatility(
    bars: Sequence[OHLCVBar],
    return_multiplier: float,
    range_multiplier: float,
) -> tuple[OHLCVBar, ...]:
    stressed: list[OHLCVBar] = []
    previous_close = float(bars[0].open)
    for index, bar in enumerate(bars):
        if index == 0:
            previous_close = float(bar.open)
        open_return = (float(bar.open) - previous_close) / max(previous_close, 0.01)
        close_return = (float(bar.close) - previous_close) / max(previous_close, 0.01)
        stressed_open = max(previous_close * (1.0 + (open_return * return_multiplier)), 0.01)
        stressed_close = max(previous_close * (1.0 + (close_return * return_multiplier)), 0.01)
        high_padding = max(float(bar.high) - max(float(bar.open), float(bar.close)), 0.0) * range_multiplier
        low_padding = max(min(float(bar.open), float(bar.close)) - float(bar.low), 0.0) * range_multiplier
        stressed_high = max(stressed_open, stressed_close) + high_padding
        stressed_low = max(min(stressed_open, stressed_close) - low_padding, 0.01)
        stressed.append(
            OHLCVBar(
                timestamp=bar.timestamp,
                symbol=bar.symbol,
                open=_round_money(stressed_open),
                high=_round_money(max(stressed_high, stressed_open, stressed_close)),
                low=_round_money(min(stressed_low, stressed_open, stressed_close)),
                close=_round_money(stressed_close),
                volume=float(bar.volume),
            )
        )
        previous_close = stressed_close
    return tuple(stressed)


def _stress_low_liquidity(bars: Sequence[OHLCVBar], volume_multiplier: float) -> tuple[OHLCVBar, ...]:
    return tuple(
        OHLCVBar(
            timestamp=bar.timestamp,
            symbol=bar.symbol,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=_round_money(float(bar.volume) * volume_multiplier),
        )
        for bar in bars
    )


def _stress_gaps(bars: Sequence[OHLCVBar], gap_open_pct: float) -> tuple[OHLCVBar, ...]:
    stressed: list[OHLCVBar] = []
    previous_close = float(bars[0].close)
    for index, bar in enumerate(bars):
        if index == 0:
            stressed.append(bar)
            previous_close = float(bar.close)
            continue
        gap_direction = -1.0 if float(bar.close) <= previous_close else 1.0
        stressed_open = max(previous_close * (1.0 + (gap_direction * gap_open_pct)), 0.01)
        close_delta = float(bar.close) - float(bar.open)
        stressed_close = max(stressed_open + close_delta, 0.01)
        high_padding = max(float(bar.high) - max(float(bar.open), float(bar.close)), 0.0)
        low_padding = max(min(float(bar.open), float(bar.close)) - float(bar.low), 0.0)
        stressed_high = max(stressed_open, stressed_close) + high_padding
        stressed_low = max(min(stressed_open, stressed_close) - low_padding, 0.01)
        stressed.append(
            OHLCVBar(
                timestamp=bar.timestamp,
                symbol=bar.symbol,
                open=_round_money(stressed_open),
                high=_round_money(max(stressed_high, stressed_open, stressed_close)),
                low=_round_money(min(stressed_low, stressed_open, stressed_close)),
                close=_round_money(stressed_close),
                volume=float(bar.volume),
            )
        )
        previous_close = stressed_close
    return tuple(stressed)


def _walk_forward_windows(
    edge: EdgeDefinition,
    bars: Sequence[OHLCVBar],
    validation_config: EdgeValidationConfig,
    robustness_config: EdgeRobustnessConfig,
) -> tuple[EdgeWalkForwardWindow, ...]:
    windows: list[EdgeWalkForwardWindow] = []
    start_index = 0
    while start_index + robustness_config.train_bars + robustness_config.test_bars <= len(bars):
        train_start = start_index
        train_end = start_index + robustness_config.train_bars
        test_end = train_end + robustness_config.test_bars
        train_slice = bars[train_start:train_end]
        test_slice = bars[train_end:test_end]
        train_result = run_edge_validation_backtest(edge, train_slice, validation_config)
        test_result = run_edge_validation_backtest(edge, test_slice, validation_config)
        train_expectancy = float(train_result.metrics.get("expectancy", 0.0)) if train_result.valid else 0.0
        test_expectancy = float(test_result.metrics.get("expectancy", 0.0)) if test_result.valid else 0.0
        windows.append(
            EdgeWalkForwardWindow(
                train_start_index=train_start,
                train_end_index=train_end - 1,
                test_start_index=train_end,
                test_end_index=test_end - 1,
                train_result=train_result,
                test_result=test_result,
                expectancy_gap=_round_money(abs(train_expectancy - test_expectancy)),
            )
        )
        start_index += robustness_config.step_bars
    return tuple(windows)


def _stress_results(
    edge: EdgeDefinition,
    bars: Sequence[OHLCVBar],
    validation_config: EdgeValidationConfig,
    robustness_config: EdgeRobustnessConfig,
) -> tuple[EdgeStressScenarioResult, ...]:
    high_vol_bars = _stress_high_volatility(
        bars,
        robustness_config.high_volatility_return_multiplier,
        robustness_config.high_volatility_range_multiplier,
    )
    low_liquidity_bars = _stress_low_liquidity(bars, robustness_config.low_liquidity_volume_multiplier)
    gap_bars = _stress_gaps(bars, robustness_config.gap_open_pct)
    scenarios = (
        (
            "high_volatility",
            high_vol_bars,
            _scenario_config(validation_config, robustness_config.high_volatility_slippage_multiplier),
        ),
        (
            "low_liquidity",
            low_liquidity_bars,
            _scenario_config(validation_config, robustness_config.low_liquidity_slippage_multiplier),
        ),
        (
            "gap",
            gap_bars,
            _scenario_config(validation_config, robustness_config.gap_slippage_multiplier),
        ),
    )
    return tuple(
        EdgeStressScenarioResult(
            scenario_name=scenario_name,
            validation_result=run_edge_validation_backtest(edge, scenario_bars, scenario_config),
        )
        for scenario_name, scenario_bars, scenario_config in scenarios
    )


def _robustness_metrics(
    base_result: EdgeValidationResult,
    windows: Sequence[EdgeWalkForwardWindow],
    stress_results: Sequence[EdgeStressScenarioResult],
) -> dict[str, Any]:
    metrics = _empty_robustness_metrics(base_result)
    if not windows:
        metrics["stress_total_count"] = len(stress_results)
        metrics["stress_pass_count"] = sum(1 for result in stress_results if result.validation_result.valid)
        return metrics

    train_expectancies = [float(window.train_result.metrics.get("expectancy", 0.0)) for window in windows]
    test_expectancies = [float(window.test_result.metrics.get("expectancy", 0.0)) for window in windows]
    total_test_trades = sum(int(window.test_result.metrics.get("total_trades", 0)) for window in windows)
    positive_windows = sum(1 for expectancy in test_expectancies if expectancy > 0.0)
    metrics.update(
        {
            "walk_forward_windows": len(windows),
            "walk_forward_total_test_trades": total_test_trades,
            "walk_forward_avg_train_expectancy": _round_money(sum(train_expectancies) / len(train_expectancies)),
            "walk_forward_avg_test_expectancy": _round_money(sum(test_expectancies) / len(test_expectancies)),
            "walk_forward_avg_expectancy_gap": _round_money(
                sum(window.expectancy_gap for window in windows) / len(windows)
            ),
            "walk_forward_positive_test_window_ratio": _round_money(positive_windows / len(windows)),
            "walk_forward_test_expectancy_range": _round_money(max(test_expectancies) - min(test_expectancies)),
            "stress_total_count": len(stress_results),
            "stress_pass_count": sum(
                1
                for result in stress_results
                if result.validation_result.valid
                and float(result.validation_result.metrics.get("expectancy", 0.0)) >= 0.0
            ),
        }
    )
    return metrics


def _blocked_robustness_result(
    edge: EdgeDefinition,
    reason: str,
    base_result: EdgeValidationResult,
    windows: Sequence[EdgeWalkForwardWindow],
    stress_results: Sequence[EdgeStressScenarioResult],
) -> EdgeRobustnessResult:
    return EdgeRobustnessResult(
        valid=False,
        edge_id=edge.edge_id,
        blocked_reason=reason,
        base_result=base_result,
        walk_forward_windows=tuple(windows),
        stress_results=tuple(stress_results),
        metrics=_robustness_metrics(base_result, windows, stress_results),
    )


def run_edge_validation_backtest(
    edge: EdgeDefinition,
    bars: Sequence[OHLCVBar],
    config: EdgeValidationConfig | None = None,
) -> EdgeValidationResult:
    config = config or EdgeValidationConfig()
    config_error = _validate_config(config)
    if config_error is not None:
        return _blocked_result(edge, config_error, config.initial_capital)

    bar_error = _validate_bars(edge, bars)
    if bar_error is not None:
        return _blocked_result(edge, bar_error, config.initial_capital)

    slippage_model = SlippageModel(base_slippage_bps=config.slippage_pct * 10_000.0)
    cash = float(config.initial_capital)
    trades: list[EdgeValidationTrade] = []
    equity_curve: list[dict[str, Any]] = []
    open_position: _OpenPosition | None = None
    pending_entry: _ScheduledEntry | None = None
    pending_exit: _ScheduledExit | None = None

    for bar_index, bar in enumerate(bars):
        if pending_entry is not None and pending_entry.execute_bar_index == bar_index and open_position is None:
            entry_open_price = float(bar.open)
            entry_fill_price = float(slippage_model.compute(entry_open_price, OrderSide.BUY))
            entry_slippage = _round_money((entry_fill_price - entry_open_price) * config.position_size)
            entry_commission = _round_money(entry_fill_price * config.position_size * config.commission_pct)
            total_entry_cash = (entry_fill_price * config.position_size) + entry_commission
            if total_entry_cash <= cash:
                cash = _round_money(cash - total_entry_cash)
                open_position = _OpenPosition(
                    signal_bar_index=pending_entry.signal_bar_index,
                    signal_timestamp=pending_entry.signal_timestamp,
                    entry_bar_index=bar_index,
                    entry_timestamp=int(bar.timestamp),
                    entry_open_price=entry_open_price,
                    entry_fill_price=entry_fill_price,
                    entry_commission=entry_commission,
                    entry_slippage=entry_slippage,
                    size=int(config.position_size),
                )
            pending_entry = None

        if pending_exit is not None and pending_exit.execute_bar_index == bar_index and open_position is not None:
            raw_exit_price = float(bar.open)
            exit_fill_price = float(slippage_model.compute(raw_exit_price, OrderSide.SELL))
            exit_commission = _round_money(exit_fill_price * open_position.size * config.commission_pct)
            exit_slippage = _round_money((raw_exit_price - exit_fill_price) * open_position.size)
            cash = _round_money(cash + (exit_fill_price * open_position.size) - exit_commission)
            commission_paid = _round_money(open_position.entry_commission + exit_commission)
            slippage_paid = _round_money(open_position.entry_slippage + exit_slippage)
            gross_pnl = _round_money((raw_exit_price - open_position.entry_open_price) * open_position.size)
            net_pnl = _round_money((exit_fill_price - open_position.entry_fill_price) * open_position.size - commission_paid)
            total_cost = _round_money(commission_paid + slippage_paid)
            trades.append(
                EdgeValidationTrade(
                    edge_id=edge.edge_id,
                    symbol=bar.symbol,
                    signal_bar_index=open_position.signal_bar_index,
                    signal_timestamp=open_position.signal_timestamp,
                    entry_bar_index=open_position.entry_bar_index,
                    entry_timestamp=open_position.entry_timestamp,
                    entry_open_price=_round_money(open_position.entry_open_price),
                    entry_fill_price=_round_money(open_position.entry_fill_price),
                    exit_bar_index=bar_index,
                    exit_timestamp=int(bar.timestamp),
                    exit_open_price=_round_money(raw_exit_price),
                    exit_fill_price=_round_money(exit_fill_price),
                    bars_held=(bar_index - open_position.entry_bar_index) + 1,
                    exit_reason=pending_exit.reason,
                    gross_pnl=gross_pnl,
                    net_pnl=net_pnl,
                    return_pct=_round_money(net_pnl / (open_position.entry_fill_price * open_position.size)),
                    commission_paid=commission_paid,
                    slippage_paid=slippage_paid,
                    total_cost=total_cost,
                )
            )
            open_position = None
            pending_exit = None

        equity = cash
        if open_position is not None:
            equity += float(bar.close) * open_position.size
        equity_curve.append(
            {
                "timestamp": int(bar.timestamp),
                "equity": _round_money(equity),
                "close": _round_money(float(bar.close)),
            }
        )

        if bar_index == len(bars) - 1:
            continue

        history = bars[: bar_index + 1]
        signal_state = _signal_state(edge, history)

        if open_position is None and pending_entry is None:
            if signal_state.can_enter:
                pending_entry = _ScheduledEntry(
                    signal_bar_index=bar_index,
                    signal_timestamp=int(bar.timestamp),
                    execute_bar_index=bar_index + 1,
                )
            continue

        if open_position is None or pending_exit is not None:
            continue

        bars_held = (bar_index - open_position.entry_bar_index) + 1
        if signal_state.should_exit:
            pending_exit = _ScheduledExit(bar_index + 1, signal_state.exit_reason or "exit_signal_active")
        elif bars_held >= edge.risk_profile.max_holding_bars:
            pending_exit = _ScheduledExit(bar_index + 1, "max_holding_bars")

    if open_position is not None:
        last_bar = bars[-1]
        raw_exit_price = float(last_bar.close)
        exit_fill_price = float(slippage_model.compute(raw_exit_price, OrderSide.SELL))
        exit_commission = _round_money(exit_fill_price * open_position.size * config.commission_pct)
        exit_slippage = _round_money((raw_exit_price - exit_fill_price) * open_position.size)
        cash = _round_money(cash + (exit_fill_price * open_position.size) - exit_commission)
        commission_paid = _round_money(open_position.entry_commission + exit_commission)
        slippage_paid = _round_money(open_position.entry_slippage + exit_slippage)
        gross_pnl = _round_money((raw_exit_price - open_position.entry_open_price) * open_position.size)
        net_pnl = _round_money((exit_fill_price - open_position.entry_fill_price) * open_position.size - commission_paid)
        total_cost = _round_money(commission_paid + slippage_paid)
        trades.append(
            EdgeValidationTrade(
                edge_id=edge.edge_id,
                symbol=last_bar.symbol,
                signal_bar_index=open_position.signal_bar_index,
                signal_timestamp=open_position.signal_timestamp,
                entry_bar_index=open_position.entry_bar_index,
                entry_timestamp=open_position.entry_timestamp,
                entry_open_price=_round_money(open_position.entry_open_price),
                entry_fill_price=_round_money(open_position.entry_fill_price),
                exit_bar_index=len(bars) - 1,
                exit_timestamp=int(last_bar.timestamp),
                exit_open_price=_round_money(raw_exit_price),
                exit_fill_price=_round_money(exit_fill_price),
                bars_held=(len(bars) - 1 - open_position.entry_bar_index) + 1,
                exit_reason="end_of_data",
                gross_pnl=gross_pnl,
                net_pnl=net_pnl,
                return_pct=_round_money(net_pnl / (open_position.entry_fill_price * open_position.size)),
                commission_paid=commission_paid,
                slippage_paid=slippage_paid,
                total_cost=total_cost,
            )
        )
        equity_curve[-1]["equity"] = _round_money(cash)

    return EdgeValidationResult(
        valid=True,
        edge_id=edge.edge_id,
        blocked_reason=None,
        metrics=_metrics(trades, equity_curve, config.initial_capital),
        trades=tuple(trades),
        equity_curve=tuple(equity_curve),
    )


def run_edge_robustness_validation(
    edge: EdgeDefinition,
    bars: Sequence[OHLCVBar],
    validation_config: EdgeValidationConfig | None = None,
    robustness_config: EdgeRobustnessConfig | None = None,
) -> EdgeRobustnessResult:
    validation_config = validation_config or EdgeValidationConfig()
    robustness_config = robustness_config or EdgeRobustnessConfig()

    config_error = _validate_config(validation_config)
    if config_error is not None:
        base_result = _blocked_result(edge, config_error, validation_config.initial_capital)
        return _blocked_robustness_result(edge, config_error, base_result, (), ())

    robustness_error = _validate_robustness_config(edge, robustness_config)
    if robustness_error is not None:
        base_result = _blocked_result(edge, robustness_error, validation_config.initial_capital)
        return _blocked_robustness_result(edge, robustness_error, base_result, (), ())

    base_result = run_edge_validation_backtest(edge, bars, validation_config)
    if base_result.valid is not True:
        return _blocked_robustness_result(
            edge,
            f"base_validation_failed:{base_result.blocked_reason}",
            base_result,
            (),
            (),
        )

    windows = _walk_forward_windows(edge, bars, validation_config, robustness_config)
    if len(windows) < robustness_config.min_walk_forward_windows:
        return _blocked_robustness_result(edge, "insufficient_walk_forward_windows", base_result, windows, ())

    for index, window in enumerate(windows):
        if window.train_result.valid is not True:
            return _blocked_robustness_result(
                edge,
                f"invalid_walk_forward_train_window:{index}:{window.train_result.blocked_reason}",
                base_result,
                windows,
                (),
            )
        if window.test_result.valid is not True:
            return _blocked_robustness_result(
                edge,
                f"invalid_walk_forward_test_window:{index}:{window.test_result.blocked_reason}",
                base_result,
                windows,
                (),
            )

    stress_results = _stress_results(edge, bars, validation_config, robustness_config)
    for stress_result in stress_results:
        if stress_result.validation_result.valid is not True:
            return _blocked_robustness_result(
                edge,
                f"stress_validation_failed:{stress_result.scenario_name}:{stress_result.validation_result.blocked_reason}",
                base_result,
                windows,
                stress_results,
            )

    metrics = _robustness_metrics(base_result, windows, stress_results)
    if int(base_result.metrics.get("total_trades", 0)) < robustness_config.min_trade_count:
        return _blocked_robustness_result(edge, "minimum_trade_count_failed:base", base_result, windows, stress_results)
    if int(metrics["walk_forward_total_test_trades"]) < robustness_config.min_trade_count:
        return _blocked_robustness_result(
            edge,
            "minimum_trade_count_failed:walk_forward",
            base_result,
            windows,
            stress_results,
        )
    if float(metrics["walk_forward_avg_test_expectancy"]) < robustness_config.min_expectancy_threshold:
        return _blocked_robustness_result(
            edge,
            "minimum_expectancy_failed:walk_forward",
            base_result,
            windows,
            stress_results,
        )
    if float(metrics["walk_forward_avg_expectancy_gap"]) > robustness_config.max_avg_train_test_expectancy_gap:
        return _blocked_robustness_result(edge, "overfit_expectancy_gap", base_result, windows, stress_results)
    if float(metrics["walk_forward_positive_test_window_ratio"]) < robustness_config.min_positive_test_window_ratio:
        return _blocked_robustness_result(edge, "unstable_positive_window_ratio", base_result, windows, stress_results)
    if float(metrics["walk_forward_test_expectancy_range"]) > robustness_config.max_test_expectancy_range:
        return _blocked_robustness_result(edge, "unstable_expectancy_range", base_result, windows, stress_results)

    for stress_result in stress_results:
        if float(stress_result.validation_result.metrics.get("expectancy", 0.0)) < robustness_config.min_expectancy_threshold:
            return _blocked_robustness_result(
                edge,
                f"minimum_expectancy_failed:stress:{stress_result.scenario_name}",
                base_result,
                windows,
                stress_results,
            )

    return EdgeRobustnessResult(
        valid=True,
        edge_id=edge.edge_id,
        blocked_reason=None,
        base_result=base_result,
        walk_forward_windows=windows,
        stress_results=stress_results,
        metrics=metrics,
    )


__all__ = [
    "EdgeRobustnessConfig",
    "EdgeRobustnessResult",
    "EdgeStressScenarioResult",
    "EdgeValidationConfig",
    "EdgeValidationResult",
    "EdgeValidationTrade",
    "EdgeWalkForwardWindow",
    "run_edge_robustness_validation",
    "run_edge_validation_backtest",
]
