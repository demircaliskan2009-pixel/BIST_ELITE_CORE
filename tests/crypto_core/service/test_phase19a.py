from __future__ import annotations

from dataclasses import replace

import pytest

import crypto_core.service.sleeve_admission_controller as admission_mod
import crypto_core.service.sleeve_candidate_workflow as workflow_mod
import crypto_core.service.sleeve_portfolio as portfolio
import crypto_core.service.sleeve_promotion_review_controller as review_mod
import crypto_core.validation as validation
from crypto_core.service.paper_shadow_session_controller import (
    PaperIntentSide,
    PaperPnLLedger,
    PaperPnLLine,
    PaperPnLStatus,
    PaperPosition,
    PaperShadowSessionSnapshot,
    PaperShadowSessionStatus,
    build_stage4_paper_summary_from_pnl_ledger,
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


def _pipeline(*, ready: bool) -> validation.ValidationPipelineResult:
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
        pbo_allocation_cap=None,
        rejection_reasons=(),
        missing_stages=() if ready else ("stage2_walk_forward",),
    )


def _sleeve(
    *,
    baseline: validation.Stage4BacktestBaseline | None = None,
    result: validation.Stage4ComparisonResult | None = None,
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
        stage4_comparison_result=result,
        stage4_backtest_baseline=baseline,
    )


def _roundtrip(sleeve: portfolio.CryptoSleeveState) -> portfolio.CryptoSleeveState:
    return portfolio.crypto_sleeve_state_from_dict(portfolio.crypto_sleeve_state_to_dict(sleeve))


def _admission_outcome(sleeve: portfolio.CryptoSleeveState):
    candidate = portfolio._build_sleeve_promotion_candidate_result(sleeve)
    sleeve = replace(sleeve, promotion_candidate=candidate)
    workflow = workflow_mod.SleeveCandidateWorkflowController(
        workflow_id="workflow-19a",
        created_at_ns=1,
        updated_at_ns=1,
        status=workflow_mod.SleeveCandidateWorkflowStatus.CREATED,
    )
    workflow.start(workflow_id="workflow-19a", started_at_ns=2)
    snapshot = workflow.inspect(portfolio.SleevePortfolioSnapshot(as_of_ns=3, sleeves=(sleeve,)))
    review_controller = review_mod.SleevePromotionReviewController(snapshot)
    review = review_controller.build_review_results()[0]
    admission = admission_mod.SleeveAdmissionController(
        review_controller.build_portfolio_summary((review,))
    ).build_admission_results()[0]
    return candidate, review, admission


def test_artifacts_helper_builds_baseline_paper_summary_and_pass_comparison():
    sleeve = portfolio.build_sleeve_with_stage4_artifacts(
        _sleeve(),
        windows=_windows(),
        ledger=_ledger(),
        snapshot=_snapshot(),
        baseline_id="baseline-from-wf",
        edge_id="edge-alpha",
        as_of_ns=31 * _DAY_NS,
    )

    assert sleeve.stage4_backtest_baseline is not None
    assert sleeve.stage4_backtest_baseline.baseline_id == "baseline-from-wf"
    assert sleeve.stage4_comparison_result is not None
    assert sleeve.stage4_comparison_result.status == "PASS"
    assert sleeve.stage4_comparison_result.passed is True


def test_artifacts_helper_missing_windows_and_baseline_attaches_insufficient_evidence():
    sleeve = portfolio.build_sleeve_with_stage4_artifacts(
        _sleeve(),
        ledger=_ledger(),
        snapshot=_snapshot(),
        baseline_id="baseline-missing",
        edge_id="edge-alpha",
        as_of_ns=31 * _DAY_NS,
    )

    assert sleeve.stage4_backtest_baseline is None
    assert sleeve.stage4_comparison_result.status == "INSUFFICIENT_EVIDENCE"
    assert sleeve.stage4_comparison_result.rejection_reasons == ("stage4:backtest_baseline_missing",)


def test_artifacts_helper_missing_ledger_snapshot_and_paper_summary_attaches_insufficient_evidence():
    sleeve = portfolio.build_sleeve_with_stage4_artifacts(
        _sleeve(),
        windows=_windows(),
        baseline_id="baseline-from-wf",
        edge_id="edge-alpha",
        as_of_ns=31 * _DAY_NS,
    )

    assert sleeve.stage4_backtest_baseline is not None
    assert sleeve.stage4_comparison_result.status == "INSUFFICIENT_EVIDENCE"
    assert sleeve.stage4_comparison_result.rejection_reasons == ("stage4:paper_summary_missing",)


def test_artifacts_helper_uses_sleeve_persisted_baseline_with_ledger_snapshot():
    sleeve = portfolio.build_sleeve_with_stage4_artifacts(
        _sleeve(baseline=_baseline(baseline_id="baseline-persisted")),
        ledger=_ledger(),
        snapshot=_snapshot(),
        baseline_id="baseline-unused",
        edge_id="edge-alpha",
        as_of_ns=31 * _DAY_NS,
    )

    assert sleeve.stage4_backtest_baseline.baseline_id == "baseline-persisted"
    assert sleeve.stage4_comparison_result.baseline_id == "baseline-persisted"
    assert sleeve.stage4_comparison_result.status == "PASS"


def test_artifacts_helper_explicit_baseline_overrides_sleeve_baseline():
    sleeve = portfolio.build_sleeve_with_stage4_artifacts(
        _sleeve(baseline=_baseline(baseline_id="baseline-sleeve", edge_id="edge-beta")),
        baseline=_baseline(baseline_id="baseline-explicit"),
        paper_summary=_paper_summary(),
        baseline_id="baseline-unused",
        edge_id="edge-alpha",
        as_of_ns=31 * _DAY_NS,
    )

    assert sleeve.stage4_backtest_baseline.baseline_id == "baseline-explicit"
    assert sleeve.stage4_comparison_result.baseline_id == "baseline-explicit"
    assert sleeve.stage4_comparison_result.status == "PASS"


def test_artifacts_helper_explicit_paper_summary_overrides_ledger_snapshot():
    sleeve = portfolio.build_sleeve_with_stage4_artifacts(
        _sleeve(),
        windows=_windows(),
        ledger=_ledger(),
        snapshot=_snapshot(),
        paper_summary=_paper_summary(paper_id="paper-explicit"),
        baseline_id="baseline-from-wf",
        edge_id="edge-alpha",
        as_of_ns=31 * _DAY_NS,
    )

    assert sleeve.stage4_comparison_result.paper_id == "paper-explicit"
    assert sleeve.stage4_comparison_result.status == "PASS"


def test_artifacts_helper_result_survives_sleeve_state_roundtrip():
    sleeve = portfolio.build_sleeve_with_stage4_artifacts(
        _sleeve(),
        windows=_windows(),
        ledger=_ledger(),
        snapshot=_snapshot(),
        baseline_id="baseline-from-wf",
        edge_id="edge-alpha",
        as_of_ns=31 * _DAY_NS,
    )
    restored = _roundtrip(sleeve)

    assert restored.stage4_backtest_baseline == sleeve.stage4_backtest_baseline
    assert restored.stage4_comparison_result == sleeve.stage4_comparison_result


def test_validation_ready_with_stage4_pass_clears_admission_stage4_blockers():
    sleeve = portfolio.build_sleeve_with_stage4_artifacts(
        _sleeve(validation_result=_pipeline(ready=True)),
        windows=_windows(),
        ledger=_ledger(),
        snapshot=_snapshot(),
        baseline_id="baseline-from-wf",
        edge_id="edge-alpha",
        as_of_ns=31 * _DAY_NS,
    )
    candidate, review, admission = _admission_outcome(sleeve)

    assert not any(item.startswith("stage4:") for item in candidate.missing_evidence)
    assert not any(item.startswith("stage4:") for item in review.missing_evidence)
    assert not any(item.startswith("stage4:") for item in admission.evidence_blockers)
    assert admission.verdict == admission_mod.SleeveAdmissionVerdict.ADMITTED_ACTIVE


def test_validation_ready_with_stage4_reject_blocks_admission():
    sleeve = portfolio.build_sleeve_with_stage4_artifacts(
        _sleeve(validation_result=_pipeline(ready=True)),
        windows=_windows(),
        ledger=_ledger(),
        snapshot=_snapshot(
            as_of_ns=29 * _DAY_NS + 5,
            stopped_at_ns=29 * _DAY_NS + 2,
        ),
        baseline_id="baseline-from-wf",
        edge_id="edge-alpha",
        as_of_ns=31 * _DAY_NS,
    )
    candidate, review, admission = _admission_outcome(sleeve)

    assert "stage4:duration_below_minimum" in candidate.missing_evidence
    assert "stage4:duration_below_minimum" in review.missing_evidence
    assert "stage4:duration_below_minimum" in admission.evidence_blockers
    assert admission.verdict == admission_mod.SleeveAdmissionVerdict.ADMITTED_UNALLOCATED


def test_artifacts_helper_replay_is_deterministic():
    kwargs = {
        "windows": _windows(),
        "ledger": _ledger(),
        "snapshot": _snapshot(),
        "baseline_id": "baseline-from-wf",
        "edge_id": "edge-alpha",
        "as_of_ns": 31 * _DAY_NS,
    }
    first = portfolio.crypto_sleeve_state_to_dict(portfolio.build_sleeve_with_stage4_artifacts(_sleeve(), **kwargs))
    second = portfolio.crypto_sleeve_state_to_dict(portfolio.build_sleeve_with_stage4_artifacts(_sleeve(), **kwargs))

    assert first == second


def test_artifacts_helper_does_not_change_paper_summary_builder_behavior():
    ledger = _ledger()
    snapshot = _snapshot()
    direct_before = build_stage4_paper_summary_from_pnl_ledger(ledger, snapshot, edge_id="edge-alpha")

    portfolio.build_sleeve_with_stage4_artifacts(
        _sleeve(),
        windows=_windows(),
        ledger=ledger,
        snapshot=snapshot,
        baseline_id="baseline-from-wf",
        edge_id="edge-alpha",
        as_of_ns=31 * _DAY_NS,
    )
    direct_after = build_stage4_paper_summary_from_pnl_ledger(ledger, snapshot, edge_id="edge-alpha")

    assert direct_after == direct_before
    assert direct_after.paper_sharpe == pytest.approx(3.0)


def test_artifacts_helper_does_not_change_compare_stage4_semantics():
    baseline = _baseline()
    paper = _paper_summary()

    sleeve = portfolio.build_sleeve_with_stage4_artifacts(
        _sleeve(),
        baseline=baseline,
        paper_summary=paper,
        baseline_id="baseline-unused",
        edge_id="edge-alpha",
        as_of_ns=31 * _DAY_NS,
    )

    assert sleeve.stage4_comparison_result == validation.compare_stage4(baseline, paper)


def test_controller_resolve_preserves_stage4_backtest_baseline():
    baseline = _baseline()
    sleeve = replace(
        _sleeve(baseline=baseline),
        status=portfolio.CryptoSleeveStatus.ALLOCATED,
        target_allocation=0.10,
        active_allocation=0.10,
    )
    controller = SleevePortfolioController(defined_sleeves=(sleeve,))

    snapshot = controller.current_snapshot(
        as_of_ns=31 * _DAY_NS,
        readiness_level="paper_live",
        readiness_is_supportive=True,
        escalation_allowed_next_step=None,
        external_regime_execution_blocked=None,
    )

    assert snapshot.sleeves[0].stage4_backtest_baseline is baseline
