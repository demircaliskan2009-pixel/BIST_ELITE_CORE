"""Tests for the deterministic paper Stage-4 completion decision (v1 = BLOCKED completion)."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import FrozenInstanceError, dataclass, fields, replace
from fractions import Fraction
from pathlib import Path

import pytest

from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, validate_strategy_spec
from crypto_core.validation import paper_daily_return_series_evidence as series_module
from crypto_core.validation import paper_stage4_completion_decision as completion_module
from crypto_core.validation.paper_30day_evidence_gate_decision import (
    PaperThirtyDayEvidenceGateDecision,
    build_paper_30day_evidence_gate_decision,
    paper_30day_evidence_gate_decision_digest,
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
from crypto_core.validation.paper_return_series_methodology import build_paper_return_series_methodology
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
from crypto_core.validation.paper_stage4_comparison_evidence import (
    PaperStage4ComparisonEvidence,
    build_paper_stage4_comparison_evidence,
    paper_stage4_comparison_evidence_digest,
)
from crypto_core.validation.paper_stage4_completion_decision import (
    PaperStage4CompletionDecision,
    PaperStage4CompletionDecisionError,
    PaperStage4CompletionDecisionStatus,
    build_paper_stage4_completion_decision,
    paper_stage4_completion_decision_digest,
    paper_stage4_completion_decision_to_dict,
)
from crypto_core.validation.paper_vs_backtest_methodology import (
    PaperVsBacktestMethodology,
    build_paper_vs_backtest_methodology,
    paper_vs_backtest_methodology_digest,
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
_EXPECTED_BLOCKERS = (
    "prdv4_minimum_30_day_live_paper_trading_unproven",
    "operational_day_evidence_source_unavailable",
    "timestamp_origin_not_proven_injected_deterministic_time_only",
    "secondary_comparison_metrics_hit_fill_slippage_declared_not_enforced_v1",
)


class _LiarStr(str):
    """A ``str`` subclass rejected by exact ``type(x) is str`` checks."""


@dataclass(frozen=True)
class _SharpeSub(PaperSharpeEvidence):
    """Subclass test double; exact input types are required."""


def _rc(code: str) -> str:
    return f"paper_stage4_completion_decision:{code}"


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _canonical(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------------------------------
# Fixture chain: real merged builders end-to-end, then one READY comparison evidence, then the
# completion decision under test.
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
    return _CHAIN_CACHE


def _not_satisfied_chain() -> dict[str, object]:
    if not _NOT_SATISFIED_CACHE:
        chain = _chain()
        # A digest-self-consistent sharpe evidence whose annualized Sharpe fails the 0.5 retention against
        # the baseline Sharpe 1.5 (0.5 / 1.5 < 0.5). The REAL comparison builder then renders a genuine
        # READY RETENTION_NOT_SATISFIED comparison evidence.
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
        _NOT_SATISFIED_CACHE.update({"sharpe": sharpe, "comparison": comparison})
    return _NOT_SATISFIED_CACHE


def _reseal_sharpe(evidence: PaperSharpeEvidence, **changes: object) -> PaperSharpeEvidence:
    seed = replace(evidence, **changes)  # type: ignore[arg-type]
    return replace(seed, sharpe_evidence_digest=paper_sharpe_evidence_digest(seed))


def _reseal_gate(decision: PaperThirtyDayEvidenceGateDecision, **changes: object) -> PaperThirtyDayEvidenceGateDecision:
    seed = replace(decision, **changes)  # type: ignore[arg-type]
    return replace(seed, decision_digest=paper_30day_evidence_gate_decision_digest(seed))


def _reseal_methodology(methodology: PaperVsBacktestMethodology, **changes: object) -> PaperVsBacktestMethodology:
    seed = replace(methodology, **changes)  # type: ignore[arg-type]
    return replace(seed, methodology_digest=paper_vs_backtest_methodology_digest(seed))


def _reseal_edge(evidence: PaperEdgeIdentityEvidence, **changes: object) -> PaperEdgeIdentityEvidence:
    seed = replace(evidence, **changes)  # type: ignore[arg-type]
    return replace(seed, edge_identity_digest=paper_edge_identity_evidence_digest(seed))


def _reseal_baseline_evidence(
    evidence: PaperStage4BacktestBaselineEvidence, **changes: object
) -> PaperStage4BacktestBaselineEvidence:
    seed = replace(evidence, **changes)  # type: ignore[arg-type]
    return replace(seed, baseline_evidence_digest=paper_stage4_backtest_baseline_evidence_digest(seed))


def _reseal_comparison(evidence: PaperStage4ComparisonEvidence, **changes: object) -> PaperStage4ComparisonEvidence:
    seed = replace(evidence, **changes)  # type: ignore[arg-type]
    return replace(seed, comparison_evidence_digest=paper_stage4_comparison_evidence_digest(seed))


def _carried_or_placeholder(value: object) -> str:
    return value if _is_hex64(value) else _HEX_A


def _build(**overrides: object) -> PaperStage4CompletionDecision:
    chain = _chain()
    comparison = overrides.pop("comparison_evidence", chain["comparison"])
    sharpe = overrides.pop("sharpe_evidence", chain["sharpe"])
    methodology = overrides.pop("methodology", chain["methodology"])
    edge = overrides.pop("edge_identity", chain["edge"])
    baseline_evidence = overrides.pop("baseline_evidence", chain["baseline_evidence"])
    gate = overrides.pop("gate_decision", chain["gate"])
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
        "completion_decision_id": "completion-decision-1",
        "correlation_id": _CORRELATION,
        "metadata": {"purpose": "stage4 completion decision"},
    }
    payload.update(overrides)
    return build_paper_stage4_completion_decision(comparison, **payload)  # type: ignore[arg-type]


def _build_not_satisfied(**overrides: object) -> PaperStage4CompletionDecision:
    variant = _not_satisfied_chain()
    payload: dict[str, object] = {
        "comparison_evidence": variant["comparison"],
        "sharpe_evidence": variant["sharpe"],
    }
    payload.update(overrides)
    return _build(**payload)


# --------------------------------------------------------------------------------------------------
# 1. Public API
# --------------------------------------------------------------------------------------------------


def test_public_api_exports_present() -> None:
    assert set(completion_module.__all__) == {
        "PaperStage4CompletionDecision",
        "PaperStage4CompletionDecisionError",
        "PaperStage4CompletionDecisionStatus",
        "build_paper_stage4_completion_decision",
        "paper_stage4_completion_decision_digest",
        "paper_stage4_completion_decision_to_dict",
    }


def test_status_enum_values() -> None:
    assert PaperStage4CompletionDecisionStatus.READY.value == "READY"
    assert PaperStage4CompletionDecisionStatus.REJECTED.value == "REJECTED"


def test_output_is_frozen() -> None:
    decision = _build()
    with pytest.raises(FrozenInstanceError):
        decision.ready = False  # type: ignore[misc]


# --------------------------------------------------------------------------------------------------
# 2. READY + methodology COMPLETE (completion still BLOCKED)
# --------------------------------------------------------------------------------------------------


def test_ready_methodology_complete_blocked_completion() -> None:
    chain = _chain()
    decision = _build()
    assert decision.status is PaperStage4CompletionDecisionStatus.READY
    assert decision.ready is True
    assert decision.reason_codes == ()
    assert decision.paper_methodology_verdict == "STAGE4_PAPER_METHOD_COMPLETE"
    assert decision.paper_methodology_complete is True
    assert decision.comparison_verdict_echo == "RETENTION_SATISFIED"
    assert decision.sharpe_retention_satisfied_echo is True
    assert decision.completion_verdict == "STAGE4_COMPLETION_BLOCKED"
    assert decision.stage4_completion_decided is True
    assert decision.stage4_completion_blockers == _EXPECTED_BLOCKERS
    assert decision.prdv4_stage4_complete is False
    assert decision.completion_scope == "prdv4_stage4_full_definition.v1"
    assert decision.completion_policy_id == "stage4_completion_blocked_pending_operational_day_source.v1"
    comparison = chain["comparison"]
    assert decision.sharpe_retention_ratio_decimal == comparison.sharpe_retention_ratio_decimal
    assert decision.sharpe_retention_threshold == _RETENTION_THRESHOLD
    assert decision.retention_comparison_operator == ">="


def test_ready_binds_identity_and_digest_echoes() -> None:
    chain = _chain()
    comparison = chain["comparison"]
    decision = _build()
    assert decision.paper_id == _PAPER_ID
    assert decision.series_id == "series-1"
    assert decision.window_id == "window-1"
    assert decision.market_symbol == _MARKET
    assert decision.paper_edge_id == chain["edge"].paper_edge_id
    assert decision.baseline_id == "baseline-1"
    assert decision.strategy_id == "alpha-funding-carry"
    assert decision.verified_comparison_evidence_digest == comparison.comparison_evidence_digest
    assert decision.verified_sharpe_evidence_digest == chain["sharpe"].sharpe_evidence_digest
    assert decision.verified_comparison_methodology_digest == chain["methodology"].methodology_digest
    assert decision.verified_edge_identity_digest == chain["edge"].edge_identity_digest
    assert decision.verified_baseline_evidence_digest == chain["baseline_evidence"].baseline_evidence_digest
    assert decision.verified_gate_decision_digest == chain["gate"].decision_digest
    assert decision.baseline_digest == comparison.baseline_digest
    assert decision.paper_summary_digest == comparison.paper_summary_digest
    assert decision.series_digest == comparison.series_digest
    assert decision.min_duration_days == 30
    assert decision.bucket_count == 30
    assert decision.window_duration_ns == 30 * _DAY_NS


# --------------------------------------------------------------------------------------------------
# 3. READY + methodology NOT complete (completion still BLOCKED)
# --------------------------------------------------------------------------------------------------


def test_ready_methodology_not_complete_still_blocked() -> None:
    decision = _build_not_satisfied()
    assert decision.status is PaperStage4CompletionDecisionStatus.READY
    assert decision.ready is True
    assert decision.reason_codes == ()
    assert decision.paper_methodology_verdict == "STAGE4_PAPER_METHOD_NOT_COMPLETE"
    assert decision.paper_methodology_complete is False
    assert decision.comparison_verdict_echo == "RETENTION_NOT_SATISFIED"
    assert decision.sharpe_retention_satisfied_echo is False
    assert decision.completion_verdict == "STAGE4_COMPLETION_BLOCKED"
    assert decision.stage4_completion_decided is True
    assert decision.stage4_completion_blockers == _EXPECTED_BLOCKERS
    assert decision.prdv4_stage4_complete is False


# --------------------------------------------------------------------------------------------------
# 4. Comparison evidence rejected / not ready
# --------------------------------------------------------------------------------------------------


def test_comparison_not_ready_rejects() -> None:
    comparison = _reseal_comparison(_chain()["comparison"], ready=False)
    decision = _build(comparison_evidence=comparison)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("comparison_evidence_not_ready") in decision.reason_codes
    assert decision.paper_methodology_verdict == ""
    assert decision.paper_methodology_complete is False
    assert decision.completion_verdict == ""
    assert decision.stage4_completion_decided is False
    assert decision.stage4_completion_blockers == ()
    assert decision.prdv4_stage4_complete is False


def test_comparison_comparator_not_invoked_rejects() -> None:
    comparison = _reseal_comparison(_chain()["comparison"], stage4_comparator_invoked=False)
    decision = _build(comparison_evidence=comparison)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("comparator_not_invoked_upstream") in decision.reason_codes


def test_comparison_not_performed_rejects() -> None:
    comparison = _reseal_comparison(_chain()["comparison"], comparison_performed=False)
    decision = _build(comparison_evidence=comparison)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("comparison_not_performed") in decision.reason_codes


# --------------------------------------------------------------------------------------------------
# 5. Digest tamper / anchor mismatch matrix (all six inputs)
# --------------------------------------------------------------------------------------------------


def test_comparison_digest_tamper_rejects() -> None:
    tampered = replace(_chain()["comparison"], comparison_evidence_id="tampered")
    decision = _build(
        comparison_evidence=tampered,
        expected_comparison_evidence_digest=_chain()["comparison"].comparison_evidence_digest,
    )
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("comparison_evidence_digest_mismatch") in decision.reason_codes


def test_comparison_anchor_mismatch_rejects() -> None:
    decision = _build(expected_comparison_evidence_digest="b" * 64)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("comparison_evidence_digest_mismatch") in decision.reason_codes


@pytest.mark.parametrize(
    ("key", "field_name", "reason"),
    [
        ("sharpe_evidence", "sharpe_evidence_id", "sharpe_evidence_digest_mismatch"),
        ("methodology", "methodology_id", "methodology_digest_mismatch"),
        ("edge_identity", "edge_identity_id", "edge_identity_digest_mismatch"),
        ("baseline_evidence", "baseline_evidence_id", "baseline_evidence_digest_mismatch"),
        ("gate_decision", "gate_id", "gate_decision_digest_mismatch"),
    ],
)
def test_upstream_digest_tamper_rejects(key: str, field_name: str, reason: str) -> None:
    chain = _chain()
    source_key = {"gate_decision": "gate", "edge_identity": "edge", "sharpe_evidence": "sharpe"}.get(key, key)
    tampered = replace(chain[source_key], **{field_name: "tampered"})  # type: ignore[arg-type]
    decision = _build(**{key: tampered})
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc(reason) in decision.reason_codes


@pytest.mark.parametrize(
    ("anchor_key", "reason"),
    [
        ("expected_sharpe_evidence_digest", "sharpe_evidence_digest_mismatch"),
        ("expected_methodology_digest", "methodology_digest_mismatch"),
        ("expected_edge_identity_digest", "edge_identity_digest_mismatch"),
        ("expected_baseline_evidence_digest", "baseline_evidence_digest_mismatch"),
        ("expected_gate_decision_digest", "gate_decision_digest_mismatch"),
    ],
)
def test_upstream_anchor_mismatch_rejects(anchor_key: str, reason: str) -> None:
    decision = _build(**{anchor_key: "b" * 64})
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc(reason) in decision.reason_codes


def test_forged_non_serializable_input_rejects_without_type_error() -> None:
    forged = replace(_chain()["sharpe"], metadata=(("purpose", object()),))  # type: ignore[arg-type]
    decision = _build(sharpe_evidence=forged, expected_sharpe_evidence_digest=_HEX_A)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("sharpe_evidence_digest_mismatch") in decision.reason_codes


def test_forged_non_serializable_comparison_rejects_without_type_error() -> None:
    forged = replace(_chain()["comparison"], metadata=(("purpose", object()),))  # type: ignore[arg-type]
    decision = _build(comparison_evidence=forged, expected_comparison_evidence_digest=_HEX_A)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("comparison_evidence_digest_mismatch") in decision.reason_codes


# --------------------------------------------------------------------------------------------------
# 6. Reseal defense: comparison must be bound to EXACTLY the supplied upstream artifacts
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "reseal"),
    [
        ("sharpe_evidence", lambda chain: _reseal_sharpe(chain["sharpe"], sharpe_evidence_id="sharpe-evidence-2")),
        (
            "methodology",
            lambda chain: _reseal_methodology(chain["methodology"], methodology_id="comparison-methodology-2"),
        ),
        ("edge_identity", lambda chain: _reseal_edge(chain["edge"], edge_identity_id="edge-identity-2")),
        (
            "baseline_evidence",
            lambda chain: _reseal_baseline_evidence(
                chain["baseline_evidence"], baseline_evidence_id="baseline-evidence-2"
            ),
        ),
        ("gate_decision", lambda chain: _reseal_gate(chain["gate"], gate_id="gate-2")),
    ],
)
def test_comparison_binding_mismatch_rejects(key: str, reseal) -> None:
    # The substituted artifact is digest-self-consistent and internally valid, but it is NOT the artifact
    # the comparison evidence consumed — the completion boundary must refuse the swap.
    substituted = reseal(_chain())
    decision = _build(**{key: substituted})
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("comparison_binding_mismatch") in decision.reason_codes


def test_comparison_expected_verified_pair_mismatch_rejects() -> None:
    comparison = _reseal_comparison(_chain()["comparison"], verified_sharpe_evidence_digest="c" * 64)
    decision = _build(comparison_evidence=comparison)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("comparison_binding_mismatch") in decision.reason_codes


def test_baseline_digest_binding_mismatch_rejects() -> None:
    comparison = _reseal_comparison(_chain()["comparison"], baseline_digest="d" * 64)
    decision = _build(comparison_evidence=comparison)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("baseline_digest_binding_mismatch") in decision.reason_codes


def test_paper_sharpe_echo_binding_mismatch_rejects() -> None:
    comparison = _reseal_comparison(_chain()["comparison"], paper_sharpe_annualized="1.000000000000000000")
    decision = _build(comparison_evidence=comparison)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("comparison_binding_mismatch") in decision.reason_codes


# --------------------------------------------------------------------------------------------------
# 7. Schema / not-ready / unsafe-flag matrices
# --------------------------------------------------------------------------------------------------


def test_comparison_schema_invalid_rejects() -> None:
    comparison = _reseal_comparison(_chain()["comparison"], schema_version="paper-stage4-comparison-evidence.v0")
    decision = _build(comparison_evidence=comparison)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("comparison_evidence_schema_invalid") in decision.reason_codes


@pytest.mark.parametrize(
    ("key", "reseal", "reason"),
    [
        (
            "sharpe_evidence",
            lambda chain: _reseal_sharpe(chain["sharpe"], schema_version="x.v0"),
            "sharpe_evidence_schema_invalid",
        ),
        (
            "methodology",
            lambda chain: _reseal_methodology(chain["methodology"], schema_version="x.v0"),
            "methodology_schema_invalid",
        ),
        (
            "edge_identity",
            lambda chain: _reseal_edge(chain["edge"], schema_version="x.v0"),
            "edge_identity_schema_invalid",
        ),
        (
            "baseline_evidence",
            lambda chain: _reseal_baseline_evidence(chain["baseline_evidence"], schema_version="x.v0"),
            "baseline_evidence_schema_invalid",
        ),
        (
            "gate_decision",
            lambda chain: _reseal_gate(chain["gate"], schema_version="x.v0"),
            "gate_decision_schema_invalid",
        ),
    ],
)
def test_upstream_schema_invalid_rejects(key: str, reseal, reason: str) -> None:
    decision = _build(**{key: reseal(_chain())})
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc(reason) in decision.reason_codes


@pytest.mark.parametrize(
    ("key", "reseal", "reason"),
    [
        ("sharpe_evidence", lambda chain: _reseal_sharpe(chain["sharpe"], ready=False), "sharpe_evidence_not_ready"),
        ("methodology", lambda chain: _reseal_methodology(chain["methodology"], ready=False), "methodology_not_ready"),
        ("edge_identity", lambda chain: _reseal_edge(chain["edge"], ready=False), "edge_identity_not_ready"),
        (
            "baseline_evidence",
            lambda chain: _reseal_baseline_evidence(chain["baseline_evidence"], ready=False),
            "baseline_evidence_not_ready",
        ),
        ("gate_decision", lambda chain: _reseal_gate(chain["gate"], ready=False), "gate_decision_not_ready"),
    ],
)
def test_upstream_not_ready_rejects(key: str, reseal, reason: str) -> None:
    decision = _build(**{key: reseal(_chain())})
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc(reason) in decision.reason_codes


def test_gate_not_satisfied_rejects() -> None:
    gate = _reseal_gate(_chain()["gate"], thirty_day_gate_satisfied=False)
    decision = _build(gate_decision=gate)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("gate_decision_not_ready") in decision.reason_codes


def test_baseline_evidence_not_bound_rejects() -> None:
    baseline_evidence = _reseal_baseline_evidence(_chain()["baseline_evidence"], baseline_bound=False)
    decision = _build(baseline_evidence=baseline_evidence)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("baseline_evidence_not_bound") in decision.reason_codes


@pytest.mark.parametrize(
    ("key", "reseal", "reason"),
    [
        (
            "comparison_evidence",
            lambda chain: _reseal_comparison(chain["comparison"], prdv4_stage4_complete=True),
            "comparison_evidence_unsafe_flags",
        ),
        (
            "comparison_evidence",
            lambda chain: _reseal_comparison(chain["comparison"], live_ready=True),
            "comparison_evidence_unsafe_flags",
        ),
        (
            "sharpe_evidence",
            lambda chain: _reseal_sharpe(chain["sharpe"], live_ready=True),
            "sharpe_evidence_unsafe_flags",
        ),
        (
            "methodology",
            lambda chain: _reseal_methodology(chain["methodology"], comparison_performed=True),
            "methodology_unsafe_flags",
        ),
        (
            "edge_identity",
            lambda chain: _reseal_edge(chain["edge"], edge_proven=True),
            "edge_identity_unsafe_flags",
        ),
        (
            "baseline_evidence",
            lambda chain: _reseal_baseline_evidence(chain["baseline_evidence"], backtest_validity_proven=True),
            "baseline_evidence_unsafe_flags",
        ),
        (
            "gate_decision",
            lambda chain: _reseal_gate(chain["gate"], sharpe_computed=True),
            "gate_decision_unsafe_flags",
        ),
    ],
)
def test_unsafe_flags_reject(key: str, reseal, reason: str) -> None:
    decision = _build(**{key: reseal(_chain())})
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc(reason) in decision.reason_codes


# --------------------------------------------------------------------------------------------------
# 8. Cross-link mismatch matrix
# --------------------------------------------------------------------------------------------------


def test_caller_correlation_mismatch_rejects() -> None:
    decision = _build(correlation_id="corr-2")
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("correlation_id_mismatch") in decision.reason_codes


@pytest.mark.parametrize(
    ("field_name", "value", "reason"),
    [
        ("market_symbol", "ETH-PERPETUAL", "market_symbol_mismatch"),
        ("paper_id", "paper-2", "paper_id_mismatch"),
        ("series_id", "series-2", "series_binding_mismatch"),
        ("window_id", "window-2", "series_binding_mismatch"),
        ("series_digest", "c" * 64, "series_binding_mismatch"),
        ("time_window_digest", "c" * 64, "series_binding_mismatch"),
        ("metrics_summary_digest", "c" * 64, "series_binding_mismatch"),
        ("series_methodology_digest", "c" * 64, "series_binding_mismatch"),
        ("bucket_count", 31, "series_binding_mismatch"),
        ("window_duration_ns", 31 * _DAY_NS, "series_binding_mismatch"),
        ("duration_satisfied", False, "series_binding_mismatch"),
        ("paper_edge_id", "d" * 64, "comparison_binding_mismatch"),
        ("baseline_id", "baseline-2", "comparison_binding_mismatch"),
        ("strategy_id", "other-strategy", "comparison_binding_mismatch"),
    ],
)
def test_comparison_cross_link_mismatch_rejects(field_name: str, value: object, reason: str) -> None:
    comparison = _reseal_comparison(_chain()["comparison"], **{field_name: value})
    decision = _build(comparison_evidence=comparison)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc(reason) in decision.reason_codes


def test_edge_id_rederivation_mismatch_rejects() -> None:
    edge = _reseal_edge(_chain()["edge"], paper_edge_id="d" * 64)
    decision = _build(edge_identity=edge)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("edge_id_derivation_mismatch") in decision.reason_codes


# --------------------------------------------------------------------------------------------------
# 9. Governance re-pin matrix
# --------------------------------------------------------------------------------------------------


def test_retention_threshold_unapproved_rejects() -> None:
    comparison = _reseal_comparison(_chain()["comparison"], sharpe_retention_threshold="0.400000000000000000")
    decision = _build(comparison_evidence=comparison)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("retention_threshold_unapproved") in decision.reason_codes


def test_methodology_threshold_unapproved_rejects() -> None:
    methodology = _reseal_methodology(_chain()["methodology"], sharpe_retention_ratio="0.100000000000000000")
    decision = _build(methodology=methodology)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("retention_threshold_unapproved") in decision.reason_codes


def test_min_duration_unapproved_rejects() -> None:
    comparison = _reseal_comparison(_chain()["comparison"], min_duration_days=29)
    decision = _build(comparison_evidence=comparison)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("min_duration_unapproved") in decision.reason_codes


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("retention_comparison_operator", ">"),
        ("retention_verdict_policy_id", "other.v1"),
        ("baseline_sharpe_conversion_policy", "other.v1"),
        ("sharpe_comparability_basis", "reproven"),
        ("paper_trade_count_source", "other.v1"),
        ("decimal_scale", 17),
        ("risk_free_policy_id", "other.v1"),
    ],
)
def test_governance_repin_mismatch_rejects(field_name: str, value: object) -> None:
    comparison = _reseal_comparison(_chain()["comparison"], **{field_name: value})
    decision = _build(comparison_evidence=comparison)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("governance_repin_mismatch") in decision.reason_codes


# --------------------------------------------------------------------------------------------------
# 10. Verdict coherence / retention recompute
# --------------------------------------------------------------------------------------------------


def test_verdict_bool_incoherence_rejects() -> None:
    comparison = _reseal_comparison(_chain()["comparison"], comparison_verdict="RETENTION_NOT_SATISFIED")
    decision = _build(comparison_evidence=comparison)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("comparison_verdict_incoherent") in decision.reason_codes


def test_bool_verdict_incoherence_rejects() -> None:
    comparison = _reseal_comparison(_chain()["comparison"], sharpe_retention_satisfied=False)
    decision = _build(comparison_evidence=comparison)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("comparison_verdict_incoherent") in decision.reason_codes


def test_unknown_verdict_rejects() -> None:
    comparison = _reseal_comparison(_chain()["comparison"], comparison_verdict="RETENTION_MAYBE")
    decision = _build(comparison_evidence=comparison)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("comparison_verdict_incoherent") in decision.reason_codes


def test_echo_incoherence_on_satisfied_rejects() -> None:
    comparison = _reseal_comparison(_chain()["comparison"], comparator_status_echo="REJECT")
    decision = _build(comparison_evidence=comparison)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("comparison_verdict_incoherent") in decision.reason_codes


def test_echo_incoherence_on_not_satisfied_rejects() -> None:
    variant = _not_satisfied_chain()
    comparison = _reseal_comparison(
        variant["comparison"], comparator_rejection_reasons_echo=("stage4:edge_id_mismatch",)
    )
    decision = _build_not_satisfied(comparison_evidence=comparison)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("comparison_verdict_incoherent") in decision.reason_codes


def test_retention_recompute_mismatch_rejects() -> None:
    comparison = _reseal_comparison(_chain()["comparison"], sharpe_retention_ratio_decimal="1.000000000000000000")
    decision = _build(comparison_evidence=comparison)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("retention_recompute_mismatch") in decision.reason_codes


def test_malformed_backtest_repr_rejects_without_decimal_crash() -> None:
    comparison = _reseal_comparison(_chain()["comparison"], backtest_sharpe_repr="not-a-number")
    decision = _build(comparison_evidence=comparison)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("retention_recompute_mismatch") in decision.reason_codes


@pytest.mark.parametrize("corrupted_value", [None, 1.5, b"0.5"])
def test_corrupted_paper_sharpe_rejects_without_crash(corrupted_value: object) -> None:
    # Codex P2 regression: a corrupted exact-typed sharpe evidence (digest reproof already fails) must
    # produce a deterministic REJECTED decision — never a raw TypeError from Decimal(None) in the recompute.
    corrupted = replace(_chain()["sharpe"], paper_sharpe_annualized=corrupted_value)  # type: ignore[arg-type]
    decision = _build(sharpe_evidence=corrupted, expected_sharpe_evidence_digest=_HEX_A)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("sharpe_evidence_digest_mismatch") in decision.reason_codes
    assert _rc("retention_recompute_mismatch") in decision.reason_codes
    assert decision.prdv4_stage4_complete is False


def test_corrupted_methodology_threshold_rejects_without_crash() -> None:
    corrupted = replace(_chain()["methodology"], sharpe_retention_ratio=None)  # type: ignore[arg-type]
    decision = _build(methodology=corrupted, expected_methodology_digest=_HEX_A)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    assert _rc("methodology_digest_mismatch") in decision.reason_codes
    assert _rc("retention_recompute_mismatch") in decision.reason_codes


# --------------------------------------------------------------------------------------------------
# 11. Raise matrix (call-boundary malformed input)
# --------------------------------------------------------------------------------------------------


def test_wrong_comparison_type_raises() -> None:
    with pytest.raises(PaperStage4CompletionDecisionError, match="comparison_evidence_malformed"):
        _build(comparison_evidence=_chain()["sharpe"])


def test_sharpe_subclass_raises() -> None:
    sharpe = _chain()["sharpe"]
    sub = _SharpeSub(**{field.name: getattr(sharpe, field.name) for field in fields(sharpe)})
    with pytest.raises(PaperStage4CompletionDecisionError, match="sharpe_evidence_malformed"):
        _build(sharpe_evidence=sub)


@pytest.mark.parametrize(
    ("key", "reason"),
    [
        ("methodology", "methodology_malformed"),
        ("edge_identity", "edge_identity_malformed"),
        ("baseline_evidence", "baseline_evidence_malformed"),
        ("gate_decision", "gate_decision_malformed"),
    ],
)
def test_wrong_input_types_raise(key: str, reason: str) -> None:
    with pytest.raises(PaperStage4CompletionDecisionError, match=reason):
        _build(**{key: "not-an-artifact"})


@pytest.mark.parametrize("bad_anchor", ["", "xyz", "B" * 64, "a" * 63, _LiarStr("a" * 64)])
def test_malformed_anchor_raises(bad_anchor: object) -> None:
    with pytest.raises(PaperStage4CompletionDecisionError, match="expected_comparison_evidence_digest_invalid"):
        _build(expected_comparison_evidence_digest=bad_anchor)


@pytest.mark.parametrize("bad_id", ["", "  padded  ", "with\x00control", _LiarStr("id")])
def test_malformed_completion_decision_id_raises(bad_id: object) -> None:
    with pytest.raises(PaperStage4CompletionDecisionError, match="completion_decision_id_invalid"):
        _build(completion_decision_id=bad_id)


@pytest.mark.parametrize("metadata", [{1: "x"}, {"k": 2}, {"k": "v\x00"}, {" k": "v"}, "not-a-mapping"])
def test_malformed_metadata_raises(metadata: object) -> None:
    with pytest.raises(PaperStage4CompletionDecisionError, match="metadata_malformed"):
        _build(metadata=metadata)


@pytest.mark.parametrize("token_id", ["deribit-check", "order-flow-x", "scheduler-run", "real_money_test"])
def test_forbidden_scope_token_raises(token_id: str) -> None:
    with pytest.raises(PaperStage4CompletionDecisionError, match="scope_violation"):
        _build(completion_decision_id=token_id)


def test_clock_token_raises() -> None:
    with pytest.raises(PaperStage4CompletionDecisionError, match="clock_token_forbidden"):
        _build(completion_decision_id="clock-1")


# --------------------------------------------------------------------------------------------------
# 12. Determinism / serializer / digest
# --------------------------------------------------------------------------------------------------


def test_deterministic_same_inputs_same_digest() -> None:
    first = _build()
    second = _build()
    assert first == second
    assert first.completion_decision_digest == second.completion_decision_digest


def test_self_digest_reproves() -> None:
    decision = _build()
    assert _is_hex64(decision.completion_decision_digest)
    assert paper_stage4_completion_decision_digest(decision) == decision.completion_decision_digest


def test_to_dict_covers_every_field_and_digest_excludes_only_self() -> None:
    decision = _build()
    payload = paper_stage4_completion_decision_to_dict(decision)
    field_names = {field.name for field in fields(decision)}
    assert set(payload.keys()) == field_names
    without_self = {key: value for key, value in payload.items() if key != "completion_decision_digest"}
    assert _canonical(without_self) == decision.completion_decision_digest
    assert payload["status"] == "READY"
    assert payload["metadata"] == [["purpose", "stage4 completion decision"]]
    assert payload["stage4_completion_blockers"] == list(_EXPECTED_BLOCKERS)


def test_metadata_normalized_sorted() -> None:
    decision = _build(metadata={"zeta": "2", "alpha": "1"})
    assert decision.metadata == (("alpha", "1"), ("zeta", "2"))


def test_tampered_decision_digest_detectable() -> None:
    decision = _build()
    tampered = replace(decision, prdv4_stage4_complete=True)
    assert paper_stage4_completion_decision_digest(tampered) != decision.completion_decision_digest


# --------------------------------------------------------------------------------------------------
# 13. Non-overclaim invariants on every path
# --------------------------------------------------------------------------------------------------

_NON_OVERCLAIM_FIELDS = (
    "prdv4_stage4_complete",
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
    "timestamp_origin_proven",
    "real_time_paper_operation_proven",
    "operational_day_evidence_consumed",
)


@pytest.mark.parametrize("builder", [_build, _build_not_satisfied])
def test_non_overclaim_fields_false_on_ready_paths(builder) -> None:
    decision = builder()
    assert decision.ready is True
    for field_name in _NON_OVERCLAIM_FIELDS:
        assert getattr(decision, field_name) is False, field_name
    assert decision.paper_only is True
    assert decision.comparison_evidence_consumed is True
    assert decision.operational_day_gate_deferred is True


def test_non_overclaim_fields_false_on_rejected_path() -> None:
    decision = _build(expected_comparison_evidence_digest="b" * 64)
    assert decision.status is PaperStage4CompletionDecisionStatus.REJECTED
    for field_name in _NON_OVERCLAIM_FIELDS:
        assert getattr(decision, field_name) is False, field_name
    assert decision.paper_methodology_complete is False
    assert decision.stage4_completion_decided is False


def test_prdv4_stage4_complete_default_is_false_in_dataclass() -> None:
    field_map = {field.name: field for field in fields(PaperStage4CompletionDecision)}
    assert field_map["prdv4_stage4_complete"].default is False


# --------------------------------------------------------------------------------------------------
# 14. AST / source forbidden-surface audit
# --------------------------------------------------------------------------------------------------


def _module_source() -> str:
    return Path(completion_module.__file__).read_text(encoding="utf-8")


def _module_ast() -> ast.Module:
    return ast.parse(_module_source())


def test_no_forbidden_imports() -> None:
    forbidden_modules = (
        "stage4_comparator",
        "datetime",
        "random",
        "socket",
        "subprocess",
        "threading",
        "pathlib",
        "os",
        "time",
    )
    forbidden_prefixes = ("crypto_core.service", "crypto_core.execution")
    for node in ast.walk(_module_ast()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden_modules, alias.name
                assert not alias.name.startswith(forbidden_prefixes), alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not module.endswith("stage4_comparator"), module
            assert not module.startswith(forbidden_prefixes), module
            assert module not in forbidden_modules, module
            for alias in node.names:
                assert "readiness" not in alias.name, alias.name
                assert "paper_adapter" not in alias.name, alias.name


def test_no_comparator_identifiers_in_source() -> None:
    source = _module_source()
    assert "compare_stage4" not in source
    assert "Stage4PaperSummary" not in source
    assert "Stage4BacktestBaseline(" not in source
    assert re.search(r"^from crypto_core\.validation\.stage4_comparator", source, re.MULTILINE) is None


def test_no_completion_true_assignment_in_source() -> None:
    source = _module_source()
    assert "prdv4_stage4_complete: bool = False" in source
    assert re.search(r"prdv4_stage4_complete\s*=\s*True", source) is None
    assert '"prdv4_stage4_complete": True' not in source


def test_no_non_overclaim_flag_assigned_true_in_source() -> None:
    source = _module_source()
    for field_name in _NON_OVERCLAIM_FIELDS:
        assert re.search(rf"{field_name}\s*[:=]\s*True", source) is None, field_name


def test_retention_recompute_helper_is_float_free() -> None:
    for node in ast.walk(_module_ast()):
        if isinstance(node, ast.FunctionDef) and node.name == "_recompute_retention_verdict":
            names = {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}
            assert "float" not in names
            return
    pytest.fail("_recompute_retention_verdict not found")


def test_builder_calls_no_comparator_functions() -> None:
    call_names: set[str] = set()
    for node in ast.walk(_module_ast()):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                call_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                call_names.add(node.func.attr)
    assert "compare_stage4" not in call_names
