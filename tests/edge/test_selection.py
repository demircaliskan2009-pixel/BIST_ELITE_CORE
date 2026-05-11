from __future__ import annotations

from dataclasses import replace

from bist_core.models.ohlcv import OHLCVBar
from bist_core.brain.regime_engine import RegimeEngine
from bist_core.edge.registry import EdgeRiskProfile, build_builtin_edge_registry
from bist_core.edge.selection import select_best_edge
from bist_core.edge.self_healing import evaluate_edge_state
from bist_core.edge.validation import EdgeRobustnessResult, EdgeValidationResult


def _bar(ts: int, close: float, spread: float = 0.8, volume: float = 1_200_000.0) -> OHLCVBar:
    open_price = close - (spread * 0.2)
    high = close + spread
    low = max(close - spread, 0.01)
    return OHLCVBar(ts, "X", round(open_price, 4), round(high, 4), round(low, 4), round(close, 4), volume)


def _trend_down_bars(n: int = 60) -> list[OHLCVBar]:
    return [_bar(1_704_067_200 + i * 86_400, 120.0 - i * 0.7) for i in range(n)]


def _builtin_edge(edge_id: str):
    registry = build_builtin_edge_registry()
    return next(edge for edge in registry.list_active_edges() if edge.edge_id == edge_id)


def _validation_result(edge_id: str) -> EdgeValidationResult:
    return EdgeValidationResult(
        valid=True,
        edge_id=edge_id,
        blocked_reason=None,
        metrics={"total_trades": 6, "expectancy": 1.0, "max_drawdown": 0.04},
        trades=(),
        equity_curve=({"timestamp": 1_704_067_200, "equity": 100_000.0, "close": 100.0},),
    )


def _robustness_result(validation_result: EdgeValidationResult) -> EdgeRobustnessResult:
    return EdgeRobustnessResult(
        valid=True,
        edge_id=validation_result.edge_id,
        blocked_reason=None,
        base_result=validation_result,
        walk_forward_windows=(),
        stress_results=(),
        metrics={"walk_forward_positive_test_window_ratio": 0.75, "walk_forward_avg_expectancy_gap": 1.0},
    )


def test_select_best_edge_picks_highest_scoring_compatible_edge() -> None:
    bars = _trend_down_bars()
    regime = RegimeEngine().detect_regime(bars)
    best_edge = _builtin_edge("bist_bear_oversold_snap")
    weaker_edge = replace(
        best_edge,
        edge_id="bist_bear_oversold_snap_low_risk",
        risk_profile=EdgeRiskProfile("low", 0.02, 5),
    )
    bull_edge = _builtin_edge("bist_bull_pullback_sma20")

    result = select_best_edge([weaker_edge, bull_edge, best_edge], regime, bars)

    assert result.selected_edge_id == "bist_bear_oversold_snap"
    assert result.score > 0.0
    assert "selected_edge_id=bist_bear_oversold_snap" in result.explanation


def test_select_best_edge_returns_no_trade_when_all_scores_are_zero() -> None:
    full_bars = _trend_down_bars()
    regime = RegimeEngine().detect_regime(full_bars)
    short_bars = _trend_down_bars(40)
    edge = _builtin_edge("bist_bear_oversold_snap")
    weaker_edge = replace(
        edge,
        edge_id="bist_bear_oversold_snap_low_risk",
        risk_profile=EdgeRiskProfile("low", 0.02, 5),
    )

    result = select_best_edge([edge, weaker_edge], regime, short_bars)

    assert result.selected_edge_id is None
    assert result.score == 0.0
    assert result.explanation == "NO TRADE: all_scores_zero"


def test_select_best_edge_is_deterministic() -> None:
    bars = _trend_down_bars()
    regime = RegimeEngine().detect_regime(bars)
    edge = _builtin_edge("bist_bear_oversold_snap")
    weaker_edge = replace(
        edge,
        edge_id="bist_bear_oversold_snap_low_risk",
        risk_profile=EdgeRiskProfile("low", 0.02, 5),
    )

    first = select_best_edge([weaker_edge, edge], regime, bars)
    second = select_best_edge([weaker_edge, edge], regime, bars)

    assert first.to_dict() == second.to_dict()


def test_select_best_edge_fail_closes_on_tied_top_score() -> None:
    bars = _trend_down_bars()
    regime = RegimeEngine().detect_regime(bars)
    edge = _builtin_edge("bist_bear_oversold_snap")
    tied_edge = replace(edge, edge_id="bist_bear_oversold_snap_tie")

    result = select_best_edge([edge, tied_edge], regime, bars)

    assert result.selected_edge_id is None
    assert result.score == 0.0
    assert result.explanation == "NO TRADE: ambiguous_top_score:bist_bear_oversold_snap,bist_bear_oversold_snap_tie"


def test_select_best_edge_excludes_disabled_edges_from_state_filter() -> None:
    bars = _trend_down_bars()
    regime = RegimeEngine().detect_regime(bars)
    edge = _builtin_edge("bist_bear_oversold_snap")
    validation_result = _validation_result(edge.edge_id)
    robustness_result = EdgeRobustnessResult(
        valid=False,
        edge_id=edge.edge_id,
        blocked_reason="overfit_expectancy_gap",
        base_result=validation_result,
        walk_forward_windows=(),
        stress_results=(),
        metrics={"walk_forward_positive_test_window_ratio": 0.0, "walk_forward_avg_expectancy_gap": 5.0},
    )
    edge_state = evaluate_edge_state(edge, validation_result, robustness_result)

    result = select_best_edge([edge], regime, bars, edge_states={edge.edge_id: edge_state})

    assert result.selected_edge_id is None
    assert result.score == 0.0
    assert result.explanation == "NO TRADE: no_active_edges_after_state_filter"