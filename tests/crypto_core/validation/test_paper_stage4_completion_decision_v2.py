"""Tests for the deterministic paper Stage-4 completion decision v2 (Path A = BLOCKED completion)."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import FrozenInstanceError, fields, replace
from fractions import Fraction
from pathlib import Path

import pytest

from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, validate_strategy_spec
from crypto_core.validation import paper_daily_return_series_evidence as series_module
from crypto_core.validation import paper_stage4_completion_decision_v2 as v2_module
from crypto_core.validation.paper_30day_evidence_gate_decision import (
    PaperThirtyDayEvidenceGateDecision,
    build_paper_30day_evidence_gate_decision,
    paper_30day_evidence_gate_decision_digest,
)
from crypto_core.validation.paper_attested_operational_day_evidence import (
    PaperAttestedOperationalDayEvidence,
    build_paper_attested_operational_day_evidence,
)
from crypto_core.validation.paper_attested_operational_thirty_day_gate_decision import (
    PaperAttestedOperationalThirtyDayGateDecision,
    PaperAttestedOperationalThirtyDayGateDecisionStatus,
    build_paper_attested_operational_thirty_day_gate_decision,
    paper_attested_operational_thirty_day_gate_decision_digest,
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
)
from crypto_core.validation.paper_return_series_methodology import build_paper_return_series_methodology
from crypto_core.validation.paper_sharpe_evidence import (
    PaperSharpeEvidence,
    build_paper_sharpe_evidence,
    paper_sharpe_evidence_digest,
)
from crypto_core.validation.paper_stage4_backtest_baseline_evidence import (
    PaperStage4BacktestBaselineEvidence,
    build_paper_stage4_backtest_baseline_evidence,
)
from crypto_core.validation.paper_stage4_comparison_evidence import (
    PaperStage4ComparisonEvidence,
    build_paper_stage4_comparison_evidence,
    paper_stage4_comparison_evidence_digest,
)
from crypto_core.validation.paper_stage4_completion_decision import (
    PaperStage4CompletionDecision,
    build_paper_stage4_completion_decision,
    paper_stage4_completion_decision_digest,
)
from crypto_core.validation.paper_stage4_completion_decision_v2 import (
    PaperStage4CompletionDecisionV2,
    PaperStage4CompletionDecisionV2Error,
    PaperStage4CompletionDecisionV2Status,
    build_paper_stage4_completion_decision_v2,
    paper_stage4_completion_decision_v2_digest,
    paper_stage4_completion_decision_v2_to_dict,
)
from crypto_core.validation.paper_vs_backtest_methodology import (
    PaperVsBacktestMethodology,
    build_paper_vs_backtest_methodology,
)
from crypto_core.validation.stage4_comparator import (
    Stage4BacktestBaseline,
    build_stage4_backtest_baseline,
    stage4_backtest_baseline_to_dict,
)

_DAY_NS = 86_400_000_000_000
_MARKET = "BTC-PERPETUAL"
_CORRELATION = "corr-1"
_PAPER_ID = "paper-1"
_HEX_A = "a" * 64
_RISK_FREE_POLICY_ID = "constant_zero_daily_review_only.v1"
_RETENTION_THRESHOLD = "0.500000000000000000"
_V1_BLOCKERS = (
    "prdv4_minimum_30_day_live_paper_trading_unproven",
    "operational_day_evidence_source_unavailable",
    "timestamp_origin_not_proven_injected_deterministic_time_only",
    "secondary_comparison_metrics_hit_fill_slippage_declared_not_enforced_v1",
)
_V2_BLOCKERS = (
    "operator_attested_only_machine_time_origin_unproven",
    "timestamp_origin_not_proven_injected_deterministic_time_only",
    "secondary_comparison_metrics_hit_fill_slippage_declared_not_enforced_v1",
)
_CHAIN_LINK = "correlation_market_and_utc_day_index_only.v1"
# The v1 fixture series occupies UTC epoch days 1..30 (first bucket starts at 1 * _DAY_NS), so the aligned
# attested chain must attest exactly those day indices.
_ATTESTED_START_DAY = 1

_STRUCTURAL_FALSE_FLAGS = (
    "prdv4_stage4_complete",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "operational_day_machine_proven",
    "real_wall_clock_used",
    "real_time_paper_operation_proven",
    "operational_readiness",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "connector_invoked",
    "private_api_ready",
    "live_api_called",
    "production_execution",
    "real_orders_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "real_account_equity_used",
    "real_capital_used",
    "scheduler_enabled",
    "auto_loop_enabled",
    "edge_proven",
    "profitability_proven",
    "same_edge_as_backtest_proven",
    "backtest_validity_proven",
)


class _LiarStr(str):
    """A ``str`` subclass rejected by exact ``type(x) is str`` checks."""


class _SharpeSub(PaperSharpeEvidence):
    """Subclass test double; exact input types are required."""


def _rc(code: str) -> str:
    return f"paper_stage4_completion_decision_v2:{code}"


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _canonical(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------------------------------
# Fixture chain: real merged builders end-to-end (identical construction to the v1 completion test),
# plus the attested 30-day chain aligned to the SAME UTC day indices, plus the real v1 predecessor.
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
    evidence = build_paper_stage4_backtest_baseline_evidence(
        baseline,
        expected_baseline_digest=_baseline_digest(baseline),
        edge_identity=edge,
        expected_edge_identity_digest=edge.edge_identity_digest,
        baseline_evidence_id="baseline-evidence-1",
        correlation_id=_CORRELATION,
        metadata={"purpose": "stage4 baseline binding"},
    )
    assert evidence.ready, evidence.reason_codes
    return evidence


def _series_window(*, days: int = 30) -> PaperDeterministicTimeWindowEvidence:
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


def _buckets_from_returns(returns: list[Fraction]) -> tuple[PaperDailyReturnBucket, ...]:
    index = Fraction(1)
    path = [index]
    for daily_return in returns:
        index = index * (Fraction(1) + daily_return)
        path.append(index)
    render = series_module._finite_decimal_string  # noqa: SLF001
    return tuple(_bucket(day, render(path[day]), render(path[day + 1])) for day in range(len(returns)))


def _series(*, days: int = 30) -> PaperDailyReturnSeriesEvidence:
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
    window = _series_window(days=days)
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
    return decision


def _comparison_methodology() -> PaperVsBacktestMethodology:
    methodology = build_paper_vs_backtest_methodology(
        methodology_id="comparison-methodology-1",
        correlation_id=_CORRELATION,
        sharpe_retention_ratio=_RETENTION_THRESHOLD,
        min_duration_days=30,
        risk_free_policy_id=_RISK_FREE_POLICY_ID,
        metadata={"purpose": "stage4 comparison policy"},
    )
    assert methodology.ready, methodology.reason_codes
    return methodology


def _comparison_from(
    *,
    baseline: Stage4BacktestBaseline,
    baseline_evidence: PaperStage4BacktestBaselineEvidence,
    sharpe: PaperSharpeEvidence,
    methodology: PaperVsBacktestMethodology,
    edge: PaperEdgeIdentityEvidence,
    gate: PaperThirtyDayEvidenceGateDecision,
) -> PaperStage4ComparisonEvidence:
    evidence = build_paper_stage4_comparison_evidence(
        baseline,
        expected_baseline_digest=_baseline_digest(baseline),
        baseline_evidence=baseline_evidence,
        expected_baseline_evidence_digest=baseline_evidence.baseline_evidence_digest,
        sharpe_evidence=sharpe,
        expected_sharpe_evidence_digest=sharpe.sharpe_evidence_digest,
        methodology=methodology,
        expected_methodology_digest=methodology.methodology_digest,
        edge_identity=edge,
        expected_edge_identity_digest=edge.edge_identity_digest,
        gate_decision=gate,
        expected_gate_decision_digest=gate.decision_digest,
        comparison_evidence_id="comparison-evidence-1",
        correlation_id=_CORRELATION,
        metadata={"purpose": "stage4 comparison"},
    )
    assert evidence.ready, evidence.reason_codes
    return evidence


def _attested_window(index: int) -> PaperDeterministicTimeWindowEvidence:
    started_at_ns = index * _DAY_NS
    duration_ns = 3_600_000_000_000
    payload: dict[str, object] = {
        "schema_version": "paper-deterministic-time-window-evidence.v1",
        "time_window_version": "paper-deterministic-time-window.v1",
        "status": PaperDeterministicTimeWindowEvidenceStatus.READY,
        "ready": True,
        "window_id": f"attested-window-{index}",
        "methodology_id": "method-1",
        "timestamp_policy": "injected_deterministic_ns.v1",
        "run_id": f"attested-run-{index}",
        "aggregate_id": f"attested-agg-{index}",
        "correlation_id": _CORRELATION,
        "market_symbol": _MARKET,
        "expected_metrics_summary_digest": _HEX_A,
        "metrics_summary_digest": _HEX_A,
        "summary_ready": True,
        "summary_readiness_verdict": "PAPER_STAGE4_CANDIDATE",
        "started_at_ns": started_at_ns,
        "stopped_at_ns": started_at_ns + duration_ns,
        "window_duration_ns": duration_ns,
        "sample_observation_count": 5,
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
    seed = PaperDeterministicTimeWindowEvidence(time_window_digest="", **payload)  # type: ignore[arg-type]
    return replace(seed, time_window_digest=paper_deterministic_time_window_evidence_digest(seed))


def _attested_day(index: int) -> PaperAttestedOperationalDayEvidence:
    window = _attested_window(index)
    day = build_paper_attested_operational_day_evidence(
        (window,),
        expected_session_window_digests=(window.time_window_digest,),
        attested_utc_day_index=index,
        attestor_id="operator-1",
        attestation_id=f"attestation-{index}",
        operational_day_evidence_id=f"operational-day-{index}",
        correlation_id=_CORRELATION,
        metadata={"purpose": "attested operational day"},
    )
    assert day.ready, day.reason_codes
    return day


def _attested_gate(start: int = _ATTESTED_START_DAY, count: int = 30) -> PaperAttestedOperationalThirtyDayGateDecision:
    days = tuple(_attested_day(start + offset) for offset in range(count))
    decision = build_paper_attested_operational_thirty_day_gate_decision(
        days,
        expected_operational_day_evidence_digests=tuple(day.attested_operational_day_evidence_digest for day in days),
        gate_decision_id="attested-gate-1",
        correlation_id=_CORRELATION,
        metadata={"purpose": "attested thirty day gate"},
    )
    assert decision.ready, decision.reason_codes
    assert decision.attested_operational_thirty_day_gate_satisfied is True
    return decision


def _predecessor_from(chain: dict[str, object]) -> PaperStage4CompletionDecision:
    decision = build_paper_stage4_completion_decision(
        chain["comparison"],  # type: ignore[arg-type]
        expected_comparison_evidence_digest=chain["comparison"].comparison_evidence_digest,  # type: ignore[union-attr]
        sharpe_evidence=chain["sharpe"],  # type: ignore[arg-type]
        expected_sharpe_evidence_digest=chain["sharpe"].sharpe_evidence_digest,  # type: ignore[union-attr]
        methodology=chain["methodology"],  # type: ignore[arg-type]
        expected_methodology_digest=chain["methodology"].methodology_digest,  # type: ignore[union-attr]
        edge_identity=chain["edge"],  # type: ignore[arg-type]
        expected_edge_identity_digest=chain["edge"].edge_identity_digest,  # type: ignore[union-attr]
        baseline_evidence=chain["baseline_evidence"],  # type: ignore[arg-type]
        expected_baseline_evidence_digest=chain["baseline_evidence"].baseline_evidence_digest,  # type: ignore[union-attr]
        gate_decision=chain["gate"],  # type: ignore[arg-type]
        expected_gate_decision_digest=chain["gate"].decision_digest,  # type: ignore[union-attr]
        completion_decision_id="completion-decision-1",
        correlation_id=_CORRELATION,
        metadata={"purpose": "stage4 completion v1"},
    )
    assert decision.ready, decision.reason_codes
    assert decision.stage4_completion_blockers == _V1_BLOCKERS
    return decision


_CHAIN_CACHE: dict[str, object] = {}
_NOT_SATISFIED_CACHE: dict[str, object] = {}


def _chain() -> dict[str, object]:
    if not _CHAIN_CACHE:
        edge = _edge_identity()
        baseline = _baseline(edge.paper_edge_id)
        baseline_evidence = _baseline_evidence(edge, baseline)
        series = _series()
        sharpe = _sharpe(series)
        gate = _gate(series)
        methodology = _comparison_methodology()
        comparison = _comparison_from(
            baseline=baseline,
            baseline_evidence=baseline_evidence,
            sharpe=sharpe,
            methodology=methodology,
            edge=edge,
            gate=gate,
        )
        assert comparison.comparison_verdict == "RETENTION_SATISFIED"
        _CHAIN_CACHE.update(
            {
                "edge": edge,
                "baseline": baseline,
                "baseline_evidence": baseline_evidence,
                "series": series,
                "sharpe": sharpe,
                "gate": gate,
                "methodology": methodology,
                "comparison": comparison,
            }
        )
        _CHAIN_CACHE["predecessor"] = _predecessor_from(_CHAIN_CACHE)
        _CHAIN_CACHE["attested_gate"] = _attested_gate()
    return _CHAIN_CACHE


def _not_satisfied_chain() -> dict[str, object]:
    if not _NOT_SATISFIED_CACHE:
        chain = _chain()
        sharpe = _reseal_sharpe(chain["sharpe"], paper_sharpe_annualized="0.500000000000000000")
        comparison = _comparison_from(
            baseline=chain["baseline"],
            baseline_evidence=chain["baseline_evidence"],
            sharpe=sharpe,
            methodology=chain["methodology"],
            edge=chain["edge"],
            gate=chain["gate"],
        )
        assert comparison.comparison_verdict == "RETENTION_NOT_SATISFIED"
        alt = dict(chain)
        alt["sharpe"] = sharpe
        alt["comparison"] = comparison
        predecessor = _predecessor_from(alt)
        assert predecessor.paper_methodology_verdict == "STAGE4_PAPER_METHOD_NOT_COMPLETE"
        _NOT_SATISFIED_CACHE.update({"sharpe": sharpe, "comparison": comparison, "predecessor": predecessor})
    return _NOT_SATISFIED_CACHE


def _reseal_sharpe(evidence: PaperSharpeEvidence, **changes: object) -> PaperSharpeEvidence:
    seed = replace(evidence, **changes)  # type: ignore[arg-type]
    return replace(seed, sharpe_evidence_digest=paper_sharpe_evidence_digest(seed))


def _reseal_gate(decision: PaperThirtyDayEvidenceGateDecision, **changes: object) -> PaperThirtyDayEvidenceGateDecision:
    seed = replace(decision, **changes)  # type: ignore[arg-type]
    return replace(seed, decision_digest=paper_30day_evidence_gate_decision_digest(seed))


def _reseal_comparison(evidence: PaperStage4ComparisonEvidence, **changes: object) -> PaperStage4ComparisonEvidence:
    seed = replace(evidence, **changes)  # type: ignore[arg-type]
    return replace(seed, comparison_evidence_digest=paper_stage4_comparison_evidence_digest(seed))


def _reseal_attested(
    decision: PaperAttestedOperationalThirtyDayGateDecision, **changes: object
) -> PaperAttestedOperationalThirtyDayGateDecision:
    seed = replace(decision, **changes)  # type: ignore[arg-type]
    return replace(
        seed,
        attested_operational_thirty_day_gate_decision_digest=(
            paper_attested_operational_thirty_day_gate_decision_digest(seed)
        ),
    )


def _reseal_predecessor(decision: PaperStage4CompletionDecision, **changes: object) -> PaperStage4CompletionDecision:
    seed = replace(decision, **changes)  # type: ignore[arg-type]
    return replace(seed, completion_decision_digest=paper_stage4_completion_decision_digest(seed))


def _carried_or_placeholder(value: object) -> str:
    return value if _is_hex64(value) else _HEX_A


def _build(**overrides: object) -> PaperStage4CompletionDecisionV2:
    chain = _chain()
    comparison = overrides.pop("comparison_evidence", chain["comparison"])
    sharpe = overrides.pop("sharpe_evidence", chain["sharpe"])
    methodology = overrides.pop("methodology", chain["methodology"])
    edge = overrides.pop("edge_identity", chain["edge"])
    baseline_evidence = overrides.pop("baseline_evidence", chain["baseline_evidence"])
    gate = overrides.pop("gate_decision", chain["gate"])
    attested = overrides.pop("attested_gate_decision", chain["attested_gate"])
    predecessor = overrides.pop("predecessor_decision", chain["predecessor"])
    payload: dict[str, object] = {
        "expected_comparison_evidence_digest": _carried_or_placeholder(
            getattr(comparison, "comparison_evidence_digest", "")
        ),
        "sharpe_evidence": sharpe,
        "expected_sharpe_evidence_digest": _carried_or_placeholder(getattr(sharpe, "sharpe_evidence_digest", "")),
        "methodology": methodology,
        "expected_methodology_digest": _carried_or_placeholder(getattr(methodology, "methodology_digest", "")),
        "edge_identity": edge,
        "expected_edge_identity_digest": _carried_or_placeholder(getattr(edge, "edge_identity_digest", "")),
        "baseline_evidence": baseline_evidence,
        "expected_baseline_evidence_digest": _carried_or_placeholder(
            getattr(baseline_evidence, "baseline_evidence_digest", "")
        ),
        "gate_decision": gate,
        "expected_gate_decision_digest": _carried_or_placeholder(getattr(gate, "decision_digest", "")),
        "attested_gate_decision": attested,
        "expected_attested_gate_decision_digest": _carried_or_placeholder(
            getattr(attested, "attested_operational_thirty_day_gate_decision_digest", "")
        ),
        "predecessor_decision": predecessor,
        "expected_predecessor_decision_digest": _carried_or_placeholder(
            getattr(predecessor, "completion_decision_digest", "")
        ),
        "completion_decision_id": "completion-decision-v2-1",
        "correlation_id": _CORRELATION,
        "metadata": {"purpose": "stage4 completion v2"},
    }
    payload.update(overrides)
    return build_paper_stage4_completion_decision_v2(comparison, **payload)  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------------------
# 1. Happy path (READY + BLOCKED) and determinism
# --------------------------------------------------------------------------------------------------


def test_ready_blocked_v2_decision() -> None:
    decision = _build()
    assert decision.status is PaperStage4CompletionDecisionV2Status.READY
    assert decision.ready is True
    assert decision.reason_codes == ()
    assert decision.schema_version == "paper-stage4-completion-decision.v2"
    assert decision.decision_version == "paper-stage4-completion-decision.v2"
    assert decision.completion_verdict == "STAGE4_COMPLETION_BLOCKED"
    assert decision.stage4_completion_decided is True
    assert decision.stage4_completion_blockers == _V2_BLOCKERS
    assert decision.completion_policy_id == "stage4_completion_blocked_pending_machine_time_and_secondary_metrics.v1"
    assert decision.paper_methodology_verdict == "STAGE4_PAPER_METHOD_COMPLETE"
    assert decision.paper_methodology_complete is True
    assert decision.attested_chain_link == _CHAIN_LINK
    assert _is_hex64(decision.completion_decision_digest)


def test_ready_decision_binds_attested_window_fields() -> None:
    decision = _build()
    assert decision.attested_day_count == 30
    assert decision.attested_selected_start_utc_day_index == _ATTESTED_START_DAY
    assert decision.attested_selected_end_utc_day_index == _ATTESTED_START_DAY + 29
    assert decision.gate_window_start_utc_day_index == _ATTESTED_START_DAY
    assert decision.gate_window_end_utc_day_index == _ATTESTED_START_DAY + 29
    assert decision.attested_gate_decision_id == "attested-gate-1"
    assert decision.predecessor_decision_id == "completion-decision-1"
    assert decision.predecessor_schema_version == "paper-stage4-completion-decision.v1"
    assert _is_hex64(decision.verified_attested_gate_decision_digest)
    assert _is_hex64(decision.verified_predecessor_decision_digest)


def test_ready_not_satisfied_methodology_path() -> None:
    alt = _not_satisfied_chain()
    decision = _build(
        comparison_evidence=alt["comparison"],
        sharpe_evidence=alt["sharpe"],
        predecessor_decision=alt["predecessor"],
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.READY
    assert decision.paper_methodology_verdict == "STAGE4_PAPER_METHOD_NOT_COMPLETE"
    assert decision.paper_methodology_complete is False
    assert decision.completion_verdict == "STAGE4_COMPLETION_BLOCKED"
    assert decision.stage4_completion_blockers == _V2_BLOCKERS


def test_deterministic_digest_roundtrip() -> None:
    first = _build()
    second = _build()
    assert first.completion_decision_digest == second.completion_decision_digest
    assert paper_stage4_completion_decision_v2_digest(first) == first.completion_decision_digest


def test_serializer_excludes_self_digest() -> None:
    decision = _build()
    payload = paper_stage4_completion_decision_v2_to_dict(decision)
    assert payload["completion_decision_digest"] == decision.completion_decision_digest
    del payload["completion_decision_digest"]
    assert _canonical(payload) == decision.completion_decision_digest


def test_frozen_immutability() -> None:
    decision = _build()
    with pytest.raises(FrozenInstanceError):
        decision.prdv4_stage4_complete = True  # type: ignore[misc]


def test_metadata_normalized_sorted() -> None:
    decision = _build(metadata={"b_key": "2", "a_key": "1"})
    assert decision.metadata == (("a_key", "1"), ("b_key", "2"))


# --------------------------------------------------------------------------------------------------
# 2. Digest anchors: tamper on every expected anchor
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("override_key", "reason_code"),
    [
        ("expected_comparison_evidence_digest", "comparison_evidence_digest_mismatch"),
        ("expected_sharpe_evidence_digest", "sharpe_evidence_digest_mismatch"),
        ("expected_methodology_digest", "methodology_digest_mismatch"),
        ("expected_edge_identity_digest", "edge_identity_digest_mismatch"),
        ("expected_baseline_evidence_digest", "baseline_evidence_digest_mismatch"),
        ("expected_gate_decision_digest", "gate_decision_digest_mismatch"),
        ("expected_attested_gate_decision_digest", "attested_gate_decision_digest_mismatch"),
        ("expected_predecessor_decision_digest", "predecessor_decision_digest_mismatch"),
    ],
)
def test_anchor_digest_tamper_rejected(override_key: str, reason_code: str) -> None:
    decision = _build(**{override_key: _HEX_A})
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert decision.ready is False
    assert _rc(reason_code) in decision.reason_codes
    assert decision.stage4_completion_decided is False
    assert decision.stage4_completion_blockers == ()


def test_comparison_carried_digest_tamper_rejected() -> None:
    chain = _chain()
    forged = replace(chain["comparison"], comparison_evidence_digest=_HEX_A)  # type: ignore[arg-type]
    decision = _build(comparison_evidence=forged, expected_comparison_evidence_digest=_HEX_A)
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("comparison_evidence_digest_mismatch") in decision.reason_codes


# --------------------------------------------------------------------------------------------------
# 3. Comparison-consumed reseal defense (real current fields)
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field_name",
    [
        "verified_sharpe_evidence_digest",
        "verified_comparison_methodology_digest",
        "verified_edge_identity_digest",
        "verified_baseline_evidence_digest",
        "verified_gate_decision_digest",
    ],
)
def test_comparison_consumed_reseal_rejected(field_name: str) -> None:
    chain = _chain()
    expected_field = field_name.replace("verified_", "expected_")
    resealed = _reseal_comparison(chain["comparison"], **{field_name: _HEX_A, expected_field: _HEX_A})
    decision = _build(
        comparison_evidence=resealed,
        expected_comparison_evidence_digest=resealed.comparison_evidence_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("comparison_binding_mismatch") in decision.reason_codes


def test_comparison_baseline_digest_reseal_rejected() -> None:
    chain = _chain()
    resealed = _reseal_comparison(chain["comparison"], baseline_digest=_HEX_A)
    decision = _build(
        comparison_evidence=resealed,
        expected_comparison_evidence_digest=resealed.comparison_evidence_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("baseline_digest_binding_mismatch") in decision.reason_codes


# --------------------------------------------------------------------------------------------------
# 4. Predecessor continuity
# --------------------------------------------------------------------------------------------------


def test_predecessor_schema_mismatch_rejected() -> None:
    chain = _chain()
    resealed = _reseal_predecessor(chain["predecessor"], schema_version="paper-stage4-completion-decision.v0")
    decision = _build(
        predecessor_decision=resealed,
        expected_predecessor_decision_digest=resealed.completion_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("predecessor_schema_version_mismatch") in decision.reason_codes


def test_predecessor_not_ready_rejected() -> None:
    chain = _chain()
    rejected_v1 = build_paper_stage4_completion_decision(
        chain["comparison"],  # type: ignore[arg-type]
        expected_comparison_evidence_digest=_HEX_A,
        sharpe_evidence=chain["sharpe"],  # type: ignore[arg-type]
        expected_sharpe_evidence_digest=chain["sharpe"].sharpe_evidence_digest,  # type: ignore[union-attr]
        methodology=chain["methodology"],  # type: ignore[arg-type]
        expected_methodology_digest=chain["methodology"].methodology_digest,  # type: ignore[union-attr]
        edge_identity=chain["edge"],  # type: ignore[arg-type]
        expected_edge_identity_digest=chain["edge"].edge_identity_digest,  # type: ignore[union-attr]
        baseline_evidence=chain["baseline_evidence"],  # type: ignore[arg-type]
        expected_baseline_evidence_digest=chain["baseline_evidence"].baseline_evidence_digest,  # type: ignore[union-attr]
        gate_decision=chain["gate"],  # type: ignore[arg-type]
        expected_gate_decision_digest=chain["gate"].decision_digest,  # type: ignore[union-attr]
        completion_decision_id="completion-decision-rejected",
        correlation_id=_CORRELATION,
    )
    assert rejected_v1.ready is False
    decision = _build(
        predecessor_decision=rejected_v1,
        expected_predecessor_decision_digest=rejected_v1.completion_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("predecessor_not_ready") in decision.reason_codes


def test_predecessor_wrong_verdict_rejected() -> None:
    chain = _chain()
    resealed = _reseal_predecessor(chain["predecessor"], completion_verdict="", stage4_completion_decided=False)
    decision = _build(
        predecessor_decision=resealed,
        expected_predecessor_decision_digest=resealed.completion_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("predecessor_verdict_incoherent") in decision.reason_codes


def test_predecessor_completion_flag_tamper_rejected() -> None:
    chain = _chain()
    resealed = _reseal_predecessor(chain["predecessor"], prdv4_stage4_complete=True)
    decision = _build(
        predecessor_decision=resealed,
        expected_predecessor_decision_digest=resealed.completion_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("predecessor_completion_flag_unsafe") in decision.reason_codes


def test_predecessor_blocker_tuple_tamper_rejected() -> None:
    chain = _chain()
    resealed = _reseal_predecessor(chain["predecessor"], stage4_completion_blockers=_V1_BLOCKERS[:3])
    decision = _build(
        predecessor_decision=resealed,
        expected_predecessor_decision_digest=resealed.completion_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("predecessor_blocker_tuple_mismatch") in decision.reason_codes


@pytest.mark.parametrize(
    ("field_name", "link_name"),
    [
        ("verified_comparison_evidence_digest", "comparison_evidence"),
        ("verified_sharpe_evidence_digest", "sharpe_evidence"),
        ("verified_comparison_methodology_digest", "comparison_methodology"),
        ("verified_edge_identity_digest", "edge_identity"),
        ("verified_baseline_evidence_digest", "baseline_evidence"),
        ("verified_gate_decision_digest", "gate_decision"),
    ],
)
def test_predecessor_chain_discontinuity_rejected(field_name: str, link_name: str) -> None:
    chain = _chain()
    resealed = _reseal_predecessor(chain["predecessor"], **{field_name: _HEX_A})
    decision = _build(
        predecessor_decision=resealed,
        expected_predecessor_decision_digest=resealed.completion_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc(f"predecessor_chain_discontinuity_{link_name}") in decision.reason_codes


def test_predecessor_correlation_mismatch_rejected() -> None:
    chain = _chain()
    resealed = _reseal_predecessor(chain["predecessor"], correlation_id="corr-2")
    decision = _build(
        predecessor_decision=resealed,
        expected_predecessor_decision_digest=resealed.completion_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("predecessor_correlation_mismatch") in decision.reason_codes


def test_predecessor_market_mismatch_rejected() -> None:
    chain = _chain()
    resealed = _reseal_predecessor(chain["predecessor"], market_symbol="ETH-PERPETUAL")
    decision = _build(
        predecessor_decision=resealed,
        expected_predecessor_decision_digest=resealed.completion_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("predecessor_market_symbol_mismatch") in decision.reason_codes


def test_predecessor_unsafe_flags_rejected() -> None:
    chain = _chain()
    resealed = _reseal_predecessor(chain["predecessor"], live_ready=True)
    decision = _build(
        predecessor_decision=resealed,
        expected_predecessor_decision_digest=resealed.completion_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("predecessor_unsafe_flags") in decision.reason_codes


# --------------------------------------------------------------------------------------------------
# 5. Attested gate coherence (checked BEFORE consuming selected-day fields)
# --------------------------------------------------------------------------------------------------


def test_attested_gate_schema_mismatch_rejected() -> None:
    chain = _chain()
    resealed = _reseal_attested(chain["attested_gate"], schema_version="x.v0")
    decision = _build(
        attested_gate_decision=resealed,
        expected_attested_gate_decision_digest=resealed.attested_operational_thirty_day_gate_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("attested_gate_schema_version_mismatch") in decision.reason_codes


def test_attested_gate_not_ready_rejected() -> None:
    chain = _chain()
    resealed = _reseal_attested(
        chain["attested_gate"],
        status=PaperAttestedOperationalThirtyDayGateDecisionStatus.REJECTED,
        ready=False,
    )
    decision = _build(
        attested_gate_decision=resealed,
        expected_attested_gate_decision_digest=resealed.attested_operational_thirty_day_gate_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("attested_gate_not_ready") in decision.reason_codes


def test_attested_gate_reason_codes_present_rejected() -> None:
    chain = _chain()
    resealed = _reseal_attested(chain["attested_gate"], reason_codes=("some_upstream_reason",))
    decision = _build(
        attested_gate_decision=resealed,
        expected_attested_gate_decision_digest=resealed.attested_operational_thirty_day_gate_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("attested_gate_reason_codes_present") in decision.reason_codes


def test_attested_gate_not_decided_rejected() -> None:
    chain = _chain()
    resealed = _reseal_attested(chain["attested_gate"], attested_operational_thirty_day_gate_decided=False)
    decision = _build(
        attested_gate_decision=resealed,
        expected_attested_gate_decision_digest=resealed.attested_operational_thirty_day_gate_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("attested_gate_not_decided") in decision.reason_codes


def test_attested_gate_not_satisfied_rejected() -> None:
    chain = _chain()
    resealed = _reseal_attested(chain["attested_gate"], attested_operational_thirty_day_gate_satisfied=False)
    decision = _build(
        attested_gate_decision=resealed,
        expected_attested_gate_decision_digest=resealed.attested_operational_thirty_day_gate_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("attested_gate_not_satisfied") in decision.reason_codes


def test_attested_gate_policy_mismatch_rejected() -> None:
    chain = _chain()
    resealed = _reseal_attested(chain["attested_gate"], gate_policy_id="weakened.v1")
    decision = _build(
        attested_gate_decision=resealed,
        expected_attested_gate_decision_digest=resealed.attested_operational_thirty_day_gate_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("attested_gate_policy_mismatch") in decision.reason_codes


def test_attested_gate_unsafe_flags_rejected() -> None:
    chain = _chain()
    resealed = _reseal_attested(chain["attested_gate"], machine_time_origin_proven=True)
    decision = _build(
        attested_gate_decision=resealed,
        expected_attested_gate_decision_digest=resealed.attested_operational_thirty_day_gate_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("attested_gate_unsafe_flags") in decision.reason_codes


def test_attested_gate_correlation_mismatch_rejected() -> None:
    chain = _chain()
    resealed = _reseal_attested(chain["attested_gate"], correlation_id="corr-2")
    decision = _build(
        attested_gate_decision=resealed,
        expected_attested_gate_decision_digest=resealed.attested_operational_thirty_day_gate_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("attested_gate_correlation_mismatch") in decision.reason_codes


def test_attested_gate_market_mismatch_rejected() -> None:
    chain = _chain()
    resealed = _reseal_attested(chain["attested_gate"], market_symbol="ETH-PERPETUAL")
    decision = _build(
        attested_gate_decision=resealed,
        expected_attested_gate_decision_digest=resealed.attested_operational_thirty_day_gate_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("attested_gate_market_symbol_mismatch") in decision.reason_codes


# --------------------------------------------------------------------------------------------------
# 6. Day-index alignment (alignment BEFORE division; inclusive end = end_ns // DAY_NS - 1)
# --------------------------------------------------------------------------------------------------


def test_gate_window_start_misaligned_rejected() -> None:
    chain = _chain()
    resealed = _reseal_gate(
        chain["gate"],
        gate_used_first_bucket_start_ns=chain["gate"].gate_used_first_bucket_start_ns + 1,  # type: ignore[union-attr]
    )
    decision = _build(gate_decision=resealed, expected_gate_decision_digest=resealed.decision_digest)
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("gate_window_start_not_day_aligned") in decision.reason_codes
    assert decision.gate_window_start_utc_day_index == 0
    assert decision.gate_window_end_utc_day_index == 0


def test_gate_window_end_misaligned_rejected() -> None:
    chain = _chain()
    resealed = _reseal_gate(
        chain["gate"],
        gate_used_last_bucket_end_ns=chain["gate"].gate_used_last_bucket_end_ns + 1,  # type: ignore[union-attr]
    )
    decision = _build(gate_decision=resealed, expected_gate_decision_digest=resealed.decision_digest)
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("gate_window_end_not_day_aligned") in decision.reason_codes


def test_end_day_off_by_one_rejected() -> None:
    chain = _chain()
    resealed = _reseal_gate(
        chain["gate"],
        gate_used_last_bucket_end_ns=chain["gate"].gate_used_last_bucket_end_ns + _DAY_NS,  # type: ignore[union-attr]
    )
    decision = _build(gate_decision=resealed, expected_gate_decision_digest=resealed.decision_digest)
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("attested_window_end_mismatch") in decision.reason_codes


def test_gate_window_end_must_equal_30th_selected_day() -> None:
    chain = _chain()
    forged_end_ns = chain["gate"].gate_used_last_bucket_end_ns + _DAY_NS  # type: ignore[union-attr]
    forged_end_day = (forged_end_ns // _DAY_NS) - 1
    resealed_gate = _reseal_gate(chain["gate"], gate_used_last_bucket_end_ns=forged_end_ns)
    resealed_attested = _reseal_attested(chain["attested_gate"], selected_end_utc_day_index=forged_end_day)
    decision = _build(
        gate_decision=resealed_gate,
        expected_gate_decision_digest=resealed_gate.decision_digest,
        attested_gate_decision=resealed_attested,
        expected_attested_gate_decision_digest=(resealed_attested.attested_operational_thirty_day_gate_decision_digest),
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("gate_window_end_day_mismatch") in decision.reason_codes


def test_attested_window_start_mismatch_rejected() -> None:
    chain = _chain()
    resealed = _reseal_attested(
        chain["attested_gate"],
        selected_start_utc_day_index=_ATTESTED_START_DAY + 1,
    )
    decision = _build(
        attested_gate_decision=resealed,
        expected_attested_gate_decision_digest=resealed.attested_operational_thirty_day_gate_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("attested_window_start_mismatch") in decision.reason_codes


def test_selected_day_indices_mismatch_rejected() -> None:
    chain = _chain()
    shifted = tuple(range(_ATTESTED_START_DAY + 1, _ATTESTED_START_DAY + 31))
    resealed = _reseal_attested(chain["attested_gate"], selected_utc_day_indices=shifted)
    decision = _build(
        attested_gate_decision=resealed,
        expected_attested_gate_decision_digest=resealed.attested_operational_thirty_day_gate_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("attested_day_indices_mismatch") in decision.reason_codes


def test_duplicate_selected_day_digest_rejected() -> None:
    chain = _chain()
    digests = list(chain["attested_gate"].selected_operational_day_evidence_digests)  # type: ignore[union-attr]
    digests[1] = digests[0]
    resealed = _reseal_attested(chain["attested_gate"], selected_operational_day_evidence_digests=tuple(digests))
    decision = _build(
        attested_gate_decision=resealed,
        expected_attested_gate_decision_digest=resealed.attested_operational_thirty_day_gate_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("attested_day_digest_duplicate") in decision.reason_codes


def test_too_few_selected_day_digests_rejected() -> None:
    chain = _chain()
    digests = chain["attested_gate"].selected_operational_day_evidence_digests[:29]  # type: ignore[union-attr]
    resealed = _reseal_attested(chain["attested_gate"], selected_operational_day_evidence_digests=digests)
    decision = _build(
        attested_gate_decision=resealed,
        expected_attested_gate_decision_digest=resealed.attested_operational_thirty_day_gate_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("attested_day_digest_count_invalid") in decision.reason_codes


def test_too_few_selected_day_indices_rejected() -> None:
    chain = _chain()
    indices = chain["attested_gate"].selected_utc_day_indices[:29]  # type: ignore[union-attr]
    resealed = _reseal_attested(chain["attested_gate"], selected_utc_day_indices=indices)
    decision = _build(
        attested_gate_decision=resealed,
        expected_attested_gate_decision_digest=resealed.attested_operational_thirty_day_gate_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("attested_day_count_invalid") in decision.reason_codes


def test_too_many_selected_day_indices_rejected() -> None:
    chain = _chain()
    indices = (*chain["attested_gate"].selected_utc_day_indices, _ATTESTED_START_DAY + 30)  # type: ignore[union-attr]
    resealed = _reseal_attested(chain["attested_gate"], selected_utc_day_indices=indices)
    decision = _build(
        attested_gate_decision=resealed,
        expected_attested_gate_decision_digest=resealed.attested_operational_thirty_day_gate_decision_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("attested_day_count_invalid") in decision.reason_codes


def test_gate_bucket_count_invalid_rejected() -> None:
    chain = _chain()
    resealed = _reseal_gate(chain["gate"], gate_bucket_count_used=29)
    decision = _build(gate_decision=resealed, expected_gate_decision_digest=resealed.decision_digest)
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("gate_bucket_count_invalid") in decision.reason_codes


# --------------------------------------------------------------------------------------------------
# 7. Correlation / market coherence via builder argument
# --------------------------------------------------------------------------------------------------


def test_builder_correlation_mismatch_rejected() -> None:
    decision = _build(correlation_id="corr-2")
    assert decision.status is PaperStage4CompletionDecisionV2Status.REJECTED
    assert _rc("correlation_id_mismatch") in decision.reason_codes
    assert _rc("attested_gate_correlation_mismatch") in decision.reason_codes
    assert _rc("predecessor_correlation_mismatch") in decision.reason_codes


# --------------------------------------------------------------------------------------------------
# 8. Blockers, chain link, and non-overclaim surface
# --------------------------------------------------------------------------------------------------


def test_blocker_tuple_exactness() -> None:
    decision = _build()
    assert decision.stage4_completion_blockers == _V2_BLOCKERS
    assert "operational_day_evidence_source_unavailable" not in decision.stage4_completion_blockers
    assert "prdv4_minimum_30_day_live_paper_trading_unproven" not in decision.stage4_completion_blockers
    assert decision.stage4_completion_blockers[0] == "operator_attested_only_machine_time_origin_unproven"


def test_chain_link_label_preserved() -> None:
    decision = _build()
    assert decision.attested_chain_link == _CHAIN_LINK
    payload = paper_stage4_completion_decision_v2_to_dict(decision)
    assert payload["attested_chain_link"] == _CHAIN_LINK


def test_structural_false_flags_on_ready() -> None:
    decision = _build()
    for flag in _STRUCTURAL_FALSE_FLAGS:
        assert getattr(decision, flag) is False, flag
    assert decision.paper_only is True
    assert decision.comparison_evidence_consumed is True
    assert decision.attested_operational_thirty_day_gate_consumed is True
    assert decision.predecessor_decision_consumed is True
    assert decision.operational_day_gate_deferred is False
    assert decision.operational_day_evidence_consumed is False


def test_structural_false_flags_on_rejected() -> None:
    decision = _build(expected_comparison_evidence_digest=_HEX_A)
    for flag in _STRUCTURAL_FALSE_FLAGS:
        assert getattr(decision, flag) is False, flag


def test_reason_code_prefix_consistency() -> None:
    decision = _build(expected_comparison_evidence_digest=_HEX_A, correlation_id="corr-2")
    assert decision.reason_codes
    for reason in decision.reason_codes:
        assert reason.startswith("paper_stage4_completion_decision_v2:"), reason


# --------------------------------------------------------------------------------------------------
# 9. Raise-vs-REJECTED boundary (call-level malformed input raises)
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwarg_name", "reason_code"),
    [
        ("sharpe_evidence", "sharpe_evidence_malformed"),
        ("methodology", "methodology_malformed"),
        ("edge_identity", "edge_identity_malformed"),
        ("baseline_evidence", "baseline_evidence_malformed"),
        ("gate_decision", "gate_decision_malformed"),
        ("attested_gate_decision", "attested_gate_decision_malformed"),
        ("predecessor_decision", "predecessor_decision_malformed"),
    ],
)
def test_wrong_type_artifact_raises(kwarg_name: str, reason_code: str) -> None:
    with pytest.raises(PaperStage4CompletionDecisionV2Error, match=_rc(reason_code)):
        _build(**{kwarg_name: object()})


def test_wrong_type_comparison_raises() -> None:
    with pytest.raises(PaperStage4CompletionDecisionV2Error, match=_rc("comparison_evidence_malformed")):
        _build(comparison_evidence=object(), expected_comparison_evidence_digest=_HEX_A)


def test_subclass_artifact_raises() -> None:
    chain = _chain()
    impostor = _SharpeSub(**{field.name: getattr(chain["sharpe"], field.name) for field in fields(PaperSharpeEvidence)})
    with pytest.raises(PaperStage4CompletionDecisionV2Error, match=_rc("sharpe_evidence_malformed")):
        _build(sharpe_evidence=impostor)


def test_malformed_expected_digest_raises() -> None:
    with pytest.raises(
        PaperStage4CompletionDecisionV2Error, match=_rc("expected_attested_gate_decision_digest_invalid")
    ):
        _build(expected_attested_gate_decision_digest="xyz")


def test_malformed_completion_decision_id_raises() -> None:
    with pytest.raises(PaperStage4CompletionDecisionV2Error, match=_rc("completion_decision_id_invalid")):
        _build(completion_decision_id="  ")


def test_liar_str_correlation_raises() -> None:
    with pytest.raises(PaperStage4CompletionDecisionV2Error, match=_rc("correlation_id_invalid")):
        _build(correlation_id=_LiarStr(_CORRELATION))


def test_malformed_metadata_raises() -> None:
    with pytest.raises(PaperStage4CompletionDecisionV2Error, match=_rc("metadata_malformed")):
        _build(metadata={"key": 1})


def test_scope_violation_raises() -> None:
    with pytest.raises(PaperStage4CompletionDecisionV2Error, match=_rc("scope_violation")):
        _build(metadata={"note": "live_order path"})


def test_clock_token_raises() -> None:
    with pytest.raises(PaperStage4CompletionDecisionV2Error, match=_rc("clock_token_forbidden")):
        _build(metadata={"note": "wall_clock source"})


# --------------------------------------------------------------------------------------------------
# 10. Module structure: AST forbidden surface + structural-False assignment scan
# --------------------------------------------------------------------------------------------------

_ALLOWED_IMPORT_ROOTS = {
    "__future__",
    "hashlib",
    "json",
    "re",
    "collections",
    "dataclasses",
    "decimal",
    "enum",
}
_ALLOWED_CRYPTO_IMPORTS = {
    "crypto_core.validation.paper_30day_evidence_gate_decision",
    "crypto_core.validation.paper_attested_operational_thirty_day_gate_decision",
    "crypto_core.validation.paper_edge_identity_evidence",
    "crypto_core.validation.paper_sharpe_evidence",
    "crypto_core.validation.paper_stage4_backtest_baseline_evidence",
    "crypto_core.validation.paper_stage4_comparison_evidence",
    "crypto_core.validation.paper_stage4_completion_decision",
    "crypto_core.validation.paper_vs_backtest_methodology",
}


def _module_source() -> str:
    return Path(v2_module.__file__).read_text(encoding="utf-8")


def test_forbidden_imports_ast() -> None:
    tree = ast.parse(_module_source())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in _ALLOWED_IMPORT_ROOTS, alias.name
        elif isinstance(node, ast.ImportFrom):
            module_name = node.module or ""
            if module_name.startswith("crypto_core"):
                assert module_name in _ALLOWED_CRYPTO_IMPORTS, module_name
            else:
                assert module_name.split(".")[0] in _ALLOWED_IMPORT_ROOTS, module_name


def test_no_comparator_or_runtime_surface_in_module() -> None:
    source = _module_source()
    # ``stage4_comparator`` as a standalone token means a module reference/import (forbidden). The
    # ``stage4_comparator_invoked`` flag we read on upstream artifacts is a different token and is allowed.
    assert re.search(r"(?<![A-Za-z0-9_])stage4_comparator(?![A-Za-z0-9_])", source) is None
    for token in ("socket", "urllib", "requests", "subprocess", "threading", "pathlib", "os.path"):
        assert re.search(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])", source) is None, token
    assert re.search(r"(?<![A-Za-z0-9_])open\s*\(", source) is None
    assert re.search(r"(?<![A-Za-z0-9_])import\s+time(?![A-Za-z0-9_])", source) is None
    assert re.search(r"(?<![A-Za-z0-9_])import\s+datetime(?![A-Za-z0-9_])", source) is None


def test_structural_false_never_assigned_true() -> None:
    source = _module_source()
    for flag in _STRUCTURAL_FALSE_FLAGS:
        pattern = rf"(?<![A-Za-z0-9_]){flag}\s*(?::\s*bool\s*)?=\s*True"
        assert re.search(pattern, source) is None, flag


def test_structural_false_defaults_in_dataclass() -> None:
    field_defaults = {field.name: field.default for field in fields(PaperStage4CompletionDecisionV2)}
    for flag in _STRUCTURAL_FALSE_FLAGS:
        assert field_defaults[flag] is False, flag
    assert field_defaults["paper_only"] is True
    assert field_defaults["attested_operational_thirty_day_gate_consumed"] is True
    assert field_defaults["predecessor_decision_consumed"] is True
    assert field_defaults["operational_day_gate_deferred"] is False
