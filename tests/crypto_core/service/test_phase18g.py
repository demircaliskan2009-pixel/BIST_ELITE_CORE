from __future__ import annotations

import math

import pytest

from crypto_core.service.paper_shadow_session_controller import (
    PaperCostLine,
    PaperCostModel,
    PaperCostResult,
    PaperCostStatus,
    PaperIntentSide,
    PaperPnLLedger,
    PaperPnLLine,
    PaperPnLStatus,
    PaperPosition,
    PaperShadowSessionController,
    PaperShadowSessionCorruptError,
    PaperShadowSessionSnapshot,
    PaperShadowSessionStatus,
    _validate_session_snapshot,
    build_stage4_paper_summary_from_pnl_ledger,
    paper_shadow_session_snapshot_from_dict,
    paper_shadow_session_snapshot_to_dict,
)
from crypto_core.validation import (
    WalkForwardWindow,
    build_stage4_backtest_baseline_from_windows,
    compare_stage4,
)

_DAY_NS = 86400 * 1_000_000_000


def _snapshot(**overrides: object) -> PaperShadowSessionSnapshot:
    values = {
        "session_id": "paper-session-001",
        "status": PaperShadowSessionStatus.STOPPED,
        "as_of_ns": 31 * _DAY_NS + 5,
        "prepared_at_ns": 1,
        "started_at_ns": 2,
        "stopped_at_ns": 31 * _DAY_NS + 2,
        "fill_attempts": 4,
        "simulated_fills": 4,
        "rejected_fills": 0,
    }
    values.update(overrides)
    return PaperShadowSessionSnapshot(**values)


def _controller_snapshot(**overrides: object) -> PaperShadowSessionSnapshot:
    values = {
        "session_id": "paper-session-001",
        "status": PaperShadowSessionStatus.CREATED,
        "as_of_ns": 1,
    }
    values.update(overrides)
    return PaperShadowSessionSnapshot(**values)


def _baseline():
    return build_stage4_backtest_baseline_from_windows(
        (
            WalkForwardWindow(
                window_id="wf-001",
                in_sample_sharpe=2.0,
                out_of_sample_sharpe=1.8,
                oos_expectancy=0.1,
                in_sample_hit_rate=0.60,
                out_of_sample_hit_rate=0.52,
                trade_count=20,
                evidence_count=5,
                in_sample_max_drawdown=1.0,
                oos_max_drawdown=1.5,
                oos_profit_factor=1.2,
            ),
            WalkForwardWindow(
                window_id="wf-002",
                in_sample_sharpe=2.0,
                out_of_sample_sharpe=2.2,
                oos_expectancy=0.1,
                in_sample_hit_rate=0.60,
                out_of_sample_hit_rate=0.58,
                trade_count=20,
                evidence_count=5,
                in_sample_max_drawdown=1.0,
                oos_max_drawdown=1.5,
                oos_profit_factor=1.2,
            ),
        ),
        baseline_id="baseline-001",
        edge_id="edge-alpha",
        as_of_ns=31 * _DAY_NS,
    )


def _ledger(
    sell_pnls: tuple[float, ...] = (),
    *,
    session_id: str = "paper-session-001",
    total_slippage: float = 2.0,
) -> PaperPnLLedger:
    def line(
        fill_id: str,
        side: PaperIntentSide,
        qty: float,
        price: float,
        realized_pnl: float,
        qty_after: float,
        avg_after: float | None,
    ) -> PaperPnLLine:
        return PaperPnLLine(
            line_id=f"paper-pnl-line-cost-001-{fill_id}",
            cost_result_id="cost-001",
            fill_id=fill_id,
            sleeve_id="sleeve-001",
            symbol="BTCUSDT",
            venue="binance",
            side=side,
            qty=qty,
            price=price,
            fee=0.0,
            slippage_cost=0.0,
            realized_pnl=realized_pnl,
            position_qty_after=qty_after,
            avg_price_after=avg_after,
            status=PaperPnLStatus.APPLIED,
            reasons=(),
        )

    if not sell_pnls:
        return PaperPnLLedger(
            ledger_id="paper-pnl-ledger-cost-001-0",
            session_id=session_id,
            as_of_ns=31 * _DAY_NS + 5,
            source_cost_result_id="cost-001",
            positions=(),
            pnl_lines=(),
            pnl_events=0,
            open_positions=0,
            closed_positions=0,
            total_fees=0.0,
            total_slippage=0.0,
            realized_pnl=0.0,
            unrealized_pnl=None,
            status=PaperPnLStatus.SKIPPED,
            reasons=("no_accepted_cost_lines",),
            operator_summary="test paper pnl ledger",
        )

    buy_qty = float(len(sell_pnls))
    gross_notional = buy_qty * 100.0
    pnl_lines = [line("fill-001", PaperIntentSide.BUY, buy_qty, 100.0, 0.0, buy_qty, 100.0)]
    for index, realized_pnl in enumerate(sell_pnls, start=2):
        sell_price = 100.0 + float(index)
        remaining_qty = float(len(sell_pnls) - index + 1)
        gross_notional += sell_price
        pnl_lines.append(
            line(
                f"fill-{index:03d}",
                PaperIntentSide.SELL,
                1.0,
                sell_price,
                realized_pnl,
                remaining_qty,
                100.0 if remaining_qty > 0.0 else None,
            )
        )
    positions = (
        PaperPosition(
            position_id="paper-position-sleeve-001-BTCUSDT-binance",
            sleeve_id="sleeve-001",
            symbol="BTCUSDT",
            venue="binance",
            qty=0.0,
            avg_price=None,
            gross_notional=gross_notional,
            fees=4.0,
            slippage_cost=total_slippage,
            realized_pnl=sum(sell_pnls),
            is_open=False,
        ),
    )
    return PaperPnLLedger(
        ledger_id=f"paper-pnl-ledger-cost-001-{len(pnl_lines)}",
        session_id=session_id,
        as_of_ns=31 * _DAY_NS + 5,
        source_cost_result_id="cost-001",
        positions=positions,
        pnl_lines=tuple(pnl_lines),
        pnl_events=len(pnl_lines),
        open_positions=0,
        closed_positions=1,
        total_fees=4.0,
        total_slippage=total_slippage,
        realized_pnl=sum(sell_pnls),
        unrealized_pnl=None,
        status=PaperPnLStatus.APPLIED,
        reasons=(),
        operator_summary="test paper pnl ledger",
    )


def _cost_result(cost_result_id: str, side: PaperIntentSide, price: float) -> PaperCostResult:
    line = PaperCostLine(
        fill_id=f"fill-{cost_result_id}",
        intent_id=f"intent-{cost_result_id}",
        sleeve_id="sleeve-001",
        symbol="BTCUSDT",
        venue="binance",
        side=side,
        gross_notional=price,
        fee=0.0,
        slippage_cost=0.0,
        net_notional=price,
        effective_price=price,
        cost_bps=0.0,
        status=PaperCostStatus.ACCEPTED,
        reasons=(),
        qty=1.0,
        fill_price=price,
        fill_ts_ns=1,
    )
    return PaperCostResult(
        cost_result_id=cost_result_id,
        session_id="paper-session-001",
        as_of_ns=1,
        source_fill_simulation_id=f"simulation-{cost_result_id}",
        cost_model=PaperCostModel(),
        costs=(line,),
        cost_evaluations=1,
        accepted_costs=1,
        rejected_costs=0,
        skipped_costs=0,
        gross_notional=price,
        fee=0.0,
        slippage_cost=0.0,
        net_notional=price,
        effective_price=price,
        cost_bps=0.0,
        status=PaperCostStatus.ACCEPTED,
        reasons=(),
        total_fee=0.0,
        total_slippage_cost=0.0,
        operator_summary="test paper cost result",
    )


def _clock(values: tuple[int, ...]):
    ticks = iter(values)
    return lambda: next(ticks)


def test_snapshot_serialization_roundtrip_preserves_equity_fields():
    snapshot = _snapshot(equity_start=100.0, equity_observations=(102.0, 105.0, 109.0))
    restored = paper_shadow_session_snapshot_from_dict(paper_shadow_session_snapshot_to_dict(snapshot))
    assert restored.equity_start == 100.0
    assert restored.equity_observations == (102.0, 105.0, 109.0)


def test_old_snapshot_payload_missing_equity_fields_restores_defaults():
    payload = paper_shadow_session_snapshot_to_dict(_snapshot())
    payload.pop("equity_start")
    payload.pop("equity_observations")
    restored = paper_shadow_session_snapshot_from_dict(payload)
    assert restored.equity_start is None
    assert restored.equity_observations == ()


def test_validate_session_snapshot_rejects_non_positive_equity_start():
    with pytest.raises(PaperShadowSessionCorruptError):
        _validate_session_snapshot(_snapshot(equity_start=0.0))
    with pytest.raises(PaperShadowSessionCorruptError):
        _validate_session_snapshot(_snapshot(equity_start=-1.0))


def test_validate_session_snapshot_rejects_equity_observations_without_equity_start():
    with pytest.raises(PaperShadowSessionCorruptError):
        _validate_session_snapshot(_snapshot(equity_observations=(101.0,)))


def test_validate_session_snapshot_rejects_non_finite_or_non_positive_equity_observation():
    with pytest.raises(PaperShadowSessionCorruptError):
        _validate_session_snapshot(_snapshot(equity_start=100.0, equity_observations=(math.inf,)))
    with pytest.raises(PaperShadowSessionCorruptError):
        _validate_session_snapshot(_snapshot(equity_start=100.0, equity_observations=(0.0,)))


def test_pnl_ledger_summary_computes_finite_paper_sharpe_from_equity_observations():
    summary = build_stage4_paper_summary_from_pnl_ledger(
        _ledger((4.0, -1.0, 3.0)),
        _snapshot(equity_start=100.0, equity_observations=(102.0, 105.0, 109.0)),
        edge_id="edge-alpha",
    )
    assert summary.paper_sharpe == pytest.approx(3.0)


def test_one_equity_observation_keeps_paper_sharpe_none():
    summary = build_stage4_paper_summary_from_pnl_ledger(
        _ledger((4.0, -1.0, 3.0)),
        _snapshot(equity_start=100.0, equity_observations=(102.0,)),
        edge_id="edge-alpha",
    )
    assert summary.paper_sharpe is None


def test_identical_returns_zero_stdev_keeps_paper_sharpe_none():
    summary = build_stage4_paper_summary_from_pnl_ledger(
        _ledger((4.0, -1.0, 3.0)),
        _snapshot(equity_start=1.0, equity_observations=(2.0, 3.0, 4.0)),
        edge_id="edge-alpha",
    )
    assert summary.paper_sharpe is None


def test_equity_start_none_keeps_paper_sharpe_none():
    summary = build_stage4_paper_summary_from_pnl_ledger(
        _ledger((4.0, -1.0, 3.0)),
        _snapshot(),
        edge_id="edge-alpha",
    )
    assert summary.paper_sharpe is None


def test_compare_stage4_passes_with_equity_observation_sharpe_and_duration():
    paper_summary = build_stage4_paper_summary_from_pnl_ledger(
        _ledger((4.0, -1.0, 3.0)),
        _snapshot(equity_start=100.0, equity_observations=(102.0, 105.0, 109.0)),
        edge_id="edge-alpha",
    )
    result = compare_stage4(_baseline(), paper_summary)
    assert result.status == "PASS"
    assert result.passed is True
    assert result.paper_sharpe == pytest.approx(3.0)


def test_compare_stage4_rejects_when_equity_observation_sharpe_below_threshold():
    paper_summary = build_stage4_paper_summary_from_pnl_ledger(
        _ledger((4.0, -1.0, 3.0)),
        _snapshot(equity_start=100.0, equity_observations=(101.0, 100.0, 100.5)),
        edge_id="edge-alpha",
    )
    result = compare_stage4(_baseline(), paper_summary)
    assert result.status == "REJECT"
    assert result.rejection_reasons == ("stage4:paper_sharpe_below_backtest_threshold",)


def test_apply_paper_pnl_ledger_appends_one_equity_observation_per_application():
    controller = PaperShadowSessionController(
        clock_ns=_clock((10, 20)),
        snapshot=_controller_snapshot(equity_start=1_000.0),
    )
    first_ledger = controller.apply_paper_pnl_ledger(_cost_result("cost-001", PaperIntentSide.BUY, 100.0))
    second_ledger = controller.apply_paper_pnl_ledger(
        _cost_result("cost-002", PaperIntentSide.SELL, 110.0),
        prior_ledger=first_ledger,
    )
    assert second_ledger.realized_pnl == pytest.approx(10.0)
    assert controller.snapshot().equity_observations == (1_000.0, 1_010.0)


def test_apply_paper_pnl_ledger_does_not_append_observation_without_equity_start():
    controller = PaperShadowSessionController(
        clock_ns=_clock((10,)),
        snapshot=_controller_snapshot(),
    )
    controller.apply_paper_pnl_ledger(_cost_result("cost-001", PaperIntentSide.BUY, 100.0))
    assert controller.snapshot().equity_start is None
    assert controller.snapshot().equity_observations == ()


def test_phase18f_hit_rate_slippage_and_fill_rate_behavior_remains_unchanged():
    ledger = _ledger((15.0, -5.0, 10.0))
    summary = build_stage4_paper_summary_from_pnl_ledger(ledger, _snapshot(), edge_id="edge-alpha")
    assert summary.paper_hit_rate == pytest.approx(2.0 / 3.0)
    assert summary.paper_slippage_bps == pytest.approx(
        ledger.total_slippage / ledger.positions[0].gross_notional * 10_000.0
    )
    assert summary.paper_fill_rate == 1.0
