"""Tests for deterministic historical walk-forward metrics (HISTORICAL_WALK_FORWARD_METRICS_V1)."""

from __future__ import annotations

import ast
import functools
import json
from dataclasses import replace
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from fractions import Fraction
from pathlib import Path

import pytest

import crypto_core.validation.historical_walk_forward_metrics as metrics_module
from crypto_core.data.requirements import data_requirement_registry_digest
from crypto_core.validation.edge_artifact_core import (
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeAuthorityBinding,
    EdgeEvidenceStatus,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_sha256_text,
)
from crypto_core.validation.historical_execution_economics import (
    HistoricalExecutionEconomicsResult,
    HistoricalExecutionValuationKind,
    build_historical_execution_economics,
    historical_execution_economics_digest,
)
from crypto_core.validation.historical_pit_dataset import (
    HistoricalPitValue,
    build_historical_pit_dataset,
    build_historical_pit_record,
)
from crypto_core.validation.historical_walk_forward_metric_policy import (
    HISTORICAL_WALK_FORWARD_NUMERIC_POLICY_V1,
    historical_walk_forward_metric_policy_digest,
)
from crypto_core.validation.historical_walk_forward_metrics import (
    HISTORICAL_WALK_FORWARD_METRICS_NON_CLAIM_FLAGS,
    HistoricalWalkForwardMetricsError,
    HistoricalWalkForwardMetricsResult,
    HistoricalWalkForwardSegmentKind,
    HistoricalWalkForwardWindowBinding,
    HistoricalWalkForwardWindowInput,
    build_historical_walk_forward_metrics,
    historical_walk_forward_metrics_digest,
    historical_walk_forward_metrics_from_payload,
    historical_walk_forward_metrics_payload_is_well_formed,
    historical_walk_forward_metrics_to_dict,
    verify_historical_walk_forward_metrics,
)
from tests.crypto_core.validation import test_historical_decision_run as runt
from tests.crypto_core.validation import test_historical_execution_economics as econ
from tests.crypto_core.validation import test_historical_execution_economics_policy as polt
from tests.crypto_core.validation import test_historical_walk_forward_metric_policy as mpt
from tests.crypto_core.validation import test_strategy_executable_binding as bind
from tests.crypto_core.validation import test_strategy_executable_profiles as prof

_PREFIX = "historical_walk_forward_metrics"
DAY = 86_400_000_000_000
S0 = DAY * 19_000  # a UTC day boundary
FUNDING = 10 * DAY
MARK_STEP = 5 * DAY
HORIZON_DAYS = 580
RATE = "0.000300000000000000"
KIND = HistoricalExecutionValuationKind
IS = HistoricalWalkForwardSegmentKind.IN_SAMPLE
OOS = HistoricalWalkForwardSegmentKind.OUT_OF_SAMPLE
d = polt.d
NUMERIC = HISTORICAL_WALK_FORWARD_NUMERIC_POLICY_V1

PARAMS_A = prof.params()
PARAMS_B = prof.params(unit="2.000000000000000000")
PARAMS_NEVER_ENTERS = prof.params(entry="0.001000000000000000")


# --- authenticated fixture chain: one PIT dataset, real decision runs, real execution economics ------------------------


def _pit(series: str, key: str, sequence: int, event: int, values: dict[str, str]):
    return build_historical_pit_record(
        series_id=series,
        data_requirement_key=key,
        instrument=econ.INS,
        sequence_id=sequence,
        event_time_ns=event,
        available_at_ns=event + 1,
        finalized_at_ns=event + 2,
        revision_vintage_id=None,
        values=tuple(HistoricalPitValue(name, value) for name, value in sorted(values.items())),
    )


def _mark(index: int) -> dict[str, str]:
    """A deterministic mark path with rises and falls every five days (a SHORT loses on a rise)."""

    return {"mark_price": d(Fraction(100) + Fraction((index * 7) % 11 - 5, 4))}


def _book() -> dict[str, str]:
    return {
        "best_bid_price": d(Fraction(9995, 100)),
        "best_ask_price": d(Fraction(10005, 100)),
        "best_bid_quantity": d(1000),
        "best_ask_quantity": d(1000),
    }


@functools.cache
def records():
    """Funding every 10 days (final after its own cycle), marks every 5 days, a book shortly after each decision."""

    funding = [
        build_historical_pit_record(
            series_id="funding-final",
            data_requirement_key="funding_rate",
            instrument=econ.INS,
            sequence_id=k,
            event_time_ns=S0 + (k - 1) * FUNDING,
            available_at_ns=S0 + k * FUNDING + 10,
            finalized_at_ns=S0 + k * FUNDING + 10,
            revision_vintage_id=None,
            values=(HistoricalPitValue("funding_rate", RATE),),
        )
        for k in range(HORIZON_DAYS // 10 + 2)
    ]
    marks = [_pit("mark", "mark_price", j, S0 + j * MARK_STEP - 1_000, _mark(j)) for j in range(HORIZON_DAYS // 5 + 2)]
    books = [_pit("book", "order_book", k, S0 + k * FUNDING + 500, _book()) for k in range(HORIZON_DAYS // 10 + 2)]
    return tuple(funding + marks + books)


@functools.cache
def _chain():
    return econ.chain()


@functools.cache
def dataset():
    manifest, _, registry = _chain()
    return build_historical_pit_dataset(
        manifest,
        expected_source_manifest_digest=manifest.source_packet_evidence_digest,
        expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
        dataset_id="dataset-1",
        correlation_id="corr-1",
        source_reference="archive:history",
        rights_status="own_research",
        rights_reference="license-1",
        records=records(),
    )


@functools.cache
def executable_binding():
    return bind.executable_binding(_chain()[1], binding_id="binding-1")


@functools.cache
def economics_policy(taker_fee_bps: str = d(5)):
    return polt.cited_policy(funding_interval_ns=FUNDING, max_mark_staleness_ns=6 * DAY, taker_fee_bps=taker_fee_bps)


@functools.cache
def economics_at(
    start_ns: int, end_ns: int, params=PARAMS_A, *, fee: str | None = None, approved: bool = True
) -> HistoricalExecutionEconomicsResult:
    run_id = f"run-{start_ns - S0}-{end_ns - S0}-{edge_sha256_text(str(params))[:8]}"
    run = runt.decision_run(
        dataset(),
        executable_binding(),
        instrument=econ.INS,
        evaluation_start_ns=start_ns,
        evaluation_end_ns=end_ns,
        parameter_assignment=params,
        run_id=run_id,
    )
    policy = economics_policy() if fee is None else economics_policy(fee)
    approval = (
        polt.approval_for(
            policy,
            strategy_spec_digest=run.strategy_spec_digest,
            data_requirement_registry_digest=data_requirement_registry_digest(_chain()[2]),
        )
        if approved
        else None
    )
    return build_historical_execution_economics(
        run,
        expected_run_digest=run.run_digest,
        economics_policy=policy,
        expected_economics_policy_digest=policy.policy_digest,
        economics_approval=approval,
        result_id=f"{run_id}-economics",
        correlation_id="corr-1",
    )


def segment(start_day: int, days: int, params=PARAMS_A, **kwargs: object) -> HistoricalExecutionEconomicsResult:
    return economics_at(S0 + start_day * DAY, S0 + (start_day + days) * DAY, params, **kwargs)  # type: ignore[arg-type]


def window(window_id: str, in_sample, out_of_sample) -> HistoricalWalkForwardWindowInput:
    return HistoricalWalkForwardWindowInput(
        window_id=window_id,
        in_sample_economics=in_sample,
        expected_in_sample_result_digest=in_sample.result_digest,
        out_of_sample_economics=out_of_sample,
        expected_out_of_sample_result_digest=out_of_sample.result_digest,
    )


def w1() -> HistoricalWalkForwardWindowInput:
    return window("wf-1", segment(0, 365), segment(365, 90))


def w2() -> HistoricalWalkForwardWindowInput:
    return window("wf-2", segment(90, 365, PARAMS_B), segment(455, 90, PARAMS_B))


@functools.cache
def metric_policy():
    return mpt.policy()


def build(windows, **overrides: object) -> HistoricalWalkForwardMetricsResult:
    arguments: dict[str, object] = {
        "metric_policy": metric_policy(),
        "expected_metric_policy_digest": metric_policy().policy_digest,
        "windows": windows,
        "result_id": "walk-forward-metrics-1",
        "correlation_id": "corr-1",
    }
    arguments.update(overrides)
    return build_historical_walk_forward_metrics(**arguments)  # type: ignore[arg-type]


@functools.cache
def one_window() -> HistoricalWalkForwardMetricsResult:
    return build((w1(),))


@functools.cache
def two_windows() -> HistoricalWalkForwardMetricsResult:
    return build((w1(), w2()))


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _reseal(result: HistoricalWalkForwardMetricsResult, **changes: object) -> HistoricalWalkForwardMetricsResult:
    changed = replace(result, **changes)
    return replace(changed, result_digest=historical_walk_forward_metrics_digest(changed))


def _reseal_record(record, digest_field: str, **changes: object):
    changed = replace(record, **changes)
    payload = metrics_module._to_payload(changed)
    del payload[digest_field]
    return replace(changed, **{digest_field: edge_sha256_text(edge_canonical_json(payload))})


def _assert_receipt_invariants(result: HistoricalWalkForwardMetricsResult) -> None:
    verification = verify_historical_walk_forward_metrics(result)
    assert verification.intact is True, verification.reason_codes
    assert verification.recomputed_digest == result.result_digest
    assert historical_walk_forward_metrics_from_payload(json.loads(verification.canonical_json)) == result
    assert historical_walk_forward_metrics_payload_is_well_formed(historical_walk_forward_metrics_to_dict(result))
    computed = result.status is EdgeEvidenceStatus.READY and result.computation_verdict is EdgeGateVerdict.PASS
    assert result.performance_metrics_computed is computed
    assert result.window_digests == tuple(window.window_digest for window in result.windows)
    assert result.window_count == len(result.window_bindings) == len(result.window_ids)
    if not computed:
        assert result.windows == ()
    if result.status is EdgeEvidenceStatus.REJECTED:
        assert result.computation_verdict is EdgeGateVerdict.NOT_EVALUATED
        assert result.integrity_reason_codes
        assert result.verdict_reason_codes == ()
        assert result.strategy_spec_digest == result.instrument == ""
    else:
        assert result.integrity_reason_codes == ()
    for name, expected in HISTORICAL_WALK_FORWARD_METRICS_NON_CLAIM_FLAGS:
        assert getattr(result, name) is expected, name


def _assert_shape(result: HistoricalWalkForwardMetricsResult) -> None:
    """Invariants that need no re-proof; ``_assert_receipt_invariants`` re-proves in the dedicated receipt tests."""

    assert result.result_digest == historical_walk_forward_metrics_digest(result)
    assert result.performance_metrics_computed is False and result.windows == () and result.window_digests == ()
    for name, expected in HISTORICAL_WALK_FORWARD_METRICS_NON_CLAIM_FLAGS:
        assert getattr(result, name) is expected, name


def _failed(result: HistoricalWalkForwardMetricsResult, *codes: str) -> None:
    _assert_shape(result)
    assert result.integrity_reason_codes == ()
    assert (result.status, result.computation_verdict) == (EdgeEvidenceStatus.READY, EdgeGateVerdict.FAIL)
    assert {_code(code) for code in codes} <= set(result.verdict_reason_codes), result.verdict_reason_codes


def _rejected(result: HistoricalWalkForwardMetricsResult, *codes: str) -> None:
    _assert_shape(result)
    assert result.verdict_reason_codes == () and result.strategy_spec_digest == result.instrument == ""
    assert (result.status, result.computation_verdict) == (EdgeEvidenceStatus.REJECTED, EdgeGateVerdict.NOT_EVALUATED)
    assert {_code(code) for code in codes} <= set(result.integrity_reason_codes), result.integrity_reason_codes


# --- independent oracle (exact Fraction returns; high-precision decimal square root) ----------------------------------


def _oracle_endpoints(result: HistoricalExecutionEconomicsResult):
    start, end = result.evaluation_start_ns, result.evaluation_end_ns
    picks = []
    for valuation in result.valuations:
        if valuation.valuation_kind is KIND.INITIAL and valuation.time_ns == start:
            picks.append(valuation)
        elif valuation.valuation_kind is KIND.UTC_DAY_BOUNDARY and start < valuation.time_ns < end:
            picks.append(valuation)
        elif valuation.valuation_kind is KIND.EVALUATION_END and valuation.time_ns == end:
            picks.append(valuation)
    return picks


def _text(value: Decimal) -> str:
    quantized = value.quantize(Decimal(1).scaleb(-18), rounding=ROUND_HALF_EVEN)
    if quantized == 0:
        quantized = Decimal(0).quantize(Decimal(1).scaleb(-18))
    return format(quantized, "f")


def _fraction_text(value: Fraction) -> str:
    with localcontext() as context:
        context.prec = 400
        context.rounding = ROUND_HALF_EVEN
        return _text(Decimal(value.numerator) / Decimal(value.denominator))


def _oracle(equities: list[Fraction]) -> dict[str, str]:
    returns = [later / earlier - 1 for earlier, later in zip(equities, equities[1:], strict=False)]
    n = len(returns)
    mean = sum(returns, Fraction(0)) / n
    variance = sum(((item - mean) ** 2 for item in returns), Fraction(0)) / (n - 1)
    with localcontext() as context:
        context.prec = 400
        context.rounding = ROUND_HALF_EVEN
        std = (Decimal(variance.numerator) / Decimal(variance.denominator)).sqrt()
        daily_sharpe = (Decimal(mean.numerator) / Decimal(mean.denominator)) / std
        sharpe = _text(daily_sharpe * Decimal(365).sqrt())
    peak, drawdown = equities[0], Fraction(0)
    for equity in equities:
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)
    gains = sum((item for item in returns if item > 0), Fraction(0))
    losses = -sum((item for item in returns if item < 0), Fraction(0))
    return {
        "annualized_sharpe": sharpe,
        "hit_rate": _fraction_text(Fraction(sum(1 for item in returns if item > 0), n)),
        "expectancy": _fraction_text(mean),
        "max_drawdown": _fraction_text(drawdown),
        "profit_factor": _fraction_text(gains / losses),
    }


def _oracle_for(source: HistoricalExecutionEconomicsResult) -> dict[str, str]:
    return _oracle([Fraction(item.equity) for item in _oracle_endpoints(source)])


# --- canonical results --------------------------------------------------------------------------------------------------


def test_canonical_one_window_result_is_ready_pass_and_re_proves() -> None:
    result = one_window()
    _assert_receipt_invariants(result)
    assert (result.status, result.computation_verdict, result.performance_metrics_computed) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.PASS,
        True,
    )
    assert result.window_count == 1 and result.window_ids == ("wf-1",)
    assert result.metric_policy_digest == metric_policy().policy_digest
    in_sample, out_of_sample = segment(0, 365), segment(365, 90)
    assert result.source_result_digests == (in_sample.result_digest, out_of_sample.result_digest)
    assert (result.strategy_spec_digest, result.instrument, result.market_type) == (
        in_sample.strategy_spec_digest,
        in_sample.instrument,
        in_sample.market_type,
    )
    assert result.economics_policy_digest == in_sample.economics_policy_digest
    assert result.synthetic_test_facts_used is True and result.synthetic_test_approval_used is True
    (metrics,) = result.windows
    assert (metrics.window_index, metrics.window_id) == (0, "wf-1")
    assert metrics.parameter_assignment_digest == in_sample.parameter_assignment_digest
    assert metrics.in_sample.segment_kind is IS and metrics.out_of_sample.segment_kind is OOS
    assert metrics.in_sample.source_result_digest == in_sample.result_digest
    assert metrics.out_of_sample.source_result_digest == out_of_sample.result_digest
    assert metrics.in_sample.source_valuation_ledger_digest == in_sample.valuation_ledger_digest


def test_repeat_builds_are_byte_identical_and_digest_identical() -> None:
    first = build((w1(),))
    second = build((w1(),))
    assert edge_canonical_json(historical_walk_forward_metrics_to_dict(first)) == edge_canonical_json(
        historical_walk_forward_metrics_to_dict(second)
    )
    assert first.result_digest == second.result_digest == one_window().result_digest


def test_window_geometry_is_exact_365_day_is_90_day_oos_and_zero_embargo() -> None:
    (metrics,) = one_window().windows
    assert (metrics.in_sample.evaluation_start_ns, metrics.in_sample.evaluation_end_ns) == (S0, S0 + 365 * DAY)
    assert (metrics.out_of_sample.evaluation_start_ns, metrics.out_of_sample.evaluation_end_ns) == (
        S0 + 365 * DAY,
        S0 + 455 * DAY,
    )
    assert metrics.out_of_sample.evaluation_start_ns == metrics.in_sample.evaluation_end_ns
    assert (metrics.in_sample.daily_return_count, metrics.out_of_sample.daily_return_count) == (365, 90)
    assert (metrics.in_sample.daily_endpoint_count, metrics.out_of_sample.daily_endpoint_count) == (366, 91)


def test_multi_window_result_advances_the_oos_start_by_the_90_day_stride() -> None:
    result = two_windows()
    _assert_receipt_invariants(result)
    assert result.computation_verdict is EdgeGateVerdict.PASS
    first, second = result.windows
    assert second.out_of_sample.evaluation_start_ns - first.out_of_sample.evaluation_start_ns == 90 * DAY
    assert second.in_sample.evaluation_start_ns - first.in_sample.evaluation_start_ns == 90 * DAY
    assert [window.window_index for window in result.windows] == [0, 1]
    assert result.window_digests == (first.window_digest, second.window_digest)


def test_the_window_count_is_generic_not_a_fixed_count() -> None:
    assert one_window().window_count == 1 and two_windows().window_count == 2
    assert one_window().computation_verdict is two_windows().computation_verdict is EdgeGateVerdict.PASS
    source = Path(metrics_module.__file__).read_text(encoding="utf-8")
    constants = {node.value for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Constant)}
    assert 16 not in constants


def test_the_parameter_assignment_may_change_between_windows() -> None:
    first, second = two_windows().windows
    assert first.parameter_assignment_digest != second.parameter_assignment_digest
    assert first.parameter_assignment_digest == segment(0, 365).parameter_assignment_digest
    assert second.parameter_assignment_digest == segment(90, 365, PARAMS_B).parameter_assignment_digest


def test_an_assignment_mismatch_within_one_window_fails() -> None:
    result = build((window("wf-1", segment(0, 365), segment(365, 90, PARAMS_B)),))
    _failed(result, "window_0:assignment_mismatch")


# --- daily return series ------------------------------------------------------------------------------------------------


def test_daily_endpoints_come_only_from_initial_day_boundary_and_end_valuations() -> None:
    (metrics,) = one_window().windows
    for segment_metrics, source in ((metrics.in_sample, segment(0, 365)), (metrics.out_of_sample, segment(365, 90))):
        picks = _oracle_endpoints(source)
        assert [item.time_ns for item in picks] == [
            segment_metrics.evaluation_start_ns + k * DAY for k in range(segment_metrics.daily_endpoint_count)
        ]
        expected = edge_sha256_text(
            edge_canonical_json(
                [[item.valuation_sequence, item.time_ns, item.valuation_digest, item.equity] for item in picks]
            )
        )
        assert segment_metrics.daily_endpoint_digest == expected
        assert (segment_metrics.start_equity, segment_metrics.end_equity) == (picks[0].equity, picks[-1].equity)
    in_sample = segment(0, 365)
    instants: dict[int, int] = {}
    for valuation in in_sample.valuations:
        instants[valuation.time_ns] = instants.get(valuation.time_ns, 0) + 1
    shared = {time for time, count in instants.items() if count > 1}
    assert shared and all(time % DAY == 0 for time in shared), "funding settlements share day-boundary instants"


def test_fees_and_funding_embedded_in_equity_are_never_counted_again() -> None:
    source = segment(0, 365)
    assert source.fee_cashflows and source.funding_cashflows
    (metrics,) = one_window().windows
    assert metrics.in_sample.start_equity == economics_policy().initial_equity
    assert metrics.in_sample.end_equity == source.terminal_state.equity  # type: ignore[union-attr]
    equities = [Fraction(item.equity) for item in _oracle_endpoints(source)]
    net = equities[-1] - equities[0]
    realized = Fraction(source.terminal_state.cumulative_realized_gross_pnl)  # type: ignore[union-attr]
    fees = Fraction(source.terminal_state.cumulative_fees)  # type: ignore[union-attr]
    funding = Fraction(source.terminal_state.cumulative_funding)  # type: ignore[union-attr]
    unrealized = Fraction(source.terminal_state.unrealized_pnl)  # type: ignore[union-attr]
    assert fees > 0 and funding != 0
    assert net == realized - fees + funding + unrealized
    assert metrics.in_sample.expectancy == _oracle_for(source)["expectancy"]
    module_source = Path(metrics_module.__file__).read_text(encoding="utf-8")
    for ledger in ("fee_cashflows", "funding_cashflows", "cumulative_fees", "cumulative_funding", "trades"):
        assert ledger not in module_source


@pytest.mark.parametrize("metric", ["annualized_sharpe", "hit_rate", "expectancy", "max_drawdown", "profit_factor"])
def test_every_metric_equals_the_independent_oracle(metric: str) -> None:
    for result, sources in (
        (one_window(), ((segment(0, 365), segment(365, 90)),)),
        (
            two_windows(),
            ((segment(0, 365), segment(365, 90)), (segment(90, 365, PARAMS_B), segment(455, 90, PARAMS_B))),
        ),
    ):
        for metrics, (in_sample, out_of_sample) in zip(result.windows, sources, strict=True):
            assert getattr(metrics.in_sample, metric) == _oracle_for(in_sample)[metric]
            assert getattr(metrics.out_of_sample, metric) == _oracle_for(out_of_sample)[metric]


def test_return_counts_partition_the_daily_returns() -> None:
    for metrics in two_windows().windows:
        for item in (metrics.in_sample, metrics.out_of_sample):
            assert item.positive_daily_return_count > 0 and item.negative_daily_return_count > 0
            assert item.zero_daily_return_count > 0
            assert (
                item.positive_daily_return_count + item.negative_daily_return_count + item.zero_daily_return_count
                == item.daily_return_count
            )
            assert item.hit_rate == _fraction_text(Fraction(item.positive_daily_return_count, item.daily_return_count))


def test_a_segment_without_losing_days_fails_closed_on_the_undefined_profit_factor() -> None:
    result = build((window("wf-1", segment(0, 365, PARAMS_NEVER_ENTERS), segment(365, 90, PARAMS_NEVER_ENTERS)),))
    _failed(
        result,
        "window_0:in_sample:profit_factor_undefined_zero_gross_loss",
        "window_0:out_of_sample:profit_factor_undefined_zero_gross_loss",
    )
    assert not any("sharpe" in code for code in result.verdict_reason_codes)


# --- exact metric arithmetic (module-level math on equity-unit paths) ---------------------------------------------------


def _figures(units: list[int]):
    return metrics_module._segment_figures(units, metric_policy())


def test_sharpe_matches_the_closed_form_on_a_known_fixture() -> None:
    figures, codes = _figures([100, 130, 117])  # daily returns +0.3 and -0.1
    assert codes == ()
    with localcontext() as context:
        context.prec = 200
        # mean 0.1, sample variance 0.08: annualized = sqrt(0.1**2 * 365 / 0.08) = sqrt(45.625)
        assert figures.annualized_sharpe == _text(Decimal("45.625").sqrt())
    assert (figures.hit_rate, figures.expectancy, figures.max_drawdown, figures.profit_factor) == (
        "0.500000000000000000",
        "0.100000000000000000",
        "0.100000000000000000",
        "3.000000000000000000",
    )


def test_sample_variance_uses_n_minus_1_not_n() -> None:
    figures, _ = _figures([100, 130, 117])
    with localcontext() as context:
        context.prec = 200
        population = _text(Decimal("91.25").sqrt())  # the n-denominator variance 0.04 would give sqrt(91.25)
        assert figures.annualized_sharpe != population
        assert figures.annualized_sharpe == _text(Decimal("45.625").sqrt())


def test_annualization_is_sqrt_365_of_the_daily_sharpe_and_reads_the_policy_factor() -> None:
    figures, _ = _figures([100, 130, 117])
    with localcontext() as context:
        context.prec = 200
        daily = Decimal("0.1") / Decimal("0.08").sqrt()
        assert figures.annualized_sharpe == _text(daily * Decimal(365).sqrt())
    altered = replace(metric_policy(), sharpe_annualization_factor=252)
    other, _ = metrics_module._segment_figures([100, 130, 117], altered)
    assert other.annualized_sharpe != figures.annualized_sharpe


def test_the_risk_free_return_is_exactly_zero_and_read_from_the_policy() -> None:
    assert metric_policy().risk_free_daily_return == "0.000000000000000000"
    base, _ = _figures([100, 130, 117])
    shifted, _ = metrics_module._segment_figures(
        [100, 130, 117], replace(metric_policy(), risk_free_daily_return="0.050000000000000000")
    )
    with localcontext() as context:
        context.prec = 200
        assert shifted.annualized_sharpe == _text(Decimal("0.05") / Decimal("0.08").sqrt() * Decimal(365).sqrt())
    assert shifted.annualized_sharpe != base.annualized_sharpe
    assert shifted.expectancy == base.expectancy  # expectancy is the raw mean, never an excess return


def test_all_zero_returns_have_zero_variance_zero_mean_and_zero_sharpe() -> None:
    sharpe, code = metrics_module._annualized_sharpe(
        total=0, squares=0, count=3, product=100, risk_free=(0, 10**18), factor=365, numeric=NUMERIC
    )
    assert (sharpe, code) == ("0.000000000000000000", None)
    figures, codes = _figures([100, 100, 100, 100])
    assert figures is None and codes == ("profit_factor_undefined_zero_gross_loss",)


def test_constant_nonzero_returns_fail_closed_without_epsilon() -> None:
    figures, codes = _figures([1000, 900, 810, 729])  # three returns of exactly -0.1
    assert figures is None and codes == ("sharpe_undefined_zero_variance_nonzero_mean",)


def test_fewer_than_two_daily_returns_fail_closed() -> None:
    assert _figures([100, 110]) == (None, ("daily_return_count_insufficient",))
    assert _figures([100]) == (None, ("daily_return_count_insufficient",))


@pytest.mark.parametrize("units", [[100, 0, 50], [100, -5, 10], [0, 10, 20], [100, 110, -1]])
def test_a_nonpositive_equity_fails_closed(units: list[int]) -> None:
    assert _figures(units) == (None, ("equity_nonpositive",))


def test_an_undefined_profit_factor_denominator_fails_closed_and_never_fabricates_infinity() -> None:
    assert _figures([100, 110, 120, 130]) == (None, ("profit_factor_undefined_zero_gross_loss",))
    figures, codes = _figures([100, 90, 81, 90])  # gains 1/9, losses 0.2
    assert codes == ()
    assert figures.profit_factor == _fraction_text(Fraction(1, 9) / Fraction(2, 10))


def test_hit_rate_counts_only_strictly_positive_returns() -> None:
    figures, _ = _figures([100, 110, 110, 99, 99, 108])
    assert (figures.positive_daily_return_count, figures.negative_daily_return_count) == (2, 1)
    assert figures.zero_daily_return_count == 2
    assert figures.hit_rate == "0.400000000000000000"


def test_max_drawdown_uses_the_exact_running_peak_including_the_start() -> None:
    figures, _ = _figures([100, 80, 120, 90, 130, 104])
    assert figures.max_drawdown == "0.250000000000000000"  # peak 120 -> 90
    figures, _ = _figures([100, 110, 121, 90])
    assert figures.max_drawdown == _fraction_text(Fraction(31, 121))


def test_a_metric_outside_the_representation_fails_closed() -> None:
    figures, codes = _figures([1, 10**45, 10**45 - 1])
    assert figures is None
    assert set(codes) == {"metric_out_of_representation:expectancy", "metric_out_of_representation:profit_factor"}


def test_rendering_bounds_magnitude_before_text_conversion() -> None:
    assert metrics_module._units_text(False, 10**5000, NUMERIC) is None
    assert metrics_module._render_ratio(10**6000, 1, NUMERIC) is None
    assert metrics_module._render_ratio(-1, 10**30, NUMERIC) == "0.000000000000000000"


@pytest.mark.parametrize(
    ("numerator", "denominator", "expected"),
    [
        (2, 1, "1.414213562373095049"),
        (9, 4, "1.500000000000000000"),
        (1, 4 * 10**36, "0.000000000000000000"),  # sqrt = 0.5e-18: tie to even 0
        (9, 4 * 10**36, "0.000000000000000002"),  # sqrt = 1.5e-18: tie to even 2
        (25, 4 * 10**36, "0.000000000000000002"),  # sqrt = 2.5e-18: tie to even 2
        (0, 7, "0.000000000000000000"),
    ],
)
def test_the_square_root_is_exact_round_half_even(numerator: int, denominator: int, expected: str) -> None:
    assert metrics_module._render_signed_sqrt(False, numerator, denominator, NUMERIC) == expected


def test_a_negative_sharpe_is_rendered_with_its_sign_and_zero_is_never_negative() -> None:
    figures, _ = _figures([100, 90, 72])  # returns -0.1 and -0.2
    assert figures.annualized_sharpe.startswith("-")
    assert metrics_module._render_signed_sqrt(True, 0, 1, NUMERIC) == "0.000000000000000000"
    assert metrics_module._render_ratio(-1, 10**40, NUMERIC) == "0.000000000000000000"


# --- geometry, ordering, identity, consistency --------------------------------------------------------------------------


def test_a_wrong_in_sample_duration_fails() -> None:
    _failed(build((window("wf-1", segment(1, 364), segment(365, 90)),)), "window_0:in_sample:duration_mismatch")


def test_a_wrong_out_of_sample_duration_fails() -> None:
    _failed(build((window("wf-1", segment(0, 365), segment(365, 91)),)), "window_0:out_of_sample:duration_mismatch")


def test_a_nonzero_embargo_fails() -> None:
    _failed(build((window("wf-1", segment(0, 365), segment(366, 90)),)), "window_0:embargo_mismatch")


def test_a_wrong_stride_fails() -> None:
    shifted = window("wf-2", segment(100, 365, PARAMS_B), segment(465, 90, PARAMS_B))
    _failed(build((w1(), shifted)), "window_1:stride_mismatch")


def test_reordered_windows_fail_and_change_the_digest() -> None:
    result = build((w2(), w1()))
    _failed(result, "window_1:order_invalid")
    assert result.result_digest != two_windows().result_digest


def test_a_duplicate_window_identity_fails() -> None:
    duplicate = replace(w2(), window_id="wf-1")
    _failed(build((w1(), duplicate)), "window_1:window_id_duplicate")


def test_non_utc_aligned_segment_boundaries_fail_without_rounding() -> None:
    in_sample = economics_at(S0 + 1, S0 + 365 * DAY + 1)
    out_of_sample = economics_at(S0 + 365 * DAY + 1, S0 + 455 * DAY + 1)
    result = build((window("wf-1", in_sample, out_of_sample),))
    _failed(
        result,
        "window_0:in_sample:boundary_not_utc_day_aligned",
        "window_0:out_of_sample:boundary_not_utc_day_aligned",
    )


def test_a_source_that_did_not_compute_economics_fails() -> None:
    unapproved = segment(365, 90, approved=False)
    assert unapproved.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    result = build((window("wf-1", segment(0, 365), unapproved),))
    _failed(result, "window_0:out_of_sample:economics_not_computed:READY:NEEDS_GOVERNANCE_APPROVAL")


def test_sources_under_different_economics_policies_fail_consistency() -> None:
    result = build((window("wf-1", segment(0, 365), segment(365, 90, fee=d(6))),))
    _failed(result, "source_inconsistent:economics_policy_digest")


def test_structural_violations_are_collected_completely_in_one_pass() -> None:
    result = build(
        (
            window("wf-1", segment(1, 364), segment(366, 90, PARAMS_B)),
            window("wf-1", segment(90, 365), segment(455, 90)),
        )
    )
    _failed(
        result,
        "window_0:in_sample:duration_mismatch",
        "window_0:embargo_mismatch",
        "window_0:assignment_mismatch",
        "window_1:window_id_duplicate",
        "window_1:stride_mismatch",
    )


# --- upstream authority re-proof ----------------------------------------------------------------------------------------


def test_a_tampered_upstream_field_with_a_stale_digest_is_rejected() -> None:
    source = segment(365, 90)
    valuation = replace(source.valuations[5], equity=d(Fraction(source.valuations[5].equity) + 1))
    tampered = replace(source, valuations=(*source.valuations[:5], valuation, *source.valuations[6:]))
    result = build((window("wf-1", segment(0, 365), tampered),))
    _rejected(
        result, "window_0:out_of_sample:source_integrity_failure:historical_execution_economics:self_digest_mismatch"
    )


def test_a_resealed_upstream_field_never_becomes_authority() -> None:
    source = segment(365, 90)
    valuation = replace(source.valuations[5], equity=d(Fraction(source.valuations[5].equity) + 1))
    changed = replace(source, valuations=(*source.valuations[:5], valuation, *source.valuations[6:]))
    resealed = replace(changed, result_digest=historical_execution_economics_digest(changed))
    stale_anchor = HistoricalWalkForwardWindowInput(
        "wf-1", segment(0, 365), segment(0, 365).result_digest, resealed, source.result_digest
    )
    _rejected(
        build((stale_anchor,)),
        "window_0:out_of_sample:source_integrity_failure:historical_execution_economics:field_mismatch:valuations",
    )
    fresh_anchor = replace(stale_anchor, expected_out_of_sample_result_digest=resealed.result_digest)
    result = build((fresh_anchor,))
    _rejected(
        result,
        "window_0:out_of_sample:source_integrity_failure:historical_execution_economics:field_mismatch:valuations",
    )


def test_a_forged_anchor_is_rejected() -> None:
    forged = replace(w1(), expected_in_sample_result_digest="e" * 64)
    _rejected(build((forged,)), "window_0:in_sample:source_digest_mismatch")


def test_a_foreign_correlation_is_rejected() -> None:
    _rejected(build((w1(),), correlation_id="corr-2"), "window_0:in_sample:source_correlation_mismatch")


def test_a_policy_anchor_mismatch_is_rejected() -> None:
    _rejected(build((w1(),), expected_metric_policy_digest="f" * 64), "policy_digest_mismatch")


def test_an_unsupported_policy_identity_is_rejected_even_when_resealed() -> None:
    forged = replace(metric_policy(), out_of_sample_duration_days=30)
    forged = replace(forged, policy_digest=historical_walk_forward_metric_policy_digest(forged))
    result = build((w1(),), metric_policy=forged, expected_metric_policy_digest=forged.policy_digest)
    _rejected(
        result,
        "policy_integrity_failure:historical_walk_forward_metric_policy:field_mismatch:out_of_sample_duration_days",
    )


def test_a_carried_upstream_digest_is_never_trusted_on_verification() -> None:
    base = one_window()
    (binding,) = base.window_bindings
    forged_binding = replace(
        binding,
        in_sample_binding=EdgeAuthorityBinding(binding.in_sample_binding.snapshot_json, "a" * 64),
    )
    forged = _reseal(
        base,
        window_bindings=(forged_binding,),
        source_result_digests=("a" * 64, base.source_result_digests[1]),
    )
    verification = verify_historical_walk_forward_metrics(forged)
    assert verification.intact is False
    assert {_code("field_mismatch:status"), _code("field_mismatch:windows")} <= set(verification.reason_codes)


# --- result tamper resistance -------------------------------------------------------------------------------------------


def test_an_altered_carried_metric_is_rejected_by_the_verifier() -> None:
    base = one_window()
    (metrics,) = base.windows
    segment_metrics = _reseal_record(metrics.in_sample, "segment_digest", hit_rate="0.999999999999999999")
    window_metrics = _reseal_record(metrics, "window_digest", in_sample=segment_metrics)
    forged = _reseal(base, windows=(window_metrics,), window_digests=(window_metrics.window_digest,))
    verification = verify_historical_walk_forward_metrics(forged)
    assert verification.intact is False
    assert _code("field_mismatch:windows") in verification.reason_codes


@pytest.mark.parametrize(
    "change",
    [
        {"source_result_digests": ("b" * 64, "c" * 64)},
        {"window_ids": ("wf-9",)},
        {"window_count": 2},
        {"performance_metrics_computed": False},
        {"computation_verdict": EdgeGateVerdict.FAIL},
        {"status": EdgeEvidenceStatus.REJECTED},
        {"strategy_spec_digest": "c" * 64},
        {"synthetic_test_facts_used": False},
        {"edge_proven": True},
        {"admission_decided": True},
        {"windows": ()},
        {"window_digests": ()},
    ],
)
def test_every_altered_result_field_is_rejected_even_when_resealed(change: dict[str, object]) -> None:
    verification = verify_historical_walk_forward_metrics(_reseal(one_window(), **change))
    assert verification.intact is False
    assert {_code(f"field_mismatch:{name}") for name in change} <= set(verification.reason_codes)


def test_a_tampered_result_with_a_stale_digest_is_detected() -> None:
    verification = verify_historical_walk_forward_metrics(replace(one_window(), result_id="walk-forward-metrics-2"))
    assert verification.intact is False
    assert _code("self_digest_mismatch") in verification.reason_codes


def test_reordered_windows_in_a_result_are_rejected_by_the_verifier() -> None:
    base = two_windows()
    forged = _reseal(
        base,
        window_bindings=tuple(reversed(base.window_bindings)),
        windows=tuple(reversed(base.windows)),
        window_digests=tuple(reversed(base.window_digests)),
        window_ids=tuple(reversed(base.window_ids)),
    )
    verification = verify_historical_walk_forward_metrics(forged)
    assert verification.intact is False


def test_fail_and_rejected_results_re_prove_and_carry_no_metrics() -> None:
    failed = build((window("wf-1", segment(0, 365), segment(366, 90)),))
    undefined = build((window("wf-1", segment(0, 365, PARAMS_NEVER_ENTERS), segment(365, 90, PARAMS_NEVER_ENTERS)),))
    rejected = build((w1(),), correlation_id="corr-2")
    tampered = build((window("wf-1", segment(0, 365), replace(segment(365, 90), result_id="forged")),))
    for result in (failed, undefined, rejected, tampered):
        _assert_receipt_invariants(result)
        assert result.performance_metrics_computed is False and result.windows == ()


# --- construction errors and verifier totality --------------------------------------------------------------------------


class _Hollow:
    pass


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"metric_policy": None}, "policy_malformed"),
        ({"metric_policy": "policy"}, "policy_malformed"),
        ({"metric_policy": replace(mpt.policy(), numeric_policy=_Hollow())}, "policy_not_serializable"),
        ({"expected_metric_policy_digest": "short"}, "policy_expected_digest_invalid"),
        ({"windows": None}, "windows_malformed"),
        ({"windows": "wf-1"}, "windows_malformed"),
        ({"windows": {"wf-1": 1}}, "windows_malformed"),
        ({"windows": ()}, "windows_empty"),
        ({"windows": []}, "windows_empty"),
        ({"windows": (None,)}, "window_malformed"),
        ({"windows": ("wf-1",)}, "window_malformed"),
        ({"result_id": ""}, "result_id_invalid"),
        ({"result_id": "live-metrics"}, "forbidden_scope_token:result_id"),
        ({"correlation_id": " corr"}, "correlation_id_invalid"),
    ],
)
def test_malformed_caller_input_is_a_construction_error(overrides: dict[str, object], code: str) -> None:
    arguments = {"windows": (w1(),), **overrides}
    windows = arguments.pop("windows")
    with pytest.raises(HistoricalWalkForwardMetricsError) as raised:
        build(windows, **arguments)
    assert str(raised.value) == _code(code)


def test_a_generator_of_windows_is_refused() -> None:
    with pytest.raises(HistoricalWalkForwardMetricsError) as raised:
        build(item for item in (w1(),))
    assert str(raised.value) == _code("windows_malformed")


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"window_id": ""}, "window_id_invalid"),
        ({"window_id": "bist-window"}, "bist_scope_leakage:window_id"),
        ({"window_id": "order_router-1"}, "forbidden_scope_token:window_id"),
        ({"in_sample_economics": None}, "in_sample_economics_malformed"),
        ({"out_of_sample_economics": "economics"}, "out_of_sample_economics_malformed"),
        ({"expected_in_sample_result_digest": "x"}, "in_sample_expected_digest_invalid"),
        ({"expected_out_of_sample_result_digest": None}, "out_of_sample_expected_digest_invalid"),
    ],
)
def test_malformed_window_input_is_a_construction_error(change: dict[str, object], code: str) -> None:
    with pytest.raises(HistoricalWalkForwardMetricsError) as raised:
        build((replace(w1(), **change),))
    assert str(raised.value) == _code(code)


def test_a_hollow_upstream_object_is_a_construction_error() -> None:
    hollow = replace(segment(365, 90), valuations=(_Hollow(),))
    with pytest.raises(HistoricalWalkForwardMetricsError) as raised:
        build((replace(w1(), out_of_sample_economics=hollow),))
    assert str(raised.value) == _code("out_of_sample_not_serializable")


def _corrupted(**changes: object) -> HistoricalWalkForwardMetricsResult:
    return replace(one_window(), **changes)


@pytest.mark.parametrize(
    "artifact",
    [
        None,
        0,
        "result",
        {"result_id": "x"},
        object(),
        _Hollow(),
        pytest.param("corrupt_policy_binding", id="policy-binding-not-a-binding"),
        pytest.param("corrupt_window_bindings", id="window-bindings-list-of-strings"),
        pytest.param("empty_window_bindings", id="window-bindings-empty"),
        pytest.param("window_binding_wrong_snapshot", id="window-binding-policy-snapshot"),
        pytest.param("bad_numeric_text", id="metric-text-non-canonical"),
        pytest.param("negative_wire_int", id="negative-window-count"),
        pytest.param("huge_wire_int", id="window-count-above-int64"),
        pytest.param("bool_as_int", id="window-count-bool"),
    ],
)
def test_public_verifier_is_total_for_any_object(artifact: object) -> None:
    base = one_window()
    (metrics,) = base.windows
    corruptions = {
        "corrupt_policy_binding": lambda: _corrupted(policy_binding="binding"),
        "corrupt_window_bindings": lambda: _corrupted(window_bindings=("wf-1",)),
        "empty_window_bindings": lambda: _reseal(base, window_bindings=()),
        "window_binding_wrong_snapshot": lambda: _corrupted(
            window_bindings=(
                HistoricalWalkForwardWindowBinding(
                    "wf-1", base.policy_binding, base.window_bindings[0].out_of_sample_binding
                ),
            )
        ),
        "bad_numeric_text": lambda: _reseal(
            base,
            windows=(replace(metrics, in_sample=replace(metrics.in_sample, hit_rate="0.5")),),
        ),
        "negative_wire_int": lambda: _reseal(base, window_count=-1),
        "huge_wire_int": lambda: _reseal(base, window_count=2**63),
        "bool_as_int": lambda: _reseal(base, window_count=True),
    }
    subject = corruptions[artifact]() if isinstance(artifact, str) and artifact in corruptions else artifact
    verification = verify_historical_walk_forward_metrics(subject)
    assert verification.intact is False
    assert verification.reason_codes


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        "payload",
    ],
)
def test_strict_parser_refuses_malformed_payloads(payload: object) -> None:
    assert historical_walk_forward_metrics_payload_is_well_formed(payload) is False


def test_strict_parser_refuses_changed_payload_shapes() -> None:
    payload = historical_walk_forward_metrics_to_dict(one_window())
    for change in (
        {"unexpected": 1},
        {"window_count": "1"},
        {"windows": "none"},
        {"window_bindings": [{"window_id": "wf-1"}]},
        {"computation_verdict": "MAYBE"},
        {"performance_metrics_computed": 1},
    ):
        assert historical_walk_forward_metrics_payload_is_well_formed({**payload, **change}) is False
    missing = dict(payload)
    del missing["windows"]
    assert historical_walk_forward_metrics_payload_is_well_formed(missing) is False


# --- non-claims and scope -----------------------------------------------------------------------------------------------


def test_performance_metrics_computed_is_true_only_for_a_computed_result() -> None:
    assert one_window().performance_metrics_computed is True
    assert build((window("wf-1", segment(0, 365), segment(366, 90)),)).performance_metrics_computed is False
    assert build((w1(),), correlation_id="corr-2").performance_metrics_computed is False


def test_every_non_claim_flag_holds_and_no_authority_is_granted() -> None:
    result = one_window()
    names = {name for name, _ in HISTORICAL_WALK_FORWARD_METRICS_NON_CLAIM_FLAGS}
    required = {
        "edge_proven",
        "profitability_proven",
        "candidate_admitted_to_paper",
        "pbo_passed",
        "stress_passed",
        "operational_readiness",
        "live_ready",
        "shadow_ready",
        "deribit_ready",
        "private_api_ready",
        "live_api_called",
        "connector_invoked",
        "real_orders_enabled",
        "real_money_enabled",
        "real_capital_reserved",
        "scheduler_enabled",
        "auto_loop_enabled",
        "venue_fill_truth_proven",
        "external_archive_truth_proven",
        "admission_decided",
        "stage_advanced",
    }
    assert required <= names
    for name in required:
        assert getattr(result, name) is False, name
    assert result.paper_only is True
    structural = {name for name, _ in EDGE_STRUCTURAL_NON_CLAIM_FLAGS}
    assert structural - names == {"performance_data_consumed", "oos_evidence_consumed"}
    payload = historical_walk_forward_metrics_to_dict(result)
    for forbidden in ("supportive", "admitted", "pbo", "stress_result", "ranking", "allocation", "ready_for"):
        assert not [key for key in payload if forbidden in key and key not in names]


def test_upstream_flags_are_never_mutated() -> None:
    source = segment(0, 365)
    one_window()
    assert source.performance_metrics_computed is False and source.edge_proven is False


def _module_trees() -> list[tuple[str, ast.Module]]:
    import crypto_core.validation.historical_walk_forward_metric_policy as policy_module

    return [
        (module.__file__, ast.parse(Path(module.__file__).read_text(encoding="utf-8")))  # type: ignore[arg-type]
        for module in (metrics_module, policy_module)
    ]


def test_new_production_modules_hold_no_float_or_decimal_authority() -> None:
    for _, tree in _module_trees():
        assert not [node for node in ast.walk(tree) if isinstance(node, ast.Constant) and type(node.value) is float]
        imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        imported |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
        assert "decimal" not in imported
        assert not [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"float", "repr"}
        ]


def test_new_production_modules_have_no_hidden_io_clock_randomness_or_concurrency() -> None:
    allowed_stdlib = {"__future__", "collections", "dataclasses", "enum", "math"}
    forbidden_calls = {"open", "eval", "exec", "compile", "input", "__import__"}
    for path, tree in _module_trees():
        roots = {
            alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
        }
        roots |= {
            node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
        }
        assert roots <= allowed_stdlib | {"crypto_core"}, (path, roots)
        assert not [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in forbidden_calls
        ]


def test_new_production_modules_import_only_the_accepted_upstream_authorities() -> None:
    allowed = {
        "crypto_core.validation.edge_artifact_core",
        "crypto_core.validation.historical_execution_economics",
        "crypto_core.validation.historical_execution_economics_policy",
        "crypto_core.validation.historical_walk_forward_metric_policy",
    }
    for path, tree in _module_trees():
        imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module} | {
            alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
        }
        crypto = {name for name in imported if name.startswith("crypto_core")}
        assert crypto <= allowed, (path, crypto)
        text = Path(path).read_text(encoding="utf-8")
        for token in (
            "bist_core",
            "pbo",
            "stress_testing",
            "paper_admission",
            "walk_forward import",
            "service",
            "venue.",
        ):
            assert not [line for line in text.splitlines() if line.startswith(("import", "from")) and token in line]


# --- record-set completeness of the daily endpoints (defense in depth behind the upstream verifier) ---------------------


def _with_valuations(source: HistoricalExecutionEconomicsResult, valuations) -> HistoricalExecutionEconomicsResult:
    return replace(source, valuations=tuple(valuations))


def _endpoint_code(valuations) -> str | None:
    source = segment(365, 90)
    endpoints, code = metrics_module._daily_endpoints(_with_valuations(source, valuations), metric_policy())
    assert (endpoints is None) is (code is not None)
    return code


def test_the_authenticated_ledger_yields_exactly_one_endpoint_per_utc_day() -> None:
    source = segment(365, 90)
    endpoints, code = metrics_module._daily_endpoints(source, metric_policy())
    assert code is None and len(endpoints) == 91
    assert [item.time_ns for item in endpoints] == [S0 + (365 + k) * DAY for k in range(91)]


def test_a_missing_or_duplicated_day_boundary_is_refused() -> None:
    valuations = list(segment(365, 90).valuations)
    boundaries = [index for index, item in enumerate(valuations) if item.valuation_kind is KIND.UTC_DAY_BOUNDARY]
    missing = [item for index, item in enumerate(valuations) if index != boundaries[3]]
    assert _endpoint_code(missing) == "daily_endpoint_boundary_set_invalid"
    duplicated = [*valuations[: boundaries[3] + 1], valuations[boundaries[3]], *valuations[boundaries[3] + 1 :]]
    assert _endpoint_code(duplicated) == "daily_endpoint_boundary_set_invalid"
    shifted = list(valuations)
    shifted[boundaries[3]] = replace(valuations[boundaries[3]], time_ns=valuations[boundaries[3]].time_ns + 1)
    assert _endpoint_code(shifted) == "daily_endpoint_boundary_set_invalid"


def test_misplaced_or_repeated_initial_and_end_valuations_are_refused() -> None:
    valuations = list(segment(365, 90).valuations)
    assert _endpoint_code([]) == "daily_endpoint_order_invalid"
    assert _endpoint_code([*valuations, valuations[1]]) == "daily_endpoint_order_invalid"
    assert _endpoint_code([valuations[1], *valuations]) == "daily_endpoint_order_invalid"
    assert _endpoint_code([valuations[0], valuations[0], *valuations[1:]]) == "daily_endpoint_start_invalid"
    assert _endpoint_code([replace(valuations[0], time_ns=valuations[0].time_ns + 1), *valuations[1:]]) == (
        "daily_endpoint_start_invalid"
    )
    assert _endpoint_code([*valuations[:-1], valuations[-1], valuations[-1]]) == "daily_endpoint_end_invalid"
    assert _endpoint_code([*valuations[:-1], replace(valuations[-1], time_ns=valuations[-1].time_ns - 1)]) == (
        "daily_endpoint_end_invalid"
    )


@pytest.mark.parametrize(
    "text",
    ["1.5", "10000", "-0.000000000000000000", "+1.000000000000000000", "1e3", "9" * 43 + "." + "0" * 18, None, 7],
)
def test_a_non_canonical_equity_text_is_refused(text: object) -> None:
    assert metrics_module._equity_units(text) is None
    source = segment(365, 90)
    endpoints, _ = metrics_module._daily_endpoints(source, metric_policy())
    index = source.valuations.index(endpoints[4])
    forged = replace(source.valuations[index], equity=text)
    tampered = _with_valuations(source, [*source.valuations[:index], forged, *source.valuations[index + 1 :]])
    segment_metrics, codes = metrics_module._segment_metrics(OOS, tampered, metric_policy())
    assert segment_metrics is None and codes == ["equity_noncanonical"]


def test_canonical_equity_text_converts_to_exact_scale_units() -> None:
    assert metrics_module._equity_units("10000.000000000000000001") == 10_000 * 10**18 + 1
    assert metrics_module._equity_units("-0.500000000000000000") == -(5 * 10**17)
