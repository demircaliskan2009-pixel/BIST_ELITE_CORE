"""Tests for deterministic paper Stage-4 comparison evidence (first authorized comparator run)."""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import FrozenInstanceError, dataclass, fields, replace
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import pytest

from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, validate_strategy_spec
from crypto_core.validation import paper_daily_return_series_evidence as series_module
from crypto_core.validation import paper_stage4_comparison_evidence as comparison_module
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
    PaperStage4ComparisonEvidenceError,
    PaperStage4ComparisonEvidenceStatus,
    build_paper_stage4_comparison_evidence,
    paper_stage4_comparison_evidence_digest,
    paper_stage4_comparison_evidence_to_dict,
)
from crypto_core.validation.paper_vs_backtest_methodology import (
    PaperVsBacktestMethodology,
    build_paper_vs_backtest_methodology,
    paper_vs_backtest_methodology_digest,
)
from crypto_core.validation.stage4_comparator import (
    Stage4BacktestBaseline,
    Stage4PaperSummary,
    build_stage4_backtest_baseline,
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


class _LiarStr(str):
    """A ``str`` subclass rejected by exact ``type(x) is str`` checks."""


@dataclass(frozen=True)
class _SharpeSub(PaperSharpeEvidence):
    """Subclass test double; exact input types are required."""


def _rc(code: str) -> str:
    return f"paper_stage4_comparison_evidence:{code}"


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _canonical(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------------------------------
# Fixture chain: real merged builders end-to-end (spec -> edge identity -> baseline evidence;
# return-series methodology -> window -> series -> sharpe + 30-day gate; comparison methodology).
# --------------------------------------------------------------------------------------------------


def _spec(**overrides: object) -> StrategySpec:
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
    payload.update(overrides)
    result = validate_strategy_spec(payload)
    assert result.accepted, result.rejection_reasons + result.needs_research_reasons
    assert result.spec is not None
    return result.spec


def _edge_identity(**overrides: object) -> PaperEdgeIdentityEvidence:
    spec = _spec(**{key: overrides.pop(key) for key in ("strategy_id",) if key in overrides})
    payload: dict[str, object] = {
        "expected_strategy_spec_digest": strategy_spec_digest(spec),
        "market_symbol": _MARKET,
        "edge_identity_id": "edge-identity-1",
        "paper_id": _PAPER_ID,
        "correlation_id": _CORRELATION,
        "metadata": {"purpose": "paper edge identity"},
    }
    payload.update(overrides)
    evidence = build_paper_edge_identity_evidence(spec, **payload)  # type: ignore[arg-type]
    assert evidence.ready, evidence.reason_codes
    return evidence


def _baseline(edge_id: str, **overrides: object) -> Stage4BacktestBaseline:
    kwargs: dict[str, object] = {
        "baseline_id": "baseline-1",
        "edge_id": edge_id,
        "as_of_ns": 1_700_000_000_000_000_000,
        "backtest_sharpe": 1.5,
        "backtest_hit_rate": 0.55,
        "backtest_slippage_bps": 2.0,
        "backtest_fill_rate": 0.9,
        "source_window_ids": ("wf-1", "wf-2"),
    }
    kwargs.update(overrides)
    return build_stage4_backtest_baseline(**kwargs)  # type: ignore[arg-type]


def _baseline_digest(baseline: Stage4BacktestBaseline) -> str:
    return _canonical(stage4_backtest_baseline_to_dict(baseline))


def _baseline_evidence(
    edge: PaperEdgeIdentityEvidence,
    baseline: Stage4BacktestBaseline,
    *,
    expected_baseline_digest: str | None = None,
) -> PaperStage4BacktestBaselineEvidence:
    return build_paper_stage4_backtest_baseline_evidence(
        baseline,
        expected_baseline_digest=(
            _baseline_digest(baseline) if expected_baseline_digest is None else expected_baseline_digest
        ),
        edge_identity=edge,
        expected_edge_identity_digest=edge.edge_identity_digest,
        baseline_evidence_id="baseline-evidence-1",
        correlation_id=_CORRELATION,
        metadata={"purpose": "stage4 baseline binding"},
    )


def _window(*, days: int = 30) -> PaperDeterministicTimeWindowEvidence:
    # The window starts one full UTC day after epoch so every bucket timestamp is a positive integer (the
    # comparator's Stage4PaperSummary requires positive started/stopped ns).
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
    assert decision.thirty_day_gate_satisfied is True
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


_CHAIN_CACHE: dict[str, object] = {}


def _chain() -> dict[str, object]:
    if not _CHAIN_CACHE:
        edge = _edge_identity()
        baseline = _baseline(edge.paper_edge_id)
        series = _series()
        _CHAIN_CACHE.update(
            {
                "edge": edge,
                "baseline": baseline,
                "baseline_evidence": _baseline_evidence(edge, baseline),
                "series": series,
                "sharpe": _sharpe(series),
                "gate": _gate(series),
                "methodology": _comparison_methodology(),
            }
        )
    return _CHAIN_CACHE


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


def _carried_or_placeholder(value: object) -> str:
    return value if _is_hex64(value) else _HEX_A


def _build(**overrides: object) -> PaperStage4ComparisonEvidence:
    chain = _chain()
    backtest_baseline = overrides.pop("backtest_baseline", chain["baseline"])
    baseline_evidence = overrides.pop("baseline_evidence", chain["baseline_evidence"])
    sharpe_evidence = overrides.pop("sharpe_evidence", chain["sharpe"])
    methodology = overrides.pop("methodology", chain["methodology"])
    edge_identity = overrides.pop("edge_identity", chain["edge"])
    gate_decision = overrides.pop("gate_decision", chain["gate"])
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
        "methodology": methodology,
        "expected_methodology_digest": _carried_or_placeholder(getattr(methodology, "methodology_digest", "")),
        "edge_identity": edge_identity,
        "expected_edge_identity_digest": _carried_or_placeholder(getattr(edge_identity, "edge_identity_digest", "")),
        "gate_decision": gate_decision,
        "expected_gate_decision_digest": _carried_or_placeholder(getattr(gate_decision, "decision_digest", "")),
        "comparison_evidence_id": "comparison-evidence-1",
        "correlation_id": _CORRELATION,
        "metadata": {"purpose": "stage4 comparison"},
    }
    payload.update(overrides)
    return build_paper_stage4_comparison_evidence(backtest_baseline, **payload)  # type: ignore[arg-type]


def _expected_retention(paper: str, backtest_repr: str) -> str:
    with localcontext() as context:
        context.prec = 80
        context.rounding = ROUND_HALF_EVEN
        ratio = Decimal(paper) / Decimal(backtest_repr)
        quantized = ratio.quantize(Decimal(1).scaleb(-18), rounding=ROUND_HALF_EVEN)
        if quantized == 0:
            quantized = Decimal(0).quantize(Decimal(1).scaleb(-18))
        return format(quantized, "f")


# --------------------------------------------------------------------------------------------------
# 1. Public API
# --------------------------------------------------------------------------------------------------


def test_public_api_exports_present() -> None:
    assert set(comparison_module.__all__) == {
        "PaperStage4ComparisonEvidence",
        "PaperStage4ComparisonEvidenceError",
        "PaperStage4ComparisonEvidenceStatus",
        "build_paper_stage4_comparison_evidence",
        "paper_stage4_comparison_evidence_digest",
        "paper_stage4_comparison_evidence_to_dict",
    }


def test_status_enum_values() -> None:
    assert PaperStage4ComparisonEvidenceStatus.READY.value == "READY"
    assert PaperStage4ComparisonEvidenceStatus.REJECTED.value == "REJECTED"


def test_output_is_frozen() -> None:
    evidence = _build()
    with pytest.raises(FrozenInstanceError):
        evidence.ready = False  # type: ignore[misc]


# --------------------------------------------------------------------------------------------------
# 2. READY + RETENTION_SATISFIED
# --------------------------------------------------------------------------------------------------


def test_happy_ready_retention_satisfied() -> None:
    evidence = _build()
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.READY
    assert evidence.ready is True
    assert evidence.reason_codes == ()
    assert evidence.comparison_verdict == "RETENTION_SATISFIED"
    assert evidence.sharpe_retention_satisfied is True
    assert evidence.duration_satisfied is True
    assert evidence.stage4_comparator_invoked is True
    assert evidence.comparison_performed is True
    assert evidence.comparator_float_advisory_only is True
    assert evidence.retention_comparison_operator == ">="
    assert evidence.sharpe_retention_threshold == _RETENTION_THRESHOLD
    assert evidence.retention_verdict_policy_id == "decimal_retention_recompute_authoritative.v1"
    assert evidence.baseline_sharpe_conversion_policy == "float_repr_decimal_conversion.v1"
    assert evidence.sharpe_comparability_basis == "policy_declared_not_reproven"
    assert evidence.paper_trade_count_source == "not_carried_zero_placeholder.v1"


def test_ready_identity_and_chain_bindings() -> None:
    chain = _chain()
    evidence = _build()
    sharpe = chain["sharpe"]
    gate = chain["gate"]
    edge = chain["edge"]
    assert evidence.paper_id == _PAPER_ID
    assert evidence.series_id == "series-1"
    assert evidence.window_id == "window-1"
    assert evidence.market_symbol == _MARKET
    assert evidence.paper_edge_id == edge.paper_edge_id
    assert evidence.baseline_id == "baseline-1"
    assert evidence.strategy_id == edge.strategy_id
    assert evidence.expected_sharpe_evidence_digest == evidence.verified_sharpe_evidence_digest
    assert evidence.expected_comparison_methodology_digest == evidence.verified_comparison_methodology_digest
    assert evidence.expected_edge_identity_digest == evidence.verified_edge_identity_digest
    assert evidence.expected_baseline_evidence_digest == evidence.verified_baseline_evidence_digest
    assert evidence.expected_gate_decision_digest == evidence.verified_gate_decision_digest
    assert evidence.baseline_digest == evidence.expected_baseline_digest == _baseline_digest(chain["baseline"])
    assert evidence.series_digest == gate.series_digest == sharpe.verified_daily_return_series_digest
    assert evidence.series_methodology_digest == sharpe.methodology_digest
    assert evidence.time_window_digest == sharpe.time_window_digest
    assert evidence.metrics_summary_digest == sharpe.metrics_summary_digest
    expected_summary = Stage4PaperSummary(
        paper_id=_PAPER_ID,
        edge_id=edge.paper_edge_id,
        started_at_ns=gate.first_bucket_start_ns,
        stopped_at_ns=gate.last_bucket_end_ns,
        paper_sharpe=float(sharpe.paper_sharpe_annualized),
        paper_hit_rate=None,
        paper_slippage_bps=None,
        paper_fill_rate=None,
        paper_trade_count=0,
    )
    assert evidence.paper_summary_digest == _canonical(stage4_paper_summary_to_dict(expected_summary))


def test_ready_decimal_block() -> None:
    chain = _chain()
    sharpe = chain["sharpe"]
    evidence = _build()
    assert evidence.paper_sharpe_annualized == sharpe.paper_sharpe_annualized
    assert evidence.backtest_sharpe_repr == "1.5"
    assert evidence.backtest_sharpe_decimal == "1.500000000000000000"
    assert evidence.sharpe_retention_ratio_decimal == _expected_retention(sharpe.paper_sharpe_annualized, "1.5")
    assert Decimal(evidence.sharpe_retention_ratio_decimal) >= Decimal(_RETENTION_THRESHOLD)
    assert evidence.min_duration_days == 30
    assert evidence.bucket_count == 30
    assert evidence.window_duration_ns == 30 * _DAY_NS
    assert evidence.decimal_policy == "decimal_quantized_scale_18_round_half_even_internal_precision_80.v1"
    assert evidence.decimal_scale == 18
    assert evidence.decimal_rounding == "ROUND_HALF_EVEN"
    assert evidence.decimal_internal_precision == 80
    assert evidence.risk_free_policy_id == _RISK_FREE_POLICY_ID


def test_equality_boundary_retention_satisfied() -> None:
    # paper == 0.5 * baseline exactly: the ``>=`` operator satisfies retention on equality.
    sharpe = _reseal_sharpe(_chain()["sharpe"], paper_sharpe_annualized="0.750000000000000000")
    evidence = _build(sharpe_evidence=sharpe)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.READY
    assert evidence.comparison_verdict == "RETENTION_SATISFIED"
    assert evidence.sharpe_retention_ratio_decimal == _RETENTION_THRESHOLD


def test_comparator_echo_on_satisfied() -> None:
    evidence = _build()
    assert evidence.comparator_status_echo == "PASS"
    assert evidence.comparator_evaluated_echo is True
    assert evidence.comparator_passed_echo is True
    assert evidence.comparator_rejection_reasons_echo == ()
    assert evidence.comparator_sharpe_retention_ratio_echo != ""
    assert evidence.comparator_required_min_paper_sharpe_echo != ""
    assert float(evidence.comparator_required_min_paper_sharpe_echo) == pytest.approx(0.75)


# --------------------------------------------------------------------------------------------------
# 3. READY + RETENTION_NOT_SATISFIED (still valid evidence)
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "paper_value",
    ["0.500000000000000000", "0.000000000000000000", "-1.000000000000000000"],
)
def test_ready_retention_not_satisfied(paper_value: str) -> None:
    sharpe = _reseal_sharpe(_chain()["sharpe"], paper_sharpe_annualized=paper_value)
    evidence = _build(sharpe_evidence=sharpe)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.READY
    assert evidence.ready is True
    assert evidence.reason_codes == ()
    assert evidence.comparison_verdict == "RETENTION_NOT_SATISFIED"
    assert evidence.sharpe_retention_satisfied is False
    assert evidence.stage4_comparator_invoked is True
    assert evidence.comparator_status_echo == "REJECT"
    assert evidence.comparator_rejection_reasons_echo == ("stage4:paper_sharpe_below_backtest_threshold",)
    assert Decimal(evidence.sharpe_retention_ratio_decimal) < Decimal(_RETENTION_THRESHOLD)


# --------------------------------------------------------------------------------------------------
# 4. Digest tamper / anchor mismatch matrix
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("input_name", "reason_code"),
    [
        ("sharpe_evidence", "sharpe_evidence_digest_mismatch"),
        ("methodology", "methodology_digest_mismatch"),
        ("edge_identity", "edge_identity_digest_mismatch"),
        ("baseline_evidence", "baseline_evidence_digest_mismatch"),
        ("gate_decision", "gate_decision_digest_mismatch"),
    ],
)
def test_tampered_input_rejects_with_digest_mismatch(input_name: str, reason_code: str) -> None:
    chain_keys = {
        "sharpe_evidence": "sharpe",
        "methodology": "methodology",
        "edge_identity": "edge",
        "baseline_evidence": "baseline_evidence",
        "gate_decision": "gate",
    }
    tampered = replace(_chain()[chain_keys[input_name]], correlation_id="corr-tampered")  # type: ignore[type-var]
    evidence = _build(**{input_name: tampered})
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc(reason_code) in evidence.reason_codes
    assert evidence.stage4_comparator_invoked is False


@pytest.mark.parametrize(
    ("anchor_name", "reason_code"),
    [
        ("expected_sharpe_evidence_digest", "sharpe_evidence_digest_mismatch"),
        ("expected_methodology_digest", "methodology_digest_mismatch"),
        ("expected_edge_identity_digest", "edge_identity_digest_mismatch"),
        ("expected_baseline_evidence_digest", "baseline_evidence_digest_mismatch"),
        ("expected_gate_decision_digest", "gate_decision_digest_mismatch"),
    ],
)
def test_anchor_mismatch_rejects(anchor_name: str, reason_code: str) -> None:
    evidence = _build(**{anchor_name: "b" * 64})
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc(reason_code) in evidence.reason_codes


def test_forged_non_serializable_input_rejects_without_type_error() -> None:
    forged = replace(_chain()["sharpe"], metadata=(object(),))  # type: ignore[arg-type]
    evidence = _build(sharpe_evidence=forged)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("sharpe_evidence_digest_mismatch") in evidence.reason_codes


def test_baseline_caller_anchor_mismatch_rejects() -> None:
    evidence = _build(expected_baseline_digest="b" * 64)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("baseline_digest_mismatch") in evidence.reason_codes
    assert _rc("baseline_evidence_baseline_digest_mismatch") in evidence.reason_codes


def test_baseline_object_differs_from_bound_baseline_rejects() -> None:
    # A self-consistent caller anchor over a DIFFERENT baseline must still fail the triple equality against
    # the digest bound inside the merged baseline evidence.
    chain = _chain()
    other = _baseline(chain["edge"].paper_edge_id, backtest_sharpe=1.6)
    evidence = _build(backtest_baseline=other)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("baseline_evidence_baseline_digest_mismatch") in evidence.reason_codes
    assert _rc("baseline_digest_mismatch") not in evidence.reason_codes


def test_edge_identity_object_mismatch_rejects_cross_digest() -> None:
    other_edge = _edge_identity(strategy_id="beta-basis-carry", edge_identity_id="edge-identity-2")
    evidence = _build(edge_identity=other_edge)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("edge_identity_cross_digest_mismatch") in evidence.reason_codes
    assert _rc("baseline_edge_id_mismatch") in evidence.reason_codes


# --------------------------------------------------------------------------------------------------
# 5. Status / ready / gate-satisfied matrix
# --------------------------------------------------------------------------------------------------


def test_sharpe_not_ready_rejects() -> None:
    sharpe = _reseal_sharpe(_chain()["sharpe"], ready=False)
    evidence = _build(sharpe_evidence=sharpe)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("sharpe_evidence_not_ready") in evidence.reason_codes


def test_methodology_not_ready_rejects() -> None:
    methodology = _reseal_methodology(_chain()["methodology"], ready=False)
    evidence = _build(methodology=methodology)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("methodology_not_ready") in evidence.reason_codes


def test_edge_identity_not_ready_rejects() -> None:
    edge = _reseal_edge(_chain()["edge"], ready=False)
    evidence = _build(edge_identity=edge)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("edge_identity_not_ready") in evidence.reason_codes


def test_baseline_evidence_not_ready_rejects() -> None:
    baseline_evidence = _reseal_baseline_evidence(_chain()["baseline_evidence"], ready=False)
    evidence = _build(baseline_evidence=baseline_evidence)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("baseline_evidence_not_ready") in evidence.reason_codes


def test_gate_not_ready_rejects() -> None:
    gate = _reseal_gate(_chain()["gate"], ready=False)
    evidence = _build(gate_decision=gate)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("gate_decision_not_ready") in evidence.reason_codes


def test_thirty_day_gate_not_satisfied_rejects() -> None:
    gate = _reseal_gate(_chain()["gate"], thirty_day_gate_satisfied=False)
    evidence = _build(gate_decision=gate)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("thirty_day_gate_not_satisfied") in evidence.reason_codes
    assert evidence.stage4_comparator_invoked is False


def test_sharpe_not_computed_rejects() -> None:
    sharpe = _reseal_sharpe(_chain()["sharpe"], sharpe_computed=False)
    evidence = _build(sharpe_evidence=sharpe)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("sharpe_not_computed") in evidence.reason_codes


# --------------------------------------------------------------------------------------------------
# 6. Cross-link mismatch matrix
# --------------------------------------------------------------------------------------------------


def test_correlation_id_mismatch_rejects() -> None:
    methodology = _reseal_methodology(_chain()["methodology"], correlation_id="corr-2")
    evidence = _build(methodology=methodology)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("correlation_id_mismatch") in evidence.reason_codes


def test_market_symbol_mismatch_rejects() -> None:
    gate = _reseal_gate(_chain()["gate"], market_symbol="ETH-PERPETUAL")
    evidence = _build(gate_decision=gate)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("market_symbol_mismatch") in evidence.reason_codes


def test_paper_id_mismatch_rejects() -> None:
    sharpe = _reseal_sharpe(_chain()["sharpe"], paper_id="paper-2")
    evidence = _build(sharpe_evidence=sharpe)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("paper_id_mismatch") in evidence.reason_codes


def test_series_digest_mismatch_rejects() -> None:
    gate = _reseal_gate(_chain()["gate"], series_digest="c" * 64)
    evidence = _build(gate_decision=gate)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("series_digest_mismatch") in evidence.reason_codes


@pytest.mark.parametrize(
    "changes",
    [
        {"window_id": "window-2"},
        {"time_window_digest": "d" * 64},
        {"metrics_summary_digest": "d" * 64},
        {"methodology_digest": "d" * 64},
    ],
)
def test_series_binding_mismatch_rejects(changes: dict[str, object]) -> None:
    gate = _reseal_gate(_chain()["gate"], **changes)
    evidence = _build(gate_decision=gate)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("series_binding_mismatch") in evidence.reason_codes


# --------------------------------------------------------------------------------------------------
# 7. Methodology / policy consistency
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "changes",
    [
        {"comparison_basis": "paper_vs_backtest_other_basis.v1"},
        {"enforced_guardrail_policy": "other_policy.v1"},
        {"annualization_factor": 252},
        {"annualization_policy": "daily_utc_252_review_only"},
        {"stddev_policy": "population_stddev_n.v1"},
        {"decimal_policy": "decimal_other.v1"},
        {"decimal_scale": 9},
        {"decimal_rounding": "ROUND_UP"},
        {"decimal_internal_precision": 40},
    ],
)
def test_methodology_policy_mismatch_rejects(changes: dict[str, object]) -> None:
    methodology = _reseal_methodology(_chain()["methodology"], **changes)
    evidence = _build(methodology=methodology)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("methodology_policy_mismatch") in evidence.reason_codes


def test_gate_risk_free_policy_mismatch_rejects() -> None:
    gate = _reseal_gate(_chain()["gate"], risk_free_policy_id="constant_zero_daily_review_only.v2")
    evidence = _build(gate_decision=gate)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("gate_risk_free_policy_mismatch") in evidence.reason_codes


def test_min_duration_policy_mismatch_rejects() -> None:
    gate = _reseal_gate(_chain()["gate"], gate_minimum_consecutive_bucket_count=29)
    evidence = _build(gate_decision=gate)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("min_duration_policy_mismatch") in evidence.reason_codes


def test_methodology_retention_threshold_invalid_rejects() -> None:
    methodology = _reseal_methodology(_chain()["methodology"], sharpe_retention_ratio="0.5")
    evidence = _build(methodology=methodology)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("methodology_retention_threshold_invalid") in evidence.reason_codes
    assert evidence.stage4_comparator_invoked is False


def test_resealed_lowered_retention_threshold_rejects_unapproved() -> None:
    # Codex P1 regression: a resealed, digest-self-consistent READY methodology carrying a WEAKENED but
    # well-formed threshold must fail closed at the consumer boundary — the approved v1 governance value
    # (0.500000000000000000) is re-pinned here, never trusted from a forgeable policy field alone.
    methodology = _reseal_methodology(_chain()["methodology"], sharpe_retention_ratio="0.100000000000000000")
    evidence = _build(methodology=methodology)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("methodology_retention_threshold_unapproved") in evidence.reason_codes
    assert evidence.stage4_comparator_invoked is False
    assert evidence.comparison_verdict == ""


def test_resealed_unapproved_min_duration_rejects() -> None:
    methodology = _reseal_methodology(_chain()["methodology"], min_duration_days=15)
    evidence = _build(methodology=methodology)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("methodology_min_duration_unapproved") in evidence.reason_codes
    assert evidence.stage4_comparator_invoked is False


# --------------------------------------------------------------------------------------------------
# 8. Edge identity re-derivation
# --------------------------------------------------------------------------------------------------


def test_forged_resealed_paper_edge_id_rejects() -> None:
    # A resealed identity whose digest/form/policy are self-consistent but whose paper_edge_id was not
    # produced by the approved derivation must fail the consumer-boundary re-derivation.
    edge = _reseal_edge(_chain()["edge"], paper_edge_id="a" * 64)
    evidence = _build(edge_identity=edge)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("edge_id_derivation_mismatch") in evidence.reason_codes


def test_edge_id_form_violation_rejects() -> None:
    edge = _reseal_edge(_chain()["edge"], edge_id_form="hex32_sha256")
    evidence = _build(edge_identity=edge)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("edge_identity_edge_id_form_invalid") in evidence.reason_codes


def test_edge_derivation_policy_violation_rejects() -> None:
    edge = _reseal_edge(_chain()["edge"], edge_id_derivation_policy="sha256_other_derivation.v9")
    evidence = _build(edge_identity=edge)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("edge_identity_derivation_policy_mismatch") in evidence.reason_codes


# --------------------------------------------------------------------------------------------------
# 9. Numeric / temporal safety
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("baseline_overrides", "reason_code"),
    [
        ({"backtest_sharpe": -1.0}, "backtest_sharpe_non_positive"),
        ({"backtest_sharpe": 0.0}, "backtest_sharpe_non_positive"),
        ({"backtest_sharpe": True}, "backtest_sharpe_non_positive"),
        ({"backtest_hit_rate": 1.5}, "backtest_hit_rate_invalid"),
        ({"backtest_slippage_bps": -1.0}, "backtest_slippage_invalid"),
        ({"backtest_fill_rate": 2.0}, "backtest_fill_rate_invalid"),
        ({"as_of_ns": 0}, "baseline_as_of_ns_invalid"),
    ],
)
def test_baseline_numeric_safety_rejects(baseline_overrides: dict[str, object], reason_code: str) -> None:
    chain = _chain()
    bad = _baseline(chain["edge"].paper_edge_id, **baseline_overrides)
    bad_evidence = _baseline_evidence(chain["edge"], bad)
    evidence = _build(backtest_baseline=bad, baseline_evidence=bad_evidence)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc(reason_code) in evidence.reason_codes
    assert evidence.stage4_comparator_invoked is False


def test_non_finite_baseline_sharpe_rejects_fail_closed() -> None:
    chain = _chain()
    bad = _baseline(chain["edge"].paper_edge_id, backtest_sharpe=float("nan"))
    bad_evidence = _baseline_evidence(chain["edge"], bad, expected_baseline_digest="f" * 64)
    evidence = _build(backtest_baseline=bad, baseline_evidence=bad_evidence, expected_baseline_digest="f" * 64)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("backtest_sharpe_non_positive") in evidence.reason_codes
    assert _rc("baseline_digest_mismatch") in evidence.reason_codes


@pytest.mark.parametrize(
    "paper_value",
    [
        "1.5",
        "1.5000000000000000000",
        "01.000000000000000000",
        "-0.000000000000000000",
        "1E-18",
        "1" * 1200 + ".000000000000000000",
    ],
)
def test_malformed_paper_sharpe_annualized_rejects(paper_value: str) -> None:
    sharpe = _reseal_sharpe(_chain()["sharpe"], paper_sharpe_annualized=paper_value)
    evidence = _build(sharpe_evidence=sharpe)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("paper_sharpe_annualized_invalid") in evidence.reason_codes
    assert evidence.stage4_comparator_invoked is False


@pytest.mark.parametrize("huge_sharpe", [1e308, 1e19])
def test_huge_backtest_sharpe_out_of_bounds_rejects(huge_sharpe: float) -> None:
    # Codex P2 regression: a digest-valid baseline with a finite but enormous Sharpe must be REJECTED
    # deterministically — never allowed to raise decimal.InvalidOperation during scale-18 quantization.
    chain = _chain()
    huge = _baseline(chain["edge"].paper_edge_id, backtest_sharpe=huge_sharpe)
    huge_evidence = _baseline_evidence(chain["edge"], huge)
    evidence = _build(backtest_baseline=huge, baseline_evidence=huge_evidence)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("backtest_sharpe_out_of_bounds") in evidence.reason_codes
    assert evidence.stage4_comparator_invoked is False


def test_tiny_backtest_sharpe_out_of_bounds_rejects() -> None:
    chain = _chain()
    tiny = _baseline(chain["edge"].paper_edge_id, backtest_sharpe=5e-324)
    tiny_evidence = _baseline_evidence(chain["edge"], tiny)
    evidence = _build(backtest_baseline=tiny, baseline_evidence=tiny_evidence)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("backtest_sharpe_out_of_bounds") in evidence.reason_codes
    assert evidence.stage4_comparator_invoked is False


def test_long_but_capped_paper_sharpe_string_rejects_before_quantization() -> None:
    # Codex P2 regression: a resealed scale-18 paper Sharpe whose integer part would overflow the
    # precision-80 quantization is rejected by the tightened length cap, not by a Decimal exception.
    sharpe = _reseal_sharpe(_chain()["sharpe"], paper_sharpe_annualized="1" * 45 + ".000000000000000000")
    evidence = _build(sharpe_evidence=sharpe)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("paper_sharpe_annualized_invalid") in evidence.reason_codes
    assert evidence.stage4_comparator_invoked is False


# --------------------------------------------------------------------------------------------------
# 10. Decimal vs float comparator divergence (fail-closed)
# --------------------------------------------------------------------------------------------------


def test_decimal_float_comparator_verdict_mismatch_fails_closed() -> None:
    # REAL divergence, no monkeypatch: paper "0.999999999999999999" (1 - 1e-18) collapses to the double 1.0,
    # so the float comparator sees paper == required_min (0.5 * 2.0) and PASSes, while the exact Decimal
    # retention 0.4999999999999999995 is strictly below the 0.5 threshold. The Decimal verdict is
    # authoritative and the disagreement must fail closed.
    chain = _chain()
    baseline = _baseline(chain["edge"].paper_edge_id, backtest_sharpe=2.0)
    baseline_evidence = _baseline_evidence(chain["edge"], baseline)
    sharpe = _reseal_sharpe(chain["sharpe"], paper_sharpe_annualized="0.999999999999999999")
    evidence = _build(backtest_baseline=baseline, baseline_evidence=baseline_evidence, sharpe_evidence=sharpe)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert evidence.ready is False
    assert evidence.reason_codes == (_rc("decimal_float_comparator_verdict_mismatch"),)
    assert evidence.stage4_comparator_invoked is True
    assert evidence.comparison_performed is True
    assert evidence.comparator_status_echo == "PASS"
    assert evidence.comparison_verdict == ""
    assert evidence.sharpe_retention_satisfied is False
    # The QUANTIZED public ratio rounds 0.4999999999999999995 up to the threshold itself — proving the
    # authoritative comparison ran on the full-precision value BEFORE output quantization.
    assert evidence.sharpe_retention_ratio_decimal == _RETENTION_THRESHOLD
    with localcontext() as context:
        context.prec = 80
        context.rounding = ROUND_HALF_EVEN
        assert Decimal("0.999999999999999999") / Decimal("2.0") < Decimal(_RETENTION_THRESHOLD)


# --------------------------------------------------------------------------------------------------
# 11. Duration prechecks
# --------------------------------------------------------------------------------------------------


def test_below_minimum_duration_rejected_before_comparator() -> None:
    chain = _chain()
    gate = _reseal_gate(
        chain["gate"],
        bucket_count=29,
        window_duration_ns=29 * _DAY_NS,
        last_bucket_end_ns=chain["gate"].first_bucket_start_ns + 29 * _DAY_NS,
    )
    sharpe = _reseal_sharpe(chain["sharpe"], bucket_count=29)
    evidence = _build(gate_decision=gate, sharpe_evidence=sharpe)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("duration_below_minimum_precheck") in evidence.reason_codes
    assert evidence.stage4_comparator_invoked is False
    assert evidence.comparison_performed is False
    assert evidence.duration_satisfied is False


def test_incoherent_window_duration_rejects() -> None:
    gate = _reseal_gate(_chain()["gate"], window_duration_ns=29 * _DAY_NS)
    evidence = _build(gate_decision=gate)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("window_duration_incoherent") in evidence.reason_codes


def test_non_positive_gate_window_timestamps_reject() -> None:
    gate = _reseal_gate(_chain()["gate"], first_bucket_start_ns=0)
    evidence = _build(gate_decision=gate)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("gate_window_timestamps_invalid") in evidence.reason_codes


def test_thirty_one_buckets_ready() -> None:
    series = _series(days=31)
    sharpe = _sharpe(series)
    gate = _gate(series)
    evidence = _build(sharpe_evidence=sharpe, gate_decision=gate)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.READY
    assert evidence.bucket_count == 31
    assert evidence.window_duration_ns == 31 * _DAY_NS
    assert evidence.duration_satisfied is True


# --------------------------------------------------------------------------------------------------
# 12. Unsafe-flag matrix
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("flag", ["comparison_ready", "prdv4_stage4_complete", "live_ready"])
def test_sharpe_unsafe_flags_reject(flag: str) -> None:
    sharpe = _reseal_sharpe(_chain()["sharpe"], **{flag: True})
    evidence = _build(sharpe_evidence=sharpe)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("sharpe_evidence_unsafe_flags") in evidence.reason_codes


@pytest.mark.parametrize("flag", ["stage4_comparator_invoked", "comparison_performed"])
def test_methodology_unsafe_flags_reject(flag: str) -> None:
    methodology = _reseal_methodology(_chain()["methodology"], **{flag: True})
    evidence = _build(methodology=methodology)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("methodology_unsafe_flags") in evidence.reason_codes


@pytest.mark.parametrize("flag", ["live_ready", "same_edge_as_backtest_proven"])
def test_edge_identity_unsafe_flags_reject(flag: str) -> None:
    edge = _reseal_edge(_chain()["edge"], **{flag: True})
    evidence = _build(edge_identity=edge)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("edge_identity_unsafe_flags") in evidence.reason_codes


@pytest.mark.parametrize("flag", ["same_edge_as_backtest_proven", "backtest_validity_proven"])
def test_baseline_evidence_unsafe_flags_reject(flag: str) -> None:
    baseline_evidence = _reseal_baseline_evidence(_chain()["baseline_evidence"], **{flag: True})
    evidence = _build(baseline_evidence=baseline_evidence)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("baseline_evidence_unsafe_flags") in evidence.reason_codes


@pytest.mark.parametrize("flag", ["sharpe_computed", "stage4_comparator_invoked"])
def test_gate_unsafe_flags_reject(flag: str) -> None:
    gate = _reseal_gate(_chain()["gate"], **{flag: True})
    evidence = _build(gate_decision=gate)
    assert evidence.status is PaperStage4ComparisonEvidenceStatus.REJECTED
    assert _rc("gate_decision_unsafe_flags") in evidence.reason_codes


# --------------------------------------------------------------------------------------------------
# 13. Raise matrix (call-level malformed input)
# --------------------------------------------------------------------------------------------------


def test_wrong_typed_baseline_raises() -> None:
    with pytest.raises(PaperStage4ComparisonEvidenceError, match="backtest_baseline_malformed"):
        _build(backtest_baseline={"baseline_id": "baseline-1"})


def test_subclass_sharpe_evidence_raises() -> None:
    chain = _chain()
    forged = _SharpeSub(**{field.name: getattr(chain["sharpe"], field.name) for field in fields(PaperSharpeEvidence)})
    with pytest.raises(PaperStage4ComparisonEvidenceError, match="sharpe_evidence_malformed"):
        _build(sharpe_evidence=forged)


def test_malformed_anchor_raises() -> None:
    with pytest.raises(PaperStage4ComparisonEvidenceError, match="expected_sharpe_evidence_digest_invalid"):
        _build(expected_sharpe_evidence_digest="not-a-digest")


def test_liar_str_comparison_evidence_id_raises() -> None:
    with pytest.raises(PaperStage4ComparisonEvidenceError, match="comparison_evidence_id_invalid"):
        _build(comparison_evidence_id=_LiarStr("comparison-evidence-1"))


def test_malformed_metadata_raises() -> None:
    with pytest.raises(PaperStage4ComparisonEvidenceError, match="metadata_malformed"):
        _build(metadata={1: "x"})


def test_forbidden_scope_token_raises() -> None:
    with pytest.raises(PaperStage4ComparisonEvidenceError, match="scope_violation"):
        _build(comparison_evidence_id="live_route-comparison")


def test_clock_token_raises() -> None:
    with pytest.raises(PaperStage4ComparisonEvidenceError, match="clock_token_forbidden"):
        _build(comparison_evidence_id="comparison-clock-check")


# --------------------------------------------------------------------------------------------------
# 14. Determinism / serializer / digest / non-overclaim
# --------------------------------------------------------------------------------------------------


def test_deterministic_same_inputs_same_digest() -> None:
    first = _build()
    second = _build()
    assert first == second
    assert first.comparison_evidence_digest == second.comparison_evidence_digest


def test_to_dict_covers_every_field() -> None:
    evidence = _build()
    payload = paper_stage4_comparison_evidence_to_dict(evidence)
    assert set(payload) == {field.name for field in fields(PaperStage4ComparisonEvidence)}
    assert payload["status"] == "READY"
    assert payload["metadata"] == [["purpose", "stage4 comparison"]]


def test_digest_excludes_only_self_digest() -> None:
    evidence = _build()
    payload = paper_stage4_comparison_evidence_to_dict(evidence)
    carried = payload.pop("comparison_evidence_digest")
    assert carried == evidence.comparison_evidence_digest
    assert _canonical(payload) == evidence.comparison_evidence_digest
    assert paper_stage4_comparison_evidence_digest(evidence) == evidence.comparison_evidence_digest
    assert _is_hex64(evidence.comparison_evidence_digest)


def test_digest_changes_on_any_field_tamper() -> None:
    evidence = _build()
    tampered = replace(evidence, sharpe_retention_satisfied=False, comparison_verdict="RETENTION_NOT_SATISFIED")
    assert paper_stage4_comparison_evidence_digest(tampered) != evidence.comparison_evidence_digest


_NON_OVERCLAIM_FIELDS = (
    "prdv4_stage4_complete",
    "stage4_completion_decided",
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
)


def test_non_overclaim_fields_all_false_and_paper_only_true() -> None:
    for built in (_build(), _build(expected_sharpe_evidence_digest="b" * 64)):
        assert built.paper_only is True
        assert built.comparator_float_advisory_only is True
        for field_name in _NON_OVERCLAIM_FIELDS:
            assert getattr(built, field_name) is False, field_name


def test_metadata_normalized_sorted() -> None:
    evidence = _build(metadata={"zeta": "2", "alpha": "1"})
    assert evidence.metadata == (("alpha", "1"), ("zeta", "2"))


# --------------------------------------------------------------------------------------------------
# 15. AST / source forbidden-surface audit
# --------------------------------------------------------------------------------------------------


def _module_source() -> str:
    return Path(comparison_module.__file__).read_text(encoding="utf-8")


def _module_ast() -> ast.Module:
    return ast.parse(_module_source())


def test_ast_comparator_import_whitelist() -> None:
    allowed = {
        "compare_stage4",
        "Stage4BacktestBaseline",
        "Stage4PaperSummary",
        "Stage4ComparisonResult",
        "stage4_backtest_baseline_to_dict",
        "stage4_paper_summary_to_dict",
    }
    for node in ast.walk(_module_ast()):
        if isinstance(node, ast.ImportFrom) and node.module and "stage4_comparator" in node.module:
            imported = {alias.name for alias in node.names}
            assert imported <= allowed, imported - allowed


def test_ast_no_forbidden_imports() -> None:
    forbidden_modules = {"datetime", "time", "random", "os", "socket", "subprocess", "threading", "pathlib"}
    for node in ast.walk(_module_ast()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in forbidden_modules, alias.name
        if isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            assert root not in forbidden_modules, node.module
            assert not node.module.startswith("crypto_core.service"), node.module
            assert not node.module.startswith("crypto_core.execution"), node.module
            assert "readiness" not in node.module, node.module
            assert "paper_adapter" not in node.module, node.module


def test_ast_compare_stage4_called_exactly_once() -> None:
    calls = [
        node
        for node in ast.walk(_module_ast())
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "compare_stage4")
            or (isinstance(node.func, ast.Attribute) and node.func.attr == "compare_stage4")
        )
    ]
    assert len(calls) == 1


def test_ast_never_constructs_backtest_baseline() -> None:
    source = _module_source()
    assert "build_stage4_backtest_baseline" not in source
    for node in ast.walk(_module_ast()):
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            assert name != "Stage4BacktestBaseline"


def test_ast_decimal_verdict_function_is_float_free() -> None:
    module = _module_ast()
    verdict_functions = [
        node
        for node in ast.walk(module)
        if isinstance(node, ast.FunctionDef) and node.name == "_decimal_retention_verdict"
    ]
    assert len(verdict_functions) == 1
    float_names = [node for node in ast.walk(verdict_functions[0]) if isinstance(node, ast.Name) and node.id == "float"]
    assert float_names == []


def test_source_never_assigns_overclaim_flags_true() -> None:
    source = _module_source()
    assert "prdv4_stage4_complete=True" not in source
    for field_name in _NON_OVERCLAIM_FIELDS:
        assert f"{field_name}=True" not in source, field_name
        assert f'"{field_name}": True' not in source, field_name
        assert f"{field_name}: bool = False" in source, field_name
