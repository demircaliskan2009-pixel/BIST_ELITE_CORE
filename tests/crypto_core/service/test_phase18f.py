from __future__ import annotations

import importlib
from dataclasses import replace

import pytest

from crypto_core.service.paper_shadow_session_controller import (
    PaperIntentSide,
    PaperPnLLedger,
    PaperPnLLine,
    PaperPnLStatus,
    PaperPosition,
    PaperShadowSessionCorruptError,
    PaperShadowSessionSnapshot,
    PaperShadowSessionStatus,
    build_stage4_paper_summary_from_pnl_ledger,
)
from crypto_core.validation import WalkForwardWindow, build_stage4_backtest_baseline_from_windows, compare_stage4

_DAY_NS = 86400 * 1_000_000_000


def _snapshot(**overrides: int | str | None) -> PaperShadowSessionSnapshot:
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
    buy_only: bool = False,
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

    if buy_only:
        pnl_lines = (line("fill-001", PaperIntentSide.BUY, 1.0, 100.0, 0.0, 1.0, 100.0),)
        positions = (
            PaperPosition(
                position_id="paper-position-sleeve-001-BTCUSDT-binance",
                sleeve_id="sleeve-001",
                symbol="BTCUSDT",
                venue="binance",
                qty=1.0,
                avg_price=100.0,
                gross_notional=100.0,
                fees=1.0,
                slippage_cost=0.25,
                realized_pnl=0.0,
                is_open=True,
            ),
        )
    elif sell_pnls:
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
        pnl_lines = tuple(pnl_lines)
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
    else:
        pnl_lines = ()
        positions = ()
    return PaperPnLLedger(
        ledger_id=f"paper-pnl-ledger-cost-001-{len(pnl_lines)}",
        session_id=session_id,
        as_of_ns=31 * _DAY_NS + 5,
        source_cost_result_id="cost-001",
        positions=positions,
        pnl_lines=pnl_lines,
        pnl_events=len(pnl_lines),
        open_positions=sum(1 for position in positions if position.is_open),
        closed_positions=sum(1 for position in positions if not position.is_open),
        total_fees=sum(position.fees for position in positions),
        total_slippage=sum(position.slippage_cost for position in positions),
        realized_pnl=sum(position.realized_pnl for position in positions),
        unrealized_pnl=None,
        status=PaperPnLStatus.APPLIED if pnl_lines else PaperPnLStatus.SKIPPED,
        reasons=() if pnl_lines else ("no_accepted_cost_lines",),
        operator_summary="test paper pnl ledger",
    )


def test_pnl_ledger_builder_computes_hit_rate_and_slippage_bps():
    ledger = _ledger((15.0, -5.0, 10.0))
    summary = build_stage4_paper_summary_from_pnl_ledger(ledger, _snapshot(), edge_id="edge-alpha")
    assert summary.paper_hit_rate == pytest.approx(2.0 / 3.0)
    assert summary.paper_slippage_bps == pytest.approx(
        ledger.total_slippage / ledger.positions[0].gross_notional * 10_000.0
    )
    assert summary.paper_fill_rate == 1.0
    assert summary.paper_trade_count == 4


def test_pnl_ledger_builder_all_wins_hit_rate_one():
    summary = build_stage4_paper_summary_from_pnl_ledger(_ledger((5.0, 7.0, 9.0)), _snapshot(), edge_id="edge-alpha")
    assert summary.paper_hit_rate == 1.0


def test_pnl_ledger_builder_all_losses_hit_rate_zero():
    summary = build_stage4_paper_summary_from_pnl_ledger(_ledger((-5.0, -7.0, -9.0)), _snapshot(), edge_id="edge-alpha")
    assert summary.paper_hit_rate == 0.0


def test_pnl_ledger_builder_buy_only_hit_rate_none():
    summary = build_stage4_paper_summary_from_pnl_ledger(
        _ledger(buy_only=True),
        _snapshot(fill_attempts=1, simulated_fills=1, rejected_fills=0),
        edge_id="edge-alpha",
    )
    assert summary.paper_hit_rate is None


def test_pnl_ledger_builder_zero_gross_notional_slippage_none():
    summary = build_stage4_paper_summary_from_pnl_ledger(
        _ledger(), _snapshot(fill_attempts=0, simulated_fills=0, rejected_fills=0), edge_id="edge-alpha"
    )
    assert summary.paper_slippage_bps is None


def test_pnl_ledger_builder_zero_fill_attempts_fill_rate_none():
    summary = build_stage4_paper_summary_from_pnl_ledger(
        _ledger(), _snapshot(fill_attempts=0, simulated_fills=0, rejected_fills=0), edge_id="edge-alpha"
    )
    assert summary.paper_fill_rate is None


def test_pnl_ledger_builder_preserves_paper_sharpe_none():
    summary = build_stage4_paper_summary_from_pnl_ledger(_ledger((4.0, -1.0, 3.0)), _snapshot(), edge_id="edge-alpha")
    assert summary.paper_sharpe is None


def test_pnl_ledger_builder_session_id_mismatch_fails_closed():
    with pytest.raises(
        PaperShadowSessionCorruptError, match="paper stage4 summary ledger session must match session snapshot"
    ):
        build_stage4_paper_summary_from_pnl_ledger(
            _ledger((5.0, -2.0), session_id="paper-session-999"), _snapshot(), edge_id="edge-alpha"
        )


def test_pnl_ledger_builder_invalid_ledger_fails_closed():
    with pytest.raises(
        PaperShadowSessionCorruptError, match="paper PnL ledger total_slippage does not match positions"
    ):
        build_stage4_paper_summary_from_pnl_ledger(
            replace(_ledger((5.0, -2.0)), total_slippage=999.0), _snapshot(), edge_id="edge-alpha"
        )


def test_compare_stage4_still_insufficient_because_paper_sharpe_none():
    result = compare_stage4(
        _baseline(),
        build_stage4_paper_summary_from_pnl_ledger(_ledger((5.0, -2.0, 4.0)), _snapshot(), edge_id="edge-alpha"),
    )
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert "stage4:paper_sharpe_not_computable" in result.rejection_reasons


def test_builder_import_does_not_break_paper_shadow_controller():
    module = importlib.import_module("crypto_core.service.paper_shadow_session_controller")
    assert module.build_stage4_paper_summary_from_pnl_ledger is build_stage4_paper_summary_from_pnl_ledger
