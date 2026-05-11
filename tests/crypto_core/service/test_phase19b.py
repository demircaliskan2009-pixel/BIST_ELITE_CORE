from __future__ import annotations

from dataclasses import replace

import pytest

import crypto_core.service.sleeve_portfolio as portfolio
import crypto_core.validation as validation
from crypto_core.service.paper_shadow_session_controller import (
    PaperIntentSide,
    PaperPnLLedger,
    PaperPnLLine,
    PaperPnLStatus,
    PaperPosition,
    PaperShadowSessionSnapshot,
    PaperShadowSessionStatus,
)
from crypto_core.service.sleeve_portfolio_controller import SleevePortfolioController

_DAY_NS = 86400 * 1_000_000_000


def _window(
    *,
    window_id: str,
    out_of_sample_sharpe: float = 2.0,
    out_of_sample_hit_rate: float = 0.60,
) -> validation.WalkForwardWindow:
    return validation.WalkForwardWindow(
        window_id=window_id,
        in_sample_sharpe=2.5,
        out_of_sample_sharpe=out_of_sample_sharpe,
        oos_expectancy=0.1,
        in_sample_hit_rate=0.65,
        out_of_sample_hit_rate=out_of_sample_hit_rate,
        trade_count=50,
        evidence_count=50,
        in_sample_max_drawdown=0.05,
        oos_max_drawdown=0.06,
        oos_profit_factor=1.4,
    )


def _windows() -> tuple[validation.WalkForwardWindow, ...]:
    return (
        _window(window_id="wf-001", out_of_sample_sharpe=1.8, out_of_sample_hit_rate=0.55),
        _window(window_id="wf-002", out_of_sample_sharpe=2.2, out_of_sample_hit_rate=0.65),
    )


def _baseline(
    *,
    baseline_id: str = "baseline-001",
    edge_id: str = "edge-alpha",
    backtest_sharpe: float = 2.0,
) -> validation.Stage4BacktestBaseline:
    return validation.build_stage4_backtest_baseline(
        baseline_id=baseline_id,
        edge_id=edge_id,
        as_of_ns=31 * _DAY_NS,
        backtest_sharpe=backtest_sharpe,
        backtest_hit_rate=0.60,
        source_window_ids=("wf-001", "wf-002"),
    )


def _paper_summary(**overrides: object) -> validation.Stage4PaperSummary:
    values = {
        "paper_id": "paper-001",
        "edge_id": "edge-alpha",
        "started_at_ns": 1,
        "stopped_at_ns": 31 * _DAY_NS + 1,
        "paper_sharpe": 1.2,
        "paper_hit_rate": 0.58,
        "paper_slippage_bps": 4.0,
        "paper_fill_rate": 0.97,
        "paper_trade_count": 42,
    }
    values.update(overrides)
    return validation.Stage4PaperSummary(**values)


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
        "equity_start": 100.0,
        "equity_observations": (102.0, 105.0, 109.0),
    }
    values.update(overrides)
    return PaperShadowSessionSnapshot(**values)


def _ledger() -> PaperPnLLedger:
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

    pnl_lines = (
        line("fill-001", PaperIntentSide.BUY, 3.0, 100.0, 0.0, 3.0, 100.0),
        line("fill-002", PaperIntentSide.SELL, 1.0, 102.0, 4.0, 2.0, 100.0),
        line("fill-003", PaperIntentSide.SELL, 1.0, 103.0, -1.0, 1.0, 100.0),
        line("fill-004", PaperIntentSide.SELL, 1.0, 104.0, 3.0, 0.0, None),
    )
    position = PaperPosition(
        position_id="paper-position-sleeve-001-BTCUSDT-binance",
        sleeve_id="sleeve-001",
        symbol="BTCUSDT",
        venue="binance",
        qty=0.0,
        avg_price=None,
        gross_notional=609.0,
        fees=4.0,
        slippage_cost=2.0,
        realized_pnl=6.0,
        is_open=False,
    )
    return PaperPnLLedger(
        ledger_id="paper-pnl-ledger-cost-001-4",
        session_id="paper-session-001",
        as_of_ns=31 * _DAY_NS + 5,
        source_cost_result_id="cost-001",
        positions=(position,),
        pnl_lines=pnl_lines,
        pnl_events=4,
        open_positions=0,
        closed_positions=1,
        total_fees=4.0,
        total_slippage=2.0,
        realized_pnl=6.0,
        unrealized_pnl=None,
        status=PaperPnLStatus.APPLIED,
        reasons=(),
        operator_summary="test paper pnl ledger",
    )


def _pipeline(*, ready: bool, cap: float | None = None) -> validation.ValidationPipelineResult:
    stage = validation.ValidationPipelineStageStatus(
        stage="stage",
        ran=True,
        passed=ready,
        skipped=False,
        rejection_reasons=(),
    )
    return validation.ValidationPipelineResult(
        validation_ready=ready,
        stage2_status=replace(stage, stage="stage2_walk_forward"),
        pbo_status=replace(stage, stage="pbo"),
        stage3_status=replace(stage, stage="stage3_stress"),
        pbo_allocation_cap=cap,
        rejection_reasons=(),
        missing_stages=() if ready else ("stage2_walk_forward",),
    )


def _sleeve(
    *,
    baseline: validation.Stage4BacktestBaseline | None = None,
    validation_result: validation.ValidationPipelineResult | None = None,
) -> portfolio.CryptoSleeveState:
    return portfolio.CryptoSleeveState(
        sleeve_id="sleeve-microstructure",
        sleeve_type=portfolio.CryptoSleeveType.MICROSTRUCTURE,
        status=portfolio.CryptoSleeveStatus.DEFINED,
        qualification=portfolio.SleeveQualificationResult(
            portfolio.SleeveQualificationStatus.PAPER_QUALIFIED,
            True,
        ),
        recommendation=portfolio.SleeveRecommendationResult(
            portfolio.SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
            True,
            True,
            portfolio.SleeveQualificationStatus.PAPER_QUALIFIED,
        ),
        campaign_evidence=portfolio.SleeveCampaignEvidenceResult(
            portfolio.SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            True,
            True,
            True,
            ("campaign-1",),
        ),
        promotion_support=portfolio.SleevePromotionSupportResult(
            portfolio.SleevePromotionSupportStatus.SUPPORTIVE,
            True,
            portfolio.SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            portfolio.SleeveQualificationStatus.PAPER_QUALIFIED,
            portfolio.SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
        ),
        validation_pipeline_result=validation_result,
        stage4_backtest_baseline=baseline,
    )


def _controller(sleeve: portfolio.CryptoSleeveState) -> SleevePortfolioController:
    return SleevePortfolioController(defined_sleeves=(sleeve,), created_at_ns=1)


def _target(snapshot: portfolio.SleevePortfolioSnapshot) -> portfolio.CryptoSleeveState:
    return snapshot.sleeves[0]


def _has_stage4_blocker(sleeve: portfolio.CryptoSleeveState, blocker: str) -> bool:
    return blocker in sleeve.promotion_candidate.missing_evidence


def test_controller_applies_explicit_baseline_and_paper_summary_pass_clears_blocker():
    controller = _controller(_sleeve(validation_result=_pipeline(ready=True)))

    snapshot = controller.apply_stage4_artifacts(
        "sleeve-microstructure",
        baseline=_baseline(),
        paper_summary=_paper_summary(),
        as_of_ns=31 * _DAY_NS,
    )
    sleeve = _target(snapshot)

    assert sleeve.stage4_comparison_result.status == "PASS"
    assert not any(item.startswith("stage4:") for item in sleeve.promotion_candidate.missing_evidence)


def test_controller_applies_windows_and_paper_summary_stores_built_baseline():
    controller = _controller(_sleeve(validation_result=_pipeline(ready=True)))

    snapshot = controller.apply_stage4_artifacts(
        "sleeve-microstructure",
        windows=_windows(),
        paper_summary=_paper_summary(),
        baseline_id="baseline-from-windows",
        edge_id="edge-alpha",
        as_of_ns=31 * _DAY_NS,
    )
    sleeve = _target(snapshot)

    assert sleeve.stage4_backtest_baseline.baseline_id == "baseline-from-windows"
    assert sleeve.stage4_backtest_baseline.source_window_ids == ("wf-001", "wf-002")
    assert sleeve.stage4_comparison_result.status == "PASS"


def test_controller_uses_persisted_baseline_and_pnl_ledger_snapshot():
    controller = _controller(
        _sleeve(
            baseline=_baseline(baseline_id="baseline-persisted"),
            validation_result=_pipeline(ready=True),
        )
    )

    snapshot = controller.apply_stage4_artifacts(
        "sleeve-microstructure",
        paper_ledger=_ledger(),
        paper_snapshot=_snapshot(),
        edge_id="edge-alpha",
        as_of_ns=31 * _DAY_NS,
    )
    sleeve = _target(snapshot)

    assert sleeve.stage4_backtest_baseline.baseline_id == "baseline-persisted"
    assert sleeve.stage4_comparison_result.baseline_id == "baseline-persisted"
    assert sleeve.stage4_comparison_result.status == "PASS"


def test_controller_missing_baseline_and_windows_produces_insufficient_evidence_blocker():
    controller = _controller(_sleeve(validation_result=_pipeline(ready=True)))

    snapshot = controller.apply_stage4_artifacts(
        "sleeve-microstructure",
        paper_summary=_paper_summary(),
        as_of_ns=31 * _DAY_NS,
    )
    sleeve = _target(snapshot)

    assert sleeve.stage4_comparison_result.status == "INSUFFICIENT_EVIDENCE"
    assert _has_stage4_blocker(sleeve, "stage4:backtest_baseline_missing")


def test_controller_missing_paper_summary_and_ledger_snapshot_produces_insufficient_evidence_blocker():
    controller = _controller(_sleeve(validation_result=_pipeline(ready=True)))

    snapshot = controller.apply_stage4_artifacts(
        "sleeve-microstructure",
        baseline=_baseline(),
        as_of_ns=31 * _DAY_NS,
    )
    sleeve = _target(snapshot)

    assert sleeve.stage4_comparison_result.status == "INSUFFICIENT_EVIDENCE"
    assert _has_stage4_blocker(sleeve, "stage4:paper_summary_missing")


def test_controller_low_paper_sharpe_produces_threshold_blocker():
    controller = _controller(_sleeve(validation_result=_pipeline(ready=True)))

    snapshot = controller.apply_stage4_artifacts(
        "sleeve-microstructure",
        baseline=_baseline(),
        paper_summary=_paper_summary(paper_sharpe=0.5),
        as_of_ns=31 * _DAY_NS,
    )
    sleeve = _target(snapshot)

    assert sleeve.stage4_comparison_result.status == "REJECT"
    assert _has_stage4_blocker(sleeve, "stage4:paper_sharpe_below_backtest_threshold")


def test_controller_unknown_sleeve_id_fails_closed():
    controller = _controller(_sleeve())

    with pytest.raises(KeyError, match="Unknown sleeve_id 'missing-sleeve'"):
        controller.apply_stage4_artifacts(
            "missing-sleeve",
            baseline=_baseline(),
            paper_summary=_paper_summary(),
            as_of_ns=31 * _DAY_NS,
        )


def test_controller_current_snapshot_preserves_stage4_result_through_resolve():
    controller = _controller(_sleeve(validation_result=_pipeline(ready=True)))
    first = controller.apply_stage4_artifacts(
        "sleeve-microstructure",
        baseline=_baseline(),
        paper_summary=_paper_summary(),
        as_of_ns=31 * _DAY_NS,
    )

    second = controller.current_snapshot(
        as_of_ns=32 * _DAY_NS,
        readiness_level=None,
        readiness_is_supportive=False,
        escalation_allowed_next_step=None,
        external_regime_execution_blocked=None,
    )

    assert _target(second).stage4_comparison_result == _target(first).stage4_comparison_result


def test_controller_stage4_artifact_application_is_deterministic():
    def build_snapshot_dict() -> dict:
        controller = _controller(_sleeve(validation_result=_pipeline(ready=True)))
        snapshot = controller.apply_stage4_artifacts(
            "sleeve-microstructure",
            windows=_windows(),
            paper_summary=_paper_summary(),
            baseline_id="baseline-from-windows",
            edge_id="edge-alpha",
            as_of_ns=31 * _DAY_NS,
        )
        return portfolio.sleeve_portfolio_snapshot_to_dict(snapshot)

    assert build_snapshot_dict() == build_snapshot_dict()


def test_controller_stage4_ingestion_preserves_validation_pipeline_and_pbo_cap():
    pipeline = _pipeline(ready=True, cap=0.25)
    controller = _controller(_sleeve(validation_result=pipeline))

    snapshot = controller.apply_stage4_artifacts(
        "sleeve-microstructure",
        baseline=_baseline(),
        paper_summary=_paper_summary(),
        as_of_ns=31 * _DAY_NS,
    )
    sleeve = _target(snapshot)

    assert sleeve.validation_pipeline_result == pipeline
    assert sleeve.promotion_candidate.pbo_allocation_cap == 0.25
    assert controller.defined_sleeves[0].validation_pipeline_result == pipeline
