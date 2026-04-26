"""Tests for Phase 15F - Crypto sleeve admission gate."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from crypto_core.service.artifact_export import (
    export_managed_sleeve_set_manifest,
    export_multi_source_run_evidence_report,
    export_paper_cost_result,
    export_paper_data_source_batch_result,
    export_paper_fill_simulation_result,
    export_paper_intent_batch,
    export_paper_intent_batch_result,
    export_paper_pnl_ledger,
    export_paper_portfolio_risk_snapshot,
    export_paper_shadow_activation_plan,
    export_paper_shadow_evidence_bundle,
    export_paper_shadow_feed_replay_plan,
    export_paper_shadow_feed_replay_result,
    export_paper_shadow_market_event_batch,
    export_paper_shadow_run_evidence_report,
    export_paper_shadow_session_snapshot,
    export_sleeve_admission_release_pack,
    load_managed_sleeve_set_manifest,
    load_multi_source_run_evidence_report,
    load_paper_cost_result,
    load_paper_data_source_batch_result,
    load_paper_fill_simulation_result,
    load_paper_intent_batch,
    load_paper_intent_batch_result,
    load_paper_pnl_ledger,
    load_paper_portfolio_risk_snapshot,
    load_paper_shadow_activation_plan,
    load_paper_shadow_evidence_bundle,
    load_paper_shadow_feed_replay_plan,
    load_paper_shadow_feed_replay_result,
    load_paper_shadow_market_event_batch,
    load_paper_shadow_run_evidence_report,
    load_paper_shadow_session_snapshot,
    load_sleeve_admission_release_pack,
)
from crypto_core.service.campaign import (
    AcceptanceResult,
    AcceptanceVerdict,
    CampaignReport,
    CampaignSleeveLinkSummary,
    CampaignSnapshot,
    CriterionResult,
)
from crypto_core.service.campaign_controller import campaign_readiness_flags
from crypto_core.service.evidence_store import EvidenceStore, EvidenceStoreConfig
from crypto_core.service.models import QueuePressure, QueueSnapshot, ServiceStatus, WatchdogStatus
from crypto_core.service.paper_shadow_session_controller import (
    FeedReplayPlan,
    GuardrailAction,
    MarketEvent,
    MarketEventBatch,
    MarketEventType,
    MultiSourceRunEvidenceReport,
    PaperCostModel,
    PaperCostStatus,
    PaperDataSourceType,
    PaperFillSimulationResult,
    PaperFillStatus,
    PaperIntent,
    PaperIntentBatchResult,
    PaperIntentSide,
    PaperIntentValidationResult,
    PaperPnLStatus,
    PaperPortfolioRiskStatus,
    PaperShadowEvidenceBundle,
    PaperShadowRunEvidenceStatus,
    PaperShadowSessionController,
    PaperShadowSessionCorruptError,
    PaperShadowSessionStatus,
    RuntimeMonitorStatus,
    build_feed_replay_plan,
    build_guardrail_snapshot,
    build_market_event_batch,
    build_multi_source_run_evidence_report,
    build_paper_data_source_batch_result,
    build_paper_intent_batch,
    build_paper_portfolio_risk_snapshot,
    build_paper_shadow_evidence_bundle,
    build_paper_shadow_run_evidence_report,
    feed_replay_plan_from_dict,
    feed_replay_plan_to_dict,
    feed_replay_result_from_dict,
    feed_replay_result_to_dict,
    guardrail_snapshot_from_dict,
    guardrail_snapshot_to_dict,
    market_event_batch_from_dict,
    market_event_batch_to_dict,
    multi_source_run_evidence_report_from_dict,
    multi_source_run_evidence_report_to_dict,
    paper_cost_result_from_dict,
    paper_cost_result_to_dict,
    paper_data_source_batch_result_from_dict,
    paper_data_source_batch_result_to_dict,
    paper_data_source_payload_to_market_event_batch,
    paper_fill_simulation_result_from_dict,
    paper_fill_simulation_result_to_dict,
    paper_intent_batch_from_dict,
    paper_intent_batch_result_from_dict,
    paper_intent_batch_result_to_dict,
    paper_intent_batch_to_dict,
    paper_pnl_ledger_from_dict,
    paper_pnl_ledger_to_dict,
    paper_portfolio_risk_snapshot_from_dict,
    paper_portfolio_risk_snapshot_to_dict,
    paper_shadow_evidence_bundle_from_dict,
    paper_shadow_evidence_bundle_to_dict,
    paper_shadow_run_evidence_report_from_dict,
    paper_shadow_run_evidence_report_to_dict,
    paper_shadow_session_snapshot_from_dict,
    paper_shadow_session_snapshot_to_dict,
    runtime_monitor_snapshot_from_dict,
    runtime_monitor_snapshot_to_dict,
)
from crypto_core.service.readiness import CriterionStatus, ReadinessEvaluator, paper_shadow_evidence_readiness_flags
from crypto_core.service.service_orchestrator import ServiceOrchestrator, operator_snapshot_to_dict
from crypto_core.service.sleeve_admission_controller import (
    ManagedSleeveSetDryRunStatus,
    PaperShadowActivationStatus,
    SleeveAdmissionController,
    SleeveAdmissionCorruptError,
    SleeveAdmissionReleaseEvidenceStatus,
    SleeveAdmissionReleaseStatus,
    SleeveAdmissionVerdict,
    build_managed_sleeve_set_manifest,
    build_paper_shadow_activation_plan,
    build_sleeve_admission_release_pack,
    managed_sleeve_set_manifest_from_dict,
    managed_sleeve_set_manifest_to_dict,
    paper_shadow_activation_plan_from_dict,
    paper_shadow_activation_plan_to_dict,
    sleeve_admission_release_pack_from_dict,
    sleeve_admission_release_pack_to_dict,
    sleeve_admission_snapshot_from_dict,
    sleeve_admission_snapshot_to_dict,
)
from crypto_core.service.sleeve_candidate_workflow import (
    SleeveCandidateWorkflowEntry,
    SleeveCandidateWorkflowSnapshot,
)
from crypto_core.service.sleeve_portfolio import (
    CryptoSleeveState,
    CryptoSleeveStatus,
    CryptoSleeveType,
    SleeveCampaignEvidenceResult,
    SleeveCampaignEvidenceStatus,
    SleeveDecisionPackResult,
    SleeveDecisionPackStatus,
    SleeveEvidenceState,
    SleevePortfolioSnapshot,
    SleevePromotionCandidateResult,
    SleevePromotionCandidateStatus,
    SleevePromotionSupportResult,
    SleevePromotionSupportStatus,
    SleeveQualificationResult,
    SleeveQualificationStatus,
    SleeveRecommendationResult,
    SleeveRecommendationStatus,
    build_sleeve_portfolio_snapshot,
)
from crypto_core.service.sleeve_promotion_review_controller import (
    SleevePromotionReviewPortfolioSummary,
    SleevePromotionReviewResult,
    SleevePromotionReviewSnapshot,
    SleevePromotionReviewVerdict,
)

_T0_NS = 1_000_000_000_000


def _review_result(
    sleeve_id: str,
    verdict: SleevePromotionReviewVerdict = SleevePromotionReviewVerdict.REVIEW_SUPPORTED,
    *,
    governance_blockers: tuple[str, ...] = (),
    missing_evidence: tuple[str, ...] = (),
    next_step: str = "continue_paper_review",
) -> SleevePromotionReviewResult:
    return SleevePromotionReviewResult(
        sleeve_id=sleeve_id,
        verdict=verdict,
        reason="review reason",
        next_step=next_step,
        missing_evidence=missing_evidence,
        governance_blockers=governance_blockers,
    )


def _review_summary(*results: SleevePromotionReviewResult) -> SleevePromotionReviewPortfolioSummary:
    return SleevePromotionReviewPortfolioSummary(
        as_of_ns=_T0_NS,
        review_results=tuple(results),
        supported=tuple(r.sleeve_id for r in results if r.verdict == SleevePromotionReviewVerdict.REVIEW_SUPPORTED),
        hold=tuple(r.sleeve_id for r in results if r.verdict == SleevePromotionReviewVerdict.HOLD),
        reject=tuple(r.sleeve_id for r in results if r.verdict == SleevePromotionReviewVerdict.REJECT),
        inconclusive=tuple(r.sleeve_id for r in results if r.verdict == SleevePromotionReviewVerdict.INCONCLUSIVE),
        repeated_weak=(),
        repeated_blocked=(),
        repeated_inconclusive=(),
        missing_evidence=tuple(dict.fromkeys(code for r in results for code in r.missing_evidence)),
        governance_blockers=tuple(dict.fromkeys(code for r in results for code in r.governance_blockers)),
        operator_summary="review summary",
    )


def _promotion_snapshot(summary: SleevePromotionReviewPortfolioSummary) -> SleevePromotionReviewSnapshot:
    return SleevePromotionReviewSnapshot(
        as_of_ns=summary.as_of_ns,
        status="active",
        review_results=summary.review_results,
        portfolio_summary=summary,
    )


def _campaign_report(
    *,
    sleeve_ids: tuple[str, ...] = ("s1",),
    verdict: AcceptanceVerdict = AcceptanceVerdict.PASS,
    sleeve_link_available: bool = True,
    persisted_tca_count: int = 8,
    completed_markout_count: int = 8,
    ext_regime_available: bool = True,
    ext_regime_evidence_sufficient: bool = True,
    ext_regime_scenario_available: bool = True,
    ext_regime_scenario_step_count: int = 6,
    ext_regime_execution_blocked_steps: int = 0,
    ext_regime_activation_blocked_steps: int = 0,
    ext_regime_activation_reduced_steps: int = 0,
    ext_regime_stale_steps: int = 1,
    ext_regime_unavailable_steps: int = 0,
    ext_regime_high_risk_steps: int = 1,
    ext_regime_safe_steps: int = 4,
    ext_regime_high_risk: bool = False,
) -> CampaignReport:
    snapshot = CampaignSnapshot(
        campaign_id="camp-release",
        status="completed",
        started_at_ns=_T0_NS - 100,
        updated_at_ns=_T0_NS,
        elapsed_seconds=100.0,
        run_id="run-release",
        service_mode="running",
        session_mode="running",
        total_events_enqueued=1_000,
        total_events_dropped=0,
        total_cycles=200,
        approved_cycles=190,
        blocked_cycles=5,
        failed_cycles=5,
        total_fills=30,
        queue_overflows=0,
        watchdog_stalls=0,
        service_restarts=0,
        persistence_failures=0,
        symbol_count=2,
        symbols_ready=2,
        symbols_blocked=0,
        symbols_with_events=2,
        symbols_with_cycles=2,
        readiness_level="paper_live",
        health_trend="stable",
        persistence_status="healthy",
        nav_usd=10_000.0,
        last_error=None,
        completed_markout_count=completed_markout_count,
        persisted_tca_count=persisted_tca_count,
        registered_fill_count=max(completed_markout_count, 30),
        ext_regime_available=ext_regime_available,
        ext_regime_fresh=True,
        ext_regime_high_risk=ext_regime_high_risk,
        ext_regime_evidence_sufficient=ext_regime_evidence_sufficient,
        ext_regime_scenario_available=ext_regime_scenario_available,
        ext_regime_scenario_step_count=ext_regime_scenario_step_count,
        ext_regime_execution_blocked_steps=ext_regime_execution_blocked_steps,
        ext_regime_activation_blocked_steps=ext_regime_activation_blocked_steps,
        ext_regime_activation_reduced_steps=ext_regime_activation_reduced_steps,
        ext_regime_stale_steps=ext_regime_stale_steps,
        ext_regime_unavailable_steps=ext_regime_unavailable_steps,
        ext_regime_high_risk_steps=ext_regime_high_risk_steps,
        ext_regime_safe_steps=ext_regime_safe_steps,
        ext_regime_scenario_summary="steps=6; safe=4; stale=1; high_risk=1; reduced=0",
        sleeve_link=CampaignSleeveLinkSummary(
            linkage_available=sleeve_link_available,
            configured_sleeve_ids=sleeve_ids if sleeve_link_available else (),
            qualified_sleeve_ids=sleeve_ids if sleeve_link_available else (),
            recommended_sleeve_ids=sleeve_ids if sleeve_link_available else (),
            blocked_sleeve_ids=(),
            summary="release pack sleeve link",
        ),
    )
    acceptance = AcceptanceResult(
        verdict=verdict,
        criteria=(
            CriterionResult(
                name="release_pack_campaign",
                passed=verdict in {AcceptanceVerdict.PASS, AcceptanceVerdict.PASS_WITH_WARNINGS},
                severity="hard",
                actual=1.0,
                threshold=1.0,
                message="release pack campaign evidence",
            ),
        ),
        failed_criteria=(),
        warning_criteria=(),
        insufficient_criteria=(),
        summary="release pack campaign evidence",
    )
    return CampaignReport(
        campaign_id="camp-release",
        status="completed",
        verdict=verdict.value,
        started_at_ns=_T0_NS - 100,
        completed_at_ns=_T0_NS,
        elapsed_seconds=100.0,
        run_id="run-release",
        snapshot=snapshot,
        acceptance=acceptance,
        symbol_participation=(),
        config={},
        ext_regime_available=ext_regime_available,
        ext_regime_fresh=True,
        ext_regime_high_risk=ext_regime_high_risk,
        ext_regime_evidence_sufficient=ext_regime_evidence_sufficient,
        ext_regime_scenario_available=ext_regime_scenario_available,
        ext_regime_scenario_step_count=ext_regime_scenario_step_count,
        ext_regime_execution_blocked_steps=ext_regime_execution_blocked_steps,
        ext_regime_activation_blocked_steps=ext_regime_activation_blocked_steps,
        ext_regime_activation_reduced_steps=ext_regime_activation_reduced_steps,
        ext_regime_stale_steps=ext_regime_stale_steps,
        ext_regime_unavailable_steps=ext_regime_unavailable_steps,
        ext_regime_high_risk_steps=ext_regime_high_risk_steps,
        ext_regime_safe_steps=ext_regime_safe_steps,
        ext_regime_scenario_summary="steps=6; safe=4; stale=1; high_risk=1; reduced=0",
        sleeve_link=snapshot.sleeve_link,
    )


def _sleeve(
    sleeve_id: str,
    *,
    status: CryptoSleeveStatus = CryptoSleeveStatus.ALLOCATED,
    recommendation_status: SleeveRecommendationStatus = SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
    qualification_status: SleeveQualificationStatus = SleeveQualificationStatus.PAPER_QUALIFIED,
    campaign_status: SleeveCampaignEvidenceStatus = SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
    support_status: SleevePromotionSupportStatus = SleevePromotionSupportStatus.SUPPORTIVE,
    candidate_status: SleevePromotionCandidateStatus = SleevePromotionCandidateStatus.SUPPORTED,
    decision_status: SleeveDecisionPackStatus = SleeveDecisionPackStatus.RECOMMENDED_ACTIVE,
    effective_allocation: float = 0.25,
    target_allocation: float = 0.25,
    missing_evidence: tuple[str, ...] = (),
    blockers: tuple[str, ...] = (),
) -> CryptoSleeveState:
    return CryptoSleeveState(
        sleeve_id=sleeve_id,
        sleeve_type=CryptoSleeveType.MICROSTRUCTURE,
        status=status,
        target_allocation=target_allocation,
        active_allocation=effective_allocation,
        effective_allocation=effective_allocation,
        blocked_reasons=blockers,
        qualification=SleeveQualificationResult(
            status=qualification_status,
            qualified_for_paper_allocation=qualification_status == SleeveQualificationStatus.PAPER_QUALIFIED,
            governance_blocked=bool(blockers),
            missing_evidence=missing_evidence,
            blocking_reasons=blockers,
            evidence=SleeveEvidenceState(supportive=not blockers and not missing_evidence),
            reason_summary="qualification reason",
            next_step="qualification next",
        ),
        recommendation=SleeveRecommendationResult(
            status=recommendation_status,
            recommended_active=recommendation_status == SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
            currently_eligible=recommendation_status
            in {
                SleeveRecommendationStatus.RECOMMENDED_ACTIVE,
                SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED,
            },
            qualification_status=qualification_status,
            effective_allocation=effective_allocation,
            target_allocation=target_allocation,
            missing_evidence=missing_evidence,
            blocking_reasons=blockers,
            reason_summary="recommendation reason",
            next_step="recommendation next",
        ),
        campaign_evidence=SleeveCampaignEvidenceResult(
            status=campaign_status,
            campaign_evidence_available=campaign_status == SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            explicit_link_available=campaign_status == SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            linked_in_campaign=campaign_status == SleeveCampaignEvidenceStatus.CAMPAIGN_SUPPORTED,
            missing_evidence=missing_evidence,
            blocking_reasons=blockers,
            reason_summary="campaign reason",
            next_step="campaign next",
        ),
        promotion_support=SleevePromotionSupportResult(
            status=support_status,
            can_be_considered_later=support_status
            in {SleevePromotionSupportStatus.SUPPORTIVE, SleevePromotionSupportStatus.WEAK_SUPPORT},
            campaign_evidence_status=campaign_status,
            qualification_status=qualification_status,
            recommendation_status=recommendation_status,
            missing_evidence=missing_evidence,
            blocking_reasons=blockers,
            reason_summary="support reason",
            next_step="support next",
        ),
        promotion_candidate=SleevePromotionCandidateResult(
            status=candidate_status,
            candidate_for_future_review=candidate_status
            in {SleevePromotionCandidateStatus.SUPPORTED, SleevePromotionCandidateStatus.WATCHLIST},
            strongly_supported=candidate_status == SleevePromotionCandidateStatus.SUPPORTED,
            campaign_evidence_status=campaign_status,
            promotion_support_status=support_status,
            qualification_status=qualification_status,
            recommendation_status=recommendation_status,
            missing_evidence=missing_evidence,
            blocking_reasons=blockers,
            reason_summary="candidate reason",
            next_step="candidate next",
        ),
        decision_pack=SleeveDecisionPackResult(
            status=decision_status,
            recommended_active=decision_status == SleeveDecisionPackStatus.RECOMMENDED_ACTIVE,
            currently_eligible=decision_status
            in {
                SleeveDecisionPackStatus.RECOMMENDED_ACTIVE,
                SleeveDecisionPackStatus.ELIGIBLE_BUT_NOT_SELECTED,
            },
            promotion_candidate=candidate_status
            in {SleevePromotionCandidateStatus.SUPPORTED, SleevePromotionCandidateStatus.WATCHLIST},
            strongly_supported_candidate=candidate_status == SleevePromotionCandidateStatus.SUPPORTED,
            recommendation_status=recommendation_status,
            qualification_status=qualification_status,
            campaign_evidence_status=campaign_status,
            promotion_support_status=support_status,
            promotion_candidate_status=candidate_status,
            missing_evidence=missing_evidence,
            blocking_reasons=blockers,
            reason_summary="decision reason",
            next_step="decision next",
        ),
    )


def _portfolio(*sleeves: CryptoSleeveState, readiness_is_supportive: bool = True) -> SleevePortfolioSnapshot:
    return SleevePortfolioSnapshot(
        as_of_ns=_T0_NS,
        sleeves=tuple(sleeves),
        readiness_level="paper_live" if readiness_is_supportive else "not_assessed",
        readiness_is_supportive=readiness_is_supportive,
    )


def _built_portfolio(*sleeves: CryptoSleeveState, readiness_is_supportive: bool = True) -> SleevePortfolioSnapshot:
    return build_sleeve_portfolio_snapshot(
        sleeves=tuple(sleeves),
        as_of_ns=_T0_NS,
        readiness_level="paper_live" if readiness_is_supportive else "not_assessed",
        readiness_is_supportive=readiness_is_supportive,
    )


def _ready_release_pack(
    *sleeves: CryptoSleeveState,
    campaign_report: CampaignReport | None = None,
):
    portfolio = _portfolio(*sleeves)
    review_summary = _review_summary(*(_review_result(sleeve.sleeve_id) for sleeve in sleeves))
    promotion_snapshot = _promotion_snapshot(review_summary)
    admission = SleeveAdmissionController(review_summary, portfolio_snapshot=portfolio).snapshot()
    report = campaign_report or _campaign_report(sleeve_ids=tuple(sleeve.sleeve_id for sleeve in sleeves))
    pack = build_sleeve_admission_release_pack(
        admission,
        promotion_review_snapshot=promotion_snapshot,
        portfolio_snapshot=portfolio,
        campaign_report=report,
        readiness_flags=campaign_readiness_flags(report),
    )
    return pack, portfolio


def _ready_activation_plan(*sleeves: CryptoSleeveState):
    pack, _ = _ready_release_pack(*sleeves)
    manifest = build_managed_sleeve_set_manifest(pack)
    return build_paper_shadow_activation_plan(manifest)


def _market_event(
    symbol: str = "BTCUSDT",
    *,
    venue: str = "binance",
    ts_ns: int = _T0_NS + 100,
    event_type: MarketEventType = MarketEventType.MARK_PRICE,
    price: float | None = 100.0,
    mark_price: float | None = None,
    index_price: float | None = None,
    funding_rate: float | None = None,
    open_interest: float | None = None,
) -> MarketEvent:
    return MarketEvent(
        symbol=symbol,
        venue=venue,
        ts_ns=ts_ns,
        event_type=event_type,
        price=price,
        mark_price=mark_price,
        index_price=index_price,
        funding_rate=funding_rate,
        open_interest=open_interest,
    )


def _paper_intent(
    sleeve_id: str = "active",
    symbol: str = "BTCUSDT",
    *,
    venue: str = "binance",
    side: PaperIntentSide = PaperIntentSide.BUY,
    qty: float | None = 0.10,
    notional: float | None = None,
    intent_ts_ns: int = _T0_NS + 150,
    reason: str = "paper_shadow_contract_test",
    source: str = "unit_test",
) -> PaperIntent:
    return PaperIntent(
        sleeve_id=sleeve_id,
        symbol=symbol,
        venue=venue,
        side=side,
        qty=qty,
        notional=notional,
        intent_ts_ns=intent_ts_ns,
        reason=reason,
        source=source,
    )


def _paper_cost_result_for_intent(
    controller: PaperShadowSessionController,
    *,
    sleeve_id: str = "active",
    symbol: str = "BTCUSDT",
    venue: str = "binance",
    side: PaperIntentSide = PaperIntentSide.BUY,
    qty: float | None = 0.10,
    price: float = 100.0,
    event_ts_ns: int = _T0_NS + 101,
    intent_ts_ns: int = _T0_NS + 150,
    batch_id: str = "paper-cost-intent",
    cost_model: PaperCostModel | None = None,
):
    controller.record_market_event_batch(
        build_market_event_batch((_market_event(symbol, venue=venue, ts_ns=event_ts_ns, price=price),))
    )
    intent_result = controller.record_paper_intent_batch(
        build_paper_intent_batch(
            (
                _paper_intent(
                    sleeve_id,
                    symbol,
                    venue=venue,
                    side=side,
                    qty=qty,
                    intent_ts_ns=intent_ts_ns,
                ),
            ),
            batch_id=batch_id,
        )
    )
    fill_result = controller.simulate_paper_fills(intent_result)
    return controller.evaluate_paper_costs(
        fill_result,
        cost_model=cost_model or PaperCostModel(fee_bps=10.0, slippage_bps=5.0),
    )


def _paper_data_source_payload(
    *,
    source_id: str = "local-feed",
    source_type: str = "local_payload",
    venue: str = "binance",
    as_of_ns: int = _T0_NS + 200,
    records: tuple[dict, ...] | None = None,
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT"),
) -> dict:
    return {
        "source_id": source_id,
        "source_type": source_type,
        "venue": venue,
        "as_of_ns": as_of_ns,
        "symbols": list(symbols),
        "records": list(
            records
            or (
                {
                    "symbol": "ETHUSDT",
                    "ts_ns": _T0_NS + 102,
                    "event_type": "mark_price",
                    "price": 2100.0,
                },
                {
                    "symbol": "BTCUSDT",
                    "ts_ns": _T0_NS + 101,
                    "event_type": "mark_price",
                    "price": 100.0,
                },
            )
        ),
    }


def _paper_shadow_full_local_run(
    *,
    source_id: str = "local-feed",
    report_id: str = "run-evidence-report",
    replay_id: str = "run-evidence-replay",
    records: tuple[dict, ...] | None = None,
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT"),
):
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 1, _T0_NS + 2, _T0_NS + 3))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))
    source_result = build_paper_data_source_batch_result(
        _paper_data_source_payload(source_id=source_id, records=records, symbols=symbols),
        allowed_source_ids=(source_id,),
    )

    controller.prepare(plan)
    controller.start()
    replay = controller.replay_feed(build_feed_replay_plan((source_result.batch,), replay_id=replay_id))
    report = build_paper_shadow_run_evidence_report(
        session_snapshot=controller.snapshot(),
        source_result=source_result,
        replay_result=replay,
        report_id=report_id,
    )
    return source_result, replay, controller.snapshot(), report


def _mock_service() -> MagicMock:
    queue = QueueSnapshot(
        current_depth=0,
        max_size=100,
        pressure=QueuePressure.NORMAL,
        total_enqueued=0,
        total_dropped=0,
        total_processed=0,
    )
    watchdog = WatchdogStatus(
        consumer_alive=True,
        last_event_time_ns=_T0_NS,
        last_cycle_time_ns=_T0_NS,
        seconds_since_event=0.0,
        seconds_since_cycle=0.0,
        stall_detected=False,
        stall_threshold_s=60.0,
    )
    status = ServiceStatus(
        service_mode="running",
        runtime_status=None,
        queue=queue,
        watchdog=watchdog,
        symbol_health=(),
        symbol_count=0,
        trading_enabled=True,
        blocked_reason=None,
        last_error=None,
    )
    service = MagicMock()
    service.status.return_value = status
    return service


def _supported_workflow(sleeve_id: str) -> SleeveCandidateWorkflowSnapshot:
    return SleeveCandidateWorkflowSnapshot(
        workflow_id="wf-admission",
        status="active",
        as_of_ns=_T0_NS,
        sleeves=(
            SleeveCandidateWorkflowEntry(
                sleeve_id=sleeve_id,
                candidate_status=SleevePromotionCandidateStatus.SUPPORTED,
                promotion_support_status=SleevePromotionSupportStatus.SUPPORTIVE,
                decision_pack_status=SleeveDecisionPackStatus.SUPPORTED_CANDIDATE,
                candidate_for_future_review=True,
                strongly_supported=True,
                reason_summary="supported",
                next_step="review",
            ),
        ),
    )


def _paper_shadow_e2e_seed(
    *,
    sleeve_id: str = "e2e-active",
    allocation: float = 0.20,
):
    sleeve = _sleeve(sleeve_id, effective_allocation=allocation, target_allocation=allocation)
    base_portfolio = _portfolio(sleeve)
    portfolio = replace(
        base_portfolio,
        effective_allocation=replace(
            base_portfolio.effective_allocation,
            effective_allocated_share=allocation,
            effective_unallocated_share=1.0 - allocation,
            recipient_sleeve_ids=(sleeve_id,),
        ),
    )
    campaign_report = _campaign_report(sleeve_ids=(sleeve_id,))
    times = iter(range(_T0_NS + 300, _T0_NS + 420))
    orch = ServiceOrchestrator(
        service=_mock_service(),
        sleeves=(sleeve,),
        readiness_level="paper_live",
        sleeve_workflow_clock_ns=lambda: next(times),
    )
    orch.start_sleeve_promotion_review(workflow_snapshot=_supported_workflow(sleeve_id))
    seed_pack = orch.sleeve_admission_release_pack(
        portfolio_snapshot=portfolio,
        campaign_report=campaign_report,
        readiness_flags=campaign_readiness_flags(campaign_report),
    )
    manifest = orch.managed_sleeve_set_manifest(release_pack=seed_pack, portfolio_snapshot=portfolio)
    plan = orch.paper_shadow_activation_plan(manifest=manifest)
    return orch, portfolio, campaign_report, seed_pack, manifest, plan


def _paper_shadow_e2e_pass_report(
    *,
    sleeve_id: str = "e2e-active",
    source_id: str = "local-e2e-feed",
    report_id: str = "run-e2e-pass",
    replay_id: str = "replay-e2e-pass",
):
    orch, portfolio, campaign_report, seed_pack, manifest, plan = _paper_shadow_e2e_seed(sleeve_id=sleeve_id)
    source_result = orch.paper_data_source_payload_to_batch_result(
        _paper_data_source_payload(source_id=source_id),
        allowed_source_ids=(source_id,),
        batch_id=f"{source_id}-batch",
    )
    orch.prepare_paper_shadow_session(plan=plan)
    orch.start_paper_shadow_session()
    replay_result = orch.replay_paper_shadow_feed(build_feed_replay_plan((source_result.batch,), replay_id=replay_id))
    report = orch.paper_shadow_run_evidence_report(
        source_result=source_result,
        replay_result=replay_result,
        report_id=report_id,
    )
    return orch, portfolio, campaign_report, seed_pack, manifest, plan, source_result, replay_result, report


def test_admission_model_construction() -> None:
    controller = SleeveAdmissionController(
        _review_summary(_review_result("s1")),
        portfolio_snapshot=_portfolio(_sleeve("s1")),
    )

    result = controller.build_admission_results()[0]

    assert result.sleeve_id == "s1"
    assert result.verdict == SleeveAdmissionVerdict.ADMITTED_ACTIVE
    assert result.admitted is True
    assert result.active is True


def test_no_review_conservative_behavior() -> None:
    controller = SleeveAdmissionController(portfolio_snapshot=_portfolio(_sleeve("s1")))

    result = controller.build_admission_results()[0]

    assert result.verdict == SleeveAdmissionVerdict.INSUFFICIENT_EVIDENCE
    assert result.admitted is False
    assert result.evidence_blockers == ("promotion_review_unavailable",)


def test_admitted_active_sleeve() -> None:
    result = SleeveAdmissionController(
        _review_summary(_review_result("active")),
        portfolio_snapshot=_portfolio(_sleeve("active", effective_allocation=0.35)),
    ).build_admission_results()[0]

    assert result.verdict == SleeveAdmissionVerdict.ADMITTED_ACTIVE
    assert result.effective_allocation == pytest.approx(0.35)


def test_admitted_unallocated_sleeve() -> None:
    result = SleeveAdmissionController(
        _review_summary(_review_result("idle")),
        portfolio_snapshot=_portfolio(
            _sleeve(
                "idle",
                status=CryptoSleeveStatus.ENABLED,
                recommendation_status=SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED,
                decision_status=SleeveDecisionPackStatus.ELIGIBLE_BUT_NOT_SELECTED,
                effective_allocation=0.0,
            )
        ),
    ).build_admission_results()[0]

    assert result.verdict == SleeveAdmissionVerdict.ADMITTED_UNALLOCATED
    assert result.admitted is True
    assert result.active is False


def test_review_supported_not_admitted_sleeve() -> None:
    result = SleeveAdmissionController(_review_summary(_review_result("missing"))).build_admission_results()[0]

    assert result.verdict == SleeveAdmissionVerdict.REVIEW_SUPPORTED_NOT_ADMITTED
    assert result.evidence_blockers == ("sleeve_portfolio_unavailable",)


def test_blocked_sleeve() -> None:
    result = SleeveAdmissionController(
        _review_summary(_review_result("blocked", SleevePromotionReviewVerdict.REJECT)),
        portfolio_snapshot=_portfolio(
            _sleeve(
                "blocked",
                status=CryptoSleeveStatus.BLOCKED,
                recommendation_status=SleeveRecommendationStatus.BLOCKED,
                qualification_status=SleeveQualificationStatus.BLOCKED,
                campaign_status=SleeveCampaignEvidenceStatus.BLOCKED_BY_GOVERNANCE,
                support_status=SleevePromotionSupportStatus.BLOCKED,
                candidate_status=SleevePromotionCandidateStatus.BLOCKED,
                decision_status=SleeveDecisionPackStatus.BLOCKED,
                blockers=("readiness_pending",),
            )
        ),
    ).build_admission_results()[0]

    assert result.verdict == SleeveAdmissionVerdict.BLOCKED
    assert result.governance_blockers == ("readiness_pending",)


def test_inconclusive_sleeve() -> None:
    result = SleeveAdmissionController(
        _review_summary(_review_result("watch", SleevePromotionReviewVerdict.HOLD)),
        portfolio_snapshot=_portfolio(
            _sleeve(
                "watch",
                recommendation_status=SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED,
                support_status=SleevePromotionSupportStatus.WEAK_SUPPORT,
                candidate_status=SleevePromotionCandidateStatus.WATCHLIST,
                decision_status=SleeveDecisionPackStatus.WATCHLIST_CANDIDATE,
                effective_allocation=0.0,
            )
        ),
    ).build_admission_results()[0]

    assert result.verdict == SleeveAdmissionVerdict.INCONCLUSIVE


def test_disabled_operator_off_sleeve() -> None:
    result = SleeveAdmissionController(
        _review_summary(_review_result("disabled")),
        portfolio_snapshot=_portfolio(
            _sleeve(
                "disabled",
                status=CryptoSleeveStatus.DISABLED,
                recommendation_status=SleeveRecommendationStatus.DISABLED_OPERATOR_OFF,
                decision_status=SleeveDecisionPackStatus.BLOCKED,
                effective_allocation=0.0,
            )
        ),
    ).build_admission_results()[0]

    assert result.verdict == SleeveAdmissionVerdict.DISABLED_OPERATOR_OFF
    assert "disabled_operator_off" in result.governance_blockers


def test_portfolio_admission_summary() -> None:
    controller = SleeveAdmissionController(
        _review_summary(
            _review_result("active"),
            _review_result("idle"),
            _review_result("missing"),
            _review_result("blocked", SleevePromotionReviewVerdict.REJECT),
            _review_result("watch", SleevePromotionReviewVerdict.INCONCLUSIVE),
        ),
        portfolio_snapshot=_portfolio(
            _sleeve("active"),
            _sleeve(
                "idle",
                status=CryptoSleeveStatus.ENABLED,
                recommendation_status=SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED,
                effective_allocation=0.0,
            ),
            _sleeve("blocked", status=CryptoSleeveStatus.BLOCKED, blockers=("gov",)),
            _sleeve("watch", effective_allocation=0.0),
        ),
    )

    summary = controller.build_portfolio_summary()

    assert summary.admitted_active_count == 1
    assert summary.admitted_unallocated_count == 1
    assert summary.review_supported_not_admitted_count == 1
    assert summary.blocked_count == 1
    assert summary.inconclusive_count == 1
    assert "gov" in summary.governance_blockers
    assert "admitted_active=1" in summary.operator_summary


def test_reason_codes_and_next_step_summary() -> None:
    controller = SleeveAdmissionController(
        _review_summary(_review_result("s1", missing_evidence=("campaign_missing",))),
        portfolio_snapshot=_portfolio(_sleeve("s1")),
    )

    summary = controller.build_portfolio_summary()

    assert summary.evidence_blockers == ("campaign_missing",)
    assert "continue_paper_review" in summary.next_step_summary
    assert summary.review_supported_not_admitted == ("s1",)


def test_serialization_roundtrip() -> None:
    controller = SleeveAdmissionController(
        _review_summary(_review_result("s1")),
        portfolio_snapshot=_portfolio(_sleeve("s1")),
    )
    snapshot = controller.finalize()

    restored = sleeve_admission_snapshot_from_dict(sleeve_admission_snapshot_to_dict(snapshot))

    assert restored == snapshot


def test_restore_fail_closed_on_malformed_payload() -> None:
    payload = {
        "as_of_ns": _T0_NS,
        "status": "active",
        "admission_results": [],
        "portfolio_summary": {
            "as_of_ns": _T0_NS,
            "admission_results": [],
            "admitted_active_count": 1,
            "admitted_active": [],
            "admitted_unallocated": [],
            "review_supported_not_admitted": [],
            "blocked": [],
            "inconclusive": [],
            "governance_blockers": [],
            "evidence_blockers": [],
            "next_step_summary": "bad",
            "operator_summary": "bad",
        },
        "history": [],
    }

    with pytest.raises(SleeveAdmissionCorruptError):
        sleeve_admission_snapshot_from_dict(payload)


def test_restore_fail_closed_on_timestamp_drift() -> None:
    controller = SleeveAdmissionController(
        _review_summary(_review_result("s1")),
        portfolio_snapshot=_portfolio(_sleeve("s1")),
    )
    payload = sleeve_admission_snapshot_to_dict(controller.finalize())
    payload["as_of_ns"] += 1

    with pytest.raises(SleeveAdmissionCorruptError):
        sleeve_admission_snapshot_from_dict(payload)


def test_service_orchestrator_integration() -> None:
    fixed_review_ns = _T0_NS + 42
    orch = ServiceOrchestrator(service=_mock_service(), sleeve_workflow_clock_ns=lambda: fixed_review_ns)
    orch.start_sleeve_promotion_review(workflow_snapshot=_supported_workflow("svc-sleeve"))

    snapshot = orch.get_sleeve_admission_snapshot(
        portfolio_snapshot=_portfolio(_sleeve("svc-sleeve", effective_allocation=0.20))
    )
    rendered = sleeve_admission_snapshot_to_dict(snapshot)

    assert snapshot.as_of_ns == fixed_review_ns
    assert snapshot.portfolio_summary.admitted_active == ("svc-sleeve",)
    assert rendered["portfolio_summary"]["admitted_active_count"] == 1


def test_operator_snapshot_surfaces_no_review_conservatively() -> None:
    orch = ServiceOrchestrator(service=_mock_service(), sleeves=(_sleeve("configured"),))

    snapshot = orch.operator_snapshot()
    rendered = operator_snapshot_to_dict(snapshot)

    assert snapshot.sleeve_admission is not None
    assert snapshot.sleeve_admission.portfolio_summary.insufficient_evidence_count == 1
    assert "promotion_review_unavailable" in rendered["sleeve_admission"]["portfolio_summary"]["evidence_blockers"]


def test_deterministic_replay() -> None:
    summary = _review_summary(_review_result("s1"))
    portfolio = _portfolio(_sleeve("s1"))

    first = sleeve_admission_snapshot_to_dict(
        SleeveAdmissionController(summary, portfolio_snapshot=portfolio).snapshot()
    )
    second = sleeve_admission_snapshot_to_dict(
        SleeveAdmissionController(summary, portfolio_snapshot=portfolio).snapshot()
    )

    assert first == second


def test_backward_compatibility_with_older_snapshot_state() -> None:
    old_result = {
        "sleeve_id": "old-blocked",
        "verdict": "not_admitted_blocked",
        "reason": "old reason",
        "next_step": "old next",
    }
    payload = {
        "as_of_ns": _T0_NS,
        "status": "active",
        "admission_results": [old_result],
        "portfolio_summary": {
            "as_of_ns": _T0_NS,
            "admission_results": [old_result],
            "admitted_active": [],
            "admitted_unallocated": [],
            "review_supported_not_admitted": [],
            "blocked": ["old-blocked"],
            "inconclusive": [],
            "governance_blockers": [],
            "evidence_blockers": [],
            "operator_summary": "old summary",
        },
        "history": [],
    }

    restored = sleeve_admission_snapshot_from_dict(payload)

    assert restored.portfolio_summary.blocked_count == 1
    assert restored.admission_results[0].verdict == SleeveAdmissionVerdict.NOT_ADMITTED_BLOCKED


def test_release_pack_model_construction_and_ready_full_admission() -> None:
    review_summary = _review_summary(_review_result("active"), _review_result("idle"))
    portfolio = _portfolio(
        _sleeve("active"),
        _sleeve(
            "idle",
            status=CryptoSleeveStatus.ENABLED,
            recommendation_status=SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED,
            decision_status=SleeveDecisionPackStatus.ELIGIBLE_BUT_NOT_SELECTED,
            effective_allocation=0.0,
        ),
    )
    admission = SleeveAdmissionController(
        review_summary,
        portfolio_snapshot=portfolio,
    ).snapshot()

    pack = build_sleeve_admission_release_pack(
        admission,
        promotion_review_snapshot=_promotion_snapshot(review_summary),
        portfolio_snapshot=portfolio,
        campaign_report=_campaign_report(sleeve_ids=("active", "idle")),
    )

    assert pack.overall_release_status == SleeveAdmissionReleaseStatus.READY_FOR_PAPER_MANAGED_SET
    assert pack.evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_READY
    assert pack.paper_campaign_evidence_available is True
    assert pack.sleeve_campaign_link_available is True
    assert pack.promotion_review_evidence_available is True
    assert pack.readiness_evidence_supportive is True
    assert pack.tca_or_markout_evidence_supportive is True
    assert pack.external_regime_evidence_supportive is True
    assert pack.admitted_sleeves == ("active", "idle")
    assert pack.admitted_active_sleeves == ("active",)
    assert pack.admitted_unallocated_sleeves == ("idle",)
    assert pack.pack_id.startswith("sleeve-admission-release-")


def test_release_pack_missing_campaign_evidence_is_not_ready() -> None:
    review_summary = _review_summary(_review_result("s1"))
    portfolio = _portfolio(_sleeve("s1"))
    admission = SleeveAdmissionController(review_summary, portfolio_snapshot=portfolio).snapshot()

    pack = build_sleeve_admission_release_pack(
        admission,
        promotion_review_snapshot=_promotion_snapshot(review_summary),
        portfolio_snapshot=portfolio,
    )

    assert pack.overall_release_status == SleeveAdmissionReleaseStatus.PARTIAL_READY
    assert pack.evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_MISSING
    assert "paper_campaign_evidence_unavailable" in pack.paper_evidence_blockers


def test_release_pack_missing_sleeve_campaign_link_is_not_ready() -> None:
    review_summary = _review_summary(_review_result("s1"))
    portfolio = _portfolio(_sleeve("s1", campaign_status=SleeveCampaignEvidenceStatus.INSUFFICIENT_EVIDENCE))
    admission = SleeveAdmissionController(review_summary, portfolio_snapshot=portfolio).snapshot()

    pack = build_sleeve_admission_release_pack(
        admission,
        promotion_review_snapshot=_promotion_snapshot(review_summary),
        portfolio_snapshot=portfolio,
        campaign_report=_campaign_report(sleeve_ids=("other",)),
    )

    assert pack.overall_release_status == SleeveAdmissionReleaseStatus.PARTIAL_READY
    assert pack.sleeve_campaign_link_available is False
    assert "sleeve_campaign_link_unavailable" in pack.paper_evidence_blockers
    assert pack.per_sleeve_evidence_blockers[0].evidence_blockers == ("sleeve_campaign_link_unavailable",)


def test_release_pack_missing_promotion_review_evidence_is_not_ready() -> None:
    review_summary = _review_summary(_review_result("s1"))
    portfolio = _portfolio(_sleeve("s1"))
    admission = SleeveAdmissionController(review_summary, portfolio_snapshot=portfolio).snapshot()

    pack = build_sleeve_admission_release_pack(
        admission,
        portfolio_snapshot=portfolio,
        campaign_report=_campaign_report(sleeve_ids=("s1",)),
    )

    assert pack.overall_release_status == SleeveAdmissionReleaseStatus.PARTIAL_READY
    assert pack.promotion_review_evidence_available is False
    assert "promotion_review_evidence_unavailable" in pack.paper_evidence_blockers


def test_release_pack_missing_readiness_support_is_not_ready() -> None:
    review_summary = _review_summary(_review_result("s1"))
    portfolio = _portfolio(_sleeve("s1"), readiness_is_supportive=False)
    admission = SleeveAdmissionController(review_summary, portfolio_snapshot=portfolio).snapshot()

    pack = build_sleeve_admission_release_pack(
        admission,
        promotion_review_snapshot=_promotion_snapshot(review_summary),
        portfolio_snapshot=portfolio,
        campaign_report=_campaign_report(sleeve_ids=("s1",)),
    )

    assert pack.overall_release_status == SleeveAdmissionReleaseStatus.PARTIAL_READY
    assert pack.evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_PARTIAL
    assert "readiness_evidence_not_supportive" in pack.paper_evidence_blockers


def test_release_pack_partial_without_tca_or_markout_evidence() -> None:
    review_summary = _review_summary(_review_result("s1"))
    portfolio = _portfolio(_sleeve("s1"))
    admission = SleeveAdmissionController(review_summary, portfolio_snapshot=portfolio).snapshot()

    pack = build_sleeve_admission_release_pack(
        admission,
        promotion_review_snapshot=_promotion_snapshot(review_summary),
        portfolio_snapshot=portfolio,
        campaign_report=_campaign_report(sleeve_ids=("s1",), persisted_tca_count=0, completed_markout_count=0),
    )

    assert pack.overall_release_status == SleeveAdmissionReleaseStatus.PARTIAL_READY
    assert pack.evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_PARTIAL
    assert "tca_or_markout_evidence_unavailable" in pack.paper_evidence_blockers


def test_release_pack_external_regime_blocker_blocks_portfolio() -> None:
    review_summary = _review_summary(_review_result("s1"))
    portfolio = _portfolio(_sleeve("s1"))
    admission = SleeveAdmissionController(review_summary, portfolio_snapshot=portfolio).snapshot()

    pack = build_sleeve_admission_release_pack(
        admission,
        promotion_review_snapshot=_promotion_snapshot(review_summary),
        portfolio_snapshot=portfolio,
        campaign_report=_campaign_report(
            sleeve_ids=("s1",),
            ext_regime_high_risk=True,
            ext_regime_high_risk_steps=4,
        ),
    )

    assert pack.overall_release_status == SleeveAdmissionReleaseStatus.BLOCKED
    assert pack.evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_BLOCKED
    assert "external_regime_governance_blocked" in pack.paper_evidence_blockers


def test_release_pack_no_candidates_and_inconclusive_states() -> None:
    empty = build_sleeve_admission_release_pack(SleeveAdmissionController().snapshot())
    review_only = build_sleeve_admission_release_pack(
        SleeveAdmissionController(_review_summary(_review_result("review-only"))).snapshot()
    )
    hold = build_sleeve_admission_release_pack(
        SleeveAdmissionController(
            _review_summary(_review_result("hold", SleevePromotionReviewVerdict.HOLD)),
            portfolio_snapshot=_portfolio(_sleeve("hold", effective_allocation=0.0)),
        ).snapshot()
    )

    assert empty.overall_release_status == SleeveAdmissionReleaseStatus.NO_CANDIDATES
    assert empty.next_actions == ()
    assert review_only.overall_release_status == SleeveAdmissionReleaseStatus.INCONCLUSIVE
    assert review_only.review_supported_not_admitted_sleeves == ("review-only",)
    assert hold.overall_release_status == SleeveAdmissionReleaseStatus.INCONCLUSIVE
    assert hold.inconclusive_sleeves == ("hold",)


def test_release_pack_partial_and_blocked_portfolio_states() -> None:
    partial = build_sleeve_admission_release_pack(
        SleeveAdmissionController(
            _review_summary(
                _review_result("active"),
                _review_result("blocked", SleevePromotionReviewVerdict.REJECT),
            ),
            portfolio_snapshot=_portfolio(
                _sleeve("active"),
                _sleeve(
                    "blocked",
                    status=CryptoSleeveStatus.BLOCKED,
                    recommendation_status=SleeveRecommendationStatus.BLOCKED,
                    qualification_status=SleeveQualificationStatus.BLOCKED,
                    campaign_status=SleeveCampaignEvidenceStatus.BLOCKED_BY_GOVERNANCE,
                    support_status=SleevePromotionSupportStatus.BLOCKED,
                    candidate_status=SleevePromotionCandidateStatus.BLOCKED,
                    decision_status=SleeveDecisionPackStatus.BLOCKED,
                    blockers=("gov_hold",),
                ),
            ),
        ).snapshot()
    )
    blocked = build_sleeve_admission_release_pack(
        SleeveAdmissionController(
            _review_summary(_review_result("blocked", SleevePromotionReviewVerdict.REJECT)),
            portfolio_snapshot=_portfolio(_sleeve("blocked", status=CryptoSleeveStatus.BLOCKED, blockers=("gov",))),
        ).snapshot()
    )

    assert partial.overall_release_status == SleeveAdmissionReleaseStatus.PARTIAL_READY
    assert partial.admitted_sleeves == ("active",)
    assert partial.blocked_sleeves == ("blocked",)
    assert blocked.overall_release_status == SleeveAdmissionReleaseStatus.BLOCKED


def test_release_pack_next_actions_and_blocker_aggregation_are_stable() -> None:
    admission = SleeveAdmissionController(
        _review_summary(
            _review_result(
                "s1",
                governance_blockers=("z_governance",),
                missing_evidence=("z_evidence",),
            )
        ),
        portfolio_snapshot=_portfolio(_sleeve("s1", missing_evidence=("a_evidence",), blockers=("a_governance",))),
    ).snapshot()

    pack = build_sleeve_admission_release_pack(admission)
    rendered = sleeve_admission_release_pack_to_dict(pack)

    assert pack.overall_release_status == SleeveAdmissionReleaseStatus.INCONCLUSIVE
    assert "a_evidence" in pack.evidence_blockers
    assert "z_evidence" in pack.evidence_blockers
    assert "paper_campaign_evidence_unavailable" in pack.evidence_blockers
    assert pack.governance_blockers == ("a_governance", "z_governance")
    assert pack.next_actions[0].next_action == "continue_paper_review"
    assert rendered["next_actions"][0]["admission_verdict"] == "review_supported_not_admitted"
    assert rendered["evidence_gate_status"] == "evidence_missing"
    assert rendered == sleeve_admission_release_pack_to_dict(pack)


def test_release_pack_serialization_roundtrip_and_backward_defaults() -> None:
    admission = SleeveAdmissionController(
        _review_summary(_review_result("s1")),
        portfolio_snapshot=_portfolio(_sleeve("s1")),
    ).snapshot()
    pack = build_sleeve_admission_release_pack(admission)
    payload = sleeve_admission_release_pack_to_dict(pack)

    restored = sleeve_admission_release_pack_from_dict(payload)
    legacy = sleeve_admission_release_pack_from_dict({"portfolio_summary": payload["portfolio_summary"]})

    assert restored == pack
    assert legacy.overall_release_status == SleeveAdmissionReleaseStatus.PARTIAL_READY
    assert legacy.evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_MISSING
    assert legacy.admitted_sleeves == ("s1",)
    assert legacy.admission_snapshot_status == "unknown"


def test_release_pack_malformed_payload_fails_closed() -> None:
    admission = SleeveAdmissionController(
        _review_summary(_review_result("s1")),
        portfolio_snapshot=_portfolio(_sleeve("s1")),
    ).snapshot()
    payload = sleeve_admission_release_pack_to_dict(build_sleeve_admission_release_pack(admission))
    payload["overall_release_status"] = "blocked"

    with pytest.raises(SleeveAdmissionCorruptError):
        sleeve_admission_release_pack_from_dict(payload)


def test_release_pack_artifact_export_load_roundtrip_and_bad_load_fail_closed(tmp_path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    admission = SleeveAdmissionController(
        _review_summary(_review_result("s1")),
        portfolio_snapshot=_portfolio(_sleeve("s1")),
    ).snapshot()
    pack = build_sleeve_admission_release_pack(admission)

    export_sleeve_admission_release_pack(pack=pack, evidence_store=store)
    restored = load_sleeve_admission_release_pack(evidence_store=store)

    assert restored == pack

    store.save_snapshot("crypto_sleeve_admission_release_pack", ["bad"])
    with pytest.raises(SleeveAdmissionCorruptError):
        load_sleeve_admission_release_pack(evidence_store=store)


def test_service_orchestrator_release_pack_helper_and_operator_compact_status() -> None:
    fixed_review_ns = _T0_NS + 42
    orch = ServiceOrchestrator(
        service=_mock_service(),
        sleeves=(_sleeve("svc-sleeve", effective_allocation=0.20, target_allocation=0.20),),
        readiness_level="paper_live",
        sleeve_workflow_clock_ns=lambda: fixed_review_ns,
    )
    campaign_report = _campaign_report(sleeve_ids=("svc-sleeve",))
    orch._last_campaign_report = campaign_report  # type: ignore[attr-defined]
    orch.start_sleeve_promotion_review(workflow_snapshot=_supported_workflow("svc-sleeve"))

    pack = orch.sleeve_admission_release_pack(
        portfolio_snapshot=_portfolio(_sleeve("svc-sleeve", effective_allocation=0.20, target_allocation=0.20)),
        campaign_report=campaign_report,
        readiness_flags=campaign_readiness_flags(campaign_report),
    )
    rendered = sleeve_admission_release_pack_to_dict(pack)
    helper_rendered = orch.sleeve_admission_release_pack_dict()

    assert pack.as_of_ns == fixed_review_ns
    assert pack.overall_release_status == SleeveAdmissionReleaseStatus.READY_FOR_PAPER_MANAGED_SET
    assert pack.evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_READY
    assert rendered["overall_release_status"] == "ready_for_paper_managed_set"
    assert rendered["evidence_gate_status"] == "evidence_ready"
    assert helper_rendered["overall_release_status"] == "inconclusive"
    assert helper_rendered["evidence_gate_status"] == "evidence_missing"

    operator = operator_snapshot_to_dict(orch.operator_snapshot())
    assert operator["sleeve_admission_release"]["overall_release_status"] == "inconclusive"
    assert operator["sleeve_admission_release"]["evidence_gate_status"] == "evidence_missing"
    assert operator["sleeve_admission_release"]["paper_campaign_evidence_available"] is True
    assert operator["sleeve_admission_release"]["available"] is True


def test_service_orchestrator_release_pack_export_load_helper(tmp_path) -> None:
    fixed_review_ns = _T0_NS + 77
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    orch = ServiceOrchestrator(
        service=_mock_service(),
        evidence_store=store,
        sleeve_workflow_clock_ns=lambda: fixed_review_ns,
    )
    orch.start_sleeve_promotion_review(workflow_snapshot=_supported_workflow("export-sleeve"))

    orch.export_sleeve_admission_release_pack()
    loaded = orch.load_sleeve_admission_release_pack()

    assert loaded == orch.sleeve_admission_release_pack()
    assert loaded.source_promotion_review_as_of_ns == fixed_review_ns


def test_release_pack_deterministic_replay_with_fixed_clock() -> None:
    fixed_review_ns = _T0_NS + 123
    portfolio = _portfolio(_sleeve("stable", effective_allocation=0.10))
    orch = ServiceOrchestrator(service=_mock_service(), sleeve_workflow_clock_ns=lambda: fixed_review_ns)
    orch.start_sleeve_promotion_review(workflow_snapshot=_supported_workflow("stable"))

    first = sleeve_admission_release_pack_to_dict(orch.sleeve_admission_release_pack(portfolio_snapshot=portfolio))
    second = sleeve_admission_release_pack_to_dict(orch.sleeve_admission_release_pack(portfolio_snapshot=portfolio))

    assert first == second
    assert first["source_promotion_review_as_of_ns"] == fixed_review_ns


def test_managed_manifest_model_construction_and_ready_dry_run() -> None:
    sleeve = _sleeve("active", effective_allocation=0.25, target_allocation=0.25)
    pack, _ = _ready_release_pack(sleeve)

    manifest = build_managed_sleeve_set_manifest(pack)
    portfolio_manifest = build_managed_sleeve_set_manifest(pack, portfolio_snapshot=_built_portfolio(sleeve))
    rendered = managed_sleeve_set_manifest_to_dict(manifest)

    assert manifest.dry_run_status == ManagedSleeveSetDryRunStatus.READY_FOR_PAPER_DRY_RUN
    assert portfolio_manifest.dry_run_status == ManagedSleeveSetDryRunStatus.READY_FOR_PAPER_DRY_RUN
    assert manifest.source_release_pack_status == SleeveAdmissionReleaseStatus.READY_FOR_PAPER_MANAGED_SET
    assert manifest.source_evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_READY
    assert manifest.active_sleeves == ("active",)
    assert rendered["effective_allocations"] == [{"sleeve_id": "active", "effective_allocation": 0.25}]
    assert rendered["unallocated_share"] == 0.75
    assert portfolio_manifest.unallocated_share == 0.75
    assert rendered["activation_blockers"] == []
    assert manifest.source_release_pack_hash
    assert manifest.manifest_id.startswith("managed-sleeve-set-manifest-")


def test_managed_manifest_empty_release_pack_is_empty_and_blocked_safe() -> None:
    pack = build_sleeve_admission_release_pack(SleeveAdmissionController().snapshot())

    manifest = build_managed_sleeve_set_manifest(pack)

    assert manifest.dry_run_status == ManagedSleeveSetDryRunStatus.EMPTY
    assert manifest.active_sleeves == ()
    assert manifest.effective_allocations == ()
    assert "no_admission_candidates" in manifest.activation_blockers


def test_managed_manifest_partial_release_pack_is_not_ready() -> None:
    portfolio = _portfolio(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    review_summary = _review_summary(_review_result("active"))
    admission = SleeveAdmissionController(review_summary, portfolio_snapshot=portfolio).snapshot()
    pack = build_sleeve_admission_release_pack(
        admission,
        promotion_review_snapshot=_promotion_snapshot(review_summary),
        portfolio_snapshot=portfolio,
    )

    manifest = build_managed_sleeve_set_manifest(pack)

    assert pack.overall_release_status == SleeveAdmissionReleaseStatus.PARTIAL_READY
    assert manifest.dry_run_status == ManagedSleeveSetDryRunStatus.PARTIAL_PAPER_DRY_RUN
    assert "release_pack_evidence_not_ready" in manifest.activation_blockers


def test_managed_manifest_tracks_unallocated_and_excludes_blocked_sleeves() -> None:
    active = _sleeve("active", effective_allocation=0.30, target_allocation=0.30)
    reserve = _sleeve(
        "reserve",
        status=CryptoSleeveStatus.ENABLED,
        recommendation_status=SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED,
        decision_status=SleeveDecisionPackStatus.ELIGIBLE_BUT_NOT_SELECTED,
        effective_allocation=0.0,
        target_allocation=0.0,
    )
    blocked = _sleeve(
        "blocked",
        status=CryptoSleeveStatus.BLOCKED,
        recommendation_status=SleeveRecommendationStatus.BLOCKED,
        qualification_status=SleeveQualificationStatus.BLOCKED,
        campaign_status=SleeveCampaignEvidenceStatus.BLOCKED_BY_GOVERNANCE,
        support_status=SleevePromotionSupportStatus.BLOCKED,
        candidate_status=SleevePromotionCandidateStatus.BLOCKED,
        decision_status=SleeveDecisionPackStatus.BLOCKED,
        effective_allocation=0.0,
        target_allocation=0.0,
        blockers=("governance_block",),
    )
    portfolio = _portfolio(active, reserve, blocked)
    review_summary = _review_summary(
        _review_result("active"),
        _review_result("reserve"),
        _review_result("blocked", SleevePromotionReviewVerdict.REJECT, governance_blockers=("review_block",)),
    )
    report = _campaign_report(sleeve_ids=("active", "reserve", "blocked"))
    admission = SleeveAdmissionController(review_summary, portfolio_snapshot=portfolio).snapshot()
    pack = build_sleeve_admission_release_pack(
        admission,
        promotion_review_snapshot=_promotion_snapshot(review_summary),
        portfolio_snapshot=portfolio,
        campaign_report=report,
        readiness_flags=campaign_readiness_flags(report),
    )

    manifest = build_managed_sleeve_set_manifest(pack)

    assert manifest.dry_run_status == ManagedSleeveSetDryRunStatus.PARTIAL_PAPER_DRY_RUN
    assert manifest.active_sleeves == ("active",)
    assert manifest.admitted_unallocated_sleeves == ("reserve",)
    assert manifest.blocked_sleeves == ("blocked",)
    assert "blocked" not in manifest.active_sleeves
    assert "governance_block" in manifest.activation_blockers
    assert "review_block" in manifest.governance_blockers

    blocked_review_summary = _review_summary(_review_result("blocked", SleevePromotionReviewVerdict.REJECT))
    blocked_report = _campaign_report(sleeve_ids=("blocked",))
    blocked_admission = SleeveAdmissionController(
        blocked_review_summary,
        portfolio_snapshot=_portfolio(blocked),
    ).snapshot()
    blocked_pack = build_sleeve_admission_release_pack(
        blocked_admission,
        promotion_review_snapshot=_promotion_snapshot(blocked_review_summary),
        portfolio_snapshot=_portfolio(blocked),
        campaign_report=blocked_report,
        readiness_flags=campaign_readiness_flags(blocked_report),
    )
    blocked_manifest = build_managed_sleeve_set_manifest(blocked_pack)
    assert blocked_manifest.dry_run_status == ManagedSleeveSetDryRunStatus.BLOCKED


def test_managed_manifest_next_actions_and_serialization_roundtrip() -> None:
    active = _sleeve("z-active", effective_allocation=0.10, target_allocation=0.10)
    reserve = _sleeve(
        "a-reserve",
        status=CryptoSleeveStatus.ENABLED,
        recommendation_status=SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED,
        decision_status=SleeveDecisionPackStatus.ELIGIBLE_BUT_NOT_SELECTED,
        effective_allocation=0.0,
        target_allocation=0.0,
    )
    pack, _ = _ready_release_pack(active, reserve)

    manifest = build_managed_sleeve_set_manifest(pack)
    rendered = managed_sleeve_set_manifest_to_dict(manifest)
    restored = managed_sleeve_set_manifest_from_dict(rendered)

    assert restored == manifest
    assert manifest.active_sleeves == ("z-active",)
    assert manifest.admitted_unallocated_sleeves == ("a-reserve",)
    assert [item["sleeve_id"] for item in rendered["next_actions"]] == ["a-reserve", "z-active"]
    assert (
        manifest.operator_summary
        == "dry_run_status=ready_for_paper_dry_run; active=1; admitted_unallocated=1; blocked=0"
    )


def test_managed_manifest_old_payload_degrades_without_effective_allocations() -> None:
    manifest = managed_sleeve_set_manifest_from_dict(
        {
            "source_release_pack_status": "ready_for_paper_managed_set",
            "active_sleeves": ["legacy-active"],
        }
    )

    assert manifest.dry_run_status == ManagedSleeveSetDryRunStatus.EMPTY
    assert manifest.active_sleeves == ()
    assert manifest.source_evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_MISSING
    assert "no_admission_candidates" in manifest.activation_blockers


def test_managed_manifest_malformed_load_fails_closed(tmp_path) -> None:
    pack, _ = _ready_release_pack(_sleeve("active", effective_allocation=0.25, target_allocation=0.25))
    manifest = build_managed_sleeve_set_manifest(pack)
    payload = managed_sleeve_set_manifest_to_dict(manifest)
    payload["dry_run_status"] = "blocked"

    with pytest.raises(SleeveAdmissionCorruptError):
        managed_sleeve_set_manifest_from_dict(payload)

    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    export_managed_sleeve_set_manifest(manifest=manifest, evidence_store=store)
    assert load_managed_sleeve_set_manifest(evidence_store=store) == manifest

    store.save_snapshot("crypto_managed_sleeve_set_manifest", ["bad"])
    with pytest.raises(SleeveAdmissionCorruptError):
        load_managed_sleeve_set_manifest(evidence_store=store)


def test_service_orchestrator_managed_manifest_helpers_and_operator_status(tmp_path) -> None:
    fixed_review_ns = _T0_NS + 321
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    sleeve = _sleeve("svc-active", effective_allocation=0.20, target_allocation=0.20)
    portfolio = _built_portfolio(sleeve)
    pack, _ = _ready_release_pack(sleeve)
    orch = ServiceOrchestrator(
        service=_mock_service(),
        sleeves=(sleeve,),
        evidence_store=store,
        readiness_level="paper_live",
        sleeve_workflow_clock_ns=lambda: fixed_review_ns,
    )
    orch._last_campaign_report = _campaign_report(sleeve_ids=("svc-active",))  # type: ignore[attr-defined]
    orch.start_sleeve_promotion_review(workflow_snapshot=_supported_workflow("svc-active"))

    manifest = orch.managed_sleeve_set_manifest(release_pack=pack, portfolio_snapshot=portfolio)
    rendered = orch.managed_sleeve_set_manifest_dict()
    operator = operator_snapshot_to_dict(orch.operator_snapshot())

    assert manifest.dry_run_status == ManagedSleeveSetDryRunStatus.READY_FOR_PAPER_DRY_RUN
    assert rendered["dry_run_status"] in {"ready_for_paper_dry_run", "partial_paper_dry_run", "inconclusive"}
    assert operator["managed_sleeve_manifest"]["available"] is True
    assert "dry_run_status" in operator["managed_sleeve_manifest"]

    orch.export_managed_sleeve_set_manifest()
    assert orch.load_managed_sleeve_set_manifest() == orch.managed_sleeve_set_manifest()


def test_managed_manifest_deterministic_replay() -> None:
    pack, _ = _ready_release_pack(_sleeve("stable", effective_allocation=0.15, target_allocation=0.15))

    first = managed_sleeve_set_manifest_to_dict(build_managed_sleeve_set_manifest(pack))
    second = managed_sleeve_set_manifest_to_dict(build_managed_sleeve_set_manifest(pack))

    assert first == second
    assert first["source_release_pack_hash"] == second["source_release_pack_hash"]


def test_paper_shadow_activation_plan_model_construction_and_ready_status() -> None:
    active = _sleeve("active", effective_allocation=0.25, target_allocation=0.25)
    pack, _ = _ready_release_pack(active)
    manifest = build_managed_sleeve_set_manifest(pack)

    plan = build_paper_shadow_activation_plan(manifest)
    rendered = paper_shadow_activation_plan_to_dict(plan)

    assert plan.activation_status == PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW
    assert plan.source_manifest_status == ManagedSleeveSetDryRunStatus.READY_FOR_PAPER_DRY_RUN
    assert plan.paper_only is True
    assert plan.real_orders_enabled is False
    assert plan.real_money_enabled is False
    assert plan.active_sleeves == ("active",)
    assert plan.inactive_sleeves == ()
    assert rendered["effective_allocations"] == [{"sleeve_id": "active", "effective_allocation": 0.25}]
    assert "paper_only_mode_confirmed" in plan.preflight_gates
    assert "record_paper_shadow_artifacts" in plan.runtime_monitoring_requirements
    assert "operator_can_disable_sleeve" in plan.kill_switch_requirements
    assert plan.source_manifest_hash
    assert plan.plan_id.startswith("paper-shadow-activation-plan-")


def test_paper_shadow_activation_plan_empty_manifest_is_empty_safe() -> None:
    manifest = build_managed_sleeve_set_manifest(
        build_sleeve_admission_release_pack(SleeveAdmissionController().snapshot())
    )

    plan = build_paper_shadow_activation_plan(manifest)

    assert plan.activation_status == PaperShadowActivationStatus.EMPTY
    assert plan.active_sleeves == ()
    assert plan.effective_allocations == ()
    assert "source_manifest_empty" in plan.activation_blockers
    assert plan.paper_only is True
    assert plan.real_orders_enabled is False
    assert plan.real_money_enabled is False


def test_paper_shadow_activation_plan_partial_manifest_is_not_ready() -> None:
    portfolio = _portfolio(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    review_summary = _review_summary(_review_result("active"))
    admission = SleeveAdmissionController(review_summary, portfolio_snapshot=portfolio).snapshot()
    pack = build_sleeve_admission_release_pack(
        admission,
        promotion_review_snapshot=_promotion_snapshot(review_summary),
        portfolio_snapshot=portfolio,
    )
    manifest = build_managed_sleeve_set_manifest(pack)

    plan = build_paper_shadow_activation_plan(manifest)

    assert manifest.dry_run_status == ManagedSleeveSetDryRunStatus.PARTIAL_PAPER_DRY_RUN
    assert plan.activation_status == PaperShadowActivationStatus.PARTIAL_READY
    assert "source_manifest_not_ready_for_paper_shadow" in plan.activation_blockers
    assert "release_pack_evidence_not_ready" in plan.activation_blockers


def test_paper_shadow_activation_plan_blocked_manifest_is_blocked() -> None:
    blocked = _sleeve(
        "blocked",
        status=CryptoSleeveStatus.BLOCKED,
        recommendation_status=SleeveRecommendationStatus.BLOCKED,
        qualification_status=SleeveQualificationStatus.BLOCKED,
        campaign_status=SleeveCampaignEvidenceStatus.BLOCKED_BY_GOVERNANCE,
        support_status=SleevePromotionSupportStatus.BLOCKED,
        candidate_status=SleevePromotionCandidateStatus.BLOCKED,
        decision_status=SleeveDecisionPackStatus.BLOCKED,
        effective_allocation=0.0,
        target_allocation=0.0,
        blockers=("governance_block",),
    )
    review_summary = _review_summary(_review_result("blocked", SleevePromotionReviewVerdict.REJECT))
    report = _campaign_report(sleeve_ids=("blocked",))
    admission = SleeveAdmissionController(review_summary, portfolio_snapshot=_portfolio(blocked)).snapshot()
    pack = build_sleeve_admission_release_pack(
        admission,
        promotion_review_snapshot=_promotion_snapshot(review_summary),
        portfolio_snapshot=_portfolio(blocked),
        campaign_report=report,
        readiness_flags=campaign_readiness_flags(report),
    )
    manifest = build_managed_sleeve_set_manifest(pack)

    plan = build_paper_shadow_activation_plan(manifest)

    assert plan.activation_status == PaperShadowActivationStatus.BLOCKED
    assert plan.active_sleeves == ()
    assert "blocked" in plan.inactive_sleeves
    assert "governance_blockers_present" in plan.activation_blockers


def test_paper_shadow_activation_plan_tracks_unallocated_and_allocations() -> None:
    active = _sleeve("z-active", effective_allocation=0.10, target_allocation=0.10)
    reserve = _sleeve(
        "a-reserve",
        status=CryptoSleeveStatus.ENABLED,
        recommendation_status=SleeveRecommendationStatus.ELIGIBLE_BUT_NOT_SELECTED,
        decision_status=SleeveDecisionPackStatus.ELIGIBLE_BUT_NOT_SELECTED,
        effective_allocation=0.0,
        target_allocation=0.0,
    )
    pack, _ = _ready_release_pack(active, reserve)
    manifest = build_managed_sleeve_set_manifest(pack)

    plan = build_paper_shadow_activation_plan(manifest)

    assert plan.activation_status == PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW
    assert plan.active_sleeves == ("z-active",)
    assert plan.inactive_sleeves == ("a-reserve",)
    assert plan.admitted_unallocated_sleeves == ("a-reserve",)
    assert plan.effective_allocations[0].sleeve_id == "z-active"
    assert plan.effective_allocations[0].effective_allocation == 0.10
    assert [action.sleeve_id for action in plan.next_actions] == ["a-reserve", "z-active"]


def test_paper_shadow_activation_plan_serialization_roundtrip_and_malformed_load(tmp_path) -> None:
    pack, _ = _ready_release_pack(_sleeve("active", effective_allocation=0.25, target_allocation=0.25))
    manifest = build_managed_sleeve_set_manifest(pack)
    plan = build_paper_shadow_activation_plan(manifest)
    payload = paper_shadow_activation_plan_to_dict(plan)

    restored = paper_shadow_activation_plan_from_dict(payload)
    assert restored == plan

    malformed = dict(payload)
    malformed["real_orders_enabled"] = True
    with pytest.raises(SleeveAdmissionCorruptError):
        paper_shadow_activation_plan_from_dict(malformed)

    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    export_paper_shadow_activation_plan(plan=plan, evidence_store=store)
    assert load_paper_shadow_activation_plan(evidence_store=store) == plan

    store.save_snapshot("crypto_paper_shadow_activation_plan", ["bad"])
    with pytest.raises(SleeveAdmissionCorruptError):
        load_paper_shadow_activation_plan(evidence_store=store)


def test_service_orchestrator_paper_shadow_activation_plan_helpers_and_operator_status(tmp_path) -> None:
    fixed_review_ns = _T0_NS + 654
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    sleeve = _sleeve("svc-active", effective_allocation=0.20, target_allocation=0.20)
    pack, _ = _ready_release_pack(sleeve)
    manifest = build_managed_sleeve_set_manifest(pack)
    orch = ServiceOrchestrator(
        service=_mock_service(),
        sleeves=(sleeve,),
        evidence_store=store,
        readiness_level="paper_live",
        sleeve_workflow_clock_ns=lambda: fixed_review_ns,
    )
    orch._last_campaign_report = _campaign_report(sleeve_ids=("svc-active",))  # type: ignore[attr-defined]
    orch.start_sleeve_promotion_review(workflow_snapshot=_supported_workflow("svc-active"))

    plan = orch.paper_shadow_activation_plan(manifest=manifest)
    rendered = paper_shadow_activation_plan_to_dict(plan)
    helper_rendered = orch.paper_shadow_activation_plan_dict()
    operator = operator_snapshot_to_dict(orch.operator_snapshot())

    assert plan.activation_status == PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW
    assert rendered["paper_only"] is True
    assert rendered["real_orders_enabled"] is False
    assert rendered["real_money_enabled"] is False
    assert "activation_status" in helper_rendered
    assert operator["paper_shadow_activation_plan"]["available"] is True
    assert operator["paper_shadow_activation_plan"]["real_orders_enabled"] is False
    assert operator["paper_shadow_activation_plan"]["real_money_enabled"] is False

    orch.export_paper_shadow_activation_plan()
    assert orch.load_paper_shadow_activation_plan() == orch.paper_shadow_activation_plan()


def test_paper_shadow_activation_plan_deterministic_replay() -> None:
    pack, _ = _ready_release_pack(_sleeve("stable", effective_allocation=0.15, target_allocation=0.15))
    manifest = build_managed_sleeve_set_manifest(pack)

    first = paper_shadow_activation_plan_to_dict(build_paper_shadow_activation_plan(manifest))
    second = paper_shadow_activation_plan_to_dict(build_paper_shadow_activation_plan(manifest))

    assert first == second
    assert first["source_manifest_hash"] == second["source_manifest_hash"]


def test_paper_shadow_session_controller_lifecycle_happy_path() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 1, _T0_NS + 2, _T0_NS + 3, _T0_NS + 4, _T0_NS + 5))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))

    prepared = controller.prepare(plan)
    running = controller.start()
    ticked = controller.record_market_event_batch(build_market_event_batch((_market_event(),)))
    stopped = controller.stop()
    finalized = controller.finalize()
    rendered = paper_shadow_session_snapshot_to_dict(finalized)

    assert prepared.status == PaperShadowSessionStatus.READY
    assert running.status == PaperShadowSessionStatus.RUNNING
    assert ticked.tick_count == 1
    assert ticked.guardrail.primary_action == GuardrailAction.NONE
    assert stopped.status == PaperShadowSessionStatus.STOPPED
    assert finalized.status == PaperShadowSessionStatus.FINALIZED
    assert finalized.started_at_ns == _T0_NS + 2
    assert finalized.stopped_at_ns == _T0_NS + 4
    assert finalized.finalized_at_ns == _T0_NS + 5
    assert rendered["paper_only"] is True
    assert rendered["real_orders_enabled"] is False
    assert rendered["real_money_enabled"] is False


def test_paper_shadow_session_blocked_plan_cannot_start() -> None:
    manifest = build_managed_sleeve_set_manifest(
        build_sleeve_admission_release_pack(SleeveAdmissionController().snapshot())
    )
    plan = build_paper_shadow_activation_plan(manifest)
    controller = PaperShadowSessionController(clock_ns=lambda: _T0_NS + 10)

    prepared = controller.prepare(plan)

    assert prepared.status == PaperShadowSessionStatus.BLOCKED
    assert "source_manifest_empty" in prepared.blockers_seen
    with pytest.raises(PaperShadowSessionCorruptError):
        controller.start()


def test_paper_shadow_session_tick_and_finalize_fail_closed_before_valid_state() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    controller = PaperShadowSessionController(clock_ns=lambda: _T0_NS + 20)

    controller.prepare(plan)

    with pytest.raises(PaperShadowSessionCorruptError):
        controller.record_tick(active_sleeves_seen=("active",))
    with pytest.raises(PaperShadowSessionCorruptError):
        controller.finalize()

    running = controller.start()
    with pytest.raises(PaperShadowSessionCorruptError):
        controller.record_tick(active_sleeves_seen=("not-admitted",))
    assert controller.snapshot() == running


def test_paper_shadow_session_deterministic_fixed_clock_replay() -> None:
    plan = _ready_activation_plan(_sleeve("stable", effective_allocation=0.15, target_allocation=0.15))

    def run_once() -> dict:
        times = iter((_T0_NS + 1, _T0_NS + 2, _T0_NS + 3, _T0_NS + 4, _T0_NS + 5))
        controller = PaperShadowSessionController(clock_ns=lambda: next(times))
        controller.prepare(plan)
        controller.start()
        controller.record_market_event_batch(build_market_event_batch((_market_event("BTCUSDT", ts_ns=_T0_NS + 101),)))
        controller.stop()
        return paper_shadow_session_snapshot_to_dict(controller.finalize())

    assert run_once() == run_once()


def test_paper_shadow_session_restore_roundtrip_and_malformed_fail_closed(tmp_path) -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 1, _T0_NS + 2, _T0_NS + 3, _T0_NS + 4, _T0_NS + 5))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))
    controller.prepare(plan)
    controller.start()
    controller.record_market_event_batch(build_market_event_batch((_market_event(),)))
    controller.stop()
    snapshot = controller.finalize()
    payload = paper_shadow_session_snapshot_to_dict(snapshot)

    restored = paper_shadow_session_snapshot_from_dict(payload)
    assert restored == snapshot

    legacy = paper_shadow_session_snapshot_from_dict({"session_id": "legacy-session", "status": "created"})
    assert legacy.status == PaperShadowSessionStatus.CREATED
    assert legacy.paper_only is True
    assert legacy.real_orders_enabled is False
    assert legacy.real_money_enabled is False

    malformed = dict(payload)
    malformed["real_money_enabled"] = True
    with pytest.raises(PaperShadowSessionCorruptError):
        paper_shadow_session_snapshot_from_dict(malformed)

    malformed_guardrail = dict(payload)
    malformed_guardrail["guardrail"] = {
        **payload["guardrail"],
        "primary_action": "warn",
        "actions": ["warn"],
        "reason_codes": ["no_market_events"],
        "block_finalize": False,
    }
    with pytest.raises(PaperShadowSessionCorruptError):
        paper_shadow_session_snapshot_from_dict(malformed_guardrail)

    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    export_paper_shadow_session_snapshot(snapshot=snapshot, evidence_store=store)
    assert load_paper_shadow_session_snapshot(evidence_store=store) == snapshot

    store.save_snapshot("crypto_paper_shadow_session", ["bad"])
    with pytest.raises(PaperShadowSessionCorruptError):
        load_paper_shadow_session_snapshot(evidence_store=store)


def test_paper_shadow_market_event_batch_valid_updates_session_counters() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 1, _T0_NS + 2, _T0_NS + 3, _T0_NS + 4))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))
    controller.prepare(plan)
    controller.start()
    batch = build_market_event_batch(
        (
            _market_event("ETHUSDT", venue="bybit", ts_ns=_T0_NS + 102, price=2100.0),
            _market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101, mark_price=100.0, price=None),
        ),
        batch_id="batch-valid",
    )

    snapshot = controller.record_market_event_batch(batch)
    rendered = paper_shadow_session_snapshot_to_dict(snapshot)

    assert snapshot.tick_count == 1
    assert snapshot.event_count == 2
    assert snapshot.symbols_seen == ("BTCUSDT", "ETHUSDT")
    assert snapshot.venues_seen == ("binance", "bybit")
    assert snapshot.first_event_ns == _T0_NS + 101
    assert snapshot.last_event_ns == _T0_NS + 102
    assert snapshot.rejected_event_count == 0
    assert snapshot.runtime_monitor.status == RuntimeMonitorStatus.HEALTHY
    assert snapshot.runtime_monitor.stale_feed_detected is False
    assert snapshot.runtime_monitor.symbol_coverage_ok is True
    assert snapshot.runtime_monitor.venue_coverage_ok is True
    assert snapshot.runtime_monitor.price_validity_ok is True
    assert rendered["runtime_monitor"]["status"] == "healthy"
    assert rendered["market_event_cursors"] == [
        {"symbol": "BTCUSDT", "venue": "binance", "last_event_ns": _T0_NS + 101},
        {"symbol": "ETHUSDT", "venue": "bybit", "last_event_ns": _T0_NS + 102},
    ]


def test_paper_shadow_runtime_monitor_zero_events_not_healthy() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    controller = PaperShadowSessionController(clock_ns=lambda: _T0_NS + 1)

    snapshot = controller.prepare(plan)
    rendered = paper_shadow_session_snapshot_to_dict(snapshot)

    assert snapshot.runtime_monitor.status == RuntimeMonitorStatus.NOT_READY
    assert snapshot.runtime_monitor.event_count == 0
    assert snapshot.runtime_monitor.symbol_coverage_ok is False
    assert snapshot.runtime_monitor.venue_coverage_ok is False
    assert snapshot.runtime_monitor.price_validity_ok is False
    assert "no_market_events" in snapshot.runtime_monitor.reason_codes
    assert rendered["runtime_monitor"]["status"] == "not_ready"
    assert snapshot.guardrail.primary_action == GuardrailAction.BLOCK_FINALIZE
    assert GuardrailAction.WARN in snapshot.guardrail.actions
    assert snapshot.guardrail.block_finalize is True
    assert "no_market_events" in snapshot.guardrail.reason_codes
    with pytest.raises(PaperShadowSessionCorruptError):
        controller.finalize()


def test_paper_shadow_runtime_monitor_missing_coverage_degraded() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 1, _T0_NS + 2, _T0_NS + 3))
    controller = PaperShadowSessionController(
        clock_ns=lambda: next(times),
        required_market_symbols=("BTCUSDT", "ETHUSDT"),
        required_market_venues=("binance", "bybit"),
    )
    controller.prepare(plan)
    controller.start()
    batch = build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101),))

    snapshot = controller.record_market_event_batch(batch)

    assert snapshot.runtime_monitor.status == RuntimeMonitorStatus.DEGRADED
    assert snapshot.runtime_monitor.symbol_coverage_ok is False
    assert snapshot.runtime_monitor.venue_coverage_ok is False
    assert "missing_symbol_coverage" in snapshot.runtime_monitor.reason_codes
    assert "missing_venue_coverage" in snapshot.runtime_monitor.reason_codes
    assert snapshot.guardrail.primary_action == GuardrailAction.PAUSE_SESSION
    assert GuardrailAction.BLOCK_FINALIZE in snapshot.guardrail.actions
    assert "missing_symbol_coverage" in snapshot.guardrail.reason_codes


def test_paper_shadow_runtime_monitor_stale_event_gap_degraded() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 1, _T0_NS + 2, _T0_NS + 3, _T0_NS + 4))
    controller = PaperShadowSessionController(
        clock_ns=lambda: next(times),
        max_market_event_gap_ns=5,
    )
    controller.prepare(plan)
    controller.start()
    batch = build_market_event_batch(
        (
            _market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101, price=100.0),
            _market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 110, price=101.0),
        ),
        batch_id="stale-gap",
    )

    snapshot = controller.record_market_event_batch(batch)

    assert snapshot.runtime_monitor.status == RuntimeMonitorStatus.DEGRADED
    assert snapshot.runtime_monitor.stale_feed_detected is True
    assert snapshot.runtime_monitor.event_gap_count == 1
    assert "stale_feed_detected" in snapshot.runtime_monitor.reason_codes
    assert snapshot.guardrail.primary_action == GuardrailAction.PAUSE_SESSION
    assert snapshot.guardrail.should_pause_session is True

    applied = controller.apply_guardrails()
    assert applied.status == PaperShadowSessionStatus.BLOCKED
    assert "stale_feed_detected" in applied.blockers_seen


def test_paper_shadow_market_event_malformed_price_rejected_fail_closed() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 1, _T0_NS + 2))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))
    controller.prepare(plan)
    controller.start()
    batch = MarketEventBatch(
        batch_id="bad-price",
        events=(_market_event(price=-1.0),),
    )

    with pytest.raises(PaperShadowSessionCorruptError):
        controller.record_market_event_batch(batch)

    snapshot = controller.snapshot()
    assert snapshot.event_count == 0
    assert snapshot.tick_count == 0
    assert snapshot.rejected_event_count == 1
    assert snapshot.runtime_monitor.status == RuntimeMonitorStatus.NOT_READY
    assert snapshot.runtime_monitor.event_count == 0
    assert snapshot.guardrail.primary_action == GuardrailAction.PAUSE_SESSION
    assert "rejected_market_events" in snapshot.guardrail.reason_codes
    assert snapshot.real_orders_enabled is False
    assert snapshot.real_money_enabled is False


def test_paper_shadow_guardrail_healthy_monitor_none_action() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 1, _T0_NS + 2, _T0_NS + 3))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))
    controller.prepare(plan)
    controller.start()

    snapshot = controller.record_market_event_batch(
        build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101),))
    )

    assert snapshot.runtime_monitor.status == RuntimeMonitorStatus.HEALTHY
    assert snapshot.guardrail.primary_action == GuardrailAction.NONE
    assert snapshot.guardrail.actions == (GuardrailAction.NONE,)
    assert snapshot.guardrail.block_finalize is False


def test_paper_shadow_guardrail_unsafe_flags_hard_stop_block() -> None:
    monitor = runtime_monitor_snapshot_from_dict(
        {
            "status": "healthy",
            "event_count": 1,
            "stale_feed_detected": False,
            "symbol_coverage_ok": True,
            "venue_coverage_ok": True,
            "price_validity_ok": True,
            "event_gap_count": 0,
            "last_event_ns": _T0_NS + 101,
            "monitored_symbols": ["BTCUSDT"],
            "monitored_venues": ["binance"],
            "reason_codes": [],
        }
    )

    guardrail = build_guardrail_snapshot(
        monitor,
        session_status=PaperShadowSessionStatus.RUNNING,
        paper_only=False,
        real_orders_enabled=True,
        real_money_enabled=True,
    )

    assert guardrail.primary_action == GuardrailAction.STOP_SESSION
    assert guardrail.should_stop_session is True
    assert guardrail.block_finalize is True
    assert "unsafe_real_trading_flags" in guardrail.reason_codes


def test_paper_shadow_market_event_non_monotonic_batch_rejected() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 1, _T0_NS + 2))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))
    controller.prepare(plan)
    controller.start()
    batch = MarketEventBatch(
        batch_id="non-monotonic",
        events=(
            _market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 102),
            _market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101),
        ),
    )

    with pytest.raises(PaperShadowSessionCorruptError):
        controller.tick_from_market_events(batch)

    assert controller.snapshot().event_count == 0
    assert controller.snapshot().rejected_event_count == 2


def test_paper_shadow_market_event_batch_ordering_and_serialization_roundtrip(tmp_path) -> None:
    batch = build_market_event_batch(
        (
            _market_event("ETHUSDT", venue="bybit", ts_ns=_T0_NS + 102, price=2100.0),
            _market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101, price=100.0),
        ),
        batch_id="stable-order",
    )
    payload = market_event_batch_to_dict(batch)

    assert [event["symbol"] for event in payload["events"]] == ["BTCUSDT", "ETHUSDT"]
    assert market_event_batch_from_dict(payload) == batch
    assert market_event_batch_to_dict(market_event_batch_from_dict(payload)) == payload

    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    export_paper_shadow_market_event_batch(batch=batch, evidence_store=store)
    assert load_paper_shadow_market_event_batch(evidence_store=store) == batch

    store.save_snapshot("crypto_paper_shadow_market_event_batch", ["bad"])
    with pytest.raises(PaperShadowSessionCorruptError):
        load_paper_shadow_market_event_batch(evidence_store=store)


def test_paper_shadow_runtime_monitor_serialization_roundtrip() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 1, _T0_NS + 2, _T0_NS + 3))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))
    controller.prepare(plan)
    controller.start()
    snapshot = controller.record_market_event_batch(
        build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101),))
    )
    payload = runtime_monitor_snapshot_to_dict(snapshot.runtime_monitor)
    guardrail_payload = guardrail_snapshot_to_dict(snapshot.guardrail)

    restored_monitor = runtime_monitor_snapshot_from_dict(payload)
    restored_guardrail = guardrail_snapshot_from_dict(guardrail_payload)
    restored_session = paper_shadow_session_snapshot_from_dict(paper_shadow_session_snapshot_to_dict(snapshot))

    assert restored_monitor == snapshot.runtime_monitor
    assert restored_guardrail == snapshot.guardrail
    assert restored_session.runtime_monitor == snapshot.runtime_monitor
    assert restored_session.guardrail == snapshot.guardrail


def test_paper_shadow_market_event_tick_before_start_fails_closed() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    controller = PaperShadowSessionController(clock_ns=lambda: _T0_NS + 1)
    controller.prepare(plan)
    batch = build_market_event_batch((_market_event(),), batch_id="too-early")

    with pytest.raises(PaperShadowSessionCorruptError):
        controller.record_market_event_batch(batch)

    snapshot = controller.snapshot()
    assert snapshot.tick_count == 0
    assert snapshot.event_count == 0
    assert snapshot.rejected_event_count == 0


def test_paper_shadow_market_event_deterministic_replay() -> None:
    plan = _ready_activation_plan(_sleeve("stable", effective_allocation=0.15, target_allocation=0.15))
    batch = build_market_event_batch(
        (
            _market_event("ETHUSDT", venue="bybit", ts_ns=_T0_NS + 102, price=2100.0),
            _market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101, price=100.0),
        ),
        batch_id="deterministic",
    )

    def run_once() -> dict:
        times = iter((_T0_NS + 1, _T0_NS + 2, _T0_NS + 3))
        controller = PaperShadowSessionController(clock_ns=lambda: next(times))
        controller.prepare(plan)
        controller.start()
        return paper_shadow_session_snapshot_to_dict(controller.record_market_event_batch(batch))

    assert run_once() == run_once()


def test_paper_shadow_feed_replay_valid_batches_update_session_monitor_and_guardrail() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 1, _T0_NS + 2, _T0_NS + 3, _T0_NS + 4))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))
    controller.prepare(plan)
    controller.start()
    replay = build_feed_replay_plan(
        (
            build_market_event_batch(
                (_market_event("ETHUSDT", venue="bybit", ts_ns=_T0_NS + 102, price=2100.0),),
                batch_id="replay-2",
            ),
            build_market_event_batch(
                (_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101, price=100.0),),
                batch_id="replay-1",
            ),
        ),
        replay_id="feed-replay-valid",
    )

    result = controller.replay_feed(replay)
    snapshot = controller.snapshot()

    assert result.batches_planned == 2
    assert result.batches_replayed == 2
    assert result.events_replayed == 2
    assert result.batches_rejected == 0
    assert result.first_event_ns == _T0_NS + 101
    assert result.last_event_ns == _T0_NS + 102
    assert result.guardrail_actions_seen == (GuardrailAction.NONE,)
    assert result.session_status == PaperShadowSessionStatus.RUNNING
    assert snapshot.event_count == 2
    assert snapshot.runtime_monitor.status == RuntimeMonitorStatus.HEALTHY
    assert snapshot.guardrail.primary_action == GuardrailAction.NONE


def test_paper_shadow_feed_replay_before_start_fails_closed() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    controller = PaperShadowSessionController(clock_ns=lambda: _T0_NS + 1)
    controller.prepare(plan)
    replay = build_feed_replay_plan((build_market_event_batch((_market_event(),)),), replay_id="too-early")

    with pytest.raises(PaperShadowSessionCorruptError):
        controller.replay_feed(replay)

    assert controller.snapshot().event_count == 0
    assert controller.snapshot().tick_count == 0


def test_paper_shadow_feed_replay_malformed_batch_rejected_and_halted() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 1, _T0_NS + 2, _T0_NS + 3))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))
    controller.prepare(plan)
    controller.start()
    replay = FeedReplayPlan(
        replay_id="feed-replay-bad",
        batches=(
            MarketEventBatch(
                batch_id="bad-price",
                events=(_market_event(price=-1.0),),
            ),
        ),
    )

    result = controller.replay_feed(replay)
    snapshot = controller.snapshot()

    assert result.batches_replayed == 0
    assert result.events_replayed == 0
    assert result.batches_rejected == 1
    assert result.rejected_batch_ids == ("bad-price",)
    assert result.halted_by_guardrail is True
    assert result.halt_reason == GuardrailAction.PAUSE_SESSION.value
    assert result.session_status == PaperShadowSessionStatus.BLOCKED
    assert GuardrailAction.PAUSE_SESSION in result.guardrail_actions_seen
    assert snapshot.rejected_event_count == 1
    assert snapshot.event_count == 0


def test_paper_shadow_feed_replay_guardrail_pause_halts_later_batches() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 1, _T0_NS + 2, _T0_NS + 3, _T0_NS + 4))
    controller = PaperShadowSessionController(
        clock_ns=lambda: next(times),
        required_market_symbols=("BTCUSDT", "ETHUSDT"),
    )
    controller.prepare(plan)
    controller.start()
    replay = build_feed_replay_plan(
        (
            build_market_event_batch(
                (_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101),),
                batch_id="coverage-missing",
            ),
            build_market_event_batch(
                (_market_event("ETHUSDT", venue="binance", ts_ns=_T0_NS + 102),),
                batch_id="not-replayed",
            ),
        ),
        replay_id="feed-replay-pause",
    )

    result = controller.replay_feed(replay)
    snapshot = controller.snapshot()

    assert result.batches_planned == 2
    assert result.batches_replayed == 1
    assert result.events_replayed == 1
    assert result.halted_by_guardrail is True
    assert result.halt_reason == GuardrailAction.PAUSE_SESSION.value
    assert result.session_status == PaperShadowSessionStatus.BLOCKED
    assert GuardrailAction.PAUSE_SESSION in result.guardrail_actions_seen
    assert snapshot.event_count == 1
    assert "missing_symbol_coverage" in snapshot.blockers_seen


def test_paper_shadow_feed_replay_deterministic_fixed_input() -> None:
    plan = _ready_activation_plan(_sleeve("stable", effective_allocation=0.15, target_allocation=0.15))
    replay = build_feed_replay_plan(
        (
            build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101),)),
            build_market_event_batch((_market_event("ETHUSDT", venue="bybit", ts_ns=_T0_NS + 102),)),
        ),
        replay_id="feed-replay-deterministic",
    )

    def run_once() -> tuple[dict, dict]:
        times = iter((_T0_NS + 1, _T0_NS + 2, _T0_NS + 3, _T0_NS + 4))
        controller = PaperShadowSessionController(clock_ns=lambda: next(times))
        controller.prepare(plan)
        controller.start()
        result = controller.replay_feed(replay)
        return feed_replay_result_to_dict(result), paper_shadow_session_snapshot_to_dict(controller.snapshot())

    assert run_once() == run_once()


def test_paper_shadow_feed_replay_serialization_and_export_roundtrip(tmp_path) -> None:
    replay = build_feed_replay_plan(
        (build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101),)),),
        replay_id="feed-replay-roundtrip",
    )
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 1, _T0_NS + 2, _T0_NS + 3))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))
    controller.prepare(plan)
    controller.start()
    result = controller.replay_feed(replay)
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())

    assert feed_replay_plan_from_dict(feed_replay_plan_to_dict(replay)) == replay
    assert feed_replay_result_from_dict(feed_replay_result_to_dict(result)) == result

    export_paper_shadow_feed_replay_plan(plan=replay, evidence_store=store)
    export_paper_shadow_feed_replay_result(result=result, evidence_store=store)
    assert load_paper_shadow_feed_replay_plan(evidence_store=store) == replay
    assert load_paper_shadow_feed_replay_result(evidence_store=store) == result

    store.save_snapshot("crypto_paper_shadow_feed_replay_result", ["bad"])
    with pytest.raises(PaperShadowSessionCorruptError):
        load_paper_shadow_feed_replay_result(evidence_store=store)


def test_paper_data_source_valid_local_payload_to_market_event_batch() -> None:
    result = build_paper_data_source_batch_result(
        _paper_data_source_payload(),
        allowed_source_ids=("local-feed",),
    )
    batch = paper_data_source_payload_to_market_event_batch(
        _paper_data_source_payload(),
        allowed_source_ids=("local-feed",),
    )
    rendered = paper_data_source_batch_result_to_dict(result)

    assert result.source.source_id == "local-feed"
    assert result.source.source_type == PaperDataSourceType.LOCAL_PAYLOAD
    assert result.source.symbols == ("BTCUSDT", "ETHUSDT")
    assert result.source.venue == "binance"
    assert result.source.events_produced == 2
    assert result.source.batches_produced == 1
    assert result.source.rejected_records == 0
    assert [event.symbol for event in result.batch.events] == ["BTCUSDT", "ETHUSDT"]
    assert batch == result.batch
    assert rendered["source"]["events_produced"] == 2
    assert rendered["batch"]["events"][0]["symbol"] == "BTCUSDT"


def test_paper_data_source_unknown_source_rejected_unless_explicitly_allowed() -> None:
    payload = _paper_data_source_payload(source_id="unregistered-local")

    with pytest.raises(PaperShadowSessionCorruptError):
        build_paper_data_source_batch_result(payload)

    result = build_paper_data_source_batch_result(payload, allow_unknown_source=True)
    assert result.source.source_id == "unregistered-local"


def test_paper_data_source_malformed_payload_rejected_fail_closed() -> None:
    bad_price = _paper_data_source_payload(
        records=(
            {
                "symbol": "BTCUSDT",
                "ts_ns": _T0_NS + 101,
                "event_type": "mark_price",
                "price": -1.0,
            },
        ),
        symbols=("BTCUSDT",),
    )
    with pytest.raises(PaperShadowSessionCorruptError):
        build_paper_data_source_batch_result(bad_price, allowed_source_ids=("local-feed",))

    future_record = _paper_data_source_payload(
        records=(
            {
                "symbol": "BTCUSDT",
                "ts_ns": _T0_NS + 301,
                "event_type": "mark_price",
                "price": 100.0,
            },
        ),
        symbols=("BTCUSDT",),
        as_of_ns=_T0_NS + 200,
    )
    with pytest.raises(PaperShadowSessionCorruptError):
        build_paper_data_source_batch_result(future_record, allowed_source_ids=("local-feed",))

    client_payload = {
        **_paper_data_source_payload(
            symbols=("BTCUSDT",),
            records=({"symbol": "BTCUSDT", "ts_ns": _T0_NS + 101, "event_type": "mark_price", "price": 100.0},),
        ),
        "client": object(),
    }
    with pytest.raises(PaperShadowSessionCorruptError):
        build_paper_data_source_batch_result(client_payload, allowed_source_ids=("local-feed",))

    network_type = _paper_data_source_payload(source_type="network_client")
    with pytest.raises(PaperShadowSessionCorruptError):
        build_paper_data_source_batch_result(network_type, allowed_source_ids=("local-feed",))


def test_paper_data_source_stable_ordering_serialization_and_export(tmp_path) -> None:
    result = build_paper_data_source_batch_result(
        _paper_data_source_payload(),
        allowed_source_ids=("local-feed",),
        batch_id="paper-source-roundtrip",
    )
    payload = paper_data_source_batch_result_to_dict(result)
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())

    restored = paper_data_source_batch_result_from_dict(payload)
    assert restored == result
    assert [event["symbol"] for event in payload["batch"]["events"]] == ["BTCUSDT", "ETHUSDT"]

    export_paper_data_source_batch_result(result=result, evidence_store=store)
    assert load_paper_data_source_batch_result(evidence_store=store) == result

    store.save_snapshot("crypto_paper_data_source_batch_result", ["bad"])
    with pytest.raises(PaperShadowSessionCorruptError):
        load_paper_data_source_batch_result(evidence_store=store)


def test_paper_data_source_replay_integration_updates_session() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 1, _T0_NS + 2, _T0_NS + 3))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))
    controller.prepare(plan)
    controller.start()
    result = build_paper_data_source_batch_result(
        _paper_data_source_payload(
            symbols=("BTCUSDT",),
            records=({"symbol": "BTCUSDT", "ts_ns": _T0_NS + 101, "event_type": "mark_price", "price": 100.0},),
        ),
        allowed_source_ids=("local-feed",),
    )

    replay = controller.replay_feed(build_feed_replay_plan((result.batch,), replay_id="data-source-replay"))
    snapshot = controller.snapshot()

    assert replay.events_replayed == 1
    assert replay.guardrail_actions_seen == (GuardrailAction.NONE,)
    assert snapshot.event_count == 1
    assert snapshot.runtime_monitor.status == RuntimeMonitorStatus.HEALTHY


def test_paper_shadow_run_evidence_report_valid_full_local_run_passes() -> None:
    source_result, replay, snapshot, report = _paper_shadow_full_local_run()
    rendered = paper_shadow_run_evidence_report_to_dict(report)

    assert source_result.source.events_produced == 2
    assert replay.events_replayed == 2
    assert snapshot.runtime_monitor.status == RuntimeMonitorStatus.HEALTHY
    assert report.evidence_status == PaperShadowRunEvidenceStatus.PASS
    assert report.monitor_status == RuntimeMonitorStatus.HEALTHY
    assert report.guardrail_status == GuardrailAction.NONE
    assert report.accepted_event_count == 2
    assert report.rejected_event_count == 0
    assert report.accepted_batch_count == 1
    assert report.rejected_batch_count == 0
    assert report.symbols == ("BTCUSDT", "ETHUSDT")
    assert report.venues == ("binance",)
    assert report.blockers == ()
    assert rendered["source_summary"]["available"] is True
    assert rendered["replay_summary"]["available"] is True
    assert rendered["evidence_status"] == "pass"


def test_paper_shadow_run_evidence_zero_events_not_pass() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    controller = PaperShadowSessionController(clock_ns=lambda: _T0_NS + 1)
    snapshot = controller.prepare(plan)

    report = build_paper_shadow_run_evidence_report(session_snapshot=snapshot, report_id="empty-run")

    assert report.evidence_status == PaperShadowRunEvidenceStatus.EMPTY
    assert report.accepted_event_count == 0
    assert "no_market_events" in report.reason_codes
    assert "provide_market_events" in report.next_actions


def test_paper_shadow_run_evidence_rejected_batch_blocks() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 1, _T0_NS + 2, _T0_NS + 3))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))
    controller.prepare(plan)
    controller.start()
    bad_replay = FeedReplayPlan(
        replay_id="run-evidence-bad-replay",
        batches=(MarketEventBatch(batch_id="bad-price", events=(_market_event(price=-1.0),)),),
    )

    replay = controller.replay_feed(bad_replay)
    report = build_paper_shadow_run_evidence_report(
        session_snapshot=controller.snapshot(),
        replay_result=replay,
        report_id="blocked-run",
    )

    assert replay.batches_rejected == 1
    assert report.evidence_status == PaperShadowRunEvidenceStatus.BLOCKED
    assert report.rejected_batch_count == 1
    assert report.rejected_event_count == 1
    assert "rejected_replay_batches" in report.reason_codes
    assert "resolve_run_evidence_blockers" in report.next_actions


def test_paper_shadow_run_evidence_guardrail_stop_or_block_cannot_pass() -> None:
    _, _, _, report = _paper_shadow_full_local_run()
    payload = paper_shadow_run_evidence_report_to_dict(report)
    payload["guardrail_status"] = "stop_session"
    payload["evidence_status"] = "pass"

    with pytest.raises(PaperShadowSessionCorruptError):
        paper_shadow_run_evidence_report_from_dict(payload)


def test_paper_shadow_run_evidence_missing_monitor_inconclusive() -> None:
    report = build_paper_shadow_run_evidence_report(
        session_snapshot=None,
        report_id="missing-monitor-run",
        as_of_ns=_T0_NS,
    )

    assert report.evidence_status == PaperShadowRunEvidenceStatus.INCONCLUSIVE
    assert report.monitor_status == RuntimeMonitorStatus.NOT_READY
    assert report.guardrail_status == GuardrailAction.BLOCK_FINALIZE
    assert "missing_session_snapshot" in report.reason_codes
    assert report.next_actions == ("restore_session_snapshot",)


def test_paper_shadow_run_evidence_serialization_export_and_fail_closed(tmp_path) -> None:
    _, _, _, report = _paper_shadow_full_local_run()
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    payload = paper_shadow_run_evidence_report_to_dict(report)

    assert paper_shadow_run_evidence_report_from_dict(payload) == report

    export_paper_shadow_run_evidence_report(report=report, evidence_store=store)
    assert load_paper_shadow_run_evidence_report(evidence_store=store) == report

    store.save_snapshot("crypto_paper_shadow_run_evidence_report", ["bad"])
    with pytest.raises(PaperShadowSessionCorruptError):
        load_paper_shadow_run_evidence_report(evidence_store=store)


def test_paper_shadow_run_evidence_deterministic_replay() -> None:
    def run_once() -> dict:
        _, _, _, report = _paper_shadow_full_local_run()
        return paper_shadow_run_evidence_report_to_dict(report)

    assert run_once() == run_once()


def test_multi_source_run_evidence_empty_aggregate_not_pass() -> None:
    aggregate = build_multi_source_run_evidence_report((), aggregate_id="empty-aggregate", as_of_ns=_T0_NS)
    rendered = multi_source_run_evidence_report_to_dict(aggregate)

    assert isinstance(aggregate, MultiSourceRunEvidenceReport)
    assert aggregate.evidence_status == PaperShadowRunEvidenceStatus.EMPTY
    assert aggregate.report_count == 0
    assert aggregate.report_ids == ()
    assert "no_run_evidence_reports" in aggregate.blockers
    assert aggregate.next_actions == ("provide_run_evidence_reports",)
    assert rendered["evidence_status"] == "empty"


def test_multi_source_run_evidence_all_pass_aggregates_counts_symbols_and_venues() -> None:
    _, _, _, first = _paper_shadow_full_local_run(
        source_id="local-feed-a",
        report_id="run-a",
        replay_id="replay-a",
        symbols=("BTCUSDT",),
        records=({"symbol": "BTCUSDT", "ts_ns": _T0_NS + 101, "event_type": "mark_price", "price": 100.0},),
    )
    _, _, _, second = _paper_shadow_full_local_run(
        source_id="local-feed-b",
        report_id="run-b",
        replay_id="replay-b",
        symbols=("ETHUSDT",),
        records=({"symbol": "ETHUSDT", "ts_ns": _T0_NS + 102, "event_type": "mark_price", "price": 2100.0},),
    )

    aggregate = build_multi_source_run_evidence_report((second, first), aggregate_id="multi-pass")

    assert aggregate.evidence_status == PaperShadowRunEvidenceStatus.PASS
    assert aggregate.report_ids == ("run-a", "run-b")
    assert aggregate.report_count == 2
    assert aggregate.pass_count == 2
    assert aggregate.warn_count == 0
    assert aggregate.accepted_event_count == 2
    assert aggregate.accepted_batch_count == 2
    assert aggregate.symbols == ("BTCUSDT", "ETHUSDT")
    assert aggregate.venues == ("binance",)
    assert aggregate.guardrail_actions == (GuardrailAction.NONE,)
    assert aggregate.blockers == ()


def test_multi_source_run_evidence_mixed_pass_warn_is_warn() -> None:
    _, _, snapshot, pass_report = _paper_shadow_full_local_run(report_id="run-pass")
    warn_report = build_paper_shadow_run_evidence_report(
        session_snapshot=snapshot,
        report_id="run-warn",
    )

    aggregate = build_multi_source_run_evidence_report((pass_report, warn_report), aggregate_id="multi-warn")

    assert aggregate.evidence_status == PaperShadowRunEvidenceStatus.WARN
    assert aggregate.pass_count == 1
    assert aggregate.warn_count == 1
    assert "missing_data_source_evidence" in aggregate.reason_codes
    assert "review_multi_source_run_warnings" in aggregate.next_actions


def test_multi_source_run_evidence_any_blocked_forces_blocked() -> None:
    _, _, _, pass_report = _paper_shadow_full_local_run(report_id="run-pass")
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 1, _T0_NS + 2, _T0_NS + 3))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))
    controller.prepare(plan)
    controller.start()
    replay = controller.replay_feed(
        FeedReplayPlan(
            replay_id="bad-replay",
            batches=(MarketEventBatch(batch_id="bad-price", events=(_market_event(price=-1.0),)),),
        )
    )
    blocked_report = build_paper_shadow_run_evidence_report(
        session_snapshot=controller.snapshot(),
        replay_result=replay,
        report_id="run-blocked",
    )

    aggregate = build_multi_source_run_evidence_report((pass_report, blocked_report), aggregate_id="multi-blocked")

    assert aggregate.evidence_status == PaperShadowRunEvidenceStatus.BLOCKED
    assert aggregate.blocked_count == 1
    assert aggregate.rejected_batch_count == 1
    assert aggregate.rejected_event_count == 1
    assert "blocked_run_evidence_report" in aggregate.reason_codes
    assert "rejected_run_evidence" in aggregate.blockers


def test_multi_source_run_evidence_inconclusive_without_blockers() -> None:
    _, _, _, pass_report = _paper_shadow_full_local_run(report_id="run-pass")
    inconclusive = build_paper_shadow_run_evidence_report(
        session_snapshot=None,
        report_id="run-inconclusive",
        as_of_ns=_T0_NS,
    )

    aggregate = build_multi_source_run_evidence_report((pass_report, inconclusive), aggregate_id="multi-inconclusive")

    assert aggregate.evidence_status == PaperShadowRunEvidenceStatus.INCONCLUSIVE
    assert aggregate.inconclusive_count == 1
    assert "inconclusive_run_evidence_report" in aggregate.reason_codes
    assert "restore_missing_run_evidence" in aggregate.next_actions


def test_multi_source_run_evidence_duplicate_report_ids_rejected() -> None:
    _, _, _, report = _paper_shadow_full_local_run(report_id="duplicate-run")

    with pytest.raises(PaperShadowSessionCorruptError):
        build_multi_source_run_evidence_report((report, report), aggregate_id="duplicate-aggregate")

    payload = multi_source_run_evidence_report_to_dict(
        build_multi_source_run_evidence_report((report,), aggregate_id="single-aggregate")
    )
    payload["report_ids"] = ["duplicate-run", "duplicate-run"]
    payload["report_count"] = 2
    with pytest.raises(PaperShadowSessionCorruptError):
        multi_source_run_evidence_report_from_dict(payload)


def test_multi_source_run_evidence_serialization_export_and_fail_closed(tmp_path) -> None:
    _, _, _, first = _paper_shadow_full_local_run(source_id="local-feed-a", report_id="run-a", replay_id="replay-a")
    _, _, _, second = _paper_shadow_full_local_run(source_id="local-feed-b", report_id="run-b", replay_id="replay-b")
    aggregate = build_multi_source_run_evidence_report((first, second), aggregate_id="multi-roundtrip")
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    payload = multi_source_run_evidence_report_to_dict(aggregate)

    assert multi_source_run_evidence_report_from_dict(payload) == aggregate

    export_multi_source_run_evidence_report(report=aggregate, evidence_store=store)
    assert load_multi_source_run_evidence_report(evidence_store=store) == aggregate

    store.save_snapshot("crypto_multi_source_run_evidence_report", ["bad"])
    with pytest.raises(PaperShadowSessionCorruptError):
        load_multi_source_run_evidence_report(evidence_store=store)


def test_multi_source_run_evidence_deterministic_replay() -> None:
    def run_once() -> dict:
        _, _, _, first = _paper_shadow_full_local_run(source_id="local-feed-a", report_id="run-a", replay_id="replay-a")
        _, _, _, second = _paper_shadow_full_local_run(
            source_id="local-feed-b",
            report_id="run-b",
            replay_id="replay-b",
        )
        return multi_source_run_evidence_report_to_dict(
            build_multi_source_run_evidence_report((second, first), aggregate_id="multi-deterministic")
        )

    assert run_once() == run_once()


def test_paper_shadow_evidence_bundle_valid_drilldown_package() -> None:
    _, _, _, first = _paper_shadow_full_local_run(
        source_id="local-feed-a",
        report_id="run-a",
        replay_id="replay-a",
        symbols=("BTCUSDT",),
        records=({"symbol": "BTCUSDT", "ts_ns": _T0_NS + 101, "event_type": "mark_price", "price": 100.0},),
    )
    _, _, _, second = _paper_shadow_full_local_run(
        source_id="local-feed-b",
        report_id="run-b",
        replay_id="replay-b",
        symbols=("ETHUSDT",),
        records=({"symbol": "ETHUSDT", "ts_ns": _T0_NS + 102, "event_type": "mark_price", "price": 2100.0},),
    )
    aggregate = build_multi_source_run_evidence_report((second, first), aggregate_id="multi-bundle")

    bundle = build_paper_shadow_evidence_bundle(
        aggregate_report=aggregate,
        run_reports=(second, first),
        bundle_id="bundle-1",
    )
    rendered = paper_shadow_evidence_bundle_to_dict(bundle)

    assert isinstance(bundle, PaperShadowEvidenceBundle)
    assert bundle.evidence_status == PaperShadowRunEvidenceStatus.PASS
    assert bundle.report_ids == ("run-a", "run-b")
    assert tuple(report.report_id for report in bundle.run_reports) == ("run-a", "run-b")
    assert bundle.missing_report_ids == ()
    assert bundle.blockers == ()
    assert rendered["aggregate_report"]["aggregate_id"] == "multi-bundle"
    assert [report["report_id"] for report in rendered["run_reports"]] == ["run-a", "run-b"]


def test_paper_shadow_evidence_bundle_missing_nested_report_blocks_pass() -> None:
    _, _, _, first = _paper_shadow_full_local_run(source_id="local-feed-a", report_id="run-a", replay_id="replay-a")
    _, _, _, second = _paper_shadow_full_local_run(source_id="local-feed-b", report_id="run-b", replay_id="replay-b")
    aggregate = build_multi_source_run_evidence_report((first, second), aggregate_id="multi-missing-drilldown")

    bundle = build_paper_shadow_evidence_bundle(
        aggregate_report=aggregate,
        run_reports=(first,),
        bundle_id="bundle-missing",
    )

    assert aggregate.evidence_status == PaperShadowRunEvidenceStatus.PASS
    assert bundle.evidence_status == PaperShadowRunEvidenceStatus.BLOCKED
    assert bundle.missing_report_ids == ("run-b",)
    assert "missing_run_report_drilldown" in bundle.blockers
    assert bundle.next_actions == ("attach_missing_run_reports",)


def test_paper_shadow_evidence_bundle_duplicate_nested_report_rejected() -> None:
    _, _, _, report = _paper_shadow_full_local_run(report_id="duplicate-run")
    aggregate = build_multi_source_run_evidence_report((report,), aggregate_id="multi-duplicate-drilldown")

    with pytest.raises(PaperShadowSessionCorruptError):
        build_paper_shadow_evidence_bundle(
            aggregate_report=aggregate,
            run_reports=(report, report),
            bundle_id="bundle-duplicate",
        )


def test_paper_shadow_evidence_bundle_mismatched_aggregate_counts_fail_closed() -> None:
    _, _, _, first = _paper_shadow_full_local_run(source_id="local-feed-a", report_id="run-a", replay_id="replay-a")
    _, _, _, second = _paper_shadow_full_local_run(source_id="local-feed-b", report_id="run-b", replay_id="replay-b")
    aggregate = build_multi_source_run_evidence_report((first, second), aggregate_id="multi-drift")
    drifted = replace(aggregate, accepted_event_count=aggregate.accepted_event_count + 1)

    with pytest.raises(PaperShadowSessionCorruptError):
        build_paper_shadow_evidence_bundle(
            aggregate_report=drifted,
            run_reports=(first, second),
            bundle_id="bundle-drift",
        )


def test_paper_shadow_evidence_bundle_blocked_nested_report_stays_blocked() -> None:
    _, _, _, pass_report = _paper_shadow_full_local_run(report_id="run-pass")
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 1, _T0_NS + 2, _T0_NS + 3))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))
    controller.prepare(plan)
    controller.start()
    replay = controller.replay_feed(
        FeedReplayPlan(
            replay_id="bad-replay-bundle",
            batches=(MarketEventBatch(batch_id="bad-price-bundle", events=(_market_event(price=-1.0),)),),
        )
    )
    blocked_report = build_paper_shadow_run_evidence_report(
        session_snapshot=controller.snapshot(),
        replay_result=replay,
        report_id="run-blocked",
    )
    aggregate = build_multi_source_run_evidence_report((pass_report, blocked_report), aggregate_id="multi-blocked")

    bundle = build_paper_shadow_evidence_bundle(
        aggregate_report=aggregate,
        run_reports=(blocked_report, pass_report),
        bundle_id="bundle-blocked",
    )

    assert bundle.evidence_status == PaperShadowRunEvidenceStatus.BLOCKED
    assert bundle.missing_report_ids == ()
    assert "rejected_run_evidence" in bundle.blockers
    assert "resolve_multi_source_run_blockers" in bundle.next_actions
    flags = paper_shadow_evidence_readiness_flags(bundle)
    assert flags["paper_shadow_evidence_passed"] is False
    assert flags["paper_shadow_evidence_blocked"] is True


def test_paper_shadow_evidence_bundle_serialization_export_and_fail_closed(tmp_path) -> None:
    _, _, _, first = _paper_shadow_full_local_run(source_id="local-feed-a", report_id="run-a", replay_id="replay-a")
    _, _, _, second = _paper_shadow_full_local_run(source_id="local-feed-b", report_id="run-b", replay_id="replay-b")
    aggregate = build_multi_source_run_evidence_report((first, second), aggregate_id="multi-bundle-roundtrip")
    bundle = build_paper_shadow_evidence_bundle(
        aggregate_report=aggregate,
        run_reports=(second, first),
        bundle_id="bundle-roundtrip",
    )
    payload = paper_shadow_evidence_bundle_to_dict(bundle)
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())

    assert paper_shadow_evidence_bundle_from_dict(payload) == bundle

    payload["run_reports"] = payload["run_reports"][:1]
    payload["evidence_status"] = "pass"
    with pytest.raises(PaperShadowSessionCorruptError):
        paper_shadow_evidence_bundle_from_dict(payload)

    export_paper_shadow_evidence_bundle(bundle=bundle, evidence_store=store)
    assert load_paper_shadow_evidence_bundle(evidence_store=store) == bundle

    store.save_snapshot("crypto_paper_shadow_evidence_bundle", ["bad"])
    with pytest.raises(PaperShadowSessionCorruptError):
        load_paper_shadow_evidence_bundle(evidence_store=store)


def test_paper_shadow_evidence_bundle_deterministic_replay() -> None:
    def run_once() -> dict:
        _, _, _, first = _paper_shadow_full_local_run(source_id="local-feed-a", report_id="run-a", replay_id="replay-a")
        _, _, _, second = _paper_shadow_full_local_run(
            source_id="local-feed-b",
            report_id="run-b",
            replay_id="replay-b",
        )
        aggregate = build_multi_source_run_evidence_report((second, first), aggregate_id="multi-bundle-deterministic")
        return paper_shadow_evidence_bundle_to_dict(
            build_paper_shadow_evidence_bundle(
                aggregate_report=aggregate,
                run_reports=(second, first),
                bundle_id="bundle-deterministic",
            )
        )

    assert run_once() == run_once()


def test_paper_shadow_evidence_bundle_pass_supports_readiness_flags() -> None:
    _, _, _, first = _paper_shadow_full_local_run(source_id="local-feed-a", report_id="run-a", replay_id="replay-a")
    _, _, _, second = _paper_shadow_full_local_run(source_id="local-feed-b", report_id="run-b", replay_id="replay-b")
    aggregate = build_multi_source_run_evidence_report((second, first), aggregate_id="multi-readiness")
    bundle = build_paper_shadow_evidence_bundle(
        aggregate_report=aggregate,
        run_reports=(second, first),
        bundle_id="bundle-readiness",
    )

    flags = paper_shadow_evidence_readiness_flags(bundle)
    status = ReadinessEvaluator().evaluate(flags, assessed_at_ns=_T0_NS)
    criteria = {criterion.name: criterion for criterion in status.criteria}

    assert flags == {
        "paper_shadow_evidence_available": True,
        "paper_shadow_evidence_passed": True,
        "paper_shadow_evidence_blocked": False,
        "paper_shadow_evidence_bundle_complete": True,
    }
    assert criteria["paper_shadow_evidence_available"].status == CriterionStatus.MET
    assert criteria["paper_shadow_evidence_passed"].status == CriterionStatus.MET
    assert criteria["paper_shadow_evidence_blocked"].status == CriterionStatus.MET
    assert criteria["paper_shadow_evidence_bundle_complete"].status == CriterionStatus.MET


def test_paper_shadow_evidence_bundle_incomplete_bridge_not_supportive() -> None:
    _, _, _, first = _paper_shadow_full_local_run(source_id="local-feed-a", report_id="run-a", replay_id="replay-a")
    _, _, _, second = _paper_shadow_full_local_run(source_id="local-feed-b", report_id="run-b", replay_id="replay-b")
    aggregate = build_multi_source_run_evidence_report((first, second), aggregate_id="multi-incomplete-bridge")
    bundle = build_paper_shadow_evidence_bundle(
        aggregate_report=aggregate,
        run_reports=(first,),
        bundle_id="bundle-incomplete-bridge",
    )
    orch = ServiceOrchestrator(service=_mock_service(), readiness_level="paper_live")

    bridge = orch.paper_shadow_evidence_readiness_bridge_dict(bundle)

    assert bridge["paper_shadow_evidence_available"] is True
    assert bridge["paper_shadow_evidence_passed"] is False
    assert bridge["paper_shadow_evidence_blocked"] is True
    assert bridge["paper_shadow_evidence_bundle_complete"] is False
    assert bridge["supportive"] is False
    assert bridge["missing_report_ids"] == ["run-b"]
    assert bridge["blockers"] == ["missing_run_report_drilldown", "paper_shadow_evidence_incomplete"]


def test_service_orchestrator_missing_evidence_bundle_gates_release_manifest_and_activation() -> None:
    fixed_review_ns = _T0_NS + 250
    sleeve = _sleeve("bridge-sleeve", effective_allocation=0.20, target_allocation=0.20)
    portfolio = _portfolio(sleeve)
    campaign_report = _campaign_report(sleeve_ids=("bridge-sleeve",))
    orch = ServiceOrchestrator(
        service=_mock_service(),
        sleeves=(sleeve,),
        readiness_level="paper_live",
        sleeve_workflow_clock_ns=lambda: fixed_review_ns,
    )
    orch.start_sleeve_promotion_review(workflow_snapshot=_supported_workflow("bridge-sleeve"))

    pack = orch.sleeve_admission_release_pack(portfolio_snapshot=portfolio, campaign_report=campaign_report)
    manifest = orch.managed_sleeve_set_manifest(release_pack=pack, portfolio_snapshot=portfolio)
    plan = orch.paper_shadow_activation_plan(manifest=manifest)
    bridge = orch.paper_shadow_evidence_readiness_bridge_dict()

    assert bridge["paper_shadow_evidence_available"] is False
    assert bridge["supportive"] is False
    assert pack.evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_MISSING
    assert pack.overall_release_status == SleeveAdmissionReleaseStatus.PARTIAL_READY
    assert "paper_shadow_evidence_unavailable" in pack.paper_evidence_blockers
    assert manifest.dry_run_status != ManagedSleeveSetDryRunStatus.READY_FOR_PAPER_DRY_RUN
    assert plan.activation_status != PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW


def test_service_orchestrator_passed_evidence_bundle_allows_existing_release_readiness() -> None:
    fixed_review_ns = _T0_NS + 260
    sleeve = _sleeve("bridge-ready", effective_allocation=0.20, target_allocation=0.20)
    base_portfolio = _portfolio(sleeve)
    portfolio = replace(
        base_portfolio,
        effective_allocation=replace(
            base_portfolio.effective_allocation,
            effective_allocated_share=0.20,
            effective_unallocated_share=0.80,
            recipient_sleeve_ids=("bridge-ready",),
        ),
    )
    campaign_report = _campaign_report(sleeve_ids=("bridge-ready",))
    _, _, _, first = _paper_shadow_full_local_run(source_id="local-feed-a", report_id="run-a", replay_id="replay-a")
    _, _, _, second = _paper_shadow_full_local_run(source_id="local-feed-b", report_id="run-b", replay_id="replay-b")
    aggregate = build_multi_source_run_evidence_report((second, first), aggregate_id="multi-release-bridge")
    orch = ServiceOrchestrator(
        service=_mock_service(),
        sleeves=(sleeve,),
        readiness_level="paper_live",
        sleeve_workflow_clock_ns=lambda: fixed_review_ns,
    )
    orch.paper_shadow_evidence_bundle(
        aggregate_report=aggregate,
        run_reports=(first, second),
        bundle_id="bundle-release-bridge",
    )
    orch.start_sleeve_promotion_review(workflow_snapshot=_supported_workflow("bridge-ready"))

    pack = orch.sleeve_admission_release_pack(portfolio_snapshot=portfolio, campaign_report=campaign_report)
    manifest = orch.managed_sleeve_set_manifest(release_pack=pack, portfolio_snapshot=portfolio)
    plan = orch.paper_shadow_activation_plan(manifest=manifest)
    evidence = operator_snapshot_to_dict(orch.operator_snapshot())["evidence"]

    assert pack.evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_READY
    assert pack.overall_release_status == SleeveAdmissionReleaseStatus.READY_FOR_PAPER_MANAGED_SET
    assert manifest.dry_run_status == ManagedSleeveSetDryRunStatus.READY_FOR_PAPER_DRY_RUN
    assert plan.activation_status == PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW
    assert evidence["paper_shadow_evidence_passed"] is True
    assert evidence["paper_shadow_evidence_bundle_complete"] is True


def test_paper_shadow_evidence_circuit_e2e_pass_path() -> None:
    (
        orch,
        portfolio,
        campaign_report,
        seed_pack,
        manifest,
        plan,
        source_result,
        replay_result,
        run_report,
    ) = _paper_shadow_e2e_pass_report(
        sleeve_id="e2e-pass-sleeve",
        source_id="local-e2e-pass",
        report_id="run-e2e-pass",
        replay_id="replay-e2e-pass",
    )
    snapshot = orch.paper_shadow_session_snapshot()
    monitor = orch.paper_shadow_runtime_monitor_dict()
    guardrail = orch.paper_shadow_guardrail_dict()
    aggregate = orch.multi_source_run_evidence_report((run_report,), aggregate_id="multi-e2e-pass")
    bundle = orch.paper_shadow_evidence_bundle(
        aggregate_report=aggregate,
        run_reports=(run_report,),
        bundle_id="bundle-e2e-pass",
    )
    bridge = orch.paper_shadow_evidence_readiness_bridge_dict()
    release_pack = orch.sleeve_admission_release_pack(
        portfolio_snapshot=portfolio,
        campaign_report=campaign_report,
    )
    ready_manifest = orch.managed_sleeve_set_manifest(release_pack=release_pack, portfolio_snapshot=portfolio)
    ready_plan = orch.paper_shadow_activation_plan(manifest=ready_manifest)

    assert seed_pack.evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_READY
    assert manifest.dry_run_status == ManagedSleeveSetDryRunStatus.READY_FOR_PAPER_DRY_RUN
    assert plan.activation_status == PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW
    assert plan.paper_only is True
    assert plan.real_orders_enabled is False
    assert plan.real_money_enabled is False
    assert source_result.source.events_produced == 2
    assert replay_result.events_replayed == 2
    assert replay_result.batches_rejected == 0
    assert snapshot.runtime_monitor.status == RuntimeMonitorStatus.HEALTHY
    assert snapshot.guardrail.primary_action == GuardrailAction.NONE
    assert monitor["status"] == "healthy"
    assert guardrail["primary_action"] == "none"
    assert run_report.evidence_status == PaperShadowRunEvidenceStatus.PASS
    assert aggregate.evidence_status == PaperShadowRunEvidenceStatus.PASS
    assert bundle.evidence_status == PaperShadowRunEvidenceStatus.PASS
    assert bundle.paper_only is True
    assert bundle.real_orders_enabled is False
    assert bundle.real_money_enabled is False
    assert bridge["paper_shadow_evidence_passed"] is True
    assert bridge["paper_shadow_evidence_blocked"] is False
    assert bridge["paper_shadow_evidence_bundle_complete"] is True
    assert bridge["supportive"] is True
    assert release_pack.evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_READY
    assert release_pack.overall_release_status == SleeveAdmissionReleaseStatus.READY_FOR_PAPER_MANAGED_SET
    assert ready_manifest.dry_run_status == ManagedSleeveSetDryRunStatus.READY_FOR_PAPER_DRY_RUN
    assert ready_plan.activation_status == PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW


def test_paper_shadow_evidence_circuit_missing_bundle_fails_closed() -> None:
    (
        orch,
        portfolio,
        campaign_report,
        _seed_pack,
        _manifest,
        _plan,
        _source_result,
        _replay_result,
        run_report,
    ) = _paper_shadow_e2e_pass_report(
        sleeve_id="e2e-missing-bundle",
        source_id="local-e2e-missing",
        report_id="run-e2e-missing",
        replay_id="replay-e2e-missing",
    )
    aggregate = orch.multi_source_run_evidence_report((run_report,), aggregate_id="multi-e2e-missing-bundle")
    bridge = orch.paper_shadow_evidence_readiness_bridge_dict()
    release_pack = orch.sleeve_admission_release_pack(
        portfolio_snapshot=portfolio,
        campaign_report=campaign_report,
    )
    manifest = orch.managed_sleeve_set_manifest(release_pack=release_pack, portfolio_snapshot=portfolio)
    plan = orch.paper_shadow_activation_plan(manifest=manifest)

    assert aggregate.evidence_status == PaperShadowRunEvidenceStatus.PASS
    assert bridge["paper_shadow_evidence_available"] is False
    assert bridge["paper_shadow_evidence_passed"] is False
    assert bridge["supportive"] is False
    assert "paper_shadow_evidence_unavailable" in bridge["blockers"]
    assert release_pack.evidence_gate_status == SleeveAdmissionReleaseEvidenceStatus.EVIDENCE_MISSING
    assert release_pack.overall_release_status != SleeveAdmissionReleaseStatus.READY_FOR_PAPER_MANAGED_SET
    assert "paper_shadow_evidence_unavailable" in release_pack.paper_evidence_blockers
    assert manifest.dry_run_status != ManagedSleeveSetDryRunStatus.READY_FOR_PAPER_DRY_RUN
    assert plan.activation_status != PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW


def test_paper_shadow_evidence_circuit_blocked_guardrail_fails_closed() -> None:
    orch, _portfolio, _campaign_report, _seed_pack, _manifest, plan = _paper_shadow_e2e_seed(
        sleeve_id="e2e-guardrail-sleeve"
    )
    source_result = build_paper_data_source_batch_result(
        _paper_data_source_payload(
            source_id="local-e2e-guardrail",
            symbols=("BTCUSDT",),
            records=(
                {
                    "symbol": "BTCUSDT",
                    "ts_ns": _T0_NS + 101,
                    "event_type": "mark_price",
                    "price": 100.0,
                },
            ),
        ),
        allowed_source_ids=("local-e2e-guardrail",),
        batch_id="local-e2e-guardrail-batch",
    )
    times = iter((_T0_NS + 501, _T0_NS + 502, _T0_NS + 503, _T0_NS + 504))
    controller = PaperShadowSessionController(
        clock_ns=lambda: next(times),
        required_market_symbols=("BTCUSDT", "ETHUSDT"),
    )
    controller.prepare(plan)
    controller.start()
    replay_result = controller.replay_feed(
        build_feed_replay_plan(
            (
                source_result.batch,
                build_market_event_batch(
                    (_market_event("ETHUSDT", venue="binance", ts_ns=_T0_NS + 102, price=2100.0),),
                    batch_id="local-e2e-guardrail-not-replayed",
                ),
            ),
            replay_id="replay-e2e-guardrail",
        )
    )
    run_report = build_paper_shadow_run_evidence_report(
        session_snapshot=controller.snapshot(),
        source_result=source_result,
        replay_result=replay_result,
        report_id="run-e2e-guardrail",
    )
    aggregate = orch.multi_source_run_evidence_report((run_report,), aggregate_id="multi-e2e-guardrail")
    bundle = orch.paper_shadow_evidence_bundle(
        aggregate_report=aggregate,
        run_reports=(run_report,),
        bundle_id="bundle-e2e-guardrail",
    )
    bridge = orch.paper_shadow_evidence_readiness_bridge_dict()

    assert replay_result.halted_by_guardrail is True
    assert replay_result.halt_reason == GuardrailAction.PAUSE_SESSION.value
    assert controller.snapshot().status == PaperShadowSessionStatus.BLOCKED
    assert run_report.evidence_status == PaperShadowRunEvidenceStatus.BLOCKED
    assert aggregate.evidence_status == PaperShadowRunEvidenceStatus.BLOCKED
    assert bundle.evidence_status == PaperShadowRunEvidenceStatus.BLOCKED
    assert bridge["paper_shadow_evidence_passed"] is False
    assert bridge["paper_shadow_evidence_blocked"] is True
    assert bridge["supportive"] is False


def test_paper_shadow_evidence_circuit_rejected_batch_fails_closed() -> None:
    orch, _portfolio, _campaign_report, _seed_pack, _manifest, plan = _paper_shadow_e2e_seed(
        sleeve_id="e2e-rejected-sleeve"
    )
    with pytest.raises(PaperShadowSessionCorruptError):
        orch.paper_data_source_payload_to_batch_result(
            _paper_data_source_payload(
                source_id="local-e2e-rejected",
                symbols=("BTCUSDT",),
                records=(
                    {
                        "symbol": "BTCUSDT",
                        "ts_ns": _T0_NS + 101,
                        "event_type": "mark_price",
                        "price": -1.0,
                    },
                ),
            ),
            allowed_source_ids=("local-e2e-rejected",),
        )
    orch.prepare_paper_shadow_session(plan=plan)
    orch.start_paper_shadow_session()
    replay_result = orch.replay_paper_shadow_feed(
        FeedReplayPlan(
            replay_id="replay-e2e-rejected",
            batches=(MarketEventBatch(batch_id="bad-e2e-price", events=(_market_event(price=-1.0),)),),
        )
    )
    run_report = orch.paper_shadow_run_evidence_report(
        replay_result=replay_result,
        report_id="run-e2e-rejected",
    )
    aggregate = orch.multi_source_run_evidence_report((run_report,), aggregate_id="multi-e2e-rejected")
    bundle = orch.paper_shadow_evidence_bundle(
        aggregate_report=aggregate,
        run_reports=(run_report,),
        bundle_id="bundle-e2e-rejected",
    )
    bridge = orch.paper_shadow_evidence_readiness_bridge_dict()

    assert replay_result.batches_rejected == 1
    assert replay_result.rejected_batch_ids == ("bad-e2e-price",)
    assert run_report.evidence_status == PaperShadowRunEvidenceStatus.BLOCKED
    assert run_report.rejected_batch_count == 1
    assert aggregate.evidence_status == PaperShadowRunEvidenceStatus.BLOCKED
    assert bundle.evidence_status == PaperShadowRunEvidenceStatus.BLOCKED
    assert bridge["paper_shadow_evidence_passed"] is False
    assert bridge["paper_shadow_evidence_blocked"] is True
    assert bridge["supportive"] is False


def test_paper_shadow_evidence_circuit_incomplete_aggregate_fails_closed() -> None:
    first = _paper_shadow_e2e_pass_report(
        sleeve_id="e2e-incomplete-a",
        source_id="local-e2e-incomplete-a",
        report_id="run-e2e-incomplete-a",
        replay_id="replay-e2e-incomplete-a",
    )
    second = _paper_shadow_e2e_pass_report(
        sleeve_id="e2e-incomplete-b",
        source_id="local-e2e-incomplete-b",
        report_id="run-e2e-incomplete-b",
        replay_id="replay-e2e-incomplete-b",
    )
    orch = first[0]
    first_report = first[-1]
    second_report = second[-1]

    aggregate = orch.multi_source_run_evidence_report(
        (second_report, first_report),
        aggregate_id="multi-e2e-incomplete",
    )
    bundle = orch.paper_shadow_evidence_bundle(
        aggregate_report=aggregate,
        run_reports=(first_report,),
        bundle_id="bundle-e2e-incomplete",
    )
    bridge = orch.paper_shadow_evidence_readiness_bridge_dict()

    assert aggregate.evidence_status == PaperShadowRunEvidenceStatus.PASS
    assert aggregate.report_ids == ("run-e2e-incomplete-a", "run-e2e-incomplete-b")
    assert bundle.evidence_status == PaperShadowRunEvidenceStatus.BLOCKED
    assert bundle.missing_report_ids == ("run-e2e-incomplete-b",)
    assert "missing_run_report_drilldown" in bundle.blockers
    assert bridge["paper_shadow_evidence_passed"] is False
    assert bridge["paper_shadow_evidence_blocked"] is True
    assert bridge["paper_shadow_evidence_bundle_complete"] is False
    assert bridge["supportive"] is False


def test_service_orchestrator_paper_shadow_session_helpers_and_operator_status(tmp_path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    plan = _ready_activation_plan(_sleeve("svc-active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 10, _T0_NS + 11, _T0_NS + 12, _T0_NS + 13, _T0_NS + 14))
    orch = ServiceOrchestrator(
        service=_mock_service(),
        evidence_store=store,
        readiness_level="paper_live",
        sleeve_workflow_clock_ns=lambda: next(times),
    )

    prepared = orch.prepare_paper_shadow_session(plan=plan)
    orch.start_paper_shadow_session()
    orch.record_paper_shadow_market_event_batch(
        build_market_event_batch((_market_event("BTCUSDT", ts_ns=_T0_NS + 120),))
    )
    orch.stop_paper_shadow_session()
    finalized = orch.finalize_paper_shadow_session()
    rendered = orch.paper_shadow_session_snapshot_dict()
    operator = operator_snapshot_to_dict(orch.operator_snapshot())

    assert prepared.status == PaperShadowSessionStatus.READY
    assert finalized.status == PaperShadowSessionStatus.FINALIZED
    assert rendered["tick_count"] == 1
    assert rendered["real_orders_enabled"] is False
    assert rendered["real_money_enabled"] is False
    assert operator["paper_shadow_session"]["available"] is True
    assert operator["paper_shadow_session"]["status"] == "finalized"
    assert operator["paper_shadow_session"]["real_orders_enabled"] is False
    assert operator["paper_shadow_session"]["real_money_enabled"] is False

    orch.export_paper_shadow_session_snapshot()
    assert orch.load_paper_shadow_session_snapshot() == finalized


def test_service_orchestrator_market_event_batch_helper(tmp_path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    plan = _ready_activation_plan(_sleeve("svc-active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 20, _T0_NS + 21, _T0_NS + 22))
    orch = ServiceOrchestrator(
        service=_mock_service(),
        evidence_store=store,
        readiness_level="paper_live",
        sleeve_workflow_clock_ns=lambda: next(times),
    )
    batch = build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 120),))

    orch.prepare_paper_shadow_session(plan=plan)
    orch.start_paper_shadow_session()
    snapshot = orch.record_paper_shadow_market_event_batch(batch)
    rendered = orch.paper_shadow_session_snapshot_dict()
    monitor = orch.paper_shadow_runtime_monitor_dict()
    guardrail = orch.paper_shadow_guardrail_dict()
    operator = operator_snapshot_to_dict(orch.operator_snapshot())

    assert snapshot.event_count == 1
    assert rendered["event_count"] == 1
    assert rendered["symbols_seen"] == ["BTCUSDT"]
    assert rendered["runtime_monitor"]["status"] == "healthy"
    assert rendered["guardrail"]["primary_action"] == "none"
    assert monitor["status"] == "healthy"
    assert monitor["last_event_ns"] == _T0_NS + 120
    assert guardrail["primary_action"] == "none"
    assert operator["paper_shadow_session"]["event_count"] == 1
    assert operator["paper_shadow_session"]["symbols_seen"] == 1
    assert operator["paper_shadow_session"]["runtime_monitor_status"] == "healthy"
    assert operator["paper_shadow_session"]["guardrail_primary_action"] == "none"
    assert operator["paper_shadow_session"]["guardrail_block_finalize"] is False
    assert operator["paper_shadow_session"]["price_validity_ok"] is True
    assert orch.paper_shadow_market_event_batch_dict(batch)["events"][0]["symbol"] == "BTCUSDT"

    orch.export_paper_shadow_market_event_batch(batch)
    assert orch.load_paper_shadow_market_event_batch() == batch


def test_paper_intent_valid_intent_accepted_as_audit_only() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 40, _T0_NS + 41, _T0_NS + 42, _T0_NS + 43))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))
    controller.prepare(plan)
    controller.start()
    controller.record_market_event_batch(
        build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101),))
    )
    batch = build_paper_intent_batch((_paper_intent("active", "BTCUSDT", venue="binance"),), batch_id="intent-valid")

    result = controller.record_paper_intent_batch(batch)
    snapshot = controller.snapshot()
    rendered = paper_shadow_session_snapshot_to_dict(snapshot)

    assert result.intents_seen == 1
    assert result.accepted_count == 1
    assert result.rejected_count == 0
    assert result.results[0].accepted is True
    assert result.rejection_reasons == ()
    assert snapshot.intents_seen == 1
    assert snapshot.accepted_intent_count == 1
    assert snapshot.rejected_intent_count == 0
    assert snapshot.intent_sleeves_seen == ("active",)
    assert snapshot.intent_symbols_seen == ("BTCUSDT",)
    assert snapshot.intent_venues_seen == ("binance",)
    assert snapshot.event_count == 1
    assert snapshot.real_orders_enabled is False
    assert snapshot.real_money_enabled is False
    assert rendered["accepted_intent_count"] == 1
    assert paper_intent_batch_from_dict(paper_intent_batch_to_dict(batch)) == batch
    assert paper_intent_batch_result_from_dict(paper_intent_batch_result_to_dict(result)) == result


def test_paper_intent_before_start_rejected_fail_closed() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 50, _T0_NS + 51))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))
    controller.prepare(plan)

    result = controller.record_paper_intent_batch(
        build_paper_intent_batch((_paper_intent("active", "BTCUSDT"),), batch_id="intent-before-start")
    )

    assert result.accepted_count == 0
    assert result.rejected_count == 1
    assert result.results[0].rejection_reasons == ("guardrail_block_finalize", "session_not_running")
    assert controller.snapshot().intents_seen == 1
    assert controller.snapshot().accepted_intent_count == 0
    assert controller.snapshot().rejected_intent_count == 1
    assert controller.snapshot().real_orders_enabled is False
    assert controller.snapshot().real_money_enabled is False


def test_paper_intent_stopped_and_blocked_guardrail_rejected() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    stopped_times = iter((_T0_NS + 60, _T0_NS + 61, _T0_NS + 62, _T0_NS + 63, _T0_NS + 64))
    stopped_controller = PaperShadowSessionController(clock_ns=lambda: next(stopped_times))
    stopped_controller.prepare(plan)
    stopped_controller.start()
    stopped_controller.record_market_event_batch(
        build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101),))
    )
    stopped_controller.stop()

    stopped_result = stopped_controller.record_paper_intent_batch(
        build_paper_intent_batch((_paper_intent("active", "BTCUSDT"),), batch_id="intent-stopped")
    )

    blocked_times = iter((_T0_NS + 70, _T0_NS + 71, _T0_NS + 72, _T0_NS + 73, _T0_NS + 74))
    blocked_controller = PaperShadowSessionController(
        clock_ns=lambda: next(blocked_times),
        required_market_symbols=("BTCUSDT", "ETHUSDT"),
    )
    blocked_controller.prepare(plan)
    blocked_controller.start()
    blocked_controller.record_market_event_batch(
        build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101),))
    )
    blocked_controller.apply_guardrails()
    blocked_result = blocked_controller.record_paper_intent_batch(
        build_paper_intent_batch((_paper_intent("active", "BTCUSDT"),), batch_id="intent-blocked")
    )

    assert stopped_result.accepted_count == 0
    assert stopped_result.results[0].rejection_reasons == ("session_not_running",)
    assert stopped_controller.snapshot().status == PaperShadowSessionStatus.STOPPED
    assert blocked_controller.snapshot().status == PaperShadowSessionStatus.BLOCKED
    assert blocked_result.accepted_count == 0
    assert "guardrail_block_finalize" in blocked_result.results[0].rejection_reasons
    assert "session_not_running" in blocked_result.results[0].rejection_reasons


def test_paper_intent_inactive_sleeve_rejected() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 80, _T0_NS + 81, _T0_NS + 82, _T0_NS + 83))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))
    controller.prepare(plan)
    controller.start()
    controller.record_market_event_batch(
        build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101),))
    )

    result = controller.record_paper_intent_batch(
        build_paper_intent_batch((_paper_intent("inactive", "BTCUSDT"),), batch_id="intent-inactive")
    )

    assert result.accepted_count == 0
    assert result.rejected_count == 1
    assert result.results[0].rejection_reasons == ("inactive_sleeve",)
    assert controller.snapshot().accepted_intent_count == 0
    assert controller.snapshot().intent_sleeves_seen == ("inactive",)


def test_paper_intent_malformed_qty_and_unknown_market_rejected() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 90, _T0_NS + 91, _T0_NS + 92, _T0_NS + 93))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))
    controller.prepare(plan)
    controller.start()
    controller.record_market_event_batch(
        build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101),))
    )
    batch = build_paper_intent_batch(
        (
            _paper_intent("active", "BTCUSDT", qty=-1.0, intent_ts_ns=_T0_NS + 151),
            _paper_intent("active", "ETHUSDT", venue="bybit", intent_ts_ns=_T0_NS + 152),
        ),
        batch_id="intent-malformed",
    )

    result = controller.record_paper_intent_batch(batch)

    assert result.accepted_count == 0
    assert result.rejected_count == 2
    assert result.rejection_reasons == ("invalid_intent_size", "unknown_symbol", "unknown_venue")
    assert result.results[0].rejection_reasons == ("invalid_intent_size",)
    assert result.results[1].rejection_reasons == ("unknown_symbol", "unknown_venue")
    assert controller.snapshot().rejected_intent_count == 2
    assert controller.snapshot().intent_rejection_reasons == (
        "invalid_intent_size",
        "unknown_symbol",
        "unknown_venue",
    )


def test_paper_intent_deterministic_replay() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    market_batch = build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101),))
    intent_batch = build_paper_intent_batch(
        (
            _paper_intent("active", "BTCUSDT", intent_ts_ns=_T0_NS + 151),
            _paper_intent("inactive", "BTCUSDT", intent_ts_ns=_T0_NS + 152),
        ),
        batch_id="intent-deterministic",
    )

    def run_once() -> tuple[dict, dict]:
        times = iter((_T0_NS + 100, _T0_NS + 101, _T0_NS + 102, _T0_NS + 103))
        controller = PaperShadowSessionController(clock_ns=lambda: next(times))
        controller.prepare(plan)
        controller.start()
        controller.record_market_event_batch(market_batch)
        result = controller.record_paper_intent_batch(intent_batch)
        return paper_intent_batch_result_to_dict(result), paper_shadow_session_snapshot_to_dict(controller.snapshot())

    assert run_once() == run_once()


def test_service_orchestrator_paper_intent_helpers_and_artifacts(tmp_path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    plan = _ready_activation_plan(_sleeve("svc-active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 110, _T0_NS + 111, _T0_NS + 112, _T0_NS + 113))
    orch = ServiceOrchestrator(
        service=_mock_service(),
        evidence_store=store,
        readiness_level="paper_live",
        sleeve_workflow_clock_ns=lambda: next(times),
    )
    intent_batch = build_paper_intent_batch(
        (_paper_intent("svc-active", "BTCUSDT", venue="binance"),),
        batch_id="svc-intents",
    )

    orch.prepare_paper_shadow_session(plan=plan)
    orch.start_paper_shadow_session()
    orch.record_paper_shadow_market_event_batch(
        build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101),))
    )
    result = orch.record_paper_intent_batch(intent_batch)
    rendered_batch = orch.paper_intent_batch_dict(intent_batch)
    rendered_result = orch.paper_intent_batch_result_dict(result)
    session = orch.paper_shadow_session_snapshot_dict()
    operator = operator_snapshot_to_dict(orch.operator_snapshot())["paper_shadow_session"]

    assert result.accepted_count == 1
    assert rendered_batch["batch_id"] == "svc-intents"
    assert rendered_result["accepted_count"] == 1
    assert session["intents_seen"] == 1
    assert session["accepted_intent_count"] == 1
    assert operator["intents_seen"] == 1
    assert operator["accepted_intent_count"] == 1
    assert operator["rejected_intent_count"] == 0
    assert operator["intent_symbols_seen"] == 1

    orch.export_paper_intent_batch(intent_batch)
    orch.export_paper_intent_batch_result(result)
    assert orch.load_paper_intent_batch() == intent_batch
    assert orch.load_paper_intent_batch_result() == result
    export_paper_intent_batch(batch=intent_batch, evidence_store=store)
    export_paper_intent_batch_result(result=result, evidence_store=store)
    assert load_paper_intent_batch(evidence_store=store) == intent_batch
    assert load_paper_intent_batch_result(evidence_store=store) == result

    store.save_snapshot("crypto_paper_intent_batch_result", ["bad"])
    with pytest.raises(PaperShadowSessionCorruptError):
        load_paper_intent_batch_result(evidence_store=store)


def test_paper_fill_valid_accepted_intent_fills_from_latest_market_price() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in (1, 2, 3, 4, 5)))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))

    controller.prepare(plan)
    controller.start()
    controller.record_market_event_batch(
        build_market_event_batch(
            (
                _market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101, price=100.0),
                _market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 102, price=None, mark_price=101.25),
            )
        )
    )
    intent_result = controller.record_paper_intent_batch(
        build_paper_intent_batch((_paper_intent("active", "BTCUSDT", venue="binance"),), batch_id="fill-valid")
    )

    result = controller.simulate_paper_fills(intent_result)
    snapshot = controller.snapshot()
    rendered = paper_fill_simulation_result_to_dict(result)
    restored = paper_fill_simulation_result_from_dict(rendered)

    assert restored == result
    assert result.fill_attempts == 1
    assert result.simulated_fills == 1
    assert result.rejected_fills == 0
    assert result.symbols_filled == ("BTCUSDT",)
    assert result.sleeves_filled == ("active",)
    assert result.fills[0].status == PaperFillStatus.FILLED
    assert result.fills[0].fill_price == 101.25
    assert result.fills[0].reason == "filled_from_latest_market_event"
    assert result.paper_only is True
    assert result.real_orders_enabled is False
    assert result.real_money_enabled is False
    assert snapshot.fill_attempts == 1
    assert snapshot.simulated_fills == 1
    assert snapshot.rejected_fills == 0
    assert snapshot.symbols_filled == ("BTCUSDT",)
    assert snapshot.sleeves_filled == ("active",)
    assert paper_shadow_session_snapshot_from_dict(paper_shadow_session_snapshot_to_dict(snapshot)) == snapshot


def test_paper_fill_rejected_intent_is_skipped_without_fill_attempt() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in (1, 2, 3, 4, 5)))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))

    controller.prepare(plan)
    controller.start()
    controller.record_market_event_batch(
        build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101),))
    )
    intent_result = controller.record_paper_intent_batch(
        build_paper_intent_batch((_paper_intent("inactive", "BTCUSDT", venue="binance"),), batch_id="fill-skipped")
    )

    result = controller.simulate_paper_fills(intent_result)

    assert intent_result.accepted_count == 0
    assert result.fill_attempts == 0
    assert result.simulated_fills == 0
    assert result.rejected_fills == 0
    assert result.fills[0].status == PaperFillStatus.SKIPPED
    assert result.fills[0].fill_price is None
    assert result.rejection_reasons == ("intent_rejected",)
    assert controller.snapshot().fill_attempts == 0


def test_paper_fill_without_latest_market_price_rejects_fail_closed() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in (1, 2, 3, 4, 5)))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))

    controller.prepare(plan)
    controller.start()
    controller.record_market_event_batch(
        build_market_event_batch(
            (
                _market_event(
                    "BTCUSDT",
                    venue="binance",
                    ts_ns=_T0_NS + 101,
                    event_type=MarketEventType.FUNDING,
                    price=None,
                    funding_rate=0.0001,
                ),
            )
        )
    )
    intent_result = controller.record_paper_intent_batch(
        build_paper_intent_batch((_paper_intent("active", "BTCUSDT", venue="binance"),), batch_id="fill-no-market")
    )

    result = controller.simulate_paper_fills(intent_result)

    assert intent_result.accepted_count == 1
    assert result.fill_attempts == 1
    assert result.simulated_fills == 0
    assert result.rejected_fills == 1
    assert result.fills[0].status == PaperFillStatus.REJECTED_NO_MARKET
    assert result.fills[0].fill_price is None
    assert result.rejection_reasons == ("missing_latest_market_price",)
    assert controller.snapshot().rejected_fills == 1


def test_paper_fill_guardrail_block_rejects_accepted_intent() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in (1, 2, 3, 4, 5, 6)))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times), max_market_event_gap_ns=5)

    controller.prepare(plan)
    controller.start()
    controller.record_market_event_batch(
        build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101, price=100.0),))
    )
    intent_result = controller.record_paper_intent_batch(
        build_paper_intent_batch((_paper_intent("active", "BTCUSDT", venue="binance"),), batch_id="fill-guardrail")
    )
    controller.record_market_event_batch(
        build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 110, price=101.0),))
    )

    result = controller.simulate_paper_fills(intent_result)

    assert intent_result.accepted_count == 1
    assert controller.snapshot().guardrail.block_finalize is True
    assert result.fill_attempts == 1
    assert result.simulated_fills == 0
    assert result.rejected_fills == 1
    assert result.fills[0].status == PaperFillStatus.REJECTED_GUARDRAIL
    assert result.rejection_reasons == ("guardrail_blocks_paper_fill",)


def test_paper_fill_invalid_intent_size_and_malformed_price_reject() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in (1, 2, 3, 4)))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))

    controller.prepare(plan)
    controller.start()
    controller.record_market_event_batch(
        build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101, price=100.0),))
    )
    invalid_intent = _paper_intent("active", "BTCUSDT", venue="binance", qty=-1.0)
    forged_result = PaperIntentBatchResult(
        batch_id="fill-invalid-intent",
        session_id=controller.snapshot().session_id,
        as_of_ns=_T0_NS + 150,
        results=(PaperIntentValidationResult(intent=invalid_intent, accepted=True),),
        intents_seen=1,
        accepted_count=1,
        rejected_count=0,
        sleeves_seen=("active",),
        symbols_seen=("BTCUSDT",),
        venues_seen=("binance",),
        rejection_reasons=(),
        operator_summary="forged accepted invalid intent",
    )

    result = controller.simulate_paper_fills(forged_result)

    assert result.fill_attempts == 1
    assert result.simulated_fills == 0
    assert result.rejected_fills == 1
    assert result.fills[0].status == PaperFillStatus.REJECTED_INVALID_INTENT
    assert result.rejection_reasons == ("invalid_intent_size",)
    with pytest.raises(PaperShadowSessionCorruptError):
        build_market_event_batch((_market_event("BTCUSDT", venue="binance", price=float("inf")),))


def test_paper_fill_before_start_rejects_without_execution_side_effects() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in (1, 2)))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))
    controller.prepare(plan)
    intent = _paper_intent("active", "BTCUSDT", venue="binance")
    forged_result = PaperIntentBatchResult(
        batch_id="fill-before-start",
        session_id=controller.snapshot().session_id,
        as_of_ns=_T0_NS + 150,
        results=(PaperIntentValidationResult(intent=intent, accepted=True),),
        intents_seen=1,
        accepted_count=1,
        rejected_count=0,
        sleeves_seen=("active",),
        symbols_seen=("BTCUSDT",),
        venues_seen=("binance",),
        rejection_reasons=(),
        operator_summary="forged accepted before start",
    )

    result = controller.simulate_paper_fills(forged_result)

    assert controller.snapshot().status == PaperShadowSessionStatus.READY
    assert result.fills[0].status == PaperFillStatus.REJECTED_GUARDRAIL
    assert result.real_orders_enabled is False
    assert result.real_money_enabled is False
    assert controller.snapshot().simulated_fills == 0


def test_paper_fill_deterministic_replay() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    market_batch = build_market_event_batch(
        (
            _market_event("ETHUSDT", venue="bybit", ts_ns=_T0_NS + 102, price=2100.0),
            _market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101, price=100.0),
        )
    )
    intent_batch = build_paper_intent_batch(
        (
            _paper_intent("active", "BTCUSDT", venue="binance", intent_ts_ns=_T0_NS + 151),
            _paper_intent("active", "ETHUSDT", venue="bybit", intent_ts_ns=_T0_NS + 152),
        ),
        batch_id="fill-deterministic",
    )

    def run_once() -> tuple[dict, dict]:
        times = iter((_T0_NS + value for value in (1, 2, 3, 4, 5)))
        controller = PaperShadowSessionController(clock_ns=lambda: next(times))
        controller.prepare(plan)
        controller.start()
        controller.record_market_event_batch(market_batch)
        intent_result = controller.record_paper_intent_batch(intent_batch)
        fill_result = controller.simulate_paper_fills(intent_result)
        return paper_fill_simulation_result_to_dict(fill_result), paper_shadow_session_snapshot_to_dict(
            controller.snapshot()
        )

    assert run_once() == run_once()


def test_service_orchestrator_paper_fill_helpers_and_artifacts(tmp_path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    plan = _ready_activation_plan(_sleeve("svc-active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in (110, 111, 112, 113, 114)))
    orch = ServiceOrchestrator(
        service=_mock_service(),
        evidence_store=store,
        readiness_level="paper_live",
        sleeve_workflow_clock_ns=lambda: next(times),
    )
    intent_batch = build_paper_intent_batch(
        (_paper_intent("svc-active", "BTCUSDT", venue="binance"),),
        batch_id="svc-fill-intents",
    )

    orch.prepare_paper_shadow_session(plan=plan)
    orch.start_paper_shadow_session()
    orch.record_paper_shadow_market_event_batch(
        build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101, price=100.0),))
    )
    intent_result = orch.record_paper_intent_batch(intent_batch)
    fill_result = orch.simulate_paper_fills(intent_result)
    rendered = orch.paper_fill_simulation_result_dict(fill_result)
    session = orch.paper_shadow_session_snapshot_dict()
    operator = operator_snapshot_to_dict(orch.operator_snapshot())["paper_shadow_session"]

    assert isinstance(fill_result, PaperFillSimulationResult)
    assert rendered["simulated_fills"] == 1
    assert session["fill_attempts"] == 1
    assert session["simulated_fills"] == 1
    assert session["rejected_fills"] == 0
    assert operator["fill_attempts"] == 1
    assert operator["simulated_fills"] == 1
    assert operator["rejected_fills"] == 0
    assert operator["symbols_filled"] == 1
    assert operator["sleeves_filled"] == 1

    orch.export_paper_fill_simulation_result(fill_result)
    assert orch.load_paper_fill_simulation_result() == fill_result
    export_paper_fill_simulation_result(result=fill_result, evidence_store=store)
    assert load_paper_fill_simulation_result(evidence_store=store) == fill_result

    store.save_snapshot("crypto_paper_fill_simulation_result", ["bad"])
    with pytest.raises(PaperShadowSessionCorruptError):
        load_paper_fill_simulation_result(evidence_store=store)


def test_paper_cost_valid_fill_fee_slippage_computed_deterministically() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in (1, 2, 3, 4, 5, 6)))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))

    controller.prepare(plan)
    controller.start()
    controller.record_market_event_batch(
        build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101, price=100.0),))
    )
    intent_result = controller.record_paper_intent_batch(
        build_paper_intent_batch((_paper_intent("active", "BTCUSDT", venue="binance"),), batch_id="cost-valid")
    )
    fill_result = controller.simulate_paper_fills(intent_result)

    result = controller.evaluate_paper_costs(
        fill_result,
        cost_model=PaperCostModel(fee_bps=10.0, slippage_bps=5.0),
    )
    line = result.costs[0]
    snapshot = controller.snapshot()

    assert result.status == PaperCostStatus.ACCEPTED
    assert result.cost_evaluations == 1
    assert result.accepted_costs == 1
    assert result.rejected_costs == 0
    assert result.gross_notional == pytest.approx(10.0)
    assert result.fee == pytest.approx(0.01)
    assert result.slippage_cost == pytest.approx(0.005)
    assert result.net_notional == pytest.approx(10.015)
    assert result.cost_bps == pytest.approx(15.0)
    assert result.effective_price == pytest.approx(100.05)
    assert line.status == PaperCostStatus.ACCEPTED
    assert line.gross_notional == pytest.approx(10.0)
    assert line.fee == pytest.approx(0.01)
    assert line.slippage_cost == pytest.approx(0.005)
    assert line.effective_price == pytest.approx(100.05)
    assert snapshot.cost_evaluations == 1
    assert snapshot.accepted_costs == 1
    assert snapshot.rejected_costs == 0
    assert snapshot.total_fee == pytest.approx(0.01)
    assert snapshot.total_slippage_cost == pytest.approx(0.005)
    assert paper_cost_result_from_dict(paper_cost_result_to_dict(result)) == result
    assert paper_shadow_session_snapshot_from_dict(paper_shadow_session_snapshot_to_dict(snapshot)) == snapshot


def test_paper_cost_rejected_fill_is_skipped_without_cost_evaluation() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in (1, 2, 3, 4, 5, 6)))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))

    controller.prepare(plan)
    controller.start()
    controller.record_market_event_batch(
        build_market_event_batch(
            (
                _market_event(
                    "BTCUSDT",
                    venue="binance",
                    ts_ns=_T0_NS + 101,
                    event_type=MarketEventType.FUNDING,
                    price=None,
                    funding_rate=0.0001,
                ),
            )
        )
    )
    intent_result = controller.record_paper_intent_batch(
        build_paper_intent_batch((_paper_intent("active", "BTCUSDT", venue="binance"),), batch_id="cost-skipped")
    )
    fill_result = controller.simulate_paper_fills(intent_result)

    result = controller.evaluate_paper_costs(fill_result, cost_model=PaperCostModel(fee_bps=10.0, slippage_bps=5.0))

    assert fill_result.simulated_fills == 0
    assert result.status == PaperCostStatus.SKIPPED
    assert result.cost_evaluations == 0
    assert result.accepted_costs == 0
    assert result.rejected_costs == 0
    assert result.skipped_costs == 1
    assert result.gross_notional == 0.0
    assert result.total_fee == 0.0
    assert result.total_slippage_cost == 0.0
    assert result.costs[0].status == PaperCostStatus.SKIPPED
    assert result.reasons == ("fill_not_filled",)
    assert controller.snapshot().cost_evaluations == 0


def test_paper_cost_invalid_config_fails_closed() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in (1, 2, 3, 4, 5, 6)))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))

    controller.prepare(plan)
    controller.start()
    controller.record_market_event_batch(
        build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101, price=100.0),))
    )
    intent_result = controller.record_paper_intent_batch(
        build_paper_intent_batch((_paper_intent("active", "BTCUSDT", venue="binance"),), batch_id="cost-invalid")
    )
    fill_result = controller.simulate_paper_fills(intent_result)

    with pytest.raises(PaperShadowSessionCorruptError):
        controller.evaluate_paper_costs(fill_result, cost_model=PaperCostModel(fee_bps=-1.0))
    with pytest.raises(PaperShadowSessionCorruptError):
        controller.evaluate_paper_costs(fill_result, cost_model=PaperCostModel(partial_fill_ratio=0.0))
    with pytest.raises(PaperShadowSessionCorruptError):
        controller.evaluate_paper_costs(fill_result, cost_model={"fee_bps": float("nan")})


def test_paper_cost_excessive_cost_rejected_by_threshold() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in (1, 2, 3, 4, 5, 6)))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))

    controller.prepare(plan)
    controller.start()
    controller.record_market_event_batch(
        build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101, price=100.0),))
    )
    intent_result = controller.record_paper_intent_batch(
        build_paper_intent_batch((_paper_intent("active", "BTCUSDT", venue="binance"),), batch_id="cost-threshold")
    )
    fill_result = controller.simulate_paper_fills(intent_result)

    result = controller.evaluate_paper_costs(
        fill_result,
        cost_model=PaperCostModel(fee_bps=20.0, slippage_bps=10.0, reject_if_cost_exceeds_bps=5.0),
    )

    assert result.status == PaperCostStatus.REJECTED_EXCESSIVE_COST
    assert result.cost_evaluations == 1
    assert result.accepted_costs == 0
    assert result.rejected_costs == 1
    assert result.costs[0].cost_bps == pytest.approx(30.0)
    assert result.costs[0].status == PaperCostStatus.REJECTED_EXCESSIVE_COST
    assert result.reasons == ("cost_exceeds_threshold",)
    assert controller.snapshot().rejected_costs == 1


def test_paper_cost_partial_fill_ratio_scales_costs() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in (1, 2, 3, 4, 5, 6)))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))

    controller.prepare(plan)
    controller.start()
    controller.record_market_event_batch(
        build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101, price=100.0),))
    )
    intent_result = controller.record_paper_intent_batch(
        build_paper_intent_batch((_paper_intent("active", "BTCUSDT", venue="binance"),), batch_id="cost-partial")
    )
    fill_result = controller.simulate_paper_fills(intent_result)

    result = controller.evaluate_paper_costs(
        fill_result,
        cost_model=PaperCostModel(fee_bps=10.0, slippage_bps=5.0, partial_fill_ratio=0.5),
    )

    assert result.status == PaperCostStatus.ACCEPTED
    assert result.gross_notional == pytest.approx(5.0)
    assert result.fee == pytest.approx(0.005)
    assert result.slippage_cost == pytest.approx(0.0025)
    assert result.net_notional == pytest.approx(5.0075)
    assert result.cost_bps == pytest.approx(15.0)


def test_paper_cost_deterministic_replay() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    market_batch = build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101),))
    intent_batch = build_paper_intent_batch(
        (_paper_intent("active", "BTCUSDT", venue="binance", intent_ts_ns=_T0_NS + 151),),
        batch_id="cost-deterministic",
    )
    model = PaperCostModel(fee_bps=10.0, slippage_bps=5.0, min_fee=0.001)

    def run_once() -> tuple[dict, dict]:
        times = iter((_T0_NS + value for value in (1, 2, 3, 4, 5, 6)))
        controller = PaperShadowSessionController(clock_ns=lambda: next(times))
        controller.prepare(plan)
        controller.start()
        controller.record_market_event_batch(market_batch)
        intent_result = controller.record_paper_intent_batch(intent_batch)
        fill_result = controller.simulate_paper_fills(intent_result)
        cost_result = controller.evaluate_paper_costs(fill_result, cost_model=model)
        return paper_cost_result_to_dict(cost_result), paper_shadow_session_snapshot_to_dict(controller.snapshot())

    assert run_once() == run_once()


def test_service_orchestrator_paper_cost_helpers_and_artifacts(tmp_path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    plan = _ready_activation_plan(_sleeve("svc-active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in (210, 211, 212, 213, 214, 215)))
    orch = ServiceOrchestrator(
        service=_mock_service(),
        evidence_store=store,
        readiness_level="paper_live",
        sleeve_workflow_clock_ns=lambda: next(times),
    )
    intent_batch = build_paper_intent_batch(
        (_paper_intent("svc-active", "BTCUSDT", venue="binance"),),
        batch_id="svc-cost-intents",
    )

    orch.prepare_paper_shadow_session(plan=plan)
    orch.start_paper_shadow_session()
    orch.record_paper_shadow_market_event_batch(
        build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101, price=100.0),))
    )
    intent_result = orch.record_paper_intent_batch(intent_batch)
    fill_result = orch.simulate_paper_fills(intent_result)
    cost_result = orch.evaluate_paper_costs(fill_result, cost_model=PaperCostModel(fee_bps=10.0, slippage_bps=5.0))
    rendered = orch.paper_cost_result_dict(cost_result)
    session = orch.paper_shadow_session_snapshot_dict()
    operator = operator_snapshot_to_dict(orch.operator_snapshot())["paper_shadow_session"]

    assert rendered["accepted_costs"] == 1
    assert rendered["fee"] == pytest.approx(0.01)
    assert session["cost_evaluations"] == 1
    assert session["accepted_costs"] == 1
    assert session["rejected_costs"] == 0
    assert session["total_fee"] == pytest.approx(0.01)
    assert session["total_slippage_cost"] == pytest.approx(0.005)
    assert operator["cost_evaluations"] == 1
    assert operator["accepted_costs"] == 1
    assert operator["rejected_costs"] == 0
    assert operator["total_fee"] == pytest.approx(0.01)
    assert operator["total_slippage_cost"] == pytest.approx(0.005)

    orch.export_paper_cost_result(cost_result)
    assert orch.load_paper_cost_result() == cost_result
    export_paper_cost_result(result=cost_result, evidence_store=store)
    assert load_paper_cost_result(evidence_store=store) == cost_result

    store.save_snapshot("crypto_paper_cost_result", ["bad"])
    with pytest.raises(PaperShadowSessionCorruptError):
        load_paper_cost_result(evidence_store=store)


def test_paper_pnl_buy_opens_position_with_unrealized_mark() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in range(1, 20)))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))

    controller.prepare(plan)
    controller.start()
    cost_result = _paper_cost_result_for_intent(
        controller,
        batch_id="pnl-buy",
        event_ts_ns=_T0_NS + 101,
        price=100.0,
    )
    ledger = controller.apply_paper_pnl_ledger(cost_result)
    position = ledger.positions[0]
    line = ledger.pnl_lines[0]
    rendered = paper_pnl_ledger_to_dict(ledger)

    assert paper_pnl_ledger_from_dict(rendered) == ledger
    assert ledger.status == PaperPnLStatus.APPLIED
    assert ledger.pnl_events == 1
    assert ledger.open_positions == 1
    assert ledger.closed_positions == 0
    assert ledger.total_fees == pytest.approx(0.01)
    assert ledger.total_slippage == pytest.approx(0.005)
    assert position.qty == pytest.approx(0.10)
    assert position.avg_price == pytest.approx(100.05)
    assert position.gross_notional == pytest.approx(10.0)
    assert position.fees == pytest.approx(0.01)
    assert position.slippage_cost == pytest.approx(0.005)
    assert position.unrealized_pnl == pytest.approx(-0.005)
    assert line.status == PaperPnLStatus.APPLIED
    assert controller.snapshot().pnl_events == 1
    assert controller.snapshot().open_positions == 1


def test_paper_pnl_second_buy_updates_average_price() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in range(1, 30)))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))

    controller.prepare(plan)
    controller.start()
    first_cost = _paper_cost_result_for_intent(
        controller,
        batch_id="pnl-buy-first",
        event_ts_ns=_T0_NS + 101,
        intent_ts_ns=_T0_NS + 151,
        price=100.0,
    )
    first_ledger = controller.apply_paper_pnl_ledger(first_cost)
    second_cost = _paper_cost_result_for_intent(
        controller,
        batch_id="pnl-buy-second",
        event_ts_ns=_T0_NS + 102,
        intent_ts_ns=_T0_NS + 152,
        price=110.0,
    )

    ledger = controller.apply_paper_pnl_ledger(second_cost, prior_ledger=first_ledger)
    position = ledger.positions[0]

    assert ledger.status == PaperPnLStatus.APPLIED
    assert ledger.pnl_events == 2
    assert position.qty == pytest.approx(0.20)
    assert position.avg_price == pytest.approx(105.0525)
    assert position.gross_notional == pytest.approx(21.0)
    assert position.fees == pytest.approx(0.021)
    assert position.slippage_cost == pytest.approx(0.0105)
    assert position.last_price == pytest.approx(110.0)
    assert position.unrealized_pnl == pytest.approx(0.9895)


def test_paper_pnl_sell_realizes_pnl_and_closes_long_only_position() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in range(1, 30)))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))

    controller.prepare(plan)
    controller.start()
    buy_cost = _paper_cost_result_for_intent(
        controller,
        batch_id="pnl-sell-buy",
        event_ts_ns=_T0_NS + 101,
        intent_ts_ns=_T0_NS + 151,
        price=100.0,
    )
    buy_ledger = controller.apply_paper_pnl_ledger(buy_cost)
    sell_cost = _paper_cost_result_for_intent(
        controller,
        side=PaperIntentSide.SELL,
        batch_id="pnl-sell-close",
        event_ts_ns=_T0_NS + 102,
        intent_ts_ns=_T0_NS + 152,
        price=110.0,
    )

    ledger = controller.apply_paper_pnl_ledger(sell_cost, prior_ledger=buy_ledger)
    position = ledger.positions[0]

    assert ledger.status == PaperPnLStatus.APPLIED
    assert ledger.pnl_events == 2
    assert ledger.open_positions == 0
    assert ledger.closed_positions == 1
    assert ledger.realized_pnl == pytest.approx(0.9685)
    assert ledger.unrealized_pnl is None
    assert position.qty == 0.0
    assert position.avg_price is None
    assert position.realized_pnl == pytest.approx(0.9685)
    assert position.fees == pytest.approx(0.021)
    assert position.slippage_cost == pytest.approx(0.0105)


def test_paper_pnl_rejected_cost_is_skipped_fail_closed() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in range(1, 20)))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))

    controller.prepare(plan)
    controller.start()
    cost_result = _paper_cost_result_for_intent(
        controller,
        batch_id="pnl-cost-rejected",
        event_ts_ns=_T0_NS + 101,
        price=100.0,
        cost_model=PaperCostModel(fee_bps=20.0, slippage_bps=10.0, reject_if_cost_exceeds_bps=5.0),
    )

    ledger = controller.apply_paper_pnl_ledger(cost_result)

    assert cost_result.status == PaperCostStatus.REJECTED_EXCESSIVE_COST
    assert ledger.status == PaperPnLStatus.SKIPPED
    assert ledger.reasons == ("cost_not_accepted",)
    assert ledger.pnl_events == 0
    assert ledger.positions == ()
    assert controller.snapshot().pnl_events == 0


def test_paper_pnl_old_cost_payload_missing_position_fields_fails_closed() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in range(1, 20)))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))

    controller.prepare(plan)
    controller.start()
    cost_result = _paper_cost_result_for_intent(
        controller,
        batch_id="pnl-old-cost-payload",
        event_ts_ns=_T0_NS + 101,
        price=100.0,
    )
    old_payload = paper_cost_result_to_dict(cost_result)
    old_payload["costs"][0].pop("qty")
    old_payload["costs"][0].pop("fill_price")
    old_payload["costs"][0].pop("fill_ts_ns")
    restored_old_cost = paper_cost_result_from_dict(old_payload)

    ledger = controller.apply_paper_pnl_ledger(restored_old_cost)

    assert restored_old_cost.status == PaperCostStatus.ACCEPTED
    assert ledger.status == PaperPnLStatus.REJECTED_INVALID_POSITION
    assert ledger.reasons == ("invalid_cost_line_for_position",)
    assert ledger.pnl_events == 0
    assert ledger.positions == ()


def test_paper_pnl_invalid_crossing_short_rejected_fail_closed() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in range(1, 20)))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))

    controller.prepare(plan)
    controller.start()
    cost_result = _paper_cost_result_for_intent(
        controller,
        side=PaperIntentSide.SELL,
        batch_id="pnl-short-rejected",
        event_ts_ns=_T0_NS + 101,
        price=100.0,
    )

    ledger = controller.apply_paper_pnl_ledger(cost_result)

    assert ledger.status == PaperPnLStatus.REJECTED_INVALID_POSITION
    assert ledger.reasons == ("short_or_crossing_sell_rejected",)
    assert ledger.pnl_events == 0
    assert ledger.positions == ()
    assert ledger.pnl_lines[0].position_qty_after == 0.0
    assert ledger.paper_only is True
    assert ledger.real_orders_enabled is False
    assert ledger.real_money_enabled is False


def test_paper_pnl_deterministic_replay() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))

    def run_once() -> tuple[dict, dict]:
        times = iter((_T0_NS + value for value in range(1, 20)))
        controller = PaperShadowSessionController(clock_ns=lambda: next(times))
        controller.prepare(plan)
        controller.start()
        cost_result = _paper_cost_result_for_intent(
            controller,
            batch_id="pnl-deterministic",
            event_ts_ns=_T0_NS + 101,
            intent_ts_ns=_T0_NS + 151,
            price=100.0,
        )
        ledger = controller.apply_paper_pnl_ledger(cost_result)
        return paper_pnl_ledger_to_dict(ledger), paper_shadow_session_snapshot_to_dict(controller.snapshot())

    assert run_once() == run_once()


def test_service_orchestrator_paper_pnl_helpers_and_artifacts(tmp_path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    plan = _ready_activation_plan(_sleeve("svc-active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in range(210, 230)))
    orch = ServiceOrchestrator(
        service=_mock_service(),
        evidence_store=store,
        readiness_level="paper_live",
        sleeve_workflow_clock_ns=lambda: next(times),
    )

    orch.prepare_paper_shadow_session(plan=plan)
    orch.start_paper_shadow_session()
    orch.record_paper_shadow_market_event_batch(
        build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101, price=100.0),))
    )
    intent_result = orch.record_paper_intent_batch(
        build_paper_intent_batch(
            (_paper_intent("svc-active", "BTCUSDT", venue="binance"),),
            batch_id="svc-pnl-intents",
        )
    )
    fill_result = orch.simulate_paper_fills(intent_result)
    cost_result = orch.evaluate_paper_costs(fill_result, cost_model=PaperCostModel(fee_bps=10.0, slippage_bps=5.0))
    ledger = orch.apply_paper_pnl_ledger(cost_result)
    rendered = orch.paper_pnl_ledger_dict(ledger)
    session = orch.paper_shadow_session_snapshot_dict()
    operator = operator_snapshot_to_dict(orch.operator_snapshot())["paper_shadow_session"]

    assert rendered["pnl_events"] == 1
    assert rendered["positions"][0]["avg_price"] == pytest.approx(100.05)
    assert session["pnl_events"] == 1
    assert session["open_positions"] == 1
    assert session["total_fees"] == pytest.approx(0.01)
    assert session["total_slippage"] == pytest.approx(0.005)
    assert operator["pnl_events"] == 1
    assert operator["open_positions"] == 1
    assert operator["closed_positions"] == 0
    assert operator["total_fees"] == pytest.approx(0.01)
    assert operator["total_slippage"] == pytest.approx(0.005)

    orch.export_paper_pnl_ledger(ledger)
    assert orch.load_paper_pnl_ledger() == ledger
    export_paper_pnl_ledger(ledger=ledger, evidence_store=store)
    assert load_paper_pnl_ledger(evidence_store=store) == ledger

    store.save_snapshot("crypto_paper_pnl_ledger", ["bad"])
    with pytest.raises(PaperShadowSessionCorruptError):
        load_paper_pnl_ledger(evidence_store=store)


def test_paper_portfolio_risk_empty_ledger_safe_snapshot() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in range(1, 20)))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))

    controller.prepare(plan)
    controller.start()
    controller.record_market_event_batch(
        build_market_event_batch(
            (
                _market_event(
                    "BTCUSDT",
                    venue="binance",
                    ts_ns=_T0_NS + 101,
                    event_type=MarketEventType.FUNDING,
                    price=None,
                    funding_rate=0.0001,
                ),
            )
        )
    )
    intent_result = controller.record_paper_intent_batch(
        build_paper_intent_batch((_paper_intent("active", "BTCUSDT", venue="binance"),), batch_id="risk-empty")
    )
    fill_result = controller.simulate_paper_fills(intent_result)
    cost_result = controller.evaluate_paper_costs(fill_result, cost_model=PaperCostModel(fee_bps=10.0))
    ledger = controller.apply_paper_pnl_ledger(cost_result)

    risk = controller.paper_portfolio_risk_snapshot(ledger, equity_start=1_000.0)

    assert risk.status == PaperPortfolioRiskStatus.EMPTY
    assert risk.open_position_count == 0
    assert risk.gross_exposure == 0.0
    assert risk.net_exposure == 0.0
    assert risk.unrealized_pnl == 0.0
    assert risk.equity_current == pytest.approx(1_000.0)
    assert risk.reasons == ("drawdown_history_unavailable", "empty_paper_pnl_ledger")
    assert paper_portfolio_risk_snapshot_from_dict(paper_portfolio_risk_snapshot_to_dict(risk)) == risk


def test_paper_portfolio_risk_open_position_uses_latest_market_price() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in range(1, 30)))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))

    controller.prepare(plan)
    controller.start()
    cost_result = _paper_cost_result_for_intent(
        controller,
        batch_id="risk-open",
        event_ts_ns=_T0_NS + 101,
        price=100.0,
    )
    ledger = controller.apply_paper_pnl_ledger(cost_result)
    controller.record_market_event_batch(
        build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 102, price=105.0),))
    )

    risk = controller.paper_portfolio_risk_snapshot(
        ledger,
        equity_start=1_000.0,
        equity_history=(1_000.0, 1_001.0),
    )

    assert risk.status == PaperPortfolioRiskStatus.COMPLETE
    assert risk.reasons == ()
    assert risk.open_position_count == 1
    assert risk.gross_exposure == pytest.approx(10.5)
    assert risk.net_exposure == pytest.approx(10.5)
    assert risk.unrealized_pnl == pytest.approx(0.495)
    assert risk.equity_current == pytest.approx(1_000.495)
    assert risk.drawdown_available is True
    assert risk.max_drawdown == pytest.approx((1_001.0 - 1_000.495) / 1_001.0)


def test_paper_portfolio_risk_missing_price_marks_incomplete() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in range(1, 20)))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))

    controller.prepare(plan)
    controller.start()
    cost_result = _paper_cost_result_for_intent(
        controller,
        batch_id="risk-missing-price",
        event_ts_ns=_T0_NS + 101,
        price=100.0,
    )
    ledger = controller.apply_paper_pnl_ledger(cost_result)

    risk = build_paper_portfolio_risk_snapshot(ledger=ledger, latest_prices=(), equity_start=1_000.0)

    assert risk.status == PaperPortfolioRiskStatus.INCOMPLETE
    assert risk.reasons == ("drawdown_history_unavailable", "missing_latest_market_price")
    assert risk.missing_price_positions == ("paper-position-active-BTCUSDT-binance",)
    assert risk.unrealized_pnl is None
    assert risk.equity_current is None
    assert risk.gross_exposure == 0.0


def test_paper_portfolio_risk_realized_pnl_carried_without_open_exposure() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in range(1, 30)))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))

    controller.prepare(plan)
    controller.start()
    buy_cost = _paper_cost_result_for_intent(
        controller,
        batch_id="risk-realized-buy",
        event_ts_ns=_T0_NS + 101,
        intent_ts_ns=_T0_NS + 151,
        price=100.0,
    )
    buy_ledger = controller.apply_paper_pnl_ledger(buy_cost)
    sell_cost = _paper_cost_result_for_intent(
        controller,
        side=PaperIntentSide.SELL,
        batch_id="risk-realized-sell",
        event_ts_ns=_T0_NS + 102,
        intent_ts_ns=_T0_NS + 152,
        price=110.0,
    )
    ledger = controller.apply_paper_pnl_ledger(sell_cost, prior_ledger=buy_ledger)

    risk = controller.paper_portfolio_risk_snapshot(ledger, equity_start=1_000.0)

    assert risk.status == PaperPortfolioRiskStatus.COMPLETE
    assert risk.realized_pnl == pytest.approx(0.9685)
    assert risk.unrealized_pnl == 0.0
    assert risk.equity_current == pytest.approx(1_000.9685)
    assert risk.gross_exposure == 0.0
    assert risk.open_position_count == 0


def test_paper_portfolio_risk_exposure_aggregation_is_stable() -> None:
    plan = _ready_activation_plan(
        _sleeve("sleeve-a", effective_allocation=0.20, target_allocation=0.20),
        _sleeve("sleeve-b", effective_allocation=0.20, target_allocation=0.20),
    )
    times = iter((_T0_NS + value for value in range(1, 30)))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))

    controller.prepare(plan)
    controller.start()
    controller.record_market_event_batch(
        build_market_event_batch(
            (
                _market_event("ETHUSDT", venue="binance", ts_ns=_T0_NS + 102, price=200.0),
                _market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101, price=100.0),
            )
        )
    )
    intent_result = controller.record_paper_intent_batch(
        build_paper_intent_batch(
            (
                _paper_intent("sleeve-b", "ETHUSDT", venue="binance", intent_ts_ns=_T0_NS + 152),
                _paper_intent("sleeve-a", "BTCUSDT", venue="binance", intent_ts_ns=_T0_NS + 151),
            ),
            batch_id="risk-aggregate",
        )
    )
    fill_result = controller.simulate_paper_fills(intent_result)
    cost_result = controller.evaluate_paper_costs(fill_result, cost_model=PaperCostModel(fee_bps=10.0))
    ledger = controller.apply_paper_pnl_ledger(cost_result)

    risk = controller.paper_portfolio_risk_snapshot(ledger)
    rendered = paper_portfolio_risk_snapshot_to_dict(risk)

    assert risk.status == PaperPortfolioRiskStatus.COMPLETE
    assert risk.gross_exposure == pytest.approx(30.0)
    assert [item["key"] for item in rendered["sleeve_exposures"]] == ["sleeve-a", "sleeve-b"]
    assert [item["gross_exposure"] for item in rendered["sleeve_exposures"]] == pytest.approx([10.0, 20.0])
    assert [item["key"] for item in rendered["symbol_exposures"]] == ["BTCUSDT", "ETHUSDT"]
    assert [item["gross_exposure"] for item in rendered["symbol_exposures"]] == pytest.approx([10.0, 20.0])


def test_paper_portfolio_risk_invalid_equity_inputs_fail_closed() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in range(1, 20)))
    controller = PaperShadowSessionController(clock_ns=lambda: next(times))

    controller.prepare(plan)
    controller.start()
    cost_result = _paper_cost_result_for_intent(controller, batch_id="risk-invalid-equity")
    ledger = controller.apply_paper_pnl_ledger(cost_result)

    with pytest.raises(PaperShadowSessionCorruptError):
        controller.paper_portfolio_risk_snapshot(ledger, equity_start=-1.0)
    with pytest.raises(PaperShadowSessionCorruptError):
        controller.paper_portfolio_risk_snapshot(ledger, equity_history=(1_000.0, float("nan")))


def test_paper_portfolio_risk_deterministic_replay() -> None:
    plan = _ready_activation_plan(_sleeve("active", effective_allocation=0.20, target_allocation=0.20))

    def run_once() -> tuple[dict, dict]:
        times = iter((_T0_NS + value for value in range(1, 30)))
        controller = PaperShadowSessionController(clock_ns=lambda: next(times))
        controller.prepare(plan)
        controller.start()
        cost_result = _paper_cost_result_for_intent(
            controller,
            batch_id="risk-deterministic",
            event_ts_ns=_T0_NS + 101,
            intent_ts_ns=_T0_NS + 151,
            price=100.0,
        )
        ledger = controller.apply_paper_pnl_ledger(cost_result)
        controller.record_market_event_batch(
            build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 102, price=105.0),))
        )
        risk = controller.paper_portfolio_risk_snapshot(
            ledger,
            equity_start=1_000.0,
            equity_history=(1_000.0, 1_001.0),
        )
        return paper_portfolio_risk_snapshot_to_dict(risk), paper_shadow_session_snapshot_to_dict(controller.snapshot())

    assert run_once() == run_once()


def test_service_orchestrator_paper_portfolio_risk_helpers_and_artifacts(tmp_path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    plan = _ready_activation_plan(_sleeve("svc-active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + value for value in range(310, 340)))
    orch = ServiceOrchestrator(
        service=_mock_service(),
        evidence_store=store,
        readiness_level="paper_live",
        sleeve_workflow_clock_ns=lambda: next(times),
    )

    orch.prepare_paper_shadow_session(plan=plan)
    orch.start_paper_shadow_session()
    orch.record_paper_shadow_market_event_batch(
        build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 101, price=100.0),))
    )
    intent_result = orch.record_paper_intent_batch(
        build_paper_intent_batch(
            (_paper_intent("svc-active", "BTCUSDT", venue="binance"),),
            batch_id="svc-risk-intents",
        )
    )
    fill_result = orch.simulate_paper_fills(intent_result)
    cost_result = orch.evaluate_paper_costs(fill_result, cost_model=PaperCostModel(fee_bps=10.0, slippage_bps=5.0))
    ledger = orch.apply_paper_pnl_ledger(cost_result)
    orch.record_paper_shadow_market_event_batch(
        build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 102, price=105.0),))
    )
    risk = orch.paper_portfolio_risk_snapshot(ledger, equity_start=1_000.0, equity_history=(1_000.0,))
    rendered = orch.paper_portfolio_risk_snapshot_dict(risk)

    assert rendered["status"] == "complete"
    assert rendered["gross_exposure"] == pytest.approx(10.5)
    assert rendered["equity_current"] == pytest.approx(1_000.495)
    assert rendered["paper_only"] is True
    assert rendered["real_orders_enabled"] is False
    assert rendered["real_money_enabled"] is False

    orch.export_paper_portfolio_risk_snapshot(risk)
    assert orch.load_paper_portfolio_risk_snapshot() == risk
    export_paper_portfolio_risk_snapshot(snapshot=risk, evidence_store=store)
    assert load_paper_portfolio_risk_snapshot(evidence_store=store) == risk

    store.save_snapshot("crypto_paper_portfolio_risk_snapshot", ["bad"])
    with pytest.raises(PaperShadowSessionCorruptError):
        load_paper_portfolio_risk_snapshot(evidence_store=store)


def test_service_orchestrator_feed_replay_helper_and_artifacts(tmp_path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    plan = _ready_activation_plan(_sleeve("svc-active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 30, _T0_NS + 31, _T0_NS + 32))
    orch = ServiceOrchestrator(
        service=_mock_service(),
        evidence_store=store,
        readiness_level="paper_live",
        sleeve_workflow_clock_ns=lambda: next(times),
    )
    replay = build_feed_replay_plan(
        (build_market_event_batch((_market_event("BTCUSDT", venue="binance", ts_ns=_T0_NS + 130),)),),
        replay_id="orch-feed-replay",
    )

    orch.prepare_paper_shadow_session(plan=plan)
    orch.start_paper_shadow_session()
    result = orch.replay_paper_shadow_feed(replay)
    rendered_plan = orch.paper_shadow_feed_replay_plan_dict(replay)
    rendered_result = orch.paper_shadow_feed_replay_result_dict(result)

    assert result.batches_replayed == 1
    assert result.events_replayed == 1
    assert rendered_plan["replay_id"] == "orch-feed-replay"
    assert rendered_result["guardrail_actions_seen"] == ["none"]
    assert orch.paper_shadow_session_snapshot().event_count == 1

    orch.export_paper_shadow_feed_replay_plan(replay)
    orch.export_paper_shadow_feed_replay_result(result)
    assert orch.load_paper_shadow_feed_replay_plan() == replay
    assert orch.load_paper_shadow_feed_replay_result() == result


def test_service_orchestrator_paper_data_source_helper_replays_and_exports(tmp_path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    plan = _ready_activation_plan(_sleeve("svc-active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 40, _T0_NS + 41, _T0_NS + 42))
    orch = ServiceOrchestrator(
        service=_mock_service(),
        evidence_store=store,
        readiness_level="paper_live",
        sleeve_workflow_clock_ns=lambda: next(times),
    )
    payload = _paper_data_source_payload(
        symbols=("BTCUSDT",),
        records=(
            {
                "symbol": "BTCUSDT",
                "ts_ns": _T0_NS + 140,
                "event_type": "mark_price",
                "price": 101.0,
            },
        ),
    )

    batch_result = orch.paper_data_source_payload_to_batch_result(payload, allowed_source_ids=("local-feed",))
    rendered = orch.paper_data_source_batch_result_dict(batch_result)
    batch = orch.paper_data_source_payload_to_market_event_batch(payload, allowed_source_ids=("local-feed",))

    orch.prepare_paper_shadow_session(plan=plan)
    orch.start_paper_shadow_session()
    replay = orch.replay_paper_data_source_payload(
        payload,
        allowed_source_ids=("local-feed",),
        replay_id="orch-data-source-replay",
    )

    assert rendered["source"]["source_id"] == "local-feed"
    assert batch == batch_result.batch
    assert replay.events_replayed == 1
    assert orch.paper_shadow_session_snapshot().event_count == 1

    orch.export_paper_data_source_batch_result(batch_result)
    assert orch.load_paper_data_source_batch_result() == batch_result


def test_service_orchestrator_paper_shadow_run_evidence_helper_and_artifact(tmp_path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    plan = _ready_activation_plan(_sleeve("svc-active", effective_allocation=0.20, target_allocation=0.20))
    times = iter((_T0_NS + 50, _T0_NS + 51, _T0_NS + 52))
    orch = ServiceOrchestrator(
        service=_mock_service(),
        evidence_store=store,
        readiness_level="paper_live",
        sleeve_workflow_clock_ns=lambda: next(times),
    )
    payload = _paper_data_source_payload(
        symbols=("BTCUSDT",),
        records=(
            {
                "symbol": "BTCUSDT",
                "ts_ns": _T0_NS + 150,
                "event_type": "mark_price",
                "price": 102.0,
            },
        ),
    )

    source_result = orch.paper_data_source_payload_to_batch_result(payload, allowed_source_ids=("local-feed",))
    orch.prepare_paper_shadow_session(plan=plan)
    orch.start_paper_shadow_session()
    replay = orch.replay_paper_shadow_feed(
        build_feed_replay_plan((source_result.batch,), replay_id="orch-run-evidence-replay")
    )
    report = orch.paper_shadow_run_evidence_report(
        source_result=source_result,
        replay_result=replay,
        report_id="orch-run-evidence-report",
    )
    rendered = orch.paper_shadow_run_evidence_report_dict(report)

    assert report.evidence_status == PaperShadowRunEvidenceStatus.PASS
    assert rendered["evidence_status"] == "pass"
    assert rendered["accepted_event_count"] == 1
    assert rendered["source_summary"]["source_id"] == "local-feed"
    assert rendered["replay_summary"]["replay_id"] == "orch-run-evidence-replay"

    orch.export_paper_shadow_run_evidence_report(report)
    assert orch.load_paper_shadow_run_evidence_report() == report


def test_service_orchestrator_multi_source_run_evidence_helper_and_artifact(tmp_path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    _, _, _, first = _paper_shadow_full_local_run(source_id="local-feed-a", report_id="run-a", replay_id="replay-a")
    _, _, _, second = _paper_shadow_full_local_run(source_id="local-feed-b", report_id="run-b", replay_id="replay-b")
    orch = ServiceOrchestrator(
        service=_mock_service(),
        evidence_store=store,
        readiness_level="paper_live",
    )

    aggregate = orch.multi_source_run_evidence_report((second, first), aggregate_id="orch-multi-source")
    rendered = orch.multi_source_run_evidence_report_dict(aggregate)

    assert aggregate.evidence_status == PaperShadowRunEvidenceStatus.PASS
    assert aggregate.report_ids == ("run-a", "run-b")
    assert rendered["evidence_status"] == "pass"
    assert rendered["report_count"] == 2

    orch.export_multi_source_run_evidence_report(aggregate)
    assert orch.load_multi_source_run_evidence_report() == aggregate


def test_service_orchestrator_paper_shadow_evidence_bundle_helper_and_artifact(tmp_path) -> None:
    store = EvidenceStore(evidence_dir=tmp_path / "evidence", config=EvidenceStoreConfig())
    _, _, _, first = _paper_shadow_full_local_run(source_id="local-feed-a", report_id="run-a", replay_id="replay-a")
    _, _, _, second = _paper_shadow_full_local_run(source_id="local-feed-b", report_id="run-b", replay_id="replay-b")
    orch = ServiceOrchestrator(
        service=_mock_service(),
        evidence_store=store,
        readiness_level="paper_live",
    )

    aggregate = orch.multi_source_run_evidence_report((second, first), aggregate_id="orch-bundle-aggregate")
    bundle = orch.paper_shadow_evidence_bundle(
        aggregate_report=aggregate,
        run_reports=(second, first),
        bundle_id="orch-evidence-bundle",
    )
    rendered = orch.paper_shadow_evidence_bundle_dict(bundle)

    assert bundle.evidence_status == PaperShadowRunEvidenceStatus.PASS
    assert bundle.report_ids == ("run-a", "run-b")
    assert rendered["bundle_id"] == "orch-evidence-bundle"
    assert rendered["aggregate_report"]["aggregate_id"] == "orch-bundle-aggregate"
    assert [report["report_id"] for report in rendered["run_reports"]] == ["run-a", "run-b"]

    orch.export_paper_shadow_evidence_bundle(bundle)
    assert orch.load_paper_shadow_evidence_bundle() == bundle
