"""Tests for deterministic paper Sharpe evidence."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, dataclass, fields, replace
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import pytest

from crypto_core.validation import paper_daily_return_series_evidence as series_module
from crypto_core.validation import paper_sharpe_evidence as sharpe_module
from crypto_core.validation.paper_daily_return_series_evidence import (
    PaperDailyReturnBucket,
    PaperDailyReturnSeriesEvidence,
    PaperDailyReturnSeriesEvidenceStatus,
    build_paper_daily_return_series_evidence,
    paper_daily_return_series_evidence_digest,
)
from crypto_core.validation.paper_deterministic_time_window_adapter import (
    PaperDeterministicTimeWindowEvidence,
    PaperDeterministicTimeWindowEvidenceStatus,
    paper_deterministic_time_window_evidence_digest,
)
from crypto_core.validation.paper_return_series_methodology import (
    build_paper_return_series_methodology,
)
from crypto_core.validation.paper_sharpe_evidence import (
    PaperSharpeEvidenceError,
    PaperSharpeEvidenceStatus,
    build_paper_sharpe_evidence,
    paper_sharpe_evidence_digest,
    paper_sharpe_evidence_to_dict,
)

_DAY_NS = 86_400_000_000_000
_HEX_A = "a" * 64
_RISK_FREE_POLICY_ID = "constant_zero_daily_review_only.v1"
_SCALE_18 = "0.000000000000000000"


class _LiarStr(str):
    """A string subclass rejected by exact string checks."""


@dataclass(frozen=True)
class _SeriesSub(PaperDailyReturnSeriesEvidence):
    """Subclass test double; exact upstream type is required."""


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


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
        "correlation_id": "corr-1",
        "market_symbol": "BTC-PERPETUAL",
        "expected_metrics_summary_digest": _HEX_A,
        "metrics_summary_digest": _HEX_A,
        "summary_ready": True,
        "summary_readiness_verdict": "PAPER_STAGE4_CANDIDATE",
        "started_at_ns": 0,
        "stopped_at_ns": days * _DAY_NS,
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
        bucket_start_ns=day * _DAY_NS,
        bucket_end_ns=(day + 1) * _DAY_NS,
        normalized_index_start=start,
        normalized_index_end=end,
        bucket_digest="",
    )
    return replace(seed, bucket_digest=series_module._bucket_digest(seed))  # noqa: SLF001


def _render(value: Fraction) -> str:
    return series_module._finite_decimal_string(value)  # noqa: SLF001


def _buckets_from_returns(returns: list[Fraction]) -> tuple[PaperDailyReturnBucket, ...]:
    """Build a contiguous UTC daily-bucket index path that yields exactly ``returns`` (terminating decimals)."""

    index = Fraction(1)
    path = [index]
    for daily_return in returns:
        index = index * (Fraction(1) + daily_return)
        path.append(index)
    return tuple(_bucket(day, _render(path[day]), _render(path[day + 1])) for day in range(len(returns)))


def _flat_buckets(days: int = 30) -> tuple[PaperDailyReturnBucket, ...]:
    return tuple(_bucket(day, "1", "1") for day in range(days))


def _alternating_returns(days: int) -> list[Fraction]:
    # Repeating [+1, -0.5] -> two distinct values, strictly positive index path (powers of 2), variance > 0.
    return [Fraction(1) if day % 2 == 0 else Fraction(-1, 2) for day in range(days)]


def _series(
    *,
    days: int = 30,
    buckets: tuple[PaperDailyReturnBucket, ...] | None = None,
    risk_free_policy_id: str = _RISK_FREE_POLICY_ID,
) -> PaperDailyReturnSeriesEvidence:
    methodology = build_paper_return_series_methodology(
        methodology_id="method-1",
        correlation_id="corr-1",
        mtm_policy_id="mtm-policy-1",
        fee_policy_id="fee-policy-1",
        funding_policy_id="funding-policy-1",
        mark_policy_id="mark-policy-1",
        exposure_policy_id="exposure-policy-1",
        liquidation_policy_id="liquidation-policy-1",
        risk_free_policy_id=risk_free_policy_id,
    )
    window = _window(days=days)
    return build_paper_daily_return_series_evidence(
        methodology,
        window,
        expected_methodology_digest=methodology.methodology_digest,
        expected_time_window_digest=window.time_window_digest,
        series_id="series-1",
        correlation_id="corr-1",
        daily_buckets=_alternating_returns_buckets(days) if buckets is None else buckets,
        metadata={"purpose": "daily return series"},
    )


def _alternating_returns_buckets(days: int) -> tuple[PaperDailyReturnBucket, ...]:
    return _buckets_from_returns(_alternating_returns(days))


def _reseal_series(series: PaperDailyReturnSeriesEvidence) -> PaperDailyReturnSeriesEvidence:
    return replace(series, series_digest=paper_daily_return_series_evidence_digest(series))


def _build(series: PaperDailyReturnSeriesEvidence | None = None, **overrides: object):
    current = _series() if series is None else series
    payload: dict[str, object] = {
        "expected_daily_return_series_digest": current.series_digest,
        "risk_free_policy_id": _RISK_FREE_POLICY_ID,
        "sharpe_evidence_id": "sharpe-1",
        "paper_id": "paper-1",
        "correlation_id": "corr-1",
        "metadata": {"purpose": "paper sharpe evidence"},
    }
    payload.update(overrides)
    return build_paper_sharpe_evidence(current, **payload)  # type: ignore[arg-type]


def _quantize(value: Decimal) -> str:
    quantized = value.quantize(Decimal("1e-18"), rounding=ROUND_HALF_EVEN)
    if quantized == 0:
        quantized = Decimal(0).quantize(Decimal("1e-18"))
    return format(quantized, "f")


# --- 1. Public API / duplicate -------------------------------------------------------------------------------


def test_public_api_exact() -> None:
    assert set(sharpe_module.__all__) == {
        "PaperSharpeEvidence",
        "PaperSharpeEvidenceError",
        "PaperSharpeEvidenceStatus",
        "build_paper_sharpe_evidence",
        "paper_sharpe_evidence_digest",
        "paper_sharpe_evidence_to_dict",
    }


def test_no_equivalent_artifact_exists() -> None:
    # No other paper Sharpe builder in the validation package (this is the first Sharpe artifact).
    validation_dir = Path(series_module.__file__).parent
    sharpe_builders = sorted(
        path.name for path in validation_dir.glob("*.py") if "build_paper_sharpe" in path.read_text(encoding="utf-8")
    )
    assert sharpe_builders == ["paper_sharpe_evidence.py"]


def test_output_is_frozen() -> None:
    result = _build()
    with pytest.raises(FrozenInstanceError):
        result.ready = False  # type: ignore[misc]


# --- 2. Happy READY ------------------------------------------------------------------------------------------


def test_happy_path_sharpe_computed() -> None:
    result = _build()
    payload = paper_sharpe_evidence_to_dict(result)

    assert result.status is PaperSharpeEvidenceStatus.READY
    assert result.ready is True
    assert result.sharpe_computed is True
    assert result.stability_warning is True
    assert result.minimum_window_only is True
    assert result.observation_count == 30
    assert result.daily_return_count == 30
    assert result.bucket_count == 30
    assert result.risk_free_policy_id == _RISK_FREE_POLICY_ID
    assert result.risk_free_policy == "constant_zero_daily_review_only"
    assert result.risk_free_daily_return == _SCALE_18
    assert result.annualization_factor == 365
    assert result.annualization_formula == "paper_sharpe_daily * sqrt(365)"
    assert result.stddev_policy == "sample_stddev_n_minus_1.v1"
    assert result.zero_variance_policy == "exact_zero_variance_fail_closed.v1"
    assert result.near_zero_epsilon_policy == "none.v1"
    assert result.decimal_policy == "decimal_quantized_scale_18_round_half_even_internal_precision_80.v1"
    assert result.decimal_scale == 18
    assert result.decimal_rounding == "ROUND_HALF_EVEN"
    assert result.decimal_internal_precision == 80
    assert result.reason_codes == ()
    assert _is_hex64(result.sharpe_evidence_digest)
    assert payload["status"] == "READY"
    assert payload["sharpe_evidence_digest"] == paper_sharpe_evidence_digest(result)
    # Provenance digests are carried from the consumed series.
    assert result.verified_daily_return_series_digest == result.daily_return_series_digest
    assert _is_hex64(result.methodology_digest)
    assert _is_hex64(result.time_window_digest)
    assert _is_hex64(result.metrics_summary_digest)


def test_non_overclaim_flags_are_false_and_digest_bound() -> None:
    result = _build()
    payload = paper_sharpe_evidence_to_dict(result)

    assert payload["paper_only"] is True
    assert payload["daily_return_series_evidence_consumed"] is True
    assert payload["paper_sharpe_evidence"] is True
    assert payload["sharpe_computed"] is True
    for flag in (
        "return_series_constructed",
        "statistical_significance_proven",
        "sharpe_stable",
        "paper_vs_backtest_comparison_ready",
        "comparison_ready",
        "stage4_comparator_invoked",
        "thirty_day_gate_satisfied",
        "thirty_day_gate_decided",
        "prdv4_stage4_complete",
        "live_ready",
        "shadow_ready",
        "operational_readiness",
        "deribit_ready",
        "profitability_proven",
        "edge_proven",
        "production_execution",
        "real_orders_enabled",
        "real_money_enabled",
        "real_capital_reserved",
        "live_api_called",
        "scheduler_enabled",
        "auto_loop_enabled",
        "connector_invoked",
        "real_wall_clock_used",
        "real_account_equity_used",
        "real_capital_used",
    ):
        assert payload[flag] is False
    for forbidden_key in ("comparator_result", "Stage4PaperSummary", "backtest_sharpe", "operator_approval"):
        assert forbidden_key not in payload

    tampered = replace(result, prdv4_stage4_complete=True)
    assert paper_sharpe_evidence_digest(tampered) != result.sharpe_evidence_digest


def test_longer_window_is_not_minimum_only_but_still_warns() -> None:
    result = _build(series=_series(days=31))

    assert result.status is PaperSharpeEvidenceStatus.READY
    assert result.observation_count == 31
    assert result.minimum_window_only is False
    assert result.stability_warning is True
    assert result.sharpe_stable is False
    assert result.statistical_significance_proven is False


# --- 3. Arithmetic -------------------------------------------------------------------------------------------


def test_arithmetic_matches_independent_decimal_computation() -> None:
    # Series of 15x(+1) and 15x(-0.5): mean = 0.25, sample variance (n-1=29) = 135/232 (hand-derived).
    result = _build()

    with localcontext() as ctx:
        ctx.prec = 80
        ctx.rounding = ROUND_HALF_EVEN
        mean = Decimal(1) / Decimal(4)
        variance = Decimal(135) / Decimal(232)
        stddev = variance.sqrt()
        daily = mean / stddev
        annualized = daily * Decimal(365).sqrt()
        expected_mean = _quantize(mean)
        expected_stddev = _quantize(stddev)
        expected_daily = _quantize(daily)
        expected_annualized = _quantize(annualized)

    assert result.mean_excess_return == "0.250000000000000000"
    assert result.mean_excess_return == expected_mean
    assert result.sample_stddev_excess_return == expected_stddev
    assert result.paper_sharpe_daily == expected_daily
    assert result.paper_sharpe_annualized == expected_annualized
    # Every public decimal output is quantized to exactly 18 fractional digits.
    for value in (
        result.mean_excess_return,
        result.sample_stddev_excess_return,
        result.paper_sharpe_daily,
        result.paper_sharpe_annualized,
        result.risk_free_daily_return,
    ):
        assert len(value.split(".")[1]) == 18
    # Sharpe is strictly positive here.
    assert result.paper_sharpe_daily[0] != "-"
    assert result.paper_sharpe_annualized[0] != "-"


def test_negative_mean_yields_negative_sharpe() -> None:
    returns = [Fraction(1)] * 8 + [Fraction(-1, 2)] * 22  # mean = (8 - 11) / 30 = -0.1
    result = _build(series=_series(buckets=_buckets_from_returns(returns)))

    assert result.status is PaperSharpeEvidenceStatus.READY
    assert result.mean_excess_return == "-0.100000000000000000"
    assert result.paper_sharpe_daily.startswith("-")
    assert result.paper_sharpe_annualized.startswith("-")


def test_zero_mean_normalizes_signed_zero() -> None:
    returns = [Fraction(1), Fraction(-1, 2), Fraction(-1, 2)] * 10  # each period sums to 0 -> mean 0
    result = _build(series=_series(buckets=_buckets_from_returns(returns)))

    assert result.status is PaperSharpeEvidenceStatus.READY
    assert result.mean_excess_return == _SCALE_18
    assert result.paper_sharpe_daily == _SCALE_18
    assert result.paper_sharpe_annualized == _SCALE_18
    assert not result.paper_sharpe_daily.startswith("-")


def test_repeated_build_is_deterministic() -> None:
    first = _build()
    second = _build()
    assert first.sharpe_evidence_digest == second.sharpe_evidence_digest
    assert first.paper_sharpe_annualized == second.paper_sharpe_annualized


# --- 4. Digest / provenance ----------------------------------------------------------------------------------


def test_expected_digest_mismatch_rejects() -> None:
    result = _build(expected_daily_return_series_digest="b" * 64)

    assert result.status is PaperSharpeEvidenceStatus.REJECTED
    assert result.sharpe_computed is False
    assert result.mean_excess_return == ""
    assert result.verified_daily_return_series_digest == ""
    assert "paper_sharpe_evidence:series_digest_mismatch" in result.reason_codes


def test_forged_stored_digest_rejects() -> None:
    series = _series()
    forged = replace(series, series_digest="c" * 64)
    result = build_paper_sharpe_evidence(
        forged,
        expected_daily_return_series_digest="c" * 64,
        risk_free_policy_id=_RISK_FREE_POLICY_ID,
        sharpe_evidence_id="sharpe-1",
        paper_id="paper-1",
        correlation_id="corr-1",
    )

    assert result.status is PaperSharpeEvidenceStatus.REJECTED
    assert "paper_sharpe_evidence:series_digest_mismatch" in result.reason_codes


def test_changed_series_changes_evidence_digest() -> None:
    base = _build()
    changed = _build(series=_series(buckets=_buckets_from_returns([Fraction(1)] * 8 + [Fraction(-1, 2)] * 22)))

    assert base.daily_return_series_digest != changed.daily_return_series_digest
    assert base.sharpe_evidence_digest != changed.sharpe_evidence_digest
    assert base.paper_sharpe_annualized != changed.paper_sharpe_annualized


def test_metadata_changes_digest_and_is_order_independent() -> None:
    first = _build(metadata={"b": "2", "a": "1"})
    second = _build(metadata={"a": "1", "b": "2"})
    changed = _build(metadata={"a": "1", "b": "3"})

    assert first.sharpe_evidence_digest == second.sharpe_evidence_digest
    assert changed.sharpe_evidence_digest != first.sharpe_evidence_digest


def test_digest_excludes_only_self_digest() -> None:
    result = _build()
    assert paper_sharpe_evidence_digest(result) == result.sharpe_evidence_digest
    resealed = replace(result, sharpe_evidence_digest="0" * 64)
    assert paper_sharpe_evidence_digest(resealed) == result.sharpe_evidence_digest


def test_serializer_matches_dataclass_fields() -> None:
    result = _build()
    payload = paper_sharpe_evidence_to_dict(result)
    dataclass_field_names = {field.name for field in fields(result)}

    assert set(payload) == dataclass_field_names
    assert payload["status"] == result.status.value
    assert payload["metadata"] == [["purpose", "paper sharpe evidence"]]


def test_inputs_not_mutated() -> None:
    series = _series()
    metadata = {"b": "2", "a": "1"}
    before_digest = series.series_digest
    _build(series=series, metadata=metadata)

    assert series.series_digest == before_digest
    assert metadata == {"b": "2", "a": "1"}


def test_carried_upstream_digests_are_bound() -> None:
    result = _build()
    tampered = replace(result, methodology_digest="d" * 64)
    assert paper_sharpe_evidence_digest(tampered) != result.sharpe_evidence_digest
    tampered_tw = replace(result, time_window_digest="d" * 64)
    assert paper_sharpe_evidence_digest(tampered_tw) != result.sharpe_evidence_digest


# --- 5. Fail-closed ------------------------------------------------------------------------------------------


def test_exact_upstream_type_required() -> None:
    series = _series()
    values = {field.name: getattr(series, field.name) for field in fields(series)}
    sub = _SeriesSub(**values)

    with pytest.raises(PaperSharpeEvidenceError, match="series_malformed"):
        _build(series=sub)


def test_malformed_expected_digest_raises() -> None:
    with pytest.raises(PaperSharpeEvidenceError, match="expected_daily_return_series_digest_invalid"):
        _build(expected_daily_return_series_digest="not-a-digest")


def test_unapproved_risk_free_policy_id_raises() -> None:
    with pytest.raises(PaperSharpeEvidenceError, match="risk_free_policy_unapproved"):
        _build(risk_free_policy_id="constant_zero_daily_review_only.v2")


def test_series_risk_free_policy_mismatch_rejects() -> None:
    mismatched = _series(risk_free_policy_id="some-other-policy")
    result = build_paper_sharpe_evidence(
        mismatched,
        expected_daily_return_series_digest=mismatched.series_digest,
        risk_free_policy_id=_RISK_FREE_POLICY_ID,
        sharpe_evidence_id="sharpe-1",
        paper_id="paper-1",
        correlation_id="corr-1",
    )

    assert result.status is PaperSharpeEvidenceStatus.REJECTED
    assert "paper_sharpe_evidence:series_risk_free_policy_mismatch" in result.reason_codes
    assert "paper_sharpe_evidence:risk_free_policy_id_series_mismatch" in result.reason_codes


def test_unsafe_upstream_flag_rejects_even_when_resealed() -> None:
    unsafe = _reseal_series(replace(_series(), live_ready=True, sharpe_computed=True))
    result = _build(series=unsafe)

    assert result.status is PaperSharpeEvidenceStatus.REJECTED
    assert "paper_sharpe_evidence:series_unsafe_flags" in result.reason_codes


def test_upstream_not_ready_rejects() -> None:
    rejected = _reseal_series(
        replace(
            _series(),
            status=PaperDailyReturnSeriesEvidenceStatus.REJECTED,
            ready=False,
            reason_codes=("paper_daily_return_series_evidence:test_rejection",),
            return_series_computed=False,
            daily_returns_computed=False,
        )
    )
    result = _build(series=rejected)

    assert result.status is PaperSharpeEvidenceStatus.REJECTED
    assert "paper_sharpe_evidence:series_not_ready" in result.reason_codes


@pytest.mark.parametrize("days", [1, 29])
def test_below_minimum_returns_rejects(days: int) -> None:
    result = _build(series=_series(days=days))

    assert result.status is PaperSharpeEvidenceStatus.REJECTED
    assert "paper_sharpe_evidence:insufficient_bucket_count" in result.reason_codes
    assert "paper_sharpe_evidence:insufficient_daily_return_count" in result.reason_codes


def test_count_mismatch_rejects_digest_valid_forgery() -> None:
    forged = _reseal_series(replace(_series(), return_count=29))
    result = _build(series=forged)

    assert result.status is PaperSharpeEvidenceStatus.REJECTED
    assert "paper_sharpe_evidence:daily_return_count_mismatch" in result.reason_codes


def test_daily_returns_list_container_rejects_even_when_resealed() -> None:
    series = _series()
    forged = _reseal_series(replace(series, daily_returns=list(series.daily_returns)))
    result = _build(series=forged)

    assert result.status is PaperSharpeEvidenceStatus.REJECTED
    assert result.sharpe_computed is False
    assert "paper_sharpe_evidence:daily_returns_container_malformed" in result.reason_codes


def test_daily_returns_none_fails_closed_without_typeerror() -> None:
    forged = replace(_series(), daily_returns=None)
    result = _build(series=forged)

    assert result.status is PaperSharpeEvidenceStatus.REJECTED
    assert "paper_sharpe_evidence:daily_returns_container_malformed" in result.reason_codes


def test_noncanonical_daily_return_rejects_even_when_resealed() -> None:
    series = _series()
    forged = _reseal_series(replace(series, daily_returns=(*series.daily_returns[:-1], "0.50")))
    result = _build(series=forged)

    assert result.status is PaperSharpeEvidenceStatus.REJECTED
    assert "paper_sharpe_evidence:daily_return_noncanonical" in result.reason_codes


def test_exact_zero_variance_rejects() -> None:
    # A flat normalized-index path yields all-zero returns -> exact zero variance -> fail closed.
    flat = _series(buckets=_flat_buckets(30))
    result = _build(series=flat)

    assert result.status is PaperSharpeEvidenceStatus.REJECTED
    assert result.sharpe_computed is False
    assert result.mean_excess_return == ""
    assert "paper_sharpe_evidence:zero_variance" in result.reason_codes


def test_correlation_id_mismatch_rejects() -> None:
    result = _build(correlation_id="corr-2")

    assert result.status is PaperSharpeEvidenceStatus.REJECTED
    assert "paper_sharpe_evidence:correlation_id_mismatch" in result.reason_codes


# --- 6. IDs / metadata ---------------------------------------------------------------------------------------


def test_empty_and_subclass_ids_raise() -> None:
    with pytest.raises(PaperSharpeEvidenceError, match="sharpe_evidence_id_invalid"):
        _build(sharpe_evidence_id="  ")
    with pytest.raises(PaperSharpeEvidenceError, match="paper_id_invalid"):
        _build(paper_id=_LiarStr("paper-1"))
    with pytest.raises(PaperSharpeEvidenceError, match="correlation_id_invalid"):
        _build(correlation_id="")


def test_malformed_metadata_raises() -> None:
    with pytest.raises(PaperSharpeEvidenceError, match="metadata_malformed"):
        _build(metadata={"ok": 1})


@pytest.mark.parametrize(
    "override",
    [
        {"sharpe_evidence_id": "live-sharpe"},
        {"paper_id": "order-paper"},
        {"correlation_id": "shadow-corr"},
        {"metadata": {"path": "crypto_core.execution.paper_adapter"}},
        {"metadata": {"venue": "BIST"}},
        {"metadata": {"source": "time.time_ns"}},
        {"metadata": {"source": "datetime.now"}},
    ],
)
def test_forbidden_scope_and_clock_tokens_raise(override: dict[str, object]) -> None:
    with pytest.raises(PaperSharpeEvidenceError):
        _build(**override)


def test_metadata_is_copied_and_frozen() -> None:
    result = _build()
    payload = paper_sharpe_evidence_to_dict(result)
    assert payload["metadata"] == [["purpose", "paper sharpe evidence"]]
    with pytest.raises(FrozenInstanceError):
        result.metadata = ()  # type: ignore[misc]


# --- 7. Non-overclaim ----------------------------------------------------------------------------------------


def test_ready_does_not_imply_comparison_or_completion() -> None:
    result = _build()
    assert result.comparison_ready is False
    assert result.paper_vs_backtest_comparison_ready is False
    assert result.stage4_comparator_invoked is False
    assert result.thirty_day_gate_satisfied is False
    assert result.prdv4_stage4_complete is False
    assert result.profitability_proven is False
    assert result.edge_proven is False
    assert result.statistical_significance_proven is False
    assert result.sharpe_stable is False


# --- 8. AST forbidden surface --------------------------------------------------------------------------------


def test_source_has_no_forbidden_runtime_or_stage4_execution_surfaces() -> None:
    source = Path(sharpe_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = (
        "math",
        "numpy",
        "pandas",
        "time",
        "datetime",
        "random",
        "secrets",
        "uuid",
        "socket",
        "requests",
        "httpx",
        "aiohttp",
        "threading",
        "asyncio",
        "multiprocessing",
        "subprocess",
        "os",
        "pathlib",
        "shutil",
        "sqlite3",
        "duckdb",
        "crypto_core.service",
        "crypto_core.execution",
        "crypto_core.venue",
        "crypto_core.runtime",
        "crypto_core.orchestrator",
        "crypto_core.temporal",
        "crypto_core.session",
        "crypto_core.data",
        "crypto_core.portfolio",
        "crypto_core.validation.stage4_comparator",
    )
    forbidden_call_names = {
        "open",
        "Path",
        "float",
        "compare_stage4",
        "Stage4PaperSummary",
        "now",
        "utcnow",
        "time",
        "time_ns",
        "perf_counter",
        "monotonic",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(
                    alias.name == module or alias.name.startswith(f"{module}.") for module in forbidden_modules
                )
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(
                node.module == module or node.module.startswith(f"{module}.") for module in forbidden_modules
            )
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name):
                assert function.id not in forbidden_call_names
            if isinstance(function, ast.Attribute):
                assert function.attr not in forbidden_call_names
