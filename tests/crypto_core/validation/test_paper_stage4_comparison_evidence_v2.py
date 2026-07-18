"""Tests for SM-6 paper Stage-4 comparison evidence v2 (real enforced secondary metrics)."""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
from dataclasses import FrozenInstanceError, fields, replace
from decimal import Decimal
from pathlib import Path

import pytest

import crypto_core.validation.paper_stage4_comparison_evidence_v2 as comparison_v2_module
from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, validate_strategy_spec
from crypto_core.validation import paper_daily_return_series_evidence as series_module
from crypto_core.validation.paper_30day_evidence_gate_decision import (
    PaperThirtyDayEvidenceGateDecision,
    build_paper_30day_evidence_gate_decision,
    paper_30day_evidence_gate_decision_digest,
)

# --------------------------------------------------------------------------------------------------
# Fixture support (paper-episode substrate for SM-3 records)
# --------------------------------------------------------------------------------------------------
from crypto_core.validation.paper_allocator_intent_draft import (
    PaperAllocatorIntentDraft,
    PaperAllocatorIntentDraftStatus,
    paper_allocator_intent_draft_digest,
)
from crypto_core.validation.paper_capacity_gate import (
    build_paper_capacity_gate_policy,
    evaluate_paper_capacity_gate,
)
from crypto_core.validation.paper_daily_return_series_evidence import (
    PaperDailyReturnBucket,
    PaperDailyReturnSeriesEvidence,
    build_paper_daily_return_series_evidence,
)
from crypto_core.validation.paper_deterministic_time_window_adapter import (
    PaperDeterministicTimeWindowEvidence,
    PaperDeterministicTimeWindowEvidenceStatus,
    paper_deterministic_time_window_evidence_digest,
)
from crypto_core.validation.paper_edge_identity_evidence import (
    PaperEdgeIdentityEvidence,
    build_paper_edge_identity_evidence,
    paper_edge_identity_evidence_digest,
)
from crypto_core.validation.paper_episode_runner import run_paper_episode
from crypto_core.validation.paper_fill_simulator import (
    build_paper_fill_market_snapshot,
    build_paper_fill_policy,
    simulate_paper_fill,
)
from crypto_core.validation.paper_order_intent import build_paper_order_intent
from crypto_core.validation.paper_order_intent_admission import (
    PaperOrderIntentType,
    PaperOrderSide,
    build_paper_order_intent_request,
    evaluate_paper_order_intent_admission,
)
from crypto_core.validation.paper_pnl_report import build_paper_mark_snapshot
from crypto_core.validation.paper_position_state import (
    PaperPositionStateSide,
    apply_paper_fill_to_position,
    build_paper_position_state,
)
from crypto_core.validation.paper_realized_pnl import compute_paper_realized_pnl_event
from crypto_core.validation.paper_return_series_methodology import build_paper_return_series_methodology
from crypto_core.validation.paper_secondary_metrics_enforcement_precondition import (
    PaperSecondaryMetricsEnforcementPrecondition,
    build_paper_secondary_metrics_enforcement_precondition,
    paper_secondary_metrics_enforcement_precondition_digest,
)
from crypto_core.validation.paper_secondary_metrics_evidence import (
    PaperSecondaryMetricsEvidence,
    build_paper_secondary_metrics_evidence,
    paper_secondary_metrics_evidence_digest,
)
from crypto_core.validation.paper_secondary_metrics_substrate_reconciliation import (
    PaperSecondaryMetricsSubstrateRecordInput,
    build_paper_secondary_metrics_substrate_reconciliation,
)
from crypto_core.validation.paper_session_sequence import build_paper_session_sequence
from crypto_core.validation.paper_sharpe_evidence import (
    PaperSharpeEvidence,
    build_paper_sharpe_evidence,
    paper_sharpe_evidence_digest,
)
from crypto_core.validation.paper_stage4_backtest_baseline_evidence import (
    PaperStage4BacktestBaselineEvidence,
    build_paper_stage4_backtest_baseline_evidence,
    paper_stage4_backtest_baseline_evidence_digest,
)
from crypto_core.validation.paper_stage4_comparison_evidence_v2 import (
    PaperStage4ComparisonEvidenceV2,
    PaperStage4ComparisonEvidenceV2Error,
    PaperStage4ComparisonEvidenceV2Status,
    build_paper_stage4_comparison_evidence_v2,
    paper_stage4_comparison_evidence_v2_digest,
    paper_stage4_comparison_evidence_v2_to_dict,
)
from crypto_core.validation.paper_vs_backtest_methodology import build_paper_vs_backtest_methodology
from crypto_core.validation.paper_vs_backtest_methodology_v2 import (
    PaperVsBacktestMethodologyV2,
    build_paper_vs_backtest_methodology_v2,
    paper_vs_backtest_methodology_v2_digest,
)
from crypto_core.validation.secondary_metrics_policy import build_secondary_metrics_policy
from crypto_core.validation.stage4_comparator import (
    Stage4BacktestBaseline,
    Stage4PaperSummary,
    build_stage4_backtest_baseline,
    compare_stage4,
    stage4_backtest_baseline_to_dict,
    stage4_paper_summary_to_dict,
)

_DAY_NS = 86_400_000_000_000
_MARKET = "BTC-PERPETUAL"
_CORRELATION = "corr-1"
_PAPER_ID = "paper-1"
_HEX_A = "a" * 64
_RISK_FREE_POLICY_ID = "constant_zero_daily_review_only.v1"
_RETENTION_THRESHOLD = "0.500000000000000000"

_EXPECTED_FIELD_ORDER = (
    "schema_version",
    "evidence_version",
    "status",
    "ready",
    "comparison_evidence_id",
    "correlation_id",
    "paper_id",
    "series_id",
    "window_id",
    "market_symbol",
    "paper_edge_id",
    "baseline_id",
    "strategy_id",
    "strategy_version",
    "strategy_family",
    "edge_family",
    "market_type",
    "secondary_metrics_policy_id",
    "metrics_evidence_id",
    "enforcement_precondition_id",
    "methodology_v2_id",
    "expected_sharpe_evidence_digest",
    "verified_sharpe_evidence_digest",
    "expected_methodology_v2_digest",
    "verified_methodology_v2_digest",
    "expected_edge_identity_digest",
    "verified_edge_identity_digest",
    "expected_baseline_evidence_digest",
    "verified_baseline_evidence_digest",
    "expected_gate_decision_digest",
    "verified_gate_decision_digest",
    "expected_enforcement_precondition_digest",
    "verified_enforcement_precondition_digest",
    "expected_metrics_evidence_digest",
    "verified_metrics_evidence_digest",
    "verified_secondary_metrics_policy_digest",
    "expected_baseline_digest",
    "baseline_digest",
    "paper_summary_digest",
    "series_digest",
    "time_window_digest",
    "metrics_summary_digest",
    "series_methodology_digest",
    "paper_sharpe_annualized",
    "backtest_sharpe_repr",
    "backtest_sharpe_decimal",
    "sharpe_retention_ratio_decimal",
    "sharpe_retention_threshold",
    "retention_comparison_operator",
    "sharpe_retention_satisfied",
    "min_duration_days",
    "window_duration_ns",
    "bucket_count",
    "duration_satisfied",
    "comparison_verdict",
    "paper_hit_rate",
    "paper_fill_rate_by_quantity",
    "paper_fill_rate_by_episode",
    "paper_slippage_bps",
    "decided_episode_count",
    "record_count",
    "approved_hit_rate_floor",
    "approved_fill_rate_floor",
    "approved_slippage_ceiling_bps",
    "approved_min_decided_episode_count",
    "hit_rate_operator",
    "fill_rate_operator",
    "slippage_operator",
    "hit_rate_floor_satisfied",
    "fill_rate_by_quantity_floor_satisfied",
    "fill_rate_by_episode_floor_satisfied",
    "fill_rate_floor_satisfied",
    "slippage_ceiling_satisfied",
    "min_decided_episode_count_satisfied",
    "secondary_thresholds_cleared",
    "secondary_metrics_source",
    "comparator_fill_rate_echo_policy",
    "comparator_slippage_echo_policy",
    "risk_free_policy_id",
    "annualization_factor",
    "annualization_policy",
    "stddev_policy",
    "decimal_policy",
    "decimal_scale",
    "decimal_rounding",
    "decimal_internal_precision",
    "secondary_metrics_decimal_policy",
    "retention_verdict_policy_id",
    "baseline_sharpe_conversion_policy",
    "sharpe_comparability_basis",
    "paper_trade_count",
    "paper_trade_count_source",
    "stage4_comparator_invoked",
    "comparison_performed",
    "comparator_status_echo",
    "comparator_evaluated_echo",
    "comparator_passed_echo",
    "comparator_sharpe_retention_ratio_echo",
    "comparator_required_min_paper_sharpe_echo",
    "comparator_rejection_reasons_echo",
    "comparator_float_advisory_only",
    "reason_codes",
    "metadata",
    "comparison_evidence_digest",
    "paper_only",
    "thresholds_reapplied_here_not_by_comparator",
    "secondary_metrics_enforced",
    "methodology_v2_consumed",
    "enforcement_precondition_consumed",
    "metrics_evidence_consumed",
    "prdv4_stage4_complete",
    "stage4_completion_decided",
    "thirty_day_gate_decided",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "drawdown_ceiling_enforced",
    "edge_proven",
    "profitability_proven",
    "same_edge_as_backtest_proven",
    "backtest_validity_proven",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "operational_readiness",
    "production_execution",
    "real_orders_enabled",
    "real_fills_used",
    "authoritative_pnl",
    "capital_mutation_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "scheduler_enabled",
    "auto_loop_enabled",
    "connector_invoked",
    "private_api_ready",
    "live_api_called",
    "real_wall_clock_used",
    "real_account_equity_used",
    "real_capital_used",
)

_ALWAYS_FALSE_FLAGS = (
    "prdv4_stage4_complete",
    "stage4_completion_decided",
    "thirty_day_gate_decided",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "drawdown_ceiling_enforced",
    "edge_proven",
    "profitability_proven",
    "same_edge_as_backtest_proven",
    "backtest_validity_proven",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "operational_readiness",
    "production_execution",
    "real_orders_enabled",
    "real_fills_used",
    "authoritative_pnl",
    "capital_mutation_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "scheduler_enabled",
    "auto_loop_enabled",
    "connector_invoked",
    "private_api_ready",
    "live_api_called",
    "real_wall_clock_used",
    "real_account_equity_used",
    "real_capital_used",
)

_uid_counter = [0]


def _uid(prefix: str) -> str:
    _uid_counter[0] += 1
    return f"{prefix}-{_uid_counter[0]}"


def _rc(code: str) -> str:
    return f"paper_stage4_comparison_evidence_v2:{code}"


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _canonical(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _scale18(value: object) -> str:
    return format(Decimal(str(value)).quantize(Decimal("1E-18")), "f")


# --------------------------------------------------------------------------------------------------
# v1-lineage fixture chain (spec -> edge identity -> baseline evidence; series -> sharpe + gate)
# --------------------------------------------------------------------------------------------------


def _spec() -> StrategySpec:
    payload: dict[str, object] = {
        "schema_version": "strategy-spec.v1",
        "strategy_id": "alpha-funding-carry",
        "strategy_version": "1.0.0",
        "strategy_family": "carry",
        "edge_family": "funding_basis_carry",
        "instrument_universe": ["BTC-PERPETUAL", "ETH-PERPETUAL"],
        "market_type": "usdt_perp",
        "venue_assumptions": ["perp_linear"],
        "timeframe": "1h",
        "bar_definition": "time_1h",
        "entry_conditions": ["funding_positive"],
        "exit_conditions": ["funding_neutral"],
        "invalidation_conditions": ["regime_break"],
        "risk_caps": {"max_leverage": 2.0},
        "data_requirements": {"funding_rate": "1h"},
        "feature_requirements": {"funding_zscore": "rolling"},
        "latency_sensitivity": "low",
        "funding_sensitivity": "high",
        "fee_model_requirement": "taker_10bps",
        "slippage_model_requirement": "depth_aware",
        "expected_regime": "ranging",
        "failure_modes": ["funding_flip"],
        "kill_switch_triggers": ["max_dd"],
        "telemetry_fields": ["funding"],
        "promotion_requirements": ["walk_forward"],
    }
    result = validate_strategy_spec(payload)
    assert result.accepted, result.rejection_reasons + result.needs_research_reasons
    assert result.spec is not None
    return result.spec


def _edge_identity() -> PaperEdgeIdentityEvidence:
    spec = _spec()
    evidence = build_paper_edge_identity_evidence(
        spec,
        expected_strategy_spec_digest=strategy_spec_digest(spec),
        market_symbol=_MARKET,
        edge_identity_id="edge-identity-1",
        paper_id=_PAPER_ID,
        correlation_id=_CORRELATION,
        metadata={"purpose": "paper edge identity"},
    )
    assert evidence.ready, evidence.reason_codes
    return evidence


def _baseline(edge_id: str) -> Stage4BacktestBaseline:
    return build_stage4_backtest_baseline(
        baseline_id="baseline-1",
        edge_id=edge_id,
        as_of_ns=1_700_000_000_000_000_000,
        backtest_sharpe=1.5,
        backtest_hit_rate=0.55,
        backtest_slippage_bps=2.0,
        backtest_fill_rate=0.9,
        source_window_ids=("wf-1", "wf-2"),
    )


def _baseline_digest(baseline: Stage4BacktestBaseline) -> str:
    return _canonical(stage4_backtest_baseline_to_dict(baseline))


def _baseline_evidence(
    edge: PaperEdgeIdentityEvidence, baseline: Stage4BacktestBaseline
) -> PaperStage4BacktestBaselineEvidence:
    return build_paper_stage4_backtest_baseline_evidence(
        baseline,
        expected_baseline_digest=_baseline_digest(baseline),
        edge_identity=edge,
        expected_edge_identity_digest=edge.edge_identity_digest,
        baseline_evidence_id="baseline-evidence-1",
        correlation_id=_CORRELATION,
        metadata={"purpose": "stage4 baseline binding"},
    )


def _window(*, days: int = 30) -> PaperDeterministicTimeWindowEvidence:
    fields_payload: dict[str, object] = {
        "schema_version": "paper-deterministic-time-window-evidence.v1",
        "time_window_version": "paper-deterministic-time-window.v1",
        "status": PaperDeterministicTimeWindowEvidenceStatus.READY,
        "ready": True,
        "window_id": "window-1",
        "methodology_id": "method-1",
        "timestamp_policy": "injected_deterministic_ns.v1",
        "run_id": "run-1",
        "aggregate_id": "agg-1",
        "correlation_id": _CORRELATION,
        "market_symbol": _MARKET,
        "expected_metrics_summary_digest": _HEX_A,
        "metrics_summary_digest": _HEX_A,
        "summary_ready": True,
        "summary_readiness_verdict": "PAPER_STAGE4_CANDIDATE",
        "started_at_ns": _DAY_NS,
        "stopped_at_ns": (days + 1) * _DAY_NS,
        "window_duration_ns": days * _DAY_NS,
        "sample_observation_count": days,
        "sample_eligible": True,
        "session_bridge_count": 1,
        "episode_count_total": 1,
        "event_count": 1,
        "computed_event_count": 1,
        "no_realized_event_count": 0,
        "source_event_digest_count": 1,
        "closed_units_total": "1",
        "realized_pnl_total": "1",
        "abs_realized_pnl_total": "1",
        "reason_codes": (),
        "metadata": (),
    }
    seed = PaperDeterministicTimeWindowEvidence(time_window_digest="", **fields_payload)  # type: ignore[arg-type]
    return replace(seed, time_window_digest=paper_deterministic_time_window_evidence_digest(seed))


def _bucket(day: int, start: str, end: str) -> PaperDailyReturnBucket:
    seed = PaperDailyReturnBucket(
        bucket_id=f"bucket-{day + 1}",
        bucket_start_ns=(day + 1) * _DAY_NS,
        bucket_end_ns=(day + 2) * _DAY_NS,
        normalized_index_start=start,
        normalized_index_end=end,
        bucket_digest="",
    )
    return replace(seed, bucket_digest=series_module._bucket_digest(seed))  # noqa: SLF001


def _buckets_from_returns(returns: list) -> tuple[PaperDailyReturnBucket, ...]:
    from fractions import Fraction

    index = Fraction(1)
    path = [index]
    for daily_return in returns:
        index = index * (Fraction(1) + daily_return)
        path.append(index)
    render = series_module._finite_decimal_string  # noqa: SLF001
    return tuple(_bucket(day, render(path[day]), render(path[day + 1])) for day in range(len(returns)))


def _series(*, days: int = 30) -> PaperDailyReturnSeriesEvidence:
    from fractions import Fraction

    methodology = build_paper_return_series_methodology(
        methodology_id="method-1",
        correlation_id=_CORRELATION,
        mtm_policy_id="mtm-policy-1",
        fee_policy_id="fee-policy-1",
        funding_policy_id="funding-policy-1",
        mark_policy_id="mark-policy-1",
        exposure_policy_id="exposure-policy-1",
        liquidation_policy_id="liquidation-policy-1",
        risk_free_policy_id=_RISK_FREE_POLICY_ID,
    )
    window = _window(days=days)
    returns = [Fraction(1) if day % 2 == 0 else Fraction(-1, 2) for day in range(days)]
    series = build_paper_daily_return_series_evidence(
        methodology,
        window,
        expected_methodology_digest=methodology.methodology_digest,
        expected_time_window_digest=window.time_window_digest,
        series_id="series-1",
        correlation_id=_CORRELATION,
        daily_buckets=_buckets_from_returns(returns),
        metadata={"purpose": "daily return series"},
    )
    assert series.ready, series.reason_codes
    return series


def _sharpe(series: PaperDailyReturnSeriesEvidence) -> PaperSharpeEvidence:
    evidence = build_paper_sharpe_evidence(
        series,
        expected_daily_return_series_digest=series.series_digest,
        risk_free_policy_id=_RISK_FREE_POLICY_ID,
        sharpe_evidence_id="sharpe-evidence-1",
        paper_id=_PAPER_ID,
        correlation_id=_CORRELATION,
        metadata={"purpose": "paper sharpe"},
    )
    assert evidence.ready, evidence.reason_codes
    return evidence


def _gate(series: PaperDailyReturnSeriesEvidence) -> PaperThirtyDayEvidenceGateDecision:
    decision = build_paper_30day_evidence_gate_decision(
        series,
        expected_series_digest=series.series_digest,
        gate_id="gate-1",
        correlation_id=_CORRELATION,
        metadata={"purpose": "thirty day gate"},
    )
    assert decision.ready, decision.reason_codes
    assert decision.thirty_day_gate_satisfied is True
    return decision


# --------------------------------------------------------------------------------------------------
# SM fixture chain (policy -> SM-3 records -> SM-4 -> reconciliation -> precondition -> methodology v2)
# --------------------------------------------------------------------------------------------------


def _make_draft() -> PaperAllocatorIntentDraft:
    fields_map: dict[str, object] = {
        "schema_version": "paper-allocator-intent-draft.v1",
        "status": PaperAllocatorIntentDraftStatus.DRAFT_READY,
        "sleeve_id": "sleeve-alpha",
        "policy_id": "policy-alpha",
        "readiness_digest": _HEX_A,
        "promotion_readiness_journal_entry_digest": _HEX_A,
        "promotion_readiness_payload_digest": _HEX_A,
        "promotion_candidate_journal_entry_digest": _HEX_A,
        "decision_journal_entry_digest": _HEX_A,
        "decision_journal_payload_digest": _HEX_A,
        "eligible_count": 2,
        "blocked_count": 0,
        "insufficient_count": 0,
        "blockers": (),
        "correlation_id": "corr-draft",
        "metadata": (),
    }
    draft = PaperAllocatorIntentDraft(**fields_map, draft_digest="")  # type: ignore[arg-type]
    return replace(draft, draft_digest=paper_allocator_intent_draft_digest(draft))


def _order_intent(side: PaperOrderSide):
    cap_policy = build_paper_capacity_gate_policy(
        policy_id="policy-alpha",
        sleeve_id="sleeve-alpha",
        max_notional="100000000",
        max_units="100000",
        max_open_intents=5,
    )
    capacity = evaluate_paper_capacity_gate(
        _make_draft(),
        cap_policy,
        requested_notional="100000",
        requested_units="1",
        correlation_id="corr-capacity",
    )
    request = build_paper_order_intent_request(
        request_id=_uid("req"),
        capacity_decision_digest=capacity.decision_digest,
        market_symbol=_MARKET,
        side=side,
        intent_type=PaperOrderIntentType.MARKET,
        requested_notional=capacity.requested_notional,
        requested_units=capacity.requested_units,
        limit_price=None,
        correlation_id="corr-req",
    )
    admission = evaluate_paper_order_intent_admission(capacity, request, correlation_id="corr-admit")
    return build_paper_order_intent(admission, intent_id=_uid("intent"), correlation_id="corr-intent")


def _short_prior():
    return build_paper_position_state(
        position_state_id=_uid("pos"),
        market_symbol=_MARKET,
        side=PaperPositionStateSide.SHORT,
        signed_units="-2",
        abs_units="2",
        average_entry_price="100",
        transition_count=0,
        correlation_id="corr-pos",
    )


def _snapshot(reference_price: str):
    return build_paper_fill_market_snapshot(
        snapshot_id=_uid("snap"),
        market_symbol=_MARKET,
        reference_price=reference_price,
    )


def _fill_policy():
    return build_paper_fill_policy(
        policy_id="fill-policy-1",
        slippage_bps="0",
        fee_rate_bps="0",
        allow_partial_fill=False,
    )


def _mark():
    return build_paper_mark_snapshot(
        mark_snapshot_id=_uid("mark"),
        market_symbol=_MARKET,
        mark_price="100",
        correlation_id="corr-mark",
    )


def _closing_bundle(episode_id: str, record_id: str, *, reference_price: str):
    from crypto_core.validation.trade_record_evidence import build_trade_record_evidence

    prior = _short_prior()
    intent = _order_intent(PaperOrderSide.BUY)
    snapshot = _snapshot(reference_price)
    ids: dict[str, object] = {
        "fill_simulation_id": _uid("fillsim"),
        "position_transition_id": _uid("trans"),
        "new_position_state_id": _uid("newpos"),
        "pnl_report_id": _uid("pnl"),
        "episode_run_id": episode_id,
        "correlation_id": _CORRELATION,
    }
    episode = run_paper_episode(intent, prior, snapshot, _fill_policy(), _mark(), **ids)  # type: ignore[arg-type]
    fill_result = simulate_paper_fill(
        intent,
        snapshot,
        _fill_policy(),
        fill_simulation_id=ids["fill_simulation_id"],
        correlation_id=_CORRELATION,
    )
    transition, new_state = apply_paper_fill_to_position(
        prior,
        fill_result,
        transition_id=ids["position_transition_id"],
        new_position_state_id=ids["new_position_state_id"],
        correlation_id=_CORRELATION,
    )
    event = compute_paper_realized_pnl_event(
        prior,
        fill_result,
        transition,
        new_state,
        realized_pnl_event_id=_uid("rp"),
        correlation_id=_CORRELATION,
    )
    filled = Decimal(fill_result.filled_units)
    unfilled = Decimal(fill_result.unfilled_units)
    record = build_trade_record_evidence(
        record_id=record_id,
        correlation_id=_CORRELATION,
        sleeve_id="sleeve-1",
        policy_id="policy-1",
        episode_id=episode_id,
        strategy_id="strategy-1",
        decision_id=_uid("decision"),
        intended_quantity=_scale18(filled + unfilled),
        filled_quantity=_scale18(filled),
        expected_fill_price="100.000000000000000000",
        realized_fill_price=_scale18(fill_result.fill_price),
        realized_pnl=_scale18(event.realized_pnl),
        decided_episode=True,
    )
    return episode, fill_result, event, record


def _policy():
    return build_secondary_metrics_policy(
        policy_id="policy-1",
        correlation_id=_CORRELATION,
        expected_fill_model_parameters_digest=_HEX_A,
        approved_hit_rate_floor="0.500000000000000000",
        approved_fill_rate_floor="0.900000000000000000",
        approved_slippage_ceiling_bps="25.000000000000000000",
        approved_min_decided_episode_count=1,
        approval_reference="gov-sm2-1",
        approval_digest="b" * 64,
        thresholds_approved=True,
    )


class _Chain:
    """Complete READY 8-anchor chain: v1 lineage + policy/records/SM-4/reconciliation/precondition/mv2."""

    def __init__(self) -> None:
        self.edge = _edge_identity()
        self.baseline = _baseline(self.edge.paper_edge_id)
        self.baseline_evidence = _baseline_evidence(self.edge, self.baseline)
        self.series = _series()
        self.sharpe = _sharpe(self.series)
        self.gate = _gate(self.series)
        self.policy = _policy()
        self.bundles = [
            _closing_bundle("ep-0", "rec-0", reference_price="95"),
            _closing_bundle("ep-1", "rec-1", reference_price="96"),
        ]
        self.inputs = [
            PaperSecondaryMetricsSubstrateRecordInput(record, episode, fill_result, event)
            for (episode, fill_result, event, record) in self.bundles
        ]
        self.records = [record for (_, _, _, record) in self.bundles]
        self.metrics = build_paper_secondary_metrics_evidence(
            self.policy,
            self.records,
            evidence_id="sm4-1",
            correlation_id=_CORRELATION,
        )
        assert self.metrics.ready, self.metrics.reason_codes
        self.session = build_paper_session_sequence(
            [episode for (episode, _, _, _) in self.bundles],
            paper_session_id="ps-1",
            correlation_id=_CORRELATION,
        )
        self.reconciliation = build_paper_secondary_metrics_substrate_reconciliation(
            self.policy,
            self.metrics,
            self.inputs,
            self.session,
            reconciliation_id="recon-1",
            correlation_id=_CORRELATION,
            expected_policy_digest=self.policy.policy_digest,
            expected_metrics_evidence_digest=self.metrics.evidence_digest,
            expected_session_sequence_digest=self.session.paper_session_sequence_digest,
        )
        self.precondition = self._precondition(self.metrics, self.reconciliation, precondition_id="precondition-1")
        assert self.precondition.ready, self.precondition.reason_codes
        self.predecessor = build_paper_vs_backtest_methodology(
            methodology_id="meth-v1-1",
            correlation_id=_CORRELATION,
            sharpe_retention_ratio=_RETENTION_THRESHOLD,
            min_duration_days=30,
            risk_free_policy_id=_RISK_FREE_POLICY_ID,
        )
        self.methodology_v2 = self._methodology_v2(self.precondition)
        assert self.methodology_v2.ready, self.methodology_v2.reason_codes

    def _precondition(
        self, metrics, reconciliation, *, precondition_id: str
    ) -> PaperSecondaryMetricsEnforcementPrecondition:
        return build_paper_secondary_metrics_enforcement_precondition(
            self.policy,
            metrics,
            reconciliation,
            precondition_id=precondition_id,
            correlation_id=_CORRELATION,
            expected_policy_digest=self.policy.policy_digest,
            expected_metrics_evidence_digest=metrics.evidence_digest,
            expected_reconciliation_digest=reconciliation.reconciliation_digest,
        )

    def _methodology_v2(self, precondition) -> PaperVsBacktestMethodologyV2:
        return build_paper_vs_backtest_methodology_v2(
            self.predecessor,
            self.policy,
            precondition,
            expected_predecessor_methodology_digest=self.predecessor.methodology_digest,
            expected_secondary_metrics_policy_digest=self.policy.policy_digest,
            expected_secondary_metrics_enforcement_precondition_digest=precondition.precondition_digest,
            methodology_id="sm5-1",
            correlation_id=_CORRELATION,
        )


_CHAIN_CACHE: list[_Chain] = []


def _chain() -> _Chain:
    if not _CHAIN_CACHE:
        _CHAIN_CACHE.append(_Chain())
    return _CHAIN_CACHE[0]


# --------------------------------------------------------------------------------------------------
# Reseal helpers (recompute the anchor's public self-digest; rebind downstream digest references)
# --------------------------------------------------------------------------------------------------


def _reseal_sharpe(evidence: PaperSharpeEvidence, **changes: object) -> PaperSharpeEvidence:
    seed = replace(evidence, **changes)  # type: ignore[arg-type]
    return replace(seed, sharpe_evidence_digest=paper_sharpe_evidence_digest(seed))


def _reseal_gate(decision: PaperThirtyDayEvidenceGateDecision, **changes: object) -> PaperThirtyDayEvidenceGateDecision:
    seed = replace(decision, **changes)  # type: ignore[arg-type]
    return replace(seed, decision_digest=paper_30day_evidence_gate_decision_digest(seed))


def _reseal_edge(evidence: PaperEdgeIdentityEvidence, **changes: object) -> PaperEdgeIdentityEvidence:
    seed = replace(evidence, **changes)  # type: ignore[arg-type]
    return replace(seed, edge_identity_digest=paper_edge_identity_evidence_digest(seed))


def _reseal_baseline_evidence(
    evidence: PaperStage4BacktestBaselineEvidence, **changes: object
) -> PaperStage4BacktestBaselineEvidence:
    seed = replace(evidence, **changes)  # type: ignore[arg-type]
    return replace(seed, baseline_evidence_digest=paper_stage4_backtest_baseline_evidence_digest(seed))


def _reseal_methodology_v2(
    methodology: PaperVsBacktestMethodologyV2, **changes: object
) -> PaperVsBacktestMethodologyV2:
    seed = replace(methodology, **changes)  # type: ignore[arg-type]
    return replace(seed, methodology_digest=paper_vs_backtest_methodology_v2_digest(seed))


def _reseal_precondition(
    precondition: PaperSecondaryMetricsEnforcementPrecondition, **changes: object
) -> PaperSecondaryMetricsEnforcementPrecondition:
    seed = replace(precondition, **changes)  # type: ignore[arg-type]
    return replace(seed, precondition_digest=paper_secondary_metrics_enforcement_precondition_digest(seed))


def _reseal_metrics(metrics: PaperSecondaryMetricsEvidence, **changes: object) -> PaperSecondaryMetricsEvidence:
    seed = replace(metrics, **changes)  # type: ignore[arg-type]
    return replace(seed, evidence_digest=paper_secondary_metrics_evidence_digest(seed))


def _resealed_sm(
    chain: _Chain,
    *,
    metrics_changes: dict[str, object] | None = None,
    precondition_changes: dict[str, object] | None = None,
):
    """Coherent adversarial SM reseal: metrics -> precondition rebind -> methodology-v2 rebind.

    Every reseal recomputes the anchor's public self-digest and rebinds every downstream digest reference,
    so all digest triples pass and only the mutated VALUES can cause rejection — proving the consumer
    recomputes rather than trusting digest validity or carried booleans.
    """

    metrics2 = _reseal_metrics(chain.metrics, **(metrics_changes or {}))
    pre_changes: dict[str, object] = {"metrics_evidence_digest": metrics2.evidence_digest}
    pre_changes.update(precondition_changes or {})
    precondition2 = _reseal_precondition(chain.precondition, **pre_changes)
    methodology2 = _reseal_methodology_v2(
        chain.methodology_v2,
        verified_secondary_metrics_enforcement_precondition_digest=precondition2.precondition_digest,
    )
    return metrics2, precondition2, methodology2


def _carried_or_placeholder(value: object) -> str:
    return value if _is_hex64(value) else _HEX_A


def _build(**overrides: object) -> PaperStage4ComparisonEvidenceV2:
    chain = _chain()
    backtest_baseline = overrides.pop("backtest_baseline", chain.baseline)
    baseline_evidence = overrides.pop("baseline_evidence", chain.baseline_evidence)
    sharpe_evidence = overrides.pop("sharpe_evidence", chain.sharpe)
    methodology_v2 = overrides.pop("methodology_v2", chain.methodology_v2)
    edge_identity = overrides.pop("edge_identity", chain.edge)
    gate_decision = overrides.pop("gate_decision", chain.gate)
    enforcement_precondition = overrides.pop("enforcement_precondition", chain.precondition)
    metrics_evidence = overrides.pop("metrics_evidence", chain.metrics)
    payload: dict[str, object] = {
        "expected_baseline_digest": (
            _baseline_digest(backtest_baseline)  # type: ignore[arg-type]
            if type(backtest_baseline) is Stage4BacktestBaseline
            else _HEX_A
        )
        if "expected_baseline_digest" not in overrides
        else overrides.pop("expected_baseline_digest"),
        "baseline_evidence": baseline_evidence,
        "expected_baseline_evidence_digest": _carried_or_placeholder(
            getattr(baseline_evidence, "baseline_evidence_digest", "")
        ),
        "sharpe_evidence": sharpe_evidence,
        "expected_sharpe_evidence_digest": _carried_or_placeholder(
            getattr(sharpe_evidence, "sharpe_evidence_digest", "")
        ),
        "methodology_v2": methodology_v2,
        "expected_methodology_v2_digest": _carried_or_placeholder(getattr(methodology_v2, "methodology_digest", "")),
        "edge_identity": edge_identity,
        "expected_edge_identity_digest": _carried_or_placeholder(getattr(edge_identity, "edge_identity_digest", "")),
        "gate_decision": gate_decision,
        "expected_gate_decision_digest": _carried_or_placeholder(getattr(gate_decision, "decision_digest", "")),
        "enforcement_precondition": enforcement_precondition,
        "expected_enforcement_precondition_digest": _carried_or_placeholder(
            getattr(enforcement_precondition, "precondition_digest", "")
        ),
        "metrics_evidence": metrics_evidence,
        "expected_metrics_evidence_digest": _carried_or_placeholder(getattr(metrics_evidence, "evidence_digest", "")),
        "comparison_evidence_id": "comparison-evidence-v2-1",
        "correlation_id": _CORRELATION,
        "metadata": {"purpose": "stage4 comparison v2"},
    }
    payload.update(overrides)
    return build_paper_stage4_comparison_evidence_v2(backtest_baseline, **payload)  # type: ignore[arg-type]


def _assert_rejected_with(evidence: PaperStage4ComparisonEvidenceV2, reason: str) -> None:
    assert evidence.status is PaperStage4ComparisonEvidenceV2Status.REJECTED
    assert evidence.ready is False
    assert _rc(reason) in evidence.reason_codes, evidence.reason_codes
    assert evidence.secondary_metrics_enforced is False
    assert evidence.prdv4_stage4_complete is False


# --------------------------------------------------------------------------------------------------
# 1. Public contract
# --------------------------------------------------------------------------------------------------


def test_public_api_exact() -> None:
    assert comparison_v2_module.__all__ == [
        "PaperStage4ComparisonEvidenceV2",
        "PaperStage4ComparisonEvidenceV2Error",
        "PaperStage4ComparisonEvidenceV2Status",
        "build_paper_stage4_comparison_evidence_v2",
        "paper_stage4_comparison_evidence_v2_digest",
        "paper_stage4_comparison_evidence_v2_to_dict",
    ]
    assert [status.value for status in PaperStage4ComparisonEvidenceV2Status] == ["READY", "REJECTED"]


def test_dataclass_field_order_exact() -> None:
    names = tuple(field.name for field in fields(PaperStage4ComparisonEvidenceV2))
    assert names == _EXPECTED_FIELD_ORDER
    assert len(names) == 139


def test_builder_signature_exact() -> None:
    parameters = inspect.signature(build_paper_stage4_comparison_evidence_v2).parameters
    assert list(parameters) == [
        "backtest_baseline",
        "expected_baseline_digest",
        "baseline_evidence",
        "expected_baseline_evidence_digest",
        "sharpe_evidence",
        "expected_sharpe_evidence_digest",
        "methodology_v2",
        "expected_methodology_v2_digest",
        "edge_identity",
        "expected_edge_identity_digest",
        "gate_decision",
        "expected_gate_decision_digest",
        "enforcement_precondition",
        "expected_enforcement_precondition_digest",
        "metrics_evidence",
        "expected_metrics_evidence_digest",
        "comparison_evidence_id",
        "correlation_id",
        "metadata",
    ]
    assert parameters["backtest_baseline"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert all(parameters[name].kind is inspect.Parameter.KEYWORD_ONLY for name in list(parameters)[1:])


def test_output_is_frozen() -> None:
    evidence = _build()
    with pytest.raises(FrozenInstanceError):
        evidence.ready = False  # type: ignore[misc]


def test_digest_is_deterministic_and_metadata_order_independent() -> None:
    first = _build(metadata={"b": "2", "a": "1"})
    second = _build(metadata={"a": "1", "b": "2"})
    changed = _build(metadata={"a": "1", "b": "3"})
    assert first.comparison_evidence_digest == second.comparison_evidence_digest
    assert changed.comparison_evidence_digest != first.comparison_evidence_digest
    assert first.comparison_evidence_digest == paper_stage4_comparison_evidence_v2_digest(first)


def test_serializer_is_fields_complete_and_excludes_only_self_digest() -> None:
    evidence = _build(metadata={"b": "2", "a": "1"})
    payload = paper_stage4_comparison_evidence_v2_to_dict(evidence)
    resealed = replace(evidence, comparison_evidence_digest="0" * 64)
    assert set(payload) == {field.name for field in fields(evidence)}
    assert payload["status"] == evidence.status.value
    assert payload["metadata"] == [["a", "1"], ["b", "2"]]
    assert payload["reason_codes"] == list(evidence.reason_codes)
    assert paper_stage4_comparison_evidence_v2_digest(resealed) == evidence.comparison_evidence_digest
    assert payload["comparison_evidence_digest"] == evidence.comparison_evidence_digest


def test_output_reseal_is_detectable() -> None:
    evidence = _build()
    forged = replace(evidence, secondary_metrics_enforced=False, ready=True)
    assert paper_stage4_comparison_evidence_v2_digest(forged) != evidence.comparison_evidence_digest


# --------------------------------------------------------------------------------------------------
# 2. Happy READY (real enforced metrics; first artifact allowed secondary_metrics_enforced=True)
# --------------------------------------------------------------------------------------------------


def test_happy_ready_retention_satisfied_with_enforced_secondary_metrics() -> None:
    chain = _chain()
    evidence = _build()
    assert evidence.status is PaperStage4ComparisonEvidenceV2Status.READY
    assert evidence.ready is True
    assert evidence.reason_codes == ()
    assert evidence.comparison_verdict == "RETENTION_SATISFIED"
    assert evidence.sharpe_retention_satisfied is True
    assert evidence.duration_satisfied is True
    assert evidence.stage4_comparator_invoked is True
    assert evidence.comparison_performed is True
    assert evidence.comparator_float_advisory_only is True
    assert evidence.secondary_metrics_enforced is True
    assert evidence.thresholds_reapplied_here_not_by_comparator is True
    assert evidence.methodology_v2_consumed is True
    assert evidence.enforcement_precondition_consumed is True
    assert evidence.metrics_evidence_consumed is True
    assert evidence.secondary_thresholds_cleared is True
    assert evidence.hit_rate_floor_satisfied is True
    assert evidence.fill_rate_by_quantity_floor_satisfied is True
    assert evidence.fill_rate_by_episode_floor_satisfied is True
    assert evidence.fill_rate_floor_satisfied is True
    assert evidence.slippage_ceiling_satisfied is True
    assert evidence.min_decided_episode_count_satisfied is True
    assert evidence.paper_hit_rate == chain.metrics.hit_rate
    assert evidence.paper_fill_rate_by_quantity == chain.metrics.fill_rate_by_quantity
    assert evidence.paper_fill_rate_by_episode == chain.metrics.fill_rate_by_episode
    assert evidence.paper_slippage_bps == chain.metrics.average_slippage_bps
    assert evidence.paper_slippage_bps is not None
    assert evidence.decided_episode_count == chain.metrics.decided_episode_count
    assert evidence.record_count == chain.metrics.record_count
    assert evidence.paper_trade_count == chain.metrics.record_count
    assert evidence.paper_trade_count_source == "secondary_metrics_record_count.v2"
    assert evidence.secondary_metrics_source == "direct_sm4_evidence_decimal_reapplied.v2"
    assert evidence.schema_version == "paper-stage4-comparison-evidence.v2"
    assert evidence.evidence_version == "paper-stage4-comparison-evidence.v2"


def test_ready_identity_and_chain_bindings() -> None:
    chain = _chain()
    evidence = _build()
    assert evidence.paper_id == _PAPER_ID
    assert evidence.market_symbol == _MARKET
    assert evidence.paper_edge_id == chain.edge.paper_edge_id
    assert evidence.baseline_id == "baseline-1"
    assert evidence.secondary_metrics_policy_id == "policy-1"
    assert evidence.metrics_evidence_id == "sm4-1"
    assert evidence.enforcement_precondition_id == "precondition-1"
    assert evidence.methodology_v2_id == "sm5-1"
    assert evidence.expected_sharpe_evidence_digest == evidence.verified_sharpe_evidence_digest
    assert evidence.expected_methodology_v2_digest == evidence.verified_methodology_v2_digest
    assert evidence.expected_edge_identity_digest == evidence.verified_edge_identity_digest
    assert evidence.expected_baseline_evidence_digest == evidence.verified_baseline_evidence_digest
    assert evidence.expected_gate_decision_digest == evidence.verified_gate_decision_digest
    assert evidence.expected_enforcement_precondition_digest == evidence.verified_enforcement_precondition_digest
    assert evidence.expected_metrics_evidence_digest == evidence.verified_metrics_evidence_digest
    assert evidence.verified_metrics_evidence_digest == chain.metrics.evidence_digest
    assert evidence.verified_enforcement_precondition_digest == chain.precondition.precondition_digest
    assert evidence.verified_secondary_metrics_policy_digest == chain.policy.policy_digest
    assert evidence.baseline_digest == evidence.expected_baseline_digest == _baseline_digest(chain.baseline)
    assert evidence.series_digest == chain.gate.series_digest


def test_ready_paper_summary_feeds_real_metrics_with_negative_slippage_echoed_as_none() -> None:
    chain = _chain()
    evidence = _build()
    # The canonical fixture slippage is favorable (negative signed bps): enforced and digest-bound here,
    # echoed as None because the comparator input contract only accepts non-negative-or-None slippage.
    assert Decimal(chain.metrics.average_slippage_bps) < 0
    expected_summary = Stage4PaperSummary(
        paper_id=_PAPER_ID,
        edge_id=chain.edge.paper_edge_id,
        started_at_ns=chain.gate.first_bucket_start_ns,
        stopped_at_ns=chain.gate.last_bucket_end_ns,
        paper_sharpe=float(chain.sharpe.paper_sharpe_annualized),
        paper_hit_rate=float(chain.metrics.hit_rate),
        paper_slippage_bps=None,
        paper_fill_rate=float(
            min(Decimal(chain.metrics.fill_rate_by_quantity), Decimal(chain.metrics.fill_rate_by_episode))
        ),
        paper_trade_count=chain.metrics.record_count,
    )
    assert evidence.paper_summary_digest == _canonical(stage4_paper_summary_to_dict(expected_summary))
    assert evidence.comparator_fill_rate_echo_policy == "min_of_quantity_and_episode_fill_rates.v1"
    assert evidence.comparator_slippage_echo_policy == "non_negative_float_echo_or_none_signed_enforced_in_v2.v1"


def test_ready_with_non_negative_slippage_echoes_float() -> None:
    chain = _chain()
    metrics2, precondition2, methodology2 = _resealed_sm(
        chain,
        metrics_changes={"average_slippage_bps": "10.000000000000000000"},
        precondition_changes={"computed_slippage_bps": "10.000000000000000000"},
    )
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    assert evidence.status is PaperStage4ComparisonEvidenceV2Status.READY, evidence.reason_codes
    assert evidence.paper_slippage_bps == "10.000000000000000000"
    expected_summary = Stage4PaperSummary(
        paper_id=_PAPER_ID,
        edge_id=chain.edge.paper_edge_id,
        started_at_ns=chain.gate.first_bucket_start_ns,
        stopped_at_ns=chain.gate.last_bucket_end_ns,
        paper_sharpe=float(chain.sharpe.paper_sharpe_annualized),
        paper_hit_rate=float(metrics2.hit_rate),
        paper_slippage_bps=10.0,
        paper_fill_rate=float(min(Decimal(metrics2.fill_rate_by_quantity), Decimal(metrics2.fill_rate_by_episode))),
        paper_trade_count=metrics2.record_count,
    )
    assert evidence.paper_summary_digest == _canonical(stage4_paper_summary_to_dict(expected_summary))


def test_retention_not_satisfied_remains_valid_ready_evidence_with_enforced_metrics() -> None:
    # paper sharpe well below 0.5 * 1.5: retention fails, but the artifact is still READY evidence and the
    # secondary metrics remain enforced — retention is a comparison outcome, not an SM threshold.
    sharpe = _reseal_sharpe(_chain().sharpe, paper_sharpe_annualized="0.500000000000000000")
    evidence = _build(sharpe_evidence=sharpe)
    assert evidence.status is PaperStage4ComparisonEvidenceV2Status.READY, evidence.reason_codes
    assert evidence.comparison_verdict == "RETENTION_NOT_SATISFIED"
    assert evidence.sharpe_retention_satisfied is False
    assert evidence.secondary_metrics_enforced is True
    assert evidence.comparator_status_echo == "REJECT"
    assert evidence.comparator_rejection_reasons_echo == ("stage4:paper_sharpe_below_backtest_threshold",)


def test_always_false_flags_on_ready_and_rejected() -> None:
    ready_evidence = _build()
    rejected_evidence = _build(expected_metrics_evidence_digest="0" * 64)
    for flag in _ALWAYS_FALSE_FLAGS:
        assert getattr(ready_evidence, flag) is False, flag
        assert getattr(rejected_evidence, flag) is False, flag
    assert ready_evidence.paper_only is True
    assert rejected_evidence.paper_only is True


def test_structural_false_defaults() -> None:
    field_defaults = {field.name: field.default for field in fields(PaperStage4ComparisonEvidenceV2)}
    for flag in _ALWAYS_FALSE_FLAGS:
        assert field_defaults[flag] is False, flag
    assert field_defaults["secondary_metrics_enforced"] is False
    assert field_defaults["methodology_v2_consumed"] is False
    assert field_defaults["enforcement_precondition_consumed"] is False
    assert field_defaults["metrics_evidence_consumed"] is False
    assert field_defaults["paper_only"] is True
    assert field_defaults["thresholds_reapplied_here_not_by_comparator"] is True


# --------------------------------------------------------------------------------------------------
# 3. Seven-anchor digest triples + caller-baseline triple
# --------------------------------------------------------------------------------------------------

_ANCHOR_CASES = {
    "sharpe": ("sharpe_evidence", "expected_sharpe_evidence_digest", "sharpe_evidence_digest_mismatch"),
    "methodology_v2": ("methodology_v2", "expected_methodology_v2_digest", "methodology_v2_digest_mismatch"),
    "edge": ("edge_identity", "expected_edge_identity_digest", "edge_identity_digest_mismatch"),
    "baseline_evidence": (
        "baseline_evidence",
        "expected_baseline_evidence_digest",
        "baseline_evidence_digest_mismatch",
    ),
    "gate": ("gate_decision", "expected_gate_decision_digest", "gate_decision_digest_mismatch"),
    "precondition": (
        "enforcement_precondition",
        "expected_enforcement_precondition_digest",
        "enforcement_precondition_digest_mismatch",
    ),
    "metrics": ("metrics_evidence", "expected_metrics_evidence_digest", "metrics_evidence_digest_mismatch"),
}

_RESEAL_BY_ANCHOR = {
    "sharpe": lambda chain: _reseal_sharpe(chain.sharpe, metadata=(("z", "reseal"),)),
    "methodology_v2": lambda chain: _reseal_methodology_v2(chain.methodology_v2, metadata=(("z", "reseal"),)),
    "edge": lambda chain: _reseal_edge(chain.edge, metadata=(("z", "reseal"),)),
    "baseline_evidence": lambda chain: _reseal_baseline_evidence(chain.baseline_evidence, metadata=(("z", "reseal"),)),
    "gate": lambda chain: _reseal_gate(chain.gate, metadata=(("z", "reseal"),)),
    "precondition": lambda chain: _reseal_precondition(chain.precondition, metadata=(("z", "reseal"),)),
    "metrics": lambda chain: _reseal_metrics(chain.metrics, metadata=(("z", "reseal"),)),
}

_ORIGINAL_BY_ANCHOR = {
    "sharpe": lambda chain: chain.sharpe,
    "methodology_v2": lambda chain: chain.methodology_v2,
    "edge": lambda chain: chain.edge,
    "baseline_evidence": lambda chain: chain.baseline_evidence,
    "gate": lambda chain: chain.gate,
    "precondition": lambda chain: chain.precondition,
    "metrics": lambda chain: chain.metrics,
}

_DIGEST_ATTR_BY_ANCHOR = {
    "sharpe": "sharpe_evidence_digest",
    "methodology_v2": "methodology_digest",
    "edge": "edge_identity_digest",
    "baseline_evidence": "baseline_evidence_digest",
    "gate": "decision_digest",
    "precondition": "precondition_digest",
    "metrics": "evidence_digest",
}


@pytest.mark.parametrize("anchor", sorted(_ANCHOR_CASES))
@pytest.mark.parametrize("mode", ["stale_expected", "tampered_carried", "resealed"])
def test_anchor_digest_triple_mismatch_rejected(anchor: str, mode: str) -> None:
    chain = _chain()
    artifact_kwarg, expected_kwarg, reason = _ANCHOR_CASES[anchor]
    overrides: dict[str, object] = {}
    if mode == "stale_expected":
        overrides[expected_kwarg] = "0" * 64
    elif mode == "tampered_carried":
        original = _ORIGINAL_BY_ANCHOR[anchor](chain)
        tampered = replace(original, **{_DIGEST_ATTR_BY_ANCHOR[anchor]: "f" * 64})  # type: ignore[arg-type]
        overrides[artifact_kwarg] = tampered
        overrides[expected_kwarg] = "f" * 64
    else:
        resealed = _RESEAL_BY_ANCHOR[anchor](chain)
        original = _ORIGINAL_BY_ANCHOR[anchor](chain)
        overrides[artifact_kwarg] = resealed
        overrides[expected_kwarg] = getattr(original, _DIGEST_ATTR_BY_ANCHOR[anchor])
    evidence = _build(**overrides)
    _assert_rejected_with(evidence, reason)
    verified_field = expected_kwarg.replace("expected_", "verified_")
    assert getattr(evidence, verified_field) == ""
    assert evidence.stage4_comparator_invoked is False


@pytest.mark.parametrize("bad_digest", [None, 7, True])
def test_non_string_carried_anchor_digest_rejects_without_crash(bad_digest: object) -> None:
    chain = _chain()
    tampered = replace(chain.metrics, evidence_digest=bad_digest)  # type: ignore[arg-type]
    evidence = _build(metrics_evidence=tampered, expected_metrics_evidence_digest=_HEX_A)
    _assert_rejected_with(evidence, "metrics_evidence_digest_mismatch")


def test_baseline_triple_stale_expected_rejected() -> None:
    evidence = _build(expected_baseline_digest="0" * 64)
    _assert_rejected_with(evidence, "baseline_digest_mismatch")
    assert evidence.baseline_digest == ""


def test_baseline_tampered_after_binding_rejected() -> None:
    chain = _chain()
    tampered = replace(chain.baseline, backtest_sharpe=9.5)
    evidence = _build(backtest_baseline=tampered)
    _assert_rejected_with(evidence, "baseline_evidence_baseline_digest_mismatch")


def test_baseline_evidence_bound_digest_mismatch_rejected() -> None:
    chain = _chain()
    resealed = _reseal_baseline_evidence(chain.baseline_evidence, baseline_digest="e" * 64)
    evidence = _build(baseline_evidence=resealed, expected_baseline_evidence_digest=resealed.baseline_evidence_digest)
    _assert_rejected_with(evidence, "baseline_evidence_baseline_digest_mismatch")


# --------------------------------------------------------------------------------------------------
# 4. SM trust-root bindings
# --------------------------------------------------------------------------------------------------


def test_precondition_metrics_digest_must_equal_direct_sm4_digest() -> None:
    chain = _chain()
    # A second READY SM-4 over the same records with a different evidence id: identical values, different
    # self-digest. The precondition remains bound to the ORIGINAL SM-4, so supplying the twin as the direct
    # SM-4 artifact must fail the mandatory equality with EXACTLY the binding reason (nothing else differs).
    twin = build_paper_secondary_metrics_evidence(
        chain.policy,
        chain.records,
        evidence_id="sm4-2",
        correlation_id=_CORRELATION,
    )
    assert twin.ready
    assert twin.evidence_digest != chain.metrics.evidence_digest
    evidence = _build(metrics_evidence=twin)
    assert evidence.status is PaperStage4ComparisonEvidenceV2Status.REJECTED
    assert evidence.reason_codes == (_rc("precondition_metrics_evidence_binding_mismatch"),)
    assert evidence.secondary_metrics_enforced is False


def test_methodology_v2_must_bind_the_same_precondition() -> None:
    chain = _chain()
    other_precondition = chain._precondition(  # noqa: SLF001
        chain.metrics, chain.reconciliation, precondition_id="precondition-2"
    )
    assert other_precondition.ready
    evidence = _build(enforcement_precondition=other_precondition)
    assert evidence.status is PaperStage4ComparisonEvidenceV2Status.REJECTED
    assert evidence.reason_codes == (_rc("methodology_v2_precondition_binding_mismatch"),)


def test_policy_binding_mismatch_rejected() -> None:
    chain = _chain()
    metrics2, precondition2, methodology2 = _resealed_sm(chain, metrics_changes={"policy_id": "policy-2"})
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    _assert_rejected_with(evidence, "policy_binding_mismatch")


def test_computed_metrics_binding_mismatch_rejected() -> None:
    chain = _chain()
    metrics2, precondition2, methodology2 = _resealed_sm(
        chain, precondition_changes={"computed_hit_rate": "0.900000000000000000"}
    )
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    _assert_rejected_with(evidence, "computed_metrics_binding_mismatch")


def test_threshold_snapshot_mismatch_rejected() -> None:
    chain = _chain()
    metrics2, precondition2, methodology2 = _resealed_sm(
        chain, precondition_changes={"approved_hit_rate_floor": "0.400000000000000000"}
    )
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    _assert_rejected_with(evidence, "threshold_snapshot_mismatch")


def test_stale_reconciliation_lineage_rejected() -> None:
    chain = _chain()
    metrics2, precondition2, methodology2 = _resealed_sm(chain, precondition_changes={"reconciliation_digest": "zz"})
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    _assert_rejected_with(evidence, "enforcement_precondition_contract_invalid")


def test_metrics_evidence_not_ready_rejected() -> None:
    chain = _chain()
    metrics2, precondition2, methodology2 = _resealed_sm(chain, metrics_changes={"ready": False})
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    _assert_rejected_with(evidence, "metrics_evidence_not_ready")


def test_precondition_not_ready_rejected() -> None:
    chain = _chain()
    metrics2, precondition2, methodology2 = _resealed_sm(chain, precondition_changes={"ready": False})
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    _assert_rejected_with(evidence, "enforcement_precondition_not_ready")


def test_methodology_v2_not_ready_rejected() -> None:
    chain = _chain()
    methodology2 = _reseal_methodology_v2(chain.methodology_v2, ready=False)
    evidence = _build(methodology_v2=methodology2)
    _assert_rejected_with(evidence, "methodology_v2_not_ready")


@pytest.mark.parametrize(
    ("anchor", "reason"),
    [
        ("metrics", "metrics_evidence_noncanonical"),
        ("precondition", "enforcement_precondition_noncanonical"),
        ("methodology_v2", "methodology_v2_noncanonical"),
        ("sharpe", "sharpe_evidence_noncanonical"),
    ],
)
def test_noncanonical_anchor_metadata_rejected(anchor: str, reason: str) -> None:
    chain = _chain()
    unsorted_metadata = (("b", "2"), ("a", "1"))
    if anchor == "metrics":
        metrics2, precondition2, methodology2 = _resealed_sm(chain, metrics_changes={"metadata": unsorted_metadata})
        evidence = _build(
            metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2
        )
    elif anchor == "precondition":
        metrics2, precondition2, methodology2 = _resealed_sm(
            chain, precondition_changes={"metadata": unsorted_metadata}
        )
        evidence = _build(
            metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2
        )
    elif anchor == "methodology_v2":
        evidence = _build(methodology_v2=_reseal_methodology_v2(chain.methodology_v2, metadata=unsorted_metadata))
    else:
        evidence = _build(sharpe_evidence=_reseal_sharpe(chain.sharpe, metadata=unsorted_metadata))
    _assert_rejected_with(evidence, reason)


def test_noncanonical_metrics_identity_rejected() -> None:
    chain = _chain()
    metrics2, precondition2, methodology2 = _resealed_sm(chain, metrics_changes={"evidence_id": " sm4-1 "})
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    _assert_rejected_with(evidence, "metrics_evidence_noncanonical")


def test_anchor_metadata_scope_violation_rejected() -> None:
    chain = _chain()
    metrics2, precondition2, methodology2 = _resealed_sm(
        chain, metrics_changes={"metadata": (("note", "deribit_ready go-live"),)}
    )
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    _assert_rejected_with(evidence, "anchor_scope_violation")


# --------------------------------------------------------------------------------------------------
# 5. Real-metric presence (None -> REJECTED; the v1 placeholder path is structurally impossible)
# --------------------------------------------------------------------------------------------------


def test_none_real_secondary_metrics_rejected() -> None:
    chain = _chain()
    # An honest upstream chain with a None slippage is READY upstream (SM-4/SM-5 vacuous-pass boundary)
    # but MUST be rejected here with exactly the missing-metric reason: the flip SM-6 exists to enforce.
    metrics2, precondition2, methodology2 = _resealed_sm(
        chain,
        metrics_changes={"average_slippage_bps": None},
        precondition_changes={"computed_slippage_bps": None},
    )
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    assert evidence.status is PaperStage4ComparisonEvidenceV2Status.REJECTED
    assert evidence.reason_codes == (_rc("missing_secondary_metric"),)
    assert evidence.secondary_metrics_enforced is False
    assert evidence.stage4_comparator_invoked is False
    assert evidence.paper_slippage_bps is None


@pytest.mark.parametrize(
    ("metrics_field", "precondition_field"),
    [
        ("hit_rate", "computed_hit_rate"),
        ("fill_rate_by_quantity", "computed_fill_rate_by_quantity"),
        ("fill_rate_by_episode", "computed_fill_rate_by_episode"),
    ],
)
def test_missing_required_metric_rejected(metrics_field: str, precondition_field: str) -> None:
    chain = _chain()
    metrics2, precondition2, methodology2 = _resealed_sm(
        chain,
        metrics_changes={metrics_field: None},
        precondition_changes={precondition_field: None},
    )
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    _assert_rejected_with(evidence, "missing_secondary_metric")
    assert evidence.stage4_comparator_invoked is False


def test_noncanonical_metric_scale_rejected_as_missing() -> None:
    chain = _chain()
    metrics2, precondition2, methodology2 = _resealed_sm(
        chain,
        metrics_changes={"hit_rate": "1.0"},
        precondition_changes={"computed_hit_rate": "1.0"},
    )
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    _assert_rejected_with(evidence, "missing_secondary_metric")


# --------------------------------------------------------------------------------------------------
# 6. Threshold enforcement (independent Decimal reapplication; carried booleans never trusted)
# --------------------------------------------------------------------------------------------------


def test_hit_rate_below_floor_blocks_secondary_metric_enforcement() -> None:
    chain = _chain()
    metrics2, precondition2, methodology2 = _resealed_sm(
        chain,
        metrics_changes={"hit_rate": "0.499999999999999999"},
        precondition_changes={"computed_hit_rate": "0.499999999999999999"},
    )
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    _assert_rejected_with(evidence, "hit_rate_floor_not_met")
    assert _rc("threshold_pass_incoherent") in evidence.reason_codes
    assert evidence.hit_rate_floor_satisfied is False
    assert evidence.stage4_comparator_invoked is False


@pytest.mark.parametrize(
    ("metrics_field", "precondition_field"),
    [
        ("fill_rate_by_quantity", "computed_fill_rate_by_quantity"),
        ("fill_rate_by_episode", "computed_fill_rate_by_episode"),
    ],
)
def test_fill_rate_below_floor_blocks_secondary_metric_enforcement(metrics_field: str, precondition_field: str) -> None:
    chain = _chain()
    metrics2, precondition2, methodology2 = _resealed_sm(
        chain,
        metrics_changes={metrics_field: "0.899999999999999999"},
        precondition_changes={precondition_field: "0.899999999999999999"},
    )
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    _assert_rejected_with(evidence, "fill_rate_floor_not_met")
    assert evidence.fill_rate_floor_satisfied is False
    assert evidence.stage4_comparator_invoked is False


def test_slippage_above_ceiling_blocks_secondary_metric_enforcement() -> None:
    chain = _chain()
    metrics2, precondition2, methodology2 = _resealed_sm(
        chain,
        metrics_changes={"average_slippage_bps": "25.000000000000000001"},
        precondition_changes={"computed_slippage_bps": "25.000000000000000001"},
    )
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    _assert_rejected_with(evidence, "slippage_ceiling_exceeded")
    assert evidence.slippage_ceiling_satisfied is False
    assert evidence.stage4_comparator_invoked is False


def test_min_decided_episode_count_below_minimum_rejected() -> None:
    chain = _chain()
    metrics2, precondition2, methodology2 = _resealed_sm(
        chain,
        metrics_changes={"decided_episode_count": 0},
        precondition_changes={"computed_decided_episode_count": 0},
    )
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    _assert_rejected_with(evidence, "min_decided_episode_count_not_met")


@pytest.mark.parametrize(
    ("metrics_changes", "precondition_changes"),
    [
        ({"hit_rate": "0.500000000000000000"}, {"computed_hit_rate": "0.500000000000000000"}),
        ({"average_slippage_bps": "25.000000000000000000"}, {"computed_slippage_bps": "25.000000000000000000"}),
        ({"decided_episode_count": 1}, {"computed_decided_episode_count": 1}),
    ],
)
def test_threshold_boundary_equality_passes(
    metrics_changes: dict[str, object], precondition_changes: dict[str, object]
) -> None:
    chain = _chain()
    metrics2, precondition2, methodology2 = _resealed_sm(
        chain, metrics_changes=metrics_changes, precondition_changes=precondition_changes
    )
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    assert evidence.status is PaperStage4ComparisonEvidenceV2Status.READY, evidence.reason_codes
    assert evidence.secondary_metrics_enforced is True


def test_carried_pass_booleans_cannot_override_recomputed_failure() -> None:
    chain = _chain()
    # Fully coherent digest-valid reseal: every carried pass boolean still claims True while the actual
    # value fails the floor — the consumer's own Decimal recompute must win.
    metrics2, precondition2, methodology2 = _resealed_sm(
        chain,
        metrics_changes={"hit_rate": "0.100000000000000000", "hit_rate_satisfied": True, "thresholds_cleared": True},
        precondition_changes={"computed_hit_rate": "0.100000000000000000", "hit_rate_passed": True},
    )
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    _assert_rejected_with(evidence, "hit_rate_floor_not_met")
    assert _rc("threshold_pass_incoherent") in evidence.reason_codes


def test_unapproved_thresholds_rejected() -> None:
    chain = _chain()
    methodology2 = _reseal_methodology_v2(chain.methodology_v2, thresholds_approved=False)
    evidence = _build(methodology_v2=methodology2)
    _assert_rejected_with(evidence, "methodology_v2_unsafe_flags")


def test_methodology_v2_enforced_flags_must_be_true() -> None:
    chain = _chain()
    methodology2 = _reseal_methodology_v2(chain.methodology_v2, hit_rate_floor_enforced=False)
    evidence = _build(methodology_v2=methodology2)
    _assert_rejected_with(evidence, "methodology_v2_unsafe_flags")


def test_methodology_v2_aggregate_enforced_flag_must_be_false() -> None:
    chain = _chain()
    methodology2 = _reseal_methodology_v2(chain.methodology_v2, secondary_metrics_enforced=True)
    evidence = _build(methodology_v2=methodology2)
    _assert_rejected_with(evidence, "methodology_v2_unsafe_flags")


def test_methodology_v2_weakened_threshold_rejected() -> None:
    chain = _chain()
    methodology2 = _reseal_methodology_v2(chain.methodology_v2, sharpe_retention_ratio="0.100000000000000000")
    evidence = _build(methodology_v2=methodology2)
    _assert_rejected_with(evidence, "methodology_v2_retention_threshold_unapproved")


def test_methodology_v2_invalid_secondary_threshold_rejected() -> None:
    chain = _chain()
    methodology2 = _reseal_methodology_v2(chain.methodology_v2, approved_hit_rate_floor=None)
    evidence = _build(methodology_v2=methodology2)
    _assert_rejected_with(evidence, "methodology_v2_thresholds_invalid")


# --------------------------------------------------------------------------------------------------
# 7. Comparator boundary (echo is never enforcement; enforcement lives outside the comparator)
# --------------------------------------------------------------------------------------------------


def test_secondary_metrics_thresholds_enforced_outside_current_comparator() -> None:
    # The current comparator's public contract decides only edge-id, duration and Sharpe retention:
    # its signature is unchanged and SM-6 rejects a failing secondary threshold BEFORE any comparator call.
    assert list(inspect.signature(compare_stage4).parameters) == [
        "baseline",
        "paper",
        "min_duration_days",
        "min_sharpe_retention_ratio",
    ]
    chain = _chain()
    metrics2, precondition2, methodology2 = _resealed_sm(
        chain,
        metrics_changes={"average_slippage_bps": "999.000000000000000000"},
        precondition_changes={"computed_slippage_bps": "999.000000000000000000"},
    )
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    _assert_rejected_with(evidence, "slippage_ceiling_exceeded")
    assert evidence.stage4_comparator_invoked is False
    assert evidence.comparator_status_echo == ""


def test_compare_stage4_echo_does_not_satisfy_secondary_metric_enforcement() -> None:
    chain = _chain()
    # Retention would comfortably PASS in the comparator, but a failed hit floor keeps the artifact
    # REJECTED and unenforced — a favorable comparator echo can never substitute for SM enforcement.
    metrics2, precondition2, methodology2 = _resealed_sm(
        chain,
        metrics_changes={"hit_rate": "0.000000000000000000", "hit_rate_satisfied": True, "thresholds_cleared": True},
        precondition_changes={"computed_hit_rate": "0.000000000000000000", "hit_rate_passed": True},
    )
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    _assert_rejected_with(evidence, "hit_rate_floor_not_met")
    assert evidence.stage4_comparator_invoked is False
    assert evidence.comparison_performed is False
    assert evidence.comparison_verdict == ""
    assert evidence.secondary_metrics_enforced is False


def test_ast_compare_stage4_called_exactly_once() -> None:
    source = Path(comparison_v2_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "compare_stage4")
            or (isinstance(node.func, ast.Attribute) and node.func.attr == "compare_stage4")
        )
    ]
    assert len(calls) == 1


# --------------------------------------------------------------------------------------------------
# 8. Cross-links, record set, duration, edge identity
# --------------------------------------------------------------------------------------------------


def test_correlation_mismatch_rejected() -> None:
    chain = _chain()
    metrics2, precondition2, methodology2 = _resealed_sm(chain, precondition_changes={"correlation_id": "corr-2"})
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    _assert_rejected_with(evidence, "correlation_id_mismatch")


def test_market_symbol_mismatch_rejected() -> None:
    chain = _chain()
    metrics2, precondition2, methodology2 = _resealed_sm(chain, precondition_changes={"market_symbol": "ETH-PERPETUAL"})
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    _assert_rejected_with(evidence, "market_symbol_mismatch")


@pytest.mark.parametrize(
    ("metrics_changes", "precondition_changes"),
    [
        ({"record_count": 3}, {}),
        ({}, {"reconciled_episode_count": 3}),
        ({}, {"record_digests": ()}),
        ({"decided_episode_count": 5}, {"computed_decided_episode_count": 5}),
    ],
)
def test_record_set_incoherence_rejected(
    metrics_changes: dict[str, object], precondition_changes: dict[str, object]
) -> None:
    chain = _chain()
    metrics2, precondition2, methodology2 = _resealed_sm(
        chain, metrics_changes=metrics_changes, precondition_changes=precondition_changes
    )
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    _assert_rejected_with(evidence, "record_set_incoherent")


def test_duplicate_record_digest_rejected() -> None:
    chain = _chain()
    digests = chain.metrics.record_digests
    duplicated = (digests[0], digests[0])
    metrics2, precondition2, methodology2 = _resealed_sm(
        chain,
        metrics_changes={"record_digests": duplicated},
        precondition_changes={"record_digests": duplicated},
    )
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    _assert_rejected_with(evidence, "record_set_incoherent")


def test_dropped_record_rejected() -> None:
    chain = _chain()
    digests = chain.metrics.record_digests
    metrics2, precondition2, methodology2 = _resealed_sm(
        chain,
        metrics_changes={"record_digests": digests[:1], "record_count": 1},
        precondition_changes={
            "record_digests": digests[:1],
            "metrics_record_count": 1,
            "reconciled_record_count": 1,
            "reconciled_episode_count": 1,
        },
    )
    evidence = _build(metrics_evidence=metrics2, enforcement_precondition=precondition2, methodology_v2=methodology2)
    _assert_rejected_with(evidence, "record_set_incoherent")


def test_baseline_edge_id_mismatch_rejected() -> None:
    foreign = build_stage4_backtest_baseline(
        baseline_id="baseline-1",
        edge_id="c" * 64,
        as_of_ns=1_700_000_000_000_000_000,
        backtest_sharpe=1.5,
        backtest_hit_rate=0.55,
        backtest_slippage_bps=2.0,
        backtest_fill_rate=0.9,
        source_window_ids=("wf-1", "wf-2"),
    )
    evidence = _build(backtest_baseline=foreign)
    _assert_rejected_with(evidence, "baseline_edge_id_mismatch")


def test_gate_duration_tamper_rejected() -> None:
    chain = _chain()
    resealed = _reseal_gate(chain.gate, window_duration_ns=29 * _DAY_NS)
    evidence = _build(gate_decision=resealed)
    _assert_rejected_with(evidence, "window_duration_incoherent")


def test_thirty_day_gate_not_satisfied_rejected() -> None:
    chain = _chain()
    resealed = _reseal_gate(chain.gate, thirty_day_gate_satisfied=False)
    evidence = _build(gate_decision=resealed)
    _assert_rejected_with(evidence, "thirty_day_gate_not_satisfied")


def test_sharpe_series_binding_mismatch_rejected() -> None:
    chain = _chain()
    resealed = _reseal_sharpe(chain.sharpe, series_id="series-2")
    evidence = _build(sharpe_evidence=resealed)
    _assert_rejected_with(evidence, "series_binding_mismatch")


# --------------------------------------------------------------------------------------------------
# 9. RAISE contract (caller-owned malformed input)
# --------------------------------------------------------------------------------------------------

_TYPE_CASES = [
    ("backtest_baseline", "backtest_baseline_malformed"),
    ("baseline_evidence", "baseline_evidence_malformed"),
    ("sharpe_evidence", "sharpe_evidence_malformed"),
    ("methodology_v2", "methodology_v2_malformed"),
    ("edge_identity", "edge_identity_malformed"),
    ("gate_decision", "gate_decision_malformed"),
    ("enforcement_precondition", "enforcement_precondition_malformed"),
    ("metrics_evidence", "metrics_evidence_malformed"),
]


@pytest.mark.parametrize(("kwarg", "reason"), _TYPE_CASES)
def test_wrong_type_artifact_raises(kwarg: str, reason: str) -> None:
    with pytest.raises(PaperStage4ComparisonEvidenceV2Error, match=_rc(reason)):
        _build(**{kwarg: object()})


_EXPECTED_DIGEST_KWARGS = [
    "expected_baseline_digest",
    "expected_baseline_evidence_digest",
    "expected_sharpe_evidence_digest",
    "expected_methodology_v2_digest",
    "expected_edge_identity_digest",
    "expected_gate_decision_digest",
    "expected_enforcement_precondition_digest",
    "expected_metrics_evidence_digest",
]


@pytest.mark.parametrize("kwarg", _EXPECTED_DIGEST_KWARGS)
def test_malformed_expected_digest_raises(kwarg: str) -> None:
    with pytest.raises(PaperStage4ComparisonEvidenceV2Error, match=_rc(f"{kwarg}_invalid")):
        _build(**{kwarg: "A" * 64})


@pytest.mark.parametrize(
    ("kwarg", "value", "reason"),
    [
        ("comparison_evidence_id", "", "comparison_evidence_id_invalid"),
        ("comparison_evidence_id", " padded ", "comparison_evidence_id_invalid"),
        ("correlation_id", "", "correlation_id_invalid"),
        ("metadata", {"key": 5}, "metadata_malformed"),
        ("metadata", {" key": "value"}, "metadata_malformed"),
        ("comparison_evidence_id", "live-order-flow-id", "scope_violation"),
        ("metadata", {"note": "uses wall_clock time"}, "clock_token_forbidden"),
    ],
)
def test_malformed_caller_input_raises(kwarg: str, value: object, reason: str) -> None:
    with pytest.raises(PaperStage4ComparisonEvidenceV2Error, match=_rc(reason)):
        _build(**{kwarg: value})


def test_str_subclass_expected_digest_raises() -> None:
    class _LiarStr(str):
        pass

    chain = _chain()
    with pytest.raises(PaperStage4ComparisonEvidenceV2Error, match=_rc("expected_metrics_evidence_digest_invalid")):
        _build(expected_metrics_evidence_digest=_LiarStr(chain.metrics.evidence_digest))


# --------------------------------------------------------------------------------------------------
# 10. Structural safety (AST forbidden surface)
# --------------------------------------------------------------------------------------------------


def test_ast_forbidden_imports_and_calls() -> None:
    source = Path(comparison_v2_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = (
        "os",
        "io",
        "pathlib",
        "time",
        "datetime",
        "random",
        "secrets",
        "socket",
        "ssl",
        "requests",
        "urllib",
        "http",
        "threading",
        "asyncio",
        "subprocess",
        "sqlite3",
        "fractions",
        "crypto_core.service",
        "crypto_core.execution",
        "crypto_core.venue",
        "crypto_core.runtime",
        "crypto_core.orchestrator",
        "crypto_core.temporal",
        "crypto_core.portfolio",
        "crypto_core.validation.paper_stage4_comparison_evidence",
        "crypto_core.validation.paper_stage4_completion_decision_v2",
        "crypto_core.validation.paper_vs_backtest_methodology",
        "crypto_core.validation.secondary_metrics_policy",
        "crypto_core.validation.paper_secondary_metrics_substrate_reconciliation",
        "crypto_core.validation.trade_record_evidence",
    )
    allowed_exact = {
        "crypto_core.validation.paper_stage4_comparison_evidence_v2",
        "crypto_core.validation.paper_vs_backtest_methodology_v2",
    }
    forbidden_call_names = {
        "open",
        "now",
        "utcnow",
        "time",
        "time_ns",
        "perf_counter",
        "monotonic",
        "system",
        "getenv",
        "eval",
        "exec",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(
                    (alias.name == module or alias.name.startswith(f"{module}.")) and alias.name not in allowed_exact
                    for module in forbidden_modules
                ), alias.name
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(
                (node.module == module or node.module.startswith(f"{module}.")) and node.module not in allowed_exact
                for module in forbidden_modules
            ), node.module
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                assert function.id not in forbidden_call_names, function.id
            if isinstance(function, ast.Attribute):
                assert function.attr not in forbidden_call_names, function.attr


def test_no_equivalent_artifact_exists() -> None:
    validation_dir = Path(comparison_v2_module.__file__).parent
    builders = sorted(
        path.name
        for path in validation_dir.glob("*.py")
        if "def build_paper_stage4_comparison_evidence_v2(" in path.read_text(encoding="utf-8")
    )
    assert builders == ["paper_stage4_comparison_evidence_v2.py"]


def test_reason_codes_are_sorted_unique_and_prefixed() -> None:
    evidence = _build(
        expected_metrics_evidence_digest="0" * 64,
        expected_enforcement_precondition_digest="0" * 64,
    )
    assert evidence.status is PaperStage4ComparisonEvidenceV2Status.REJECTED
    assert list(evidence.reason_codes) == sorted(set(evidence.reason_codes))
    assert all(code.startswith("paper_stage4_comparison_evidence_v2:") for code in evidence.reason_codes)
