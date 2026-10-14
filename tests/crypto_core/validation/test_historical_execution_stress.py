"""Tests for the Stage-3 synthetic stress extension of the accepted economics engine (STRESS_PIT_TRANSFORM_V1).

Fixtures are the economics test module's REAL authenticated worlds (decision run, PIT dataset, policy and approval).
Every scenario value below is a SYNTHETIC TEST VALUE; the engine defines the transformations, a governed policy owns
the values. The stressed run is a modeled scenario, never an authenticated market event, and the historical simulation
itself is unchanged.
"""

from __future__ import annotations

import functools
import json
from dataclasses import replace
from fractions import Fraction

import pytest

import crypto_core.validation.historical_execution_economics as economics_module
from crypto_core.validation.edge_artifact_core import edge_canonical_json, edge_sha256_text
from crypto_core.validation.historical_execution_economics import (
    HistoricalExecutionEconomicsError,
    HistoricalExecutionStressOutcome,
    HistoricalExecutionStressScenario,
    HistoricalExecutionStressScenarioKind,
    HistoricalExecutionValuationKind,
    canonical_historical_execution_stress_scenario,
    historical_execution_stress_outcome_digest,
    historical_execution_stress_outcome_to_dict,
    historical_execution_stress_scenario_digest,
    simulate_historical_execution_stress,
)

try:  # the module object pytest collects (basename import), so its cached worlds are shared
    import test_historical_execution_economics as econ
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_historical_execution_economics as econ

d = econ.d
KIND = HistoricalExecutionStressScenarioKind
ZERO, ONE = d(0), d(1)


def scenario(kind: KIND, **changes: object) -> HistoricalExecutionStressScenario:
    values: dict[str, object] = {
        "scenario_kind": kind,
        "return_multiplier": d("1.5") if kind is KIND.HIGH_VOLATILITY else ONE,
        "slippage_multiplier": d(2),
        "depth_multiplier": ONE if kind is KIND.HIGH_VOLATILITY else d("0.2"),
        "gap_fraction": d("0.1") if kind is KIND.FLASH_CRASH else ZERO,
        "recovery_ns": 3_000 if kind is KIND.FLASH_CRASH else 0,
        "maintenance_margin_fraction": d("0.005") if kind is KIND.FLASH_CRASH else ZERO,
    }
    values.update(changes)
    return HistoricalExecutionStressScenario(**values)  # type: ignore[arg-type]


@functools.cache
def anchored_result():
    """The default world plus one mark visible just before the evaluation start (the HIGH_VOLATILITY anchor)."""

    records = econ.market_records(extra_marks=((econ.BASE - 3, 1, econ.default_mark(0)),))
    return econ.economics(econ.world(records=records))


def stress(result, value: HistoricalExecutionStressScenario) -> HistoricalExecutionStressOutcome:
    return simulate_historical_execution_stress(result, expected_result_digest=result.result_digest, scenario=value)


def _endpoints(result) -> tuple[str, ...]:
    kinds = {
        HistoricalExecutionValuationKind.INITIAL,
        HistoricalExecutionValuationKind.UTC_DAY_BOUNDARY,
        HistoricalExecutionValuationKind.EVALUATION_END,
    }
    return tuple(item.equity for item in result.valuations if item.valuation_kind in kinds)


def _simulation(result, value: HistoricalExecutionStressScenario, *, shock: int | None = None, sign: int = 0):
    """The stressed simulation object itself, so the exact transformed observations can be inspected."""

    _, run = economics_module._run_authority(result.run_binding, correlation_id=result.correlation_id)
    _, policy = economics_module._policy_authority(result.policy_binding)
    context = economics_module._run_context(run)[1]
    anchor = None
    if value.scenario_kind is KIND.HIGH_VOLATILITY:
        anchor = economics_module._stress_anchor(context.dataset, run, result.mark_series_id, policy)
    gap = Fraction(value.gap_fraction)
    return economics_module._StressSimulation(
        scenario=value,
        anchor=anchor,
        shock_time_ns=shock,
        shock_factor=1 - gap if sign > 0 else 1 + gap,
        run=run,
        run_digest=result.run_digest,
        dataset=context.dataset,
        policy=policy,
        unit_size=economics_module._unit_size(run),
        max_leverage=economics_module._max_leverage(context.spec)[0],
        mark_series=result.mark_series_id,
        book_series=result.order_book_series_id,
    )


# --- identity, determinism and the record ---------------------------------------------------------------------------------


def test_a_neutral_scenario_reproduces_the_accepted_engine_endpoints_exactly() -> None:
    baseline = econ.default_result()
    outcome = stress(baseline, scenario(KIND.LOW_LIQUIDITY, slippage_multiplier=ONE, depth_multiplier=ONE))
    assert outcome.simulated is True and outcome.reason_codes == ()
    assert outcome.daily_endpoint_equities == _endpoints(baseline)
    assert outcome.daily_endpoint_digest == edge_sha256_text(edge_canonical_json(list(_endpoints(baseline))))
    neutral = _simulation(baseline, scenario(KIND.LOW_LIQUIDITY, slippage_multiplier=ONE, depth_multiplier=ONE))
    assert [item.equity for item in neutral.run_all().valuations] == [item.equity for item in baseline.valuations]


def test_the_historical_simulation_hooks_are_identities() -> None:
    simulation = economics_module._Simulation.__new__(economics_module._Simulation)
    book = object()
    assert economics_module._Simulation._observed_book(simulation, book) is book  # type: ignore[arg-type]
    assert economics_module._Simulation._effective_slippage(simulation, Fraction(7, 3), book) == Fraction(7, 3)  # type: ignore[arg-type]
    marks, books = object(), [book]
    assert economics_module._Simulation._transformed_marks(simulation, marks) is marks  # type: ignore[arg-type]
    assert economics_module._Simulation._transformed_books(simulation, books) is books  # type: ignore[arg-type]


def test_stress_is_deterministic_and_digest_bound() -> None:
    baseline = econ.default_result()
    value = scenario(KIND.HIGH_VOLATILITY)
    first, second = stress(baseline, value), stress(baseline, value)
    assert historical_execution_stress_outcome_to_dict(first) == historical_execution_stress_outcome_to_dict(second)
    assert first.outcome_digest == historical_execution_stress_outcome_digest(first)
    assert first.scenario_digest == historical_execution_stress_scenario_digest(value)
    assert (first.baseline_result_digest, first.stress_method_id) == (baseline.result_digest, "STRESS_PIT_TRANSFORM_V1")
    flags = {name: getattr(first, name) for name in ("authenticated_market_event", "venue_liquidation_modeled")}
    assert flags == {"authenticated_market_event": False, "venue_liquidation_modeled": False}
    assert (first.stress_passed, first.live_ready, first.paper_only) == (False, False, True)
    json.loads(edge_canonical_json(historical_execution_stress_outcome_to_dict(first)))


# --- HIGH_VOLATILITY -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Fraction(4), Fraction(2)),
        (Fraction(1), Fraction(1)),
        (Fraction(2), Fraction("1.414213562373095049")),
        (Fraction(1, 4 * 10**36), Fraction(0)),  # sqrt = 0.5 ulp exactly: the tie rounds to the even 0
        (Fraction(9, 4 * 10**36), Fraction(2, 10**18)),  # sqrt = 1.5 ulp exactly: the tie rounds to the even 2
    ],
)
def test_the_volatility_factor_is_one_exact_half_even_scale18_square_root(value: Fraction, expected: Fraction) -> None:
    assert economics_module._scaled_sqrt(value) == expected


def test_high_volatility_multiplies_log_deviations_from_the_anchor_by_three_halves() -> None:
    baseline = anchored_result()
    assert baseline.simulated_economics_computed is True
    simulation = _simulation(baseline, scenario(KIND.HIGH_VOLATILITY))
    plain = _simulation(baseline, scenario(KIND.LOW_LIQUIDITY, slippage_multiplier=ONE, depth_multiplier=ONE))
    anchor = simulation.marks._marks[0].price / economics_module._scaled_sqrt(Fraction(1))
    assert anchor == econ.price(0)
    outcome = stress(baseline, scenario(KIND.HIGH_VOLATILITY))
    assert outcome.simulated is True and outcome.anchor_mark_price == d(econ.price(0))
    for stressed, original in zip(simulation.marks._marks, plain.marks._marks, strict=True):
        factor = economics_module._scaled_sqrt(original.price / anchor)
        assert stressed.price == original.price * factor
        # p' = p * sqrt(p / m0) is m0 * (p / m0)^(3/2) up to the one scale-18 rendering of the factor.
        assert abs(stressed.price**2 * anchor - original.price**3) <= original.price**2 * anchor / 10**16
    for stressed, original in zip(simulation.books, plain.books, strict=True):
        factor = economics_module._scaled_sqrt((original.bid + original.ask) / 2 / anchor)
        assert (stressed.bid, stressed.ask) == (original.bid * factor, original.ask * factor)
        assert (stressed.bid_quantity, stressed.ask_quantity) == (original.bid_quantity, original.ask_quantity)
        assert (stressed.ask - stressed.bid) / (stressed.ask + stressed.bid) == (original.ask - original.bid) / (
            original.ask + original.bid
        )


def test_high_volatility_without_an_anchor_mark_is_not_simulated() -> None:
    baseline = econ.default_result()  # its first mark becomes visible one nanosecond after the evaluation start
    assert baseline.simulated_economics_computed is True
    outcome = stress(baseline, scenario(KIND.HIGH_VOLATILITY))
    assert outcome.simulated is False
    assert outcome.reason_codes == ("historical_execution_economics:stress_anchor_mark_unavailable",)
    assert outcome.daily_endpoint_equities == ()


# --- LOW_LIQUIDITY and the slippage multiplier ----------------------------------------------------------------------------


def test_low_liquidity_truncates_visible_depth_on_the_quantity_grid_and_keeps_prices() -> None:
    baseline = econ.default_result()
    value = scenario(KIND.LOW_LIQUIDITY, depth_multiplier=d("0.333333333333333333"))
    simulation = _simulation(baseline, value)
    plain = _simulation(baseline, scenario(KIND.LOW_LIQUIDITY, slippage_multiplier=ONE, depth_multiplier=ONE))
    for stressed, original in zip(simulation.books, plain.books, strict=True):
        expected = Fraction(int(original.ask_quantity * Fraction(value.depth_multiplier) * 10**18), 10**18)
        assert stressed.ask_quantity == expected <= original.ask_quantity * Fraction(value.depth_multiplier)
        assert (stressed.bid, stressed.ask) == (original.bid, original.ask)


@pytest.mark.parametrize("multiplier", ["2", "3.5"])
def test_the_slippage_multiplier_scales_the_effective_slippage_on_every_fill(multiplier: str) -> None:
    baseline = econ.default_result()
    value = scenario(KIND.LOW_LIQUIDITY, slippage_multiplier=d(multiplier), depth_multiplier=ONE)
    stressed = [item for item in _simulation(baseline, value).run_all().fills if item.effective_slippage_bps]
    original = [item for item in baseline.fills if item.effective_slippage_bps]
    assert len(stressed) == len(original) > 0
    for left, right in zip(stressed, original, strict=True):
        expected = Fraction(right.effective_slippage_bps) * Fraction(multiplier)
        assert abs(Fraction(left.effective_slippage_bps) - expected) <= Fraction(4, 10**18)
        assert (left.half_spread_bps, left.impact_bps, left.filled_quantity) == (
            right.half_spread_bps,
            right.impact_bps,
            right.filled_quantity,
        )


# --- FLASH_CRASH -------------------------------------------------------------------------------------------------------------


def _exposed_boundaries(result) -> list:
    return [
        item
        for item in result.valuations
        if item.valuation_kind is HistoricalExecutionValuationKind.UTC_DAY_BOUNDARY and Fraction(item.position_quantity)
    ]


def test_flash_crash_shocks_the_maximal_leverage_day_boundary_against_the_position() -> None:
    baseline = econ.default_result()
    exposed = _exposed_boundaries(baseline)
    assert exposed, "the default world must be exposed at its day boundary"
    outcome = stress(baseline, scenario(KIND.FLASH_CRASH))
    leverage = [
        abs(Fraction(item.position_quantity)) * Fraction(item.mark_price) / Fraction(item.equity) for item in exposed
    ]
    chosen = exposed[leverage.index(max(leverage))]
    assert outcome.shock_time_ns == chosen.time_ns
    expected = "PRICE_DOWN_AGAINST_LONG" if Fraction(chosen.position_quantity) > 0 else "PRICE_UP_AGAINST_SHORT"
    assert outcome.shock_direction == expected
    assert outcome.maintenance_breached is False and outcome.simulated is True
    # The shocked day-boundary equity is below the baseline: the gap always moves against the held position.
    endpoints = _endpoints(baseline)
    assert len(endpoints) == len(outcome.daily_endpoint_equities) == 3  # initial, the one day boundary, end
    assert Fraction(outcome.daily_endpoint_equities[1]) < Fraction(chosen.equity) == Fraction(endpoints[1])
    assert outcome.daily_endpoint_equities[0] == endpoints[0]


def test_flash_crash_without_exposure_is_the_baseline() -> None:
    baseline = econ.economics(econ.world(parameters=econ.prof.params(entry="0.010000000000000000")))
    assert not _exposed_boundaries(baseline)
    outcome = stress(baseline, scenario(KIND.FLASH_CRASH))
    assert (outcome.shock_time_ns, outcome.shock_direction) == (None, "NONE")
    assert outcome.daily_endpoint_equities == _endpoints(baseline)


def test_a_maintenance_zone_breach_is_recorded_and_no_liquidation_is_executed() -> None:
    policy = econ.polt.cited_policy(initial_equity=d(105))
    baseline = econ.economics(policy=policy)
    assert baseline.simulated_economics_computed is True
    assert _exposed_boundaries(baseline)
    safe = stress(baseline, scenario(KIND.FLASH_CRASH, maintenance_margin_fraction=d("0.5")))
    breached = stress(baseline, scenario(KIND.FLASH_CRASH, maintenance_margin_fraction=d("0.9")))
    assert safe.maintenance_breached is False
    assert breached.maintenance_breached is True and breached.first_breach_time_ns == breached.shock_time_ns
    # Recording a breach executes nothing: the stressed run's fills are those of the run without a breach.
    assert breached.closed_trade_count == safe.closed_trade_count
    assert breached.daily_endpoint_equities == safe.daily_endpoint_equities


# --- validation ----------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "code"),
    [
        (object(), "stress_scenario_malformed"),
        (scenario(KIND.LOW_LIQUIDITY, scenario_kind="LOW_LIQUIDITY"), "stress_scenario_malformed:scenario_kind"),
        (scenario(KIND.LOW_LIQUIDITY, slippage_multiplier=2.0), "stress_scenario_malformed:slippage_multiplier"),
        (scenario(KIND.LOW_LIQUIDITY, recovery_ns=-1), "stress_scenario_malformed:recovery_ns"),
        (scenario(KIND.HIGH_VOLATILITY, return_multiplier=d(2)), "stress_scenario_invalid:return_multiplier"),
        (scenario(KIND.LOW_LIQUIDITY, return_multiplier=d("1.5")), "stress_scenario_invalid:return_multiplier"),
        (scenario(KIND.LOW_LIQUIDITY, slippage_multiplier=d("0.9")), "stress_scenario_invalid:slippage_multiplier"),
        (scenario(KIND.LOW_LIQUIDITY, depth_multiplier=ZERO), "stress_scenario_invalid:depth_multiplier"),
        (scenario(KIND.LOW_LIQUIDITY, depth_multiplier=d("1.1")), "stress_scenario_invalid:depth_multiplier"),
        (scenario(KIND.HIGH_VOLATILITY, depth_multiplier=d("0.5")), "stress_scenario_invalid:depth_multiplier"),
        (scenario(KIND.FLASH_CRASH, gap_fraction=ZERO), "stress_scenario_invalid:gap_fraction"),
        (scenario(KIND.FLASH_CRASH, gap_fraction=ONE), "stress_scenario_invalid:gap_fraction"),
        (scenario(KIND.LOW_LIQUIDITY, gap_fraction=d("0.1")), "stress_scenario_invalid:gap_fraction"),
        (scenario(KIND.FLASH_CRASH, recovery_ns=0), "stress_scenario_invalid:recovery_ns"),
        (
            scenario(KIND.FLASH_CRASH, maintenance_margin_fraction=ONE),
            "stress_scenario_invalid:maintenance_margin_fraction",
        ),
        (
            scenario(KIND.LOW_LIQUIDITY, maintenance_margin_fraction=d("0.1")),
            "stress_scenario_invalid:maintenance_margin_fraction",
        ),
    ],
)
def test_malformed_or_inconsistent_scenarios_are_refused(value: object, code: str) -> None:
    with pytest.raises(HistoricalExecutionEconomicsError, match=f"historical_execution_economics:{code}$"):
        canonical_historical_execution_stress_scenario(value)


def test_only_an_authentic_computed_baseline_can_be_stressed() -> None:
    baseline = econ.default_result()
    with pytest.raises(HistoricalExecutionEconomicsError, match="stress_baseline_not_authentic"):
        simulate_historical_execution_stress(
            baseline, expected_result_digest="0" * 64, scenario=scenario(KIND.LOW_LIQUIDITY)
        )
    forged = replace(baseline, result_id="result-forged")
    with pytest.raises(HistoricalExecutionEconomicsError, match="stress_baseline_not_authentic"):
        stress(forged, scenario(KIND.LOW_LIQUIDITY))
    blocked = econ.economics(economics_approval=None)
    with pytest.raises(HistoricalExecutionEconomicsError, match="stress_baseline_not_computed"):
        stress(blocked, scenario(KIND.LOW_LIQUIDITY))
    with pytest.raises(HistoricalExecutionEconomicsError, match="stress_baseline_malformed"):
        simulate_historical_execution_stress(
            object(), expected_result_digest="0" * 64, scenario=scenario(KIND.LOW_LIQUIDITY)
        )  # type: ignore[arg-type]
