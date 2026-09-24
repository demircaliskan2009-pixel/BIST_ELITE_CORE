"""Tests for deterministic historical execution economics (DETERMINISTIC_HISTORICAL_EXECUTION_ECONOMICS_V2)."""

from __future__ import annotations

import ast
import decimal
import functools
import json
from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from fractions import Fraction
from pathlib import Path

import pytest

import crypto_core.validation.historical_execution_economics as economics_module
from crypto_core.data.requirements import (
    DataRequirementRegistry,
    data_requirement_registry_digest,
    default_perp_data_requirement_registry,
)
from crypto_core.strategy.source_packet import build_source_packet
from crypto_core.strategy.spec import strategy_spec_digest, validate_strategy_spec
from crypto_core.validation.edge_artifact_core import (
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
)
from crypto_core.validation.edge_idea_intake_evidence import (
    build_edge_idea_intake_evidence,
    build_edge_kill_criteria_policy,
)
from crypto_core.validation.edge_source_packet_evidence import EdgeInputSeries, build_edge_source_packet_evidence
from crypto_core.validation.edge_strategy_spec_admission import build_edge_strategy_spec_admission
from crypto_core.validation.historical_decision_run import HistoricalDecisionRun, historical_decision_run_digest
from crypto_core.validation.historical_execution_economics import (
    HISTORICAL_EXECUTION_NON_CLAIM_FLAGS,
    HistoricalExecutionEconomicsError,
    HistoricalExecutionEconomicsResult,
    HistoricalExecutionFillOutcome,
    HistoricalExecutionSide,
    HistoricalExecutionTradeStatus,
    HistoricalExecutionTransitionKind,
    HistoricalExecutionValuation,
    HistoricalExecutionValuationKind,
    build_historical_execution_economics,
    historical_execution_economics_digest,
    historical_execution_economics_from_payload,
    historical_execution_economics_payload_is_well_formed,
    historical_execution_economics_to_dict,
    verify_historical_execution_economics,
)
from crypto_core.validation.historical_execution_economics_policy import (
    HistoricalExecutionApprovalKind,
    HistoricalExecutionCitationKind,
    HistoricalExecutionEconomicsPolicy,
    HistoricalExecutionFactId,
    build_historical_execution_economics_policy,
    historical_execution_render_amount,
)
from crypto_core.validation.historical_pit_dataset import (
    HistoricalPitDataset,
    HistoricalPitRecord,
    HistoricalPitValue,
    build_historical_pit_dataset,
    build_historical_pit_record,
)
from tests.crypto_core.validation import test_historical_decision_run as runt
from tests.crypto_core.validation import test_historical_execution_economics_policy as polt
from tests.crypto_core.validation import test_historical_pit_dataset as pit
from tests.crypto_core.validation import test_strategy_executable_binding as bind
from tests.crypto_core.validation import test_strategy_executable_profiles as prof

_PREFIX = "historical_execution_economics"
INS = polt.INSTRUMENT
d = polt.d
DAY_NS = 86_400_000_000_000
BASE = DAY_NS * 19_000 - 50_000
INTERVAL = polt.INTERVAL_NS
START = BASE + 1
END = BASE + 8 * INTERVAL + 5_020
ULP = Fraction(1, 10**18)
RATES = (
    "0.000200000000000000",
    "0.000300000000000000",
    "0.000300000000000000",
    "0.000100000000000000",
    "-0.000100000000000000",
    "-0.000300000000000000",
    "-0.000300000000000000",
    "-0.000200000000000000",
    "-0.000200000000000000",
    "-0.000200000000000000",
)
KEYS = ("funding_rate", "mark_price", "order_book")
SERIES_IDS = {"funding_rate": "funding-final", "mark_price": "mark", "order_book": "book"}
Values = dict[str, str]


def price(j: int) -> Fraction:
    return Fraction(100) + Fraction(j, 100)


def flipped(rates: tuple[str, ...] = RATES) -> tuple[str, ...]:
    """The same funding path with every sign flipped: the mirror LONG world of a SHORT fixture."""

    return tuple(rate[1:] if rate.startswith("-") else "-" + rate for rate in rates)


def default_mark(j: int) -> Values | None:
    return {"mark_price": d(price(j))}


def book_with(*, half_spread: object = "0.05", quantity: object = 100) -> Callable[[int], Values | None]:
    def book(j: int) -> Values | None:
        mid = price(j)
        depth = quantity(j) if callable(quantity) else quantity
        return {
            "best_bid_price": d(mid - Fraction(str(half_spread))),
            "best_ask_price": d(mid + Fraction(str(half_spread))),
            "best_bid_quantity": d(depth),
            "best_ask_quantity": d(depth),
        }

    return book


default_book = book_with()


def _record(
    series: str, key: str, seq: int, event: int, values: Values, available: int, finalized: int | None
) -> HistoricalPitRecord:
    return build_historical_pit_record(
        series_id=series,
        data_requirement_key=key,
        instrument=INS,
        sequence_id=seq,
        event_time_ns=event,
        available_at_ns=event + available,
        finalized_at_ns=None if finalized is None else event + finalized,
        revision_vintage_id=None,
        values=tuple(HistoricalPitValue(name, value) for name, value in sorted(values.items())),
    )


def market_records(
    *,
    rates: tuple[str, ...] = RATES,
    mark: Callable[[int], Values | None] = default_mark,
    book: Callable[[int], Values | None] | None = default_book,
    observations: int = 101,
    extra_marks: tuple[tuple[int, int, Values], ...] = (),
    extra_books: tuple[tuple[int, int, Values], ...] = (),
    funding_times: tuple[int, int | None] = (INTERVAL + 10, INTERVAL + 20),
    funding_overrides: dict[int, tuple[int, int | None]] | None = None,
    first_funding_sequence: int = 0,
) -> tuple[HistoricalPitRecord, ...]:
    """Funding every INTERVAL; marks and books every 1000 ns; extras renumbered by time.

    ``funding_times`` and ``funding_overrides`` are ``(available, finalized)`` offsets from the funding window open
    (``event_time``). The default publishes and finalizes a record after its own cycle closes, as
    ``finality=funding_cycle_closed`` requires; a ``None`` finalized offset is a record that never becomes final.
    ``first_funding_sequence`` omits that many LEADING settlements while keeping the retained rows canonical.
    """

    records = [
        _record(
            "funding-final",
            "funding_rate",
            first_funding_sequence + k,
            BASE + (first_funding_sequence + k) * INTERVAL,
            {"funding_rate": rate},
            *(funding_overrides or {}).get(first_funding_sequence + k, funding_times),
        )
        for k, rate in enumerate(rates)
    ]
    marks = [(BASE + j * 1_000, 1, values) for j in range(observations) for values in (mark(j),) if values is not None]
    books = []
    if book is not None:
        books = [(BASE + j * 1_000 + 500, 1, values) for j in range(observations) for values in (book(j),) if values]
    for series, key, rows in (
        ("mark", "mark_price", marks + list(extra_marks)),
        ("book", "order_book", books + list(extra_books)),
    ):
        for seq, (event, available, values) in enumerate(sorted(rows, key=lambda row: row[0])):
            records.append(_record(series, key, seq, event, values, available, available + 1))
    return tuple(records)


def chain(
    *,
    spec_changes: dict[str, object] | None = None,
    revision: dict[str, str] | None = None,
    keys: tuple[str, ...] = KEYS,
    intake_id: str = "intake-1",
):
    packet = build_source_packet(
        packet_id="pkt-1",
        source_type="academic_paper",
        source_reference="doi:10.0/carry",
        source_title="Perpetual funding carry",
        rights_status="own_research",
        edge_hypothesis="Funding pays passive carry.",
        content_digest="c" * 64,
        market_scope_tags=("crypto_perpetuals",),
    )
    kill_policy = build_edge_kill_criteria_policy(
        policy_id="kp-1",
        correlation_id="corr-1",
        kill_criteria=pit.CRITERIA,
        thresholds_approved=True,
        approval_reference="gov-1",
        approval_digest="d" * 64,
    )
    intake = build_edge_idea_intake_evidence(
        packet,
        expected_source_packet_digest=packet.packet_digest,
        intake_id=intake_id,
        correlation_id="corr-1",
        candidate_strategy_id="passive-funding-carry",
        edge_family="funding_basis_carry",
        economic_rationale="Funding pays carry.",
        data_requirement_keys=keys,
        declared_regime_dependence="positive_funding_regime",
        kill_criteria_draft=pit.CRITERIA,
        kill_criteria_policy=kill_policy,
        expected_kill_criteria_policy_digest=kill_policy.policy_digest,
    )
    registry = default_perp_data_requirement_registry()
    series = tuple(
        EdgeInputSeries(
            SERIES_IDS[key],
            key,
            f"archive:{SERIES_IDS[key]}",
            "own_research",
            "note-1",
            "finalized_only",
            (revision or {}).get(key, "immutable_after_finalization"),
            (INS,),
        )
        for key in keys
    )
    manifest = build_edge_source_packet_evidence(
        intake,
        expected_root_intake_digest=intake.intake_digest,
        data_requirement_registry=registry,
        expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
        manifest_id="manifest-1",
        correlation_id="corr-1",
        input_series=series,
    )
    spec = validate_strategy_spec(
        {**pit.SPEC, "market_type": "usdt_perp", "instrument_universe": [INS], **(spec_changes or {})}
    ).spec
    admission = build_edge_strategy_spec_admission(
        manifest,
        expected_predecessor_digest=manifest.source_packet_evidence_digest,
        expected_root_intake_digest=intake.intake_digest,
        strategy_spec=spec,
        expected_strategy_spec_digest=strategy_spec_digest(spec),
        admission_id="admission-1",
        correlation_id="corr-1",
        admitted_kill_criteria=pit.CRITERIA,
        kill_criteria_policy=kill_policy,
        expected_kill_criteria_policy_digest=kill_policy.policy_digest,
    )
    return manifest, admission, registry


@dataclass(frozen=True)
class World:
    run: HistoricalDecisionRun
    dataset: HistoricalPitDataset
    registry: DataRequirementRegistry

    @property
    def registry_digest(self) -> str:
        return data_requirement_registry_digest(self.registry)


def world(
    *,
    records: tuple[HistoricalPitRecord, ...] | None = None,
    spec_changes: dict[str, object] | None = None,
    revision: dict[str, str] | None = None,
    keys: tuple[str, ...] = KEYS,
    parameters=None,
    end: int = END,
    binding_id: str = "binding-1",
    intake_id: str = "intake-1",
    **run_overrides: object,
) -> World:
    manifest, admission, registry = chain(spec_changes=spec_changes, revision=revision, keys=keys, intake_id=intake_id)
    dataset = build_historical_pit_dataset(
        manifest,
        expected_source_manifest_digest=manifest.source_packet_evidence_digest,
        expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
        dataset_id="dataset-1",
        correlation_id="corr-1",
        source_reference="archive:history",
        rights_status="own_research",
        rights_reference="license-1",
        records=market_records() if records is None else records,
    )
    binding = bind.executable_binding(admission, binding_id=binding_id)
    run = runt.decision_run(
        dataset,
        binding,
        instrument=INS,
        evaluation_start_ns=START,
        evaluation_end_ns=end,
        parameter_assignment=prof.params() if parameters is None else parameters,
        **run_overrides,
    )
    return World(run, dataset, registry)


@functools.cache
def default_world() -> World:
    return world()


@functools.cache
def default_policy() -> HistoricalExecutionEconomicsPolicy:
    return polt.cited_policy()


def approval(w: World, policy: HistoricalExecutionEconomicsPolicy, **overrides: object):
    return polt.approval_for(
        policy,
        strategy_spec_digest=w.run.strategy_spec_digest,
        data_requirement_registry_digest=w.registry_digest,
        **overrides,
    )


def economics(
    w: World | None = None,
    *,
    policy: HistoricalExecutionEconomicsPolicy | None = None,
    economics_approval: object = "auto",
    **overrides: object,
) -> HistoricalExecutionEconomicsResult:
    w = default_world() if w is None else w
    policy = default_policy() if policy is None else policy
    arguments: dict[str, object] = {
        "expected_run_digest": w.run.run_digest,
        "economics_policy": policy,
        "expected_economics_policy_digest": policy.policy_digest,
        "economics_approval": approval(w, policy) if economics_approval == "auto" else economics_approval,
        "result_id": "result-1",
        "correlation_id": "corr-1",
    }
    arguments.update(overrides)
    return build_historical_execution_economics(w.run, **arguments)  # type: ignore[arg-type]


@functools.cache
def default_result() -> HistoricalExecutionEconomicsResult:
    return economics()


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _reseal(result: HistoricalExecutionEconomicsResult, **changes: object) -> HistoricalExecutionEconomicsResult:
    changed = replace(result, **changes)
    return replace(changed, result_digest=historical_execution_economics_digest(changed))


def _assert_receipt_invariants(result: HistoricalExecutionEconomicsResult) -> None:
    verification = verify_historical_execution_economics(result)
    assert verification.intact is True, verification.reason_codes
    assert verification.recomputed_digest == result.result_digest
    assert historical_execution_economics_from_payload(json.loads(verification.canonical_json)) == result
    assert historical_execution_economics_payload_is_well_formed(historical_execution_economics_to_dict(result))
    assert result.advances is (
        result.status is EdgeEvidenceStatus.READY and result.gate_verdict is EdgeGateVerdict.PASS
    )
    assert result.simulated_economics_computed is result.advances
    if not result.advances:
        _assert_no_economics(result)
    if result.status is EdgeEvidenceStatus.REJECTED:
        assert result.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
        assert result.integrity_reason_codes
        assert result.verdict_reason_codes == ()
    else:
        assert result.integrity_reason_codes == ()


def _assert_no_economics(result: HistoricalExecutionEconomicsResult) -> None:
    assert (
        result.intents,
        result.fills,
        result.position_transitions,
        result.fee_cashflows,
        result.funding_cashflows,
        result.valuations,
        result.trades,
        result.terminal_state,
    ) == ((), (), (), (), (), (), (), None)


def _blocked(result: HistoricalExecutionEconomicsResult, verdict: EdgeGateVerdict, *codes: str) -> None:
    _assert_receipt_invariants(result)
    assert (result.status, result.gate_verdict) == (EdgeEvidenceStatus.READY, verdict)
    assert {_code(code) for code in codes} <= set(result.verdict_reason_codes), result.verdict_reason_codes
    _assert_no_economics(result)


def _t(result_time: int | None) -> int | None:
    return None if result_time is None else result_time - BASE


def _executed(result: HistoricalExecutionEconomicsResult):
    return [
        fill
        for fill in result.fills
        if fill.outcome in (HistoricalExecutionFillOutcome.FILLED, HistoricalExecutionFillOutcome.PARTIALLY_FILLED)
    ]


def _signed(fill) -> Fraction:
    quantity = Fraction(fill.filled_quantity)
    return quantity if fill.side is HistoricalExecutionSide.BUY else -quantity


# --- happy path: frozen P1 trace executed under the approved policy ----------------------------------------------------


def test_default_result_is_ready_pass_and_re_proves() -> None:
    result = default_result()
    _assert_receipt_invariants(result)
    assert (result.status, result.gate_verdict, result.advances) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.PASS,
        True,
    )
    run = default_world().run
    assert result.run_digest == run.run_digest == historical_decision_run_digest(run)
    assert (result.instrument, result.market_type) == (INS, "usdt_perp")
    assert result.strategy_spec_digest == run.strategy_spec_digest
    assert result.economics_policy_digest == default_policy().policy_digest
    assert (result.mark_series_id, result.order_book_series_id) == ("mark", "book")
    assert result.funding_series_id == run.funding_series_id


def test_intents_follow_only_the_frozen_decision_targets() -> None:
    result = default_result()
    decisions = {item.decision_digest: item for item in default_world().run.decisions}
    assert result.intents
    for intent in result.intents:
        decision = decisions[intent.decision_digest]
        assert intent.decision_time_ns == decision.decision_time_ns
        assert intent.resulting_direction == decision.resulting_direction
        assert intent.earliest_execution_time_ns == decision.decision_time_ns + default_policy().latency_ns
        expected = {"LONG": 1, "SHORT": -1, "FLAT": 0}[decision.resulting_direction]
        assert Fraction(intent.target_quantity) == expected * Fraction(prof._UNIT)
        assert Fraction(intent.delta_quantity) == Fraction(intent.target_quantity) - Fraction(intent.actual_quantity)


def test_fill_prices_follow_the_governed_cost_composition() -> None:
    result = default_result()
    policy = default_policy()
    for fill in _executed(result):
        bid, ask = Fraction(fill.best_bid_price), Fraction(fill.best_ask_price)
        mid = (bid + ask) / 2
        spread_bps = (ask - bid) / mid * 10_000
        depth = Fraction(fill.side_visible_quantity)
        participation = Fraction(fill.filled_quantity) / depth * 100
        impact = Fraction(policy.impact_coefficient_bps_per_participation_pct) * participation
        effective = max(Fraction(policy.slippage_floor_bps), spread_bps / 2 + impact)
        # every quoted field is ONE rendering of its own exact value; the price is composed from the exact values
        assert fill.mid_price == historical_execution_render_amount(mid)
        assert fill.spread_bps == historical_execution_render_amount(spread_bps)
        assert fill.half_spread_bps == historical_execution_render_amount(spread_bps / 2)
        assert fill.participation_pct == historical_execution_render_amount(participation)
        assert fill.impact_bps == historical_execution_render_amount(impact)
        assert fill.effective_slippage_bps == historical_execution_render_amount(effective)
        sign = 1 if fill.side is HistoricalExecutionSide.BUY else -1
        assert fill.fill_price == historical_execution_render_amount(mid * (1 + sign * effective / 10_000))
        assert (Fraction(fill.fill_price) - mid) * sign > 0
        assert Fraction(fill.fill_notional) == Fraction(fill.fill_price) * Fraction(fill.filled_quantity)


def test_slippage_floor_applies_when_spread_and_impact_are_small() -> None:
    fill = _first_fill(book_with(half_spread="0.000001", quantity=10**6))
    policy = default_policy()
    assert Fraction(fill.half_spread_bps) + Fraction(fill.impact_bps) < Fraction(policy.slippage_floor_bps)
    assert fill.effective_slippage_bps == policy.slippage_floor_bps


def test_slippage_units_never_mix_bps_percent_and_fraction() -> None:
    """A 1% spread is 100 bps and 1% participation costs exactly the coefficient in bps."""

    fill = _first_fill(book_with(half_spread="0.5", quantity=100), max_spread_bps=d(200))
    exact_spread = (
        (Fraction(fill.best_ask_price) - Fraction(fill.best_bid_price))
        / ((Fraction(fill.best_ask_price) + Fraction(fill.best_bid_price)) / 2)
        * 10_000
    )
    assert fill.spread_bps == historical_execution_render_amount(exact_spread)
    assert Fraction(99) < exact_spread < Fraction(101)  # a ~1% spread is ~100 bps, never 1 or 0.01
    assert Fraction(fill.participation_pct) == Fraction(1)  # 1 of 100 visible units is one PERCENT, not 0.01
    assert Fraction(fill.impact_bps) == Fraction(default_policy().impact_coefficient_bps_per_participation_pct)
    assert fill.effective_slippage_bps == historical_execution_render_amount(
        exact_spread / 2 + Fraction(fill.impact_bps)
    )


def test_participation_and_impact_follow_the_filled_not_the_requested_quantity() -> None:
    partial = partial_result().fills[0]
    assert partial.outcome is HistoricalExecutionFillOutcome.PARTIALLY_FILLED
    assert (
        Fraction(partial.participation_pct)
        == Fraction(partial.filled_quantity) / Fraction(partial.side_visible_quantity) * 100
    )
    assert (
        Fraction(partial.participation_pct)
        < Fraction(partial.requested_quantity) / Fraction(partial.side_visible_quantity) * 100
    )


def test_static_spread_is_impossible_prices_track_the_observed_book() -> None:
    def book(j: int) -> Values | None:
        return book_with(half_spread="0.05" if j % 2 else "0.2")(j)

    result = economics(world(records=market_records(book=book)))
    _assert_receipt_invariants(result)
    assert len({fill.spread_bps for fill in _executed(result)}) > 1


# --- exact internal accounting (inherited P1 blocker: ROUNDED_COST_BASIS) ----------------------------------------------

_EXACT_UNIT = 7000
_EXACT_EQUITY = 10_000_000


def _exact_depth(j: int) -> int:
    """1000 executable units for the opening fill, 6000 for the top-up, then unconstrained."""

    if j < 25:
        return 50_000
    if j < 35:
        return 300_000
    return 100_000_000


@functools.cache
def exact_basis_result(direction: str) -> HistoricalExecutionEconomicsResult:
    """A world whose weighted average entry price is NOT representable at scale 18."""

    records = market_records(rates=flipped() if direction == "long" else RATES, book=book_with(quantity=_exact_depth))
    w = world(records=records, parameters=prof.params(unit=d(_EXACT_UNIT)))
    return economics(w, policy=polt.cited_policy(initial_equity=d(_EXACT_EQUITY)))


def _exact_average(result: HistoricalExecutionEconomicsResult) -> Fraction:
    """The exact weighted entry basis of the first excursion, recomputed independently from the fills."""

    entry = _executed(result)[:2]
    quantity = sum(abs(Fraction(fill.filled_quantity)) for fill in entry)
    return sum(abs(Fraction(fill.filled_quantity)) * Fraction(fill.fill_price) for fill in entry) / quantity


@pytest.mark.parametrize("direction", ["short", "long"])
def test_increase_keeps_an_exact_cost_basis_and_never_a_rendered_one(direction: str) -> None:
    result = exact_basis_result(direction)
    _assert_receipt_invariants(result)
    kinds = [item.transition_kind for item in result.position_transitions]
    assert kinds[:3] == [
        HistoricalExecutionTransitionKind.OPEN,
        HistoricalExecutionTransitionKind.INCREASE,
        HistoricalExecutionTransitionKind.CLOSE,
    ]
    average = _exact_average(result)
    assert (average * 10**18).denominator != 1  # the fixture really does force a non-representable basis
    increase = result.position_transitions[1]
    assert increase.post_average_entry_price == historical_execution_render_amount(average)
    assert Fraction(increase.post_average_entry_price) != average  # the rendered field is a VIEW, not the state
    closed = result.position_transitions[2]
    sign = 1 if direction == "long" else -1
    exit_price = Fraction(_executed(result)[2].fill_price)
    exact = Fraction(closed.closed_quantity) * (exit_price - average) * sign
    assert closed.realized_gross_pnl == historical_execution_render_amount(exact)


@pytest.mark.parametrize("direction", ["short", "long"])
def test_the_rejected_rounded_basis_result_is_not_reproduced(direction: str) -> None:
    """The negative-evidence case: a rounded internal basis distorts closed gross by hundreds of scale units."""

    result = exact_basis_result(direction)
    average = _exact_average(result)
    rounded = Fraction(historical_execution_render_amount(average))
    closed = result.position_transitions[2]
    sign = 1 if direction == "long" else -1
    exit_price = Fraction(_executed(result)[2].fill_price)
    quantity = Fraction(closed.closed_quantity)
    exact_value = quantity * (exit_price - average) * sign
    rounded_value = quantity * (exit_price - rounded) * sign
    assert abs(exact_value - rounded_value) > 100 * ULP
    assert closed.realized_gross_pnl == historical_execution_render_amount(exact_value)
    assert closed.realized_gross_pnl != historical_execution_render_amount(rounded_value)


@pytest.mark.parametrize("direction", ["short", "long"])
def test_closed_trade_reconciles_with_its_signed_fill_cashflows(direction: str) -> None:
    result = exact_basis_result(direction)
    closed = next(item for item in result.trades if item.status is HistoricalExecutionTradeStatus.CLOSED)
    digests = set(closed.entry_fill_digests) | set(closed.exit_fill_digests)
    cashflow = -sum(_signed(fill) * Fraction(fill.fill_price) for fill in result.fills if fill.fill_digest in digests)
    assert closed.realized_gross_pnl == historical_execution_render_amount(cashflow)
    fees = [item for item in result.fee_cashflows if item.fee_digest in closed.fee_digests]
    funding = [item for item in result.funding_cashflows if item.cashflow_digest in closed.funding_cashflow_digests]
    assert closed.total_fees == historical_execution_render_amount(sum(Fraction(f.fee_amount) for f in fees))
    assert closed.total_funding == historical_execution_render_amount(sum(Fraction(c.cashflow_amount) for c in funding))
    assert Fraction(closed.realized_net_pnl) == (
        Fraction(closed.realized_gross_pnl) - Fraction(closed.total_fees) + Fraction(closed.total_funding)
    )


@pytest.mark.parametrize("direction", ["short", "long"])
def test_valuation_equity_and_mark_to_market_consume_the_exact_basis(direction: str) -> None:
    result = exact_basis_result(direction)
    average = _exact_average(result)
    increase = result.position_transitions[1]
    valuation = next(
        item
        for item in result.valuations
        if item.valuation_kind is HistoricalExecutionValuationKind.FILL and item.trigger_digest == increase.fill_digest
    )
    quantity = Fraction(valuation.position_quantity)
    exact_unrealized = quantity * (Fraction(valuation.mark_price) - average)
    assert valuation.unrealized_pnl == historical_execution_render_amount(exact_unrealized)
    assert valuation.average_entry_price == historical_execution_render_amount(average)
    exact_equity = (
        Fraction(polt.cited_policy(initial_equity=d(_EXACT_EQUITY)).initial_equity)
        + Fraction(valuation.cumulative_realized_gross_pnl)
        - Fraction(valuation.cumulative_fees)
        + Fraction(valuation.cumulative_funding)
        + exact_unrealized
    )
    assert abs(Fraction(valuation.equity) - exact_equity) <= 3 * ULP  # each field carries ONE rounding, never two


@pytest.mark.parametrize("direction", ["short", "long"])
def test_partial_reduction_keeps_the_exact_average_and_realizes_against_it(direction: str) -> None:
    reductions = [
        item
        for item in partial_result(direction).position_transitions
        if item.transition_kind is HistoricalExecutionTransitionKind.REDUCE
    ]
    assert reductions
    for transition in reductions:
        assert transition.post_average_entry_price == transition.prior_average_entry_price
        prior, post = Fraction(transition.prior_quantity), Fraction(transition.post_quantity)
        assert abs(prior) > abs(post) > 0 and prior * post > 0


def test_long_and_short_accounting_are_sign_symmetric() -> None:
    short, long = exact_basis_result("short"), exact_basis_result("long")
    for a, b in zip(short.position_transitions, long.position_transitions, strict=True):
        assert a.transition_kind is b.transition_kind
        assert Fraction(a.prior_quantity) == -Fraction(b.prior_quantity)
        assert Fraction(a.post_quantity) == -Fraction(b.post_quantity)
        assert Fraction(a.closed_quantity) == Fraction(b.closed_quantity)


@pytest.mark.parametrize("direction", ["short", "long"])
def test_exact_basis_world_rebuilds_byte_identically(direction: str) -> None:
    first = exact_basis_result(direction)
    records = market_records(rates=flipped() if direction == "long" else RATES, book=book_with(quantity=_exact_depth))
    again = economics(
        world(records=records, parameters=prof.params(unit=d(_EXACT_UNIT))),
        policy=polt.cited_policy(initial_equity=d(_EXACT_EQUITY)),
    )
    assert edge_canonical_json(historical_execution_economics_to_dict(first)) == edge_canonical_json(
        historical_execution_economics_to_dict(again)
    )


# --- exact leverage authority (inherited P2 blocker: FLOAT_LEVERAGE_AUTHORITY) ------------------------------------------


def test_a_positive_integer_max_leverage_is_the_only_accepted_representation() -> None:
    result = economics(world(spec_changes={"risk_caps": {"max_leverage": 3}}))
    _assert_receipt_invariants(result)
    assert result.advances is True


@pytest.mark.parametrize(
    "max_leverage",
    [3.0, 2.5, 1.0],
    ids=["integral_float", "fractional_float", "one_point_zero"],
)
def test_a_non_integer_max_leverage_fails_closed_at_the_economics_boundary(max_leverage: object) -> None:
    """The exact-numeric boundary refuses float leverage instead of coercing it through ``repr`` or ``float``.

    An accepted StrategySpec may legitimately carry a float cap, so this layer must refuse it on its own: an
    integral float is refused exactly like a fractional one, because neither is an exact representation here.
    """

    w = world(spec_changes={"risk_caps": {"max_leverage": max_leverage}})
    _blocked(economics(w), EdgeGateVerdict.FAIL, "strategy_max_leverage_representation_unsupported")


@pytest.mark.parametrize(
    "risk_caps",
    [{"max_leverage": True}, {"max_notional": 1000}, {"max_leverage": 0}, {"max_leverage": "3"}],
    ids=["bool", "missing", "zero", "text"],
)
def test_leverage_forms_the_admission_chain_already_refuses_never_reach_the_economics(risk_caps: dict) -> None:
    """Defence in depth: these forms never produce an accepted spec, so no run can carry them into economics."""

    assert validate_strategy_spec({**pit.SPEC, "market_type": "usdt_perp", "risk_caps": risk_caps}).accepted is False


def test_the_module_holds_no_float_or_decimal_numeric_authority() -> None:
    source = Path(economics_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Constant) and type(node.value) is float]
    names = {
        alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names
    }
    modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert "decimal" not in names and "decimal" not in modules
    assert not [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"float", "repr"}
    ]


# --- funding ------------------------------------------------------------------------------------------------------------


def test_funding_signs_and_liability_semantics() -> None:
    result = default_result()
    policy = default_policy()
    rows = [
        (_t(c.liability_time_ns), c.position_quantity, c.funding_rate, c.cashflow_amount)
        for c in result.funding_cashflows
    ]
    assert rows == [
        (30_000, d(-1), RATES[2], d(Fraction(RATES[2]) * price(29))),
        (40_000, d(-1), RATES[3], d(Fraction(RATES[3]) * price(39))),
        (50_000, d(-1), RATES[4], d(Fraction(RATES[4]) * price(49))),
        (70_000, d(1), RATES[6], d(-Fraction(RATES[6]) * price(69))),
        (80_000, d(1), RATES[7], d(-Fraction(RATES[7]) * price(79))),
    ]
    assert Fraction(rows[0][3]) > 0  # SHORT receives positive funding
    assert Fraction(rows[2][3]) < 0  # SHORT pays negative funding
    assert Fraction(rows[3][3]) > 0  # LONG receives negative funding
    for cashflow in result.funding_cashflows:
        assert cashflow.liability_time_ns == cashflow.funding_event_time_ns + policy.funding_interval_ns
        quantity, mark, rate = (
            Fraction(cashflow.position_quantity),
            Fraction(cashflow.mark_price),
            Fraction(cashflow.funding_rate),
        )
        assert quantity != 0
        assert Fraction(cashflow.funding_notional) == abs(quantity) * mark
        assert cashflow.cashflow_amount == historical_execution_render_amount(-quantity * mark * rate)
        if rate > 0:
            assert (Fraction(cashflow.cashflow_amount) > 0) is (quantity < 0)  # positive rate: LONG pays
    assert len({c.funding_record_digest for c in result.funding_cashflows}) == len(result.funding_cashflows)


def test_long_pays_positive_funding() -> None:
    rates = ("-0.000200000000000000", "-0.000300000000000000", "0.000100000000000000") + RATES[3:]
    result = economics(world(records=market_records(rates=rates)))
    _assert_receipt_invariants(result)
    first = result.funding_cashflows[0]
    assert (Fraction(first.position_quantity), Fraction(first.funding_rate)) == (1, Fraction("0.0001"))
    assert Fraction(first.cashflow_amount) < 0


def test_zero_position_settlements_produce_no_cashflow_and_each_record_settles_once() -> None:
    result = default_result()
    liabilities = [_t(c.liability_time_ns) for c in result.funding_cashflows]
    assert 20_000 not in liabilities and 60_000 not in liabilities  # flat before entry and after the exit
    digests = [c.funding_record_digest for c in result.funding_cashflows]
    assert len(digests) == len(set(digests))


def test_signal_records_are_reused_as_settlements_without_re_deciding() -> None:
    result = default_result()
    run = default_world().run
    signal_inputs = {digest for decision in run.decisions for digest in decision.input_record_digests}
    assert {c.funding_record_digest for c in result.funding_cashflows} & signal_inputs
    snapshot = json.loads(result.run_binding.snapshot_json)
    assert (
        snapshot["decisions"] == json.loads(edge_canonical_json(runt.historical_decision_run_to_dict(run)))["decisions"]
    )
    assert historical_decision_run_digest(run) == run.run_digest


def test_funding_settlement_precedes_a_fill_at_the_same_nanosecond() -> None:
    """A liability landing exactly on a fill instant settles against the position BEFORE that fill."""

    def book(j: int) -> Values | None:
        return None if 20 <= j < 30 else default_book(j)

    extra = ((BASE + 29_998, 1, default_book(29)),)  # visible exactly at the liability instant BASE + 30_000
    policy = polt.cited_policy(max_execution_delay_ns=10_000)
    result = economics(world(records=market_records(book=book, extra_books=extra)), policy=policy)
    _assert_receipt_invariants(result)
    entry = result.fills[0]
    assert _t(entry.execution_time_ns) == 30_000
    assert entry.outcome is HistoricalExecutionFillOutcome.FILLED
    assert 30_000 not in [_t(c.liability_time_ns) for c in result.funding_cashflows]  # flat when it settled
    kinds = [(v.valuation_kind, _t(v.time_ns)) for v in result.valuations if _t(v.time_ns) == 30_000]
    assert kinds == [(HistoricalExecutionValuationKind.FILL, 30_000)]


def test_no_settlement_pays_a_rate_its_own_entry_decision_could_not_know() -> None:
    for w in (default_world(), world(records=market_records(funding_times=(INTERVAL, INTERVAL)))):
        result = economics(w)
        assert result.advances is True
        decisions = {item.decision_digest: item for item in w.run.decisions}
        fills = {f.fill_digest: f for f in result.fills}
        for cashflow in result.funding_cashflows:
            liable = [t for t in result.position_transitions if t.time_ns < cashflow.liability_time_ns]
            decision = decisions[fills[liable[-1].fill_digest].decision_digest]
            if decision.decision_time_ns < cashflow.liability_time_ns:
                assert cashflow.funding_record_digest not in decision.input_record_digests


def test_missing_trailing_funding_coverage_fails_without_interpolation() -> None:
    """The series stops while a position is still open: the later liabilities are never silently interpolated."""

    short_series = market_records(rates=RATES[:6])
    _blocked(economics(world(records=short_series)), EdgeGateVerdict.FAIL, "funding_coverage_incomplete")


def test_funding_interval_must_match_the_approved_interval() -> None:
    _blocked(
        economics(policy=polt.cited_policy(funding_interval_ns=INTERVAL * 2)),
        EdgeGateVerdict.FAIL,
        "funding_interval_inconsistent",
    )


def test_duplicate_funding_records_never_reach_economics() -> None:
    manifest, _, registry = chain()
    records = market_records()
    duplicate = next(r for r in records if r.series_id == "funding-final")
    dataset = build_historical_pit_dataset(
        manifest,
        expected_source_manifest_digest=manifest.source_packet_evidence_digest,
        expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
        dataset_id="dataset-1",
        correlation_id="corr-1",
        source_reference="archive:history",
        rights_status="own_research",
        rights_reference="license-1",
        records=(*records, duplicate),
    )
    assert dataset.status is EdgeEvidenceStatus.REJECTED


def test_leading_funding_records_cannot_be_silently_omitted() -> None:
    """Old review finding: coverage derived from retained rows could miss omitted LEADING settlements.

    Coverage is decided against the governed grid, and the contract also makes the case unreachable: a decision can
    only fire at a funding visibility, finality cannot precede the liability, so no position is liable before the
    first retained liability.
    """

    result = economics(world(records=market_records(first_funding_sequence=3)))
    _assert_receipt_invariants(result)
    assert result.advances is True
    first_liability = BASE + 3 * INTERVAL + INTERVAL
    executed = _executed(result)
    assert executed
    assert min(fill.execution_time_ns for fill in executed) > first_liability
    settled = sorted(c.liability_time_ns for c in result.funding_cashflows)
    assert settled
    liable_from = min(fill.execution_time_ns for fill in executed)
    expected = [
        instant
        for instant in range(first_liability, END, INTERVAL)
        if liable_from < instant < END and instant >= first_liability
    ]
    assert settled == [instant for instant in expected if instant in settled]
    assert all(instant in settled for instant in expected if instant > liable_from)


def test_the_coverage_rule_counts_every_governed_grid_instant() -> None:
    """Leading, interior and trailing instants are counted by one arithmetic rule, not by scanning the rows."""

    count = economics_module._grid_instant_count
    assert count(100, 10, 100, 100) == 1
    assert count(100, 10, 101, 109) == 0
    assert count(100, 10, 90, 130) == 5  # 90, 100, 110, 120, 130: instants BELOW the anchor count too
    assert count(100, 10, 60, 99) == 4  # 60, 70, 80, 90: a leading gap is visible to the same rule
    assert count(100, 10, 130, 100) == 0
    assert count(100, 1, 0, 10**9) == 10**9 + 1  # arithmetic, never an unbounded scan


def test_funding_settlements_cover_every_liable_grid_instant() -> None:
    result = default_result()
    settled = {c.liability_time_ns for c in result.funding_cashflows}
    segments = [(t.time_ns, Fraction(t.post_quantity)) for t in result.position_transitions]
    for index, (start, quantity) in enumerate(segments):
        if quantity == 0:
            continue
        stop = segments[index + 1][0] if index + 1 < len(segments) else END - 1
        for instant in range(BASE, END, INTERVAL):
            if start < instant <= min(stop, END - 1):
                assert instant in settled, instant - BASE


# --- funding cycle finality ---------------------------------------------------------------------------------------------


def test_funding_final_before_its_own_cycle_closes_fails_before_any_simulation() -> None:
    w = world(records=market_records(funding_times=(0, 0)))  # published and "final" already at the window open
    assert (w.run.status, w.run.gate_verdict) == (EdgeEvidenceStatus.READY, EdgeGateVerdict.PASS)
    entry_decision = next(item for item in w.run.decisions if item.resulting_direction == "SHORT")
    unclosed = [
        record
        for record in w.dataset.records
        if record.record_digest in entry_decision.input_record_digests
        and entry_decision.decision_time_ns < record.event_time_ns + INTERVAL
    ]
    assert unclosed  # the frozen entry reads a rate whose own cycle has not closed, and would then collect it
    result = economics(w)
    _blocked(result, EdgeGateVerdict.FAIL, "funding_finalized_before_cycle_close")
    assert (result.simulated_economics_computed, result.advances) == (False, False)


@pytest.mark.parametrize(
    "finalized", [INTERVAL - 1, INTERVAL // 2, 0], ids=["one_ns_early", "mid_cycle", "at_window_open"]
)
def test_a_single_early_final_funding_record_fails_the_whole_result(finalized: int) -> None:
    w = world(records=market_records(funding_overrides={2: (finalized, finalized)}))
    assert w.run.gate_verdict is EdgeGateVerdict.PASS
    _blocked(economics(w), EdgeGateVerdict.FAIL, "funding_finalized_before_cycle_close")


def test_finality_exactly_at_the_cycle_close_is_supported() -> None:
    result = economics(world(records=market_records(funding_times=(INTERVAL, INTERVAL))))
    _assert_receipt_invariants(result)
    assert result.advances is True
    assert result.funding_cashflows
    for cashflow in result.funding_cashflows:
        assert cashflow.liability_time_ns == cashflow.funding_event_time_ns + INTERVAL


def test_archive_finality_after_the_liability_keeps_settlement_at_the_governed_instant() -> None:
    w = world(records=market_records(funding_times=(INTERVAL + 10, 2 * INTERVAL)))
    result = economics(w)
    _assert_receipt_invariants(result)
    assert result.advances is True
    assert result.funding_cashflows
    records = {r.record_digest: r for r in w.dataset.records}
    for cashflow in result.funding_cashflows:
        record = records[cashflow.funding_record_digest]
        assert record.finalized_at_ns > cashflow.liability_time_ns  # the archive finalizes it only later
        assert cashflow.liability_time_ns == record.event_time_ns + INTERVAL  # settlement never moves
        valuation = next(v for v in result.valuations if v.trigger_digest == cashflow.cashflow_digest)
        assert valuation.time_ns == cashflow.liability_time_ns


def test_the_funding_repair_never_re_runs_the_frozen_decision_trace() -> None:
    w = world(records=market_records(funding_times=(0, 0)))
    failed = economics(w)
    snapshot = json.loads(failed.run_binding.snapshot_json)
    expected = json.loads(edge_canonical_json(runt.historical_decision_run_to_dict(w.run)))
    assert snapshot["decisions"] == expected["decisions"]
    assert (failed.intents, failed.position_transitions) == ((), ())


def test_never_final_funding_decides_nothing_and_settles_nothing() -> None:
    """A rate that never becomes final drives no decision, so there is no position and no settlement to book."""

    w = world(records=market_records(funding_times=(INTERVAL + 10, None)))
    assert w.run.decisions == ()
    result = economics(w)
    _assert_receipt_invariants(result)
    assert (result.intents, result.fills, result.funding_cashflows, result.trades) == ((), (), (), ())
    assert result.terminal_state.position_quantity == d(0)


def test_a_never_final_record_cannot_settle_an_open_position() -> None:
    """If a position IS open when a non-final record's liability arrives, the result fails closed."""

    records = market_records(funding_overrides={6: (INTERVAL + 10, None)})
    _blocked(economics(world(records=records)), EdgeGateVerdict.FAIL, "funding_coverage_incomplete")


def test_a_liability_instant_outside_the_wire_domain_fails_closed() -> None:
    single = world(records=market_records(rates=RATES[:1]))  # one record: the grid has no spacing to contradict
    _blocked(
        economics(single, policy=polt.cited_policy(funding_interval_ns=polt.INT64_MAX)),
        EdgeGateVerdict.FAIL,
        "economic_value_out_of_representation:funding_liability_time_ns",
    )


def test_the_funding_finality_failure_is_re_derived_and_cannot_be_resealed_away() -> None:
    blocked = economics(world(records=market_records(funding_times=(10, 20))))
    healthy = default_result()
    forged = _reseal(
        blocked,
        gate_verdict=EdgeGateVerdict.PASS,
        advances=True,
        simulated_economics_computed=True,
        verdict_reason_codes=(),
        fills=healthy.fills,
        funding_cashflows=healthy.funding_cashflows,
    )
    verification = verify_historical_execution_economics(forged)
    assert verification.intact is False
    assert verification.reason_codes


# --- valuation and marks -----------------------------------------------------------------------------------------------


def test_valuation_schedule_and_equity_identity() -> None:
    result = default_result()
    kinds = [(v.valuation_kind.value, _t(v.time_ns)) for v in result.valuations]
    assert kinds[0] == ("INITIAL", 1)
    assert ("UTC_DAY_BOUNDARY", 50_000) in kinds
    assert kinds[-1] == ("EVALUATION_END", END - BASE)
    assert (BASE + 50_000) % DAY_NS == 0
    assert [v.valuation_sequence for v in result.valuations] == list(range(len(result.valuations)))
    policy = default_policy()
    for valuation in result.valuations:
        expected = (
            Fraction(policy.initial_equity)
            + Fraction(valuation.cumulative_realized_gross_pnl)
            - Fraction(valuation.cumulative_fees)
            + Fraction(valuation.cumulative_funding)
            + Fraction(valuation.unrealized_pnl)
        )
        assert abs(Fraction(valuation.equity) - expected) <= 3 * ULP
        if Fraction(valuation.position_quantity) == 0:
            assert (valuation.mark_price, valuation.unrealized_pnl) == (None, d(0))
        else:
            assert valuation.mark_price is not None
            assert (
                abs(
                    Fraction(valuation.unrealized_pnl)
                    - Fraction(valuation.position_quantity)
                    * (Fraction(valuation.mark_price) - Fraction(valuation.average_entry_price))
                )
                <= 3 * ULP
            )


def test_unavailable_mark_is_never_used_for_valuation() -> None:
    extra = ((BASE + 20_400, 5_000, {"mark_price": d(500)}),)  # event before the fill, visible only later
    result = economics(world(records=market_records(extra_marks=extra)))
    fill_valuation = next(v for v in result.valuations if v.valuation_kind is HistoricalExecutionValuationKind.FILL)
    assert fill_valuation.mark_price == d(price(20))
    assert all(v.mark_price != d(500) for v in result.valuations)


def test_stale_mark_fails() -> None:
    _blocked(economics(policy=polt.cited_policy(max_mark_staleness_ns=500)), EdgeGateVerdict.FAIL, "mark_stale:fill")


def test_missing_mark_fails() -> None:
    sparse = market_records(mark=lambda j: None if j < 25 else default_mark(j))
    _blocked(economics(world(records=sparse)), EdgeGateVerdict.FAIL, "mark_missing:fill")
    no_series = world(keys=("funding_rate", "order_book"), records=_without(market_records(), "mark"))
    _blocked(economics(no_series), EdgeGateVerdict.FAIL, "economic_series_missing:mark_price")


def _without(records: tuple[HistoricalPitRecord, ...], series: str) -> tuple[HistoricalPitRecord, ...]:
    return tuple(record for record in records if record.series_id != series)


def test_terminal_open_position_is_marked_not_force_closed() -> None:
    result = default_result()
    terminal = result.terminal_state
    assert terminal is not None
    closed, opened = result.trades
    assert (closed.status, closed.direction) == (HistoricalExecutionTradeStatus.CLOSED, "SHORT")
    assert (opened.status, opened.direction, opened.end_time_ns) == (HistoricalExecutionTradeStatus.OPEN, "LONG", None)
    assert terminal.open_trade_id == opened.trade_id
    assert opened.unrealized_pnl == terminal.unrealized_pnl == result.valuations[-1].unrealized_pnl
    assert opened.terminal_valuation_digest == terminal.end_valuation_digest == result.valuations[-1].valuation_digest
    assert terminal.position_quantity == d(1)
    assert len(result.fills) == 3  # no fabricated exit


def test_closed_trade_accounts_realized_fees_and_funding() -> None:
    result = default_result()
    closed = result.trades[0]
    entry, exit_fill = result.fills[0], result.fills[1]
    assert closed.entry_fill_digests == (entry.fill_digest,)
    assert closed.exit_fill_digests == (exit_fill.fill_digest,)
    assert Fraction(closed.realized_gross_pnl) == Fraction(entry.fill_price) - Fraction(exit_fill.fill_price)
    fees = [f for f in result.fee_cashflows if f.fill_digest in (entry.fill_digest, exit_fill.fill_digest)]
    assert closed.fee_digests == tuple(f.fee_digest for f in fees)
    assert Fraction(closed.total_fees) == sum(Fraction(f.fee_amount) for f in fees)
    funding = [c for c in result.funding_cashflows if c.cashflow_digest in closed.funding_cashflow_digests]
    assert Fraction(closed.total_funding) == sum(Fraction(c.cashflow_amount) for c in funding)
    assert Fraction(closed.realized_net_pnl) == (
        Fraction(closed.realized_gross_pnl) - Fraction(closed.total_fees) + Fraction(closed.total_funding)
    )


# --- fees ---------------------------------------------------------------------------------------------------------------


def test_fee_is_a_taker_cost_counted_once_per_executed_fill() -> None:
    result = default_result()
    executed = _executed(result)
    assert [f.fill_digest for f in result.fee_cashflows] == [f.fill_digest for f in executed]
    for fee, fill in zip(result.fee_cashflows, executed, strict=True):
        assert fee.taker_fee_bps == default_policy().taker_fee_bps
        assert fee.fee_amount == historical_execution_render_amount(
            Fraction(fill.fill_price) * Fraction(fill.filled_quantity) * 5 / 10_000
        )
        assert Fraction(fee.fee_amount) >= 0
    assert (
        abs(Fraction(result.terminal_state.cumulative_fees) - sum(Fraction(f.fee_amount) for f in result.fee_cashflows))
        <= 3 * ULP
    )


# --- partial fills, divergence reconciliation, close-only clamp --------------------------------------------------------


@functools.cache
def partial_result(direction: str = "short") -> HistoricalExecutionEconomicsResult:
    rates = flipped() if direction == "long" else RATES
    return economics(world(records=market_records(rates=rates, book=book_with(quantity=10))))


def test_partial_fill_is_capped_by_visible_depth_and_the_remainder_is_cancelled() -> None:
    fill = partial_result().fills[0]
    assert (fill.outcome, fill.reason) == (
        HistoricalExecutionFillOutcome.PARTIALLY_FILLED,
        "visible_depth_cap_partial_remainder_cancelled",
    )
    assert (fill.requested_quantity, fill.filled_quantity, fill.cancelled_quantity) == (d(1), d("0.2"), d("0.8"))
    assert (fill.fill_ratio, fill.max_executable_quantity, fill.participation_pct) == (d("0.2"), d("0.2"), d(2))


def test_divergence_is_reconciled_by_target_delta_with_close_only_clamp() -> None:
    result = partial_result()
    _assert_receipt_invariants(result)
    assert [(i.action.value, i.close_only_clamped, i.actual_quantity, i.target_quantity) for i in result.intents] == [
        ("SELL", False, d(0), d(-1)),
        ("SELL", False, d("-0.2"), d(-1)),
        ("SELL", False, d("-0.4"), d(-1)),
        ("CLOSE_SHORT", False, d("-0.6"), d(0)),
        ("CLOSE_SHORT", True, d("-0.4"), d(1)),
        ("CLOSE_SHORT", True, d("-0.2"), d(1)),
        ("BUY", False, d(0), d(1)),
    ]
    assert [t.transition_kind for t in result.position_transitions] == [
        HistoricalExecutionTransitionKind.OPEN,
        HistoricalExecutionTransitionKind.INCREASE,
        HistoricalExecutionTransitionKind.INCREASE,
        HistoricalExecutionTransitionKind.REDUCE,
        HistoricalExecutionTransitionKind.REDUCE,
        HistoricalExecutionTransitionKind.CLOSE,
        HistoricalExecutionTransitionKind.OPEN,
    ]
    for transition in result.position_transitions:
        prior, post = Fraction(transition.prior_quantity), Fraction(transition.post_quantity)
        assert prior * post >= 0  # no cross-through, no same-instant opposite entry


def test_top_up_uses_the_exact_weighted_average_and_reduction_keeps_it() -> None:
    result = partial_result()
    first, second, _, reduce, *_ = result.position_transitions
    p1, p2 = Fraction(result.fills[0].fill_price), Fraction(result.fills[1].fill_price)
    assert second.post_average_entry_price == d((Fraction("0.2") * p1 + Fraction("0.2") * p2) / Fraction("0.4"))
    assert reduce.post_average_entry_price == reduce.prior_average_entry_price
    assert reduce.realized_gross_pnl == historical_execution_render_amount(
        Fraction(reduce.closed_quantity)
        * (Fraction(reduce.prior_average_entry_price) - Fraction(result.fills[3].fill_price))
    )
    assert first.prior_average_entry_price is None


def test_opposite_entry_happens_only_at_a_later_decision() -> None:
    result = partial_result()
    reentry = result.intents[-1]
    clamped = [i for i in result.intents if i.close_only_clamped]
    assert all(i.decision_time_ns < reentry.decision_time_ns for i in clamped)
    assert result.trades[0].status is HistoricalExecutionTradeStatus.CLOSED
    assert result.trades[-1].direction == "LONG"


def test_long_partial_reduction() -> None:
    result = partial_result("long")
    reductions = [
        t for t in result.position_transitions if t.transition_kind is HistoricalExecutionTransitionKind.REDUCE
    ]
    assert reductions
    assert all(Fraction(t.prior_quantity) > Fraction(t.post_quantity) > 0 for t in reductions)


# --- PRDV4 fill-model gates ---------------------------------------------------------------------------------------------


def _first_fill(book: Callable[[int], Values | None], **policy_overrides: object):
    policy = polt.cited_policy(**policy_overrides) if policy_overrides else None
    result = economics(world(records=market_records(book=book)), policy=policy)
    _assert_receipt_invariants(result)
    return result.fills[0]


def _book(**values: object) -> Callable[[int], Values | None]:
    def book(j: int) -> Values | None:
        base = default_book(j)
        return {**base, **{key: d(value) for key, value in values.items()}}  # type: ignore[dict-item]

    return book


def test_crossed_book_is_rejected() -> None:
    fill = _first_fill(_book(best_bid_price=101, best_ask_price=100))
    assert (fill.outcome, fill.reason, fill.fill_price) == (
        HistoricalExecutionFillOutcome.REJECTED,
        "book_crossed",
        None,
    )


def test_excessive_spread_is_rejected() -> None:
    fill = _first_fill(_book(best_bid_price=90, best_ask_price=110))
    assert (fill.outcome, fill.reason) == (HistoricalExecutionFillOutcome.REJECTED, "spread_exceeds_max")


@pytest.mark.parametrize(
    ("values", "reason"),
    [
        ({"best_bid_quantity": 0, "best_ask_quantity": 0}, "insufficient_depth"),
        (
            {"best_bid_quantity": "0.00000000000000001", "best_ask_quantity": "0.00000000000000001"},
            "insufficient_depth",
        ),
        ({"best_bid_quantity": -1, "best_ask_quantity": -1}, "book_invalid"),
        ({"best_bid_price": 0}, "book_invalid"),
    ],
    ids=["zero_depth", "depth_truncates_to_zero", "negative_depth", "zero_price"],
)
def test_invalid_or_empty_depth_is_rejected(values: dict[str, object], reason: str) -> None:
    fill = _first_fill(_book(**values))
    assert (fill.outcome, fill.reason, fill.filled_quantity) == (HistoricalExecutionFillOutcome.REJECTED, reason, d(0))


def test_rejected_intents_leave_the_position_flat() -> None:
    result = economics(world(records=market_records(book=_book(best_bid_price=101, best_ask_price=100))))
    assert result.position_transitions == ()
    assert result.fee_cashflows == ()
    assert result.terminal_state.position_quantity == d(0)
    assert all(f.outcome is HistoricalExecutionFillOutcome.REJECTED for f in result.fills)


def test_no_eligible_observation_is_unfilled() -> None:
    fill = _first_fill(lambda j: default_book(j) if j < 20 else None)
    assert (fill.outcome, fill.reason, fill.execution_time_ns) == (
        HistoricalExecutionFillOutcome.UNFILLED,
        "no_eligible_book_observation",
        None,
    )


def test_execution_delay_expiry_is_unfilled() -> None:
    fill = _first_fill(default_book, max_execution_delay_ns=300)
    assert (fill.outcome, fill.reason) == (HistoricalExecutionFillOutcome.UNFILLED, "execution_delay_expired")


def test_observation_after_the_next_decision_is_unfilled() -> None:
    fill = _first_fill(lambda j: default_book(j) if j % 10 == 0 and j != 20 else None, max_execution_delay_ns=20_000)
    assert (fill.outcome, fill.reason) == (HistoricalExecutionFillOutcome.UNFILLED, "execution_window_closed")


def test_same_observation_or_stale_late_book_never_prices_a_fill() -> None:
    decision_time = default_world().run.decisions[1].decision_time_ns
    stale = ((decision_time - 5, 150, {**default_book(20), "best_bid_price": d(998), "best_ask_price": d(999)}),)
    fill = economics(world(records=market_records(extra_books=stale))).fills[0]
    assert fill.book_event_time_ns > decision_time
    assert Fraction(fill.fill_price) < 200


def test_missing_order_book_series_fails() -> None:
    w = world(keys=("funding_rate", "mark_price"), records=_without(market_records(), "book"))
    _blocked(economics(w), EdgeGateVerdict.FAIL, "economic_series_missing:order_book")


# --- risk: the cap binds the EXACT candidate post-fill state ------------------------------------------------------------

_REFERENCE_EQUITY = Fraction(10_000)


def _first_fill_valuation(result: HistoricalExecutionEconomicsResult) -> HistoricalExecutionValuation:
    return next(v for v in result.valuations if v.valuation_kind is HistoricalExecutionValuationKind.FILL)


def _ceil18(value: Fraction) -> Fraction:
    scaled = value * 10**18
    return Fraction(-((-scaled.numerator) // scaled.denominator), 10**18)


def _risk_boundary(w: World | None = None, *, max_leverage: int = 1, **policy_overrides: object) -> Fraction:
    """The EXACT minimum initial equity at which the first fill still satisfies the governed cap.

    Recomputed independently from the fill and its mark: for an opening fill the exact candidate equity is
    ``initial + signed*(mark - price) - fee``, so the cap binds at ``notional/leverage - carry``.
    """

    policy = polt.cited_policy(initial_equity=d(_REFERENCE_EQUITY), **policy_overrides)
    result = economics(w, policy=policy)
    fill = result.fills[0]
    valuation = _first_fill_valuation(result)
    quantity, fill_price = Fraction(fill.filled_quantity), Fraction(fill.fill_price)
    mark = Fraction(valuation.mark_price)
    signed = quantity if fill.side is HistoricalExecutionSide.BUY else -quantity
    carry = signed * (mark - fill_price) - fill_price * quantity * Fraction(policy.taker_fee_bps) / 10_000
    return quantity * mark / max_leverage - carry


def _risk_reasons(result: HistoricalExecutionEconomicsResult) -> list[str]:
    return [f.reason for f in result.fills]


def test_leverage_breach_is_an_explicit_rejection_never_a_clip() -> None:
    result = economics(policy=polt.cited_policy(initial_equity=d(50)))
    _assert_receipt_invariants(result)
    assert result.advances is True
    assert {(f.outcome, f.reason) for f in result.fills} == {
        (HistoricalExecutionFillOutcome.REJECTED, "risk_limit_exceeded")
    }
    assert all(f.filled_quantity == d(0) for f in result.fills)
    assert result.position_transitions == ()
    assert result.terminal_state.equity == d(50)


def test_leverage_within_cap_fills() -> None:
    fills = economics(policy=polt.cited_policy(initial_equity=d(101))).fills
    assert fills[0].outcome is HistoricalExecutionFillOutcome.FILLED


def test_pre_fill_equity_alone_no_longer_authorizes_a_fill() -> None:
    boundary = _risk_boundary()
    valuation = _first_fill_valuation(economics(policy=polt.cited_policy(initial_equity=d(_REFERENCE_EQUITY))))
    notional = abs(Fraction(valuation.position_quantity)) * Fraction(valuation.mark_price)
    assert boundary > notional  # the fee and the adverse fill-versus-mark both raise the required equity
    result = economics(policy=polt.cited_policy(initial_equity=d(notional)))  # the old pre-fill boundary
    _assert_receipt_invariants(result)
    assert _risk_reasons(result) == ["risk_limit_exceeded"] * len(result.fills)
    assert (result.position_transitions, result.fee_cashflows) == ((), ())


def test_the_exact_post_fill_boundary_is_accepted_and_one_scale_unit_below_is_rejected() -> None:
    boundary = _ceil18(_risk_boundary())
    accepted = economics(policy=polt.cited_policy(initial_equity=d(boundary)))
    _assert_receipt_invariants(accepted)
    assert accepted.fills[0].outcome is HistoricalExecutionFillOutcome.FILLED
    valuation = _first_fill_valuation(accepted)
    assert abs(Fraction(valuation.position_quantity)) * Fraction(valuation.mark_price) <= Fraction(valuation.equity)
    rejected = economics(policy=polt.cited_policy(initial_equity=d(boundary - ULP)))
    assert rejected.fills[0].reason == "risk_limit_exceeded"


def test_a_high_taker_fee_is_charged_to_the_candidate_state() -> None:
    expensive = {"taker_fee_bps": d(500)}
    cheap_boundary = _ceil18(_risk_boundary())
    on_the_cheap_boundary = economics(policy=polt.cited_policy(initial_equity=d(cheap_boundary), **expensive))
    assert on_the_cheap_boundary.fills[0].reason == "risk_limit_exceeded"
    expensive_boundary = _ceil18(_risk_boundary(**expensive))
    assert expensive_boundary > cheap_boundary
    accepted = economics(policy=polt.cited_policy(initial_equity=d(expensive_boundary), **expensive))
    assert accepted.fills[0].outcome is HistoricalExecutionFillOutcome.FILLED


def test_the_adverse_fill_versus_mark_alone_can_breach_the_cap() -> None:
    free = {"taker_fee_bps": d(0)}
    valuation = _first_fill_valuation(economics(policy=polt.cited_policy(initial_equity=d(_REFERENCE_EQUITY), **free)))
    notional = abs(Fraction(valuation.position_quantity)) * Fraction(valuation.mark_price)
    rejected = economics(policy=polt.cited_policy(initial_equity=d(notional), **free))
    assert rejected.fills[0].reason == "risk_limit_exceeded"  # no fee at all: the fill price is worse than the mark
    accepted = economics(policy=polt.cited_policy(initial_equity=d(_ceil18(_risk_boundary(**free))), **free))
    assert accepted.fills[0].outcome is HistoricalExecutionFillOutcome.FILLED


def test_fee_and_mark_to_market_are_both_required_to_clear_the_cap() -> None:
    covers_only_the_mark_to_market = _ceil18(_risk_boundary(**{"taker_fee_bps": d(0)}))
    result = economics(policy=polt.cited_policy(initial_equity=d(covers_only_the_mark_to_market)))
    assert result.fills[0].reason == "risk_limit_exceeded"


@pytest.mark.parametrize("gap", [Fraction(0), ULP], ids=["exactly_zero", "one_unit_above_zero"])
def test_a_candidate_post_fill_equity_at_or_below_zero_is_rejected(gap: Fraction) -> None:
    policy = polt.cited_policy(initial_equity=d(_REFERENCE_EQUITY))
    result = economics(policy=policy)
    fill = result.fills[0]
    valuation = _first_fill_valuation(result)
    quantity, fill_price = Fraction(fill.filled_quantity), Fraction(fill.fill_price)
    signed = quantity if fill.side is HistoricalExecutionSide.BUY else -quantity
    carry = (
        signed * (Fraction(valuation.mark_price) - fill_price)
        - fill_price * quantity * Fraction(policy.taker_fee_bps) / 10_000
    )
    equity = Fraction(historical_execution_render_amount(gap - carry))  # candidate equity lands at or just above 0
    blocked = economics(policy=polt.cited_policy(initial_equity=d(equity)))
    _assert_receipt_invariants(blocked)
    assert blocked.advances is True
    assert _risk_reasons(blocked) == ["risk_limit_exceeded"] * len(blocked.fills)
    assert blocked.position_transitions == ()


def test_the_partial_fill_boundary_uses_the_filled_quantity_and_its_own_fee() -> None:
    w = world(records=market_records(book=book_with(quantity=10)))
    boundary = _ceil18(_risk_boundary(w))
    reference = economics(w, policy=polt.cited_policy(initial_equity=d(_REFERENCE_EQUITY)))
    assert reference.fills[0].outcome is HistoricalExecutionFillOutcome.PARTIALLY_FILLED
    assert Fraction(reference.fills[0].filled_quantity) == Fraction("0.2")
    accepted = economics(w, policy=polt.cited_policy(initial_equity=d(boundary)))
    assert accepted.fills[0].outcome is HistoricalExecutionFillOutcome.PARTIALLY_FILLED
    rejected = economics(w, policy=polt.cited_policy(initial_equity=d(boundary - ULP)))
    assert rejected.fills[0].reason == "risk_limit_exceeded"


@pytest.mark.parametrize("direction", ["short", "long"], ids=["short", "long"])
def test_increases_are_capped_while_reductions_and_closes_still_execute(direction: str) -> None:
    rates = RATES if direction == "short" else flipped()
    w = world(records=market_records(rates=rates, book=book_with(quantity=10)))
    result = economics(w, policy=polt.cited_policy(initial_equity=d(_ceil18(_risk_boundary(w)))))
    _assert_receipt_invariants(result)
    kinds = [t.transition_kind for t in result.position_transitions]
    assert kinds[0] is HistoricalExecutionTransitionKind.OPEN
    assert HistoricalExecutionTransitionKind.INCREASE not in kinds  # every top-up is judged on its own candidate state
    assert {HistoricalExecutionTransitionKind.REDUCE, HistoricalExecutionTransitionKind.CLOSE} & set(kinds)
    rejected = {f.fill_digest for f in result.fills if f.reason == "risk_limit_exceeded"}
    assert rejected
    applied = {t.fill_digest for t in result.position_transitions}
    charged = {f.fill_digest for f in result.fee_cashflows}
    assert not rejected & (applied | charged)  # no transition, no fee, no state mutation


@pytest.mark.parametrize("scenario", ["default", "tight", "partial", "long", "leverage_3x", "exact_basis"])
def test_every_accepted_exposure_increase_respects_the_cap_in_its_own_valuation(scenario: str) -> None:
    max_leverage = Fraction(1)
    w, policy = None, None
    if scenario == "tight":
        policy = polt.cited_policy(initial_equity=d(_ceil18(_risk_boundary())))
    elif scenario == "partial":
        w = world(records=market_records(book=book_with(quantity=10)))
    elif scenario == "long":
        w = world(records=market_records(rates=flipped()))
    elif scenario == "leverage_3x":
        max_leverage = Fraction(3)
        w = world(spec_changes={"risk_caps": {"max_leverage": 3}})
        policy = polt.cited_policy(initial_equity=d(_ceil18(_risk_boundary(w, max_leverage=3))))
    elif scenario == "exact_basis":
        result = exact_basis_result("short")
        _assert_increases_respect_cap(result, Fraction(1))
        return
    result = economics(w, policy=policy)
    _assert_receipt_invariants(result)
    _assert_increases_respect_cap(result, max_leverage)


def _assert_increases_respect_cap(result: HistoricalExecutionEconomicsResult, max_leverage: Fraction) -> None:
    valuations = {
        v.trigger_digest: v for v in result.valuations if v.valuation_kind is HistoricalExecutionValuationKind.FILL
    }
    increases = [
        t for t in result.position_transitions if abs(Fraction(t.post_quantity)) > abs(Fraction(t.prior_quantity))
    ]
    assert increases
    for transition in increases:
        valuation = valuations[transition.fill_digest]
        equity = Fraction(valuation.equity)
        assert equity > 0
        assert abs(Fraction(valuation.position_quantity)) * Fraction(valuation.mark_price) <= max_leverage * equity + (
            3 * ULP
        )


# --- external facts and governance --------------------------------------------------------------------------------------


def test_missing_citation_needs_external_facts_with_zero_execution() -> None:
    policy = polt.cited_policy(skip=(HistoricalExecutionFactId.TAKER_FEE_BPS,))
    _blocked(economics(policy=policy), EdgeGateVerdict.NEEDS_EXTERNAL_FACTS, "policy_not_advanced:NEEDS_EXTERNAL_FACTS")


def test_tampered_citation_rejects_the_result() -> None:
    policy = default_policy()
    tampered = [replace(c, evidence_digest="c" * 64) for c in policy.external_fact_citations]
    broken = build_historical_execution_economics_policy(**polt.policy_args(external_fact_citations=tampered))  # type: ignore[arg-type]
    result = economics(policy=broken)
    _assert_receipt_invariants(result)
    assert result.status is EdgeEvidenceStatus.REJECTED
    assert any(
        "policy_integrity_failure" in code or "policy_rejected" in code for code in result.integrity_reason_codes
    )


def test_missing_approval_needs_governance_with_zero_execution() -> None:
    _blocked(
        economics(economics_approval=None), EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL, "economics_approval_missing"
    )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("approved_economics_policy_digest", "1" * 64),
        ("approved_strategy_spec_digest", "2" * 64),
        ("approved_instrument", "ETH-USDT-PERP"),
        ("approved_market_type", "inverse_perp"),
        ("approved_data_requirement_registry_digest", "3" * 64),
        ("approved_quantity_semantics_id", "contracts_v1"),
        ("approved_execution_identity_digest", "4" * 64),
        ("approved_funding_identity_digest", "5" * 64),
    ],
)
def test_mismatched_approval_needs_governance_with_zero_execution(field_name: str, value: str) -> None:
    w = default_world()
    _blocked(
        economics(economics_approval=approval(w, default_policy(), **{field_name: value})),
        EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL,
        f"economics_approval_{field_name}_mismatch",
    )


def test_human_governance_approval_with_deep_research_citations_is_not_flagged_synthetic() -> None:
    policy = polt.cited_policy(kind=HistoricalExecutionCitationKind.DEEP_RESEARCH_CITED)
    result = economics(
        policy=policy,
        economics_approval=approval(
            default_world(), policy, approval_kind=HistoricalExecutionApprovalKind.HUMAN_GOVERNANCE
        ),
    )
    _assert_receipt_invariants(result)
    assert result.advances is True
    assert (result.synthetic_test_facts_used, result.synthetic_test_approval_used) == (False, False)
    assert default_result().synthetic_test_facts_used is True
    assert default_result().synthetic_test_approval_used is True


@pytest.mark.parametrize(
    "change", [{"latency_ns": 150}, {"taker_fee_bps": d(6)}, {"funding_interval_ns": INTERVAL + 1}]
)
def test_policy_substitution_cannot_reuse_the_old_approval(change: dict[str, object]) -> None:
    substitute = polt.cited_policy(**change)
    result = economics(policy=substitute, economics_approval=approval(default_world(), default_policy()))
    _assert_receipt_invariants(result)
    assert result.gate_verdict in (EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL, EdgeGateVerdict.FAIL)
    assert result.advances is False


def test_approval_from_another_strategy_spec_is_refused() -> None:
    other = world(spec_changes={"expected_regime": "negative_funding_regime"})
    _blocked(
        economics(economics_approval=approval(other, default_policy())),
        EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL,
        "economics_approval_approved_strategy_spec_digest_mismatch",
    )


# --- compatibility FAILs ------------------------------------------------------------------------------------------------


def test_inverse_perp_fails_closed_without_economics() -> None:
    inverse = world(spec_changes={"market_type": "inverse_perp"})
    result = economics(inverse, economics_approval=approval(inverse, default_policy(), market_type="inverse_perp"))
    _blocked(result, EdgeGateVerdict.FAIL, "market_type_unsupported_for_economics_v1")


def test_policy_must_explicitly_satisfy_the_spec_requirements() -> None:
    for change, code in (
        ({"satisfies_fee_model_requirement": "flat_fee"}, "spec_fee_model_requirement_unsatisfied"),
        ({"satisfies_slippage_model_requirement": "none"}, "spec_slippage_model_requirement_unsatisfied"),
        ({"satisfies_latency_sensitivity": "high"}, "spec_latency_sensitivity_unsatisfied"),
    ):
        policy = polt.cited_policy(**change)
        _blocked(
            economics(policy=policy, economics_approval=approval(default_world(), policy)), EdgeGateVerdict.FAIL, code
        )


def test_policy_for_another_instrument_fails() -> None:
    policy = polt.cited_policy(instrument="ETH-USDT-PERP")
    result = economics(policy=policy, economics_approval=approval(default_world(), policy, instrument="ETH-USDT-PERP"))
    _blocked(result, EdgeGateVerdict.FAIL, "economics_policy_instrument_mismatch")


def test_vintage_revised_economic_series_fails() -> None:
    w = world(revision={"mark_price": "revised_with_point_in_time_vintages"})
    _blocked(economics(w), EdgeGateVerdict.FAIL, "economic_series_revision_semantics_unsupported")


def test_non_advancing_run_propagates_without_economics() -> None:
    w = world(parameter_approval=None)
    _blocked(economics(w), EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL, "run_not_advanced:NEEDS_GOVERNANCE_APPROVAL")


# --- authority and transplants ------------------------------------------------------------------------------------------


def test_forged_or_mis_anchored_run_is_rejected() -> None:
    w = default_world()
    result = economics(w, expected_run_digest="a" * 64)
    _assert_receipt_invariants(result)
    assert result.status is EdgeEvidenceStatus.REJECTED
    assert _code("run_digest_mismatch") in result.integrity_reason_codes
    other = economics(w, correlation_id="corr-2")
    _assert_receipt_invariants(other)
    assert _code("run_correlation_mismatch") in other.integrity_reason_codes


@pytest.mark.parametrize(
    "field_name",
    ["strategy_spec_digest", "dataset_digest", "executable_binding_digest", "parameter_assignment_digest"],
)
def test_resealed_run_with_transplanted_authority_is_rejected(field_name: str) -> None:
    run = default_world().run
    forged = replace(run, **{field_name: "9" * 64})
    forged = replace(forged, run_digest=historical_decision_run_digest(forged))
    result = build_historical_execution_economics(
        forged,
        expected_run_digest=forged.run_digest,
        economics_policy=default_policy(),
        expected_economics_policy_digest=default_policy().policy_digest,
        economics_approval=approval(default_world(), default_policy()),
        result_id="result-1",
        correlation_id="corr-1",
    )
    _assert_receipt_invariants(result)
    assert result.status is EdgeEvidenceStatus.REJECTED


def test_carried_run_or_policy_transplant_never_verifies() -> None:
    other_run = economics(world(binding_id="binding-2"))
    transplanted = _reseal(default_result(), run_binding=other_run.run_binding, run_digest=other_run.run_digest)
    assert verify_historical_execution_economics(transplanted).intact is False
    other_policy = economics(policy=polt.cited_policy(latency_ns=150))
    transplanted = _reseal(default_result(), policy_binding=other_policy.policy_binding)
    assert verify_historical_execution_economics(transplanted).intact is False


# --- carried-ledger tamper ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: {"fills": (replace(r.fills[0], fill_price=d(1)),) + r.fills[1:]},
        lambda r: {"fills": partial_result().fills},
        lambda r: {"funding_cashflows": partial_result().funding_cashflows},
        lambda r: {"trades": partial_result().trades},
        lambda r: {"valuations": tuple(reversed(r.valuations))},
        lambda r: {"fills": r.fills + r.fills[:1]},
        lambda r: {"fee_cashflows": r.fee_cashflows + r.fee_cashflows[:1]},
        lambda r: {"terminal_state": replace(r.terminal_state, equity=d(1_000_000))},
        lambda r: {"intents": r.intents[1:]},
        lambda r: {"position_transitions": ()},
        lambda r: {"conformance": replace(r.conformance, almgren_chriss_modeled=True)},
        lambda r: {"conformance": replace(r.conformance, exact_internal_cost_basis_enforced=False)},
        lambda r: {"economics_approval": None},
        lambda r: {"gate_verdict": EdgeGateVerdict.FAIL},
    ],
    ids=[
        "resealed_fill_price",
        "copied_fills_new_parent",
        "copied_funding_new_parent",
        "copied_trades_new_parent",
        "reordered_ledger",
        "duplicate_fill",
        "duplicate_fee",
        "altered_terminal_state",
        "dropped_intent",
        "dropped_transitions",
        "forged_conformance",
        "forged_exact_basis_claim",
        "dropped_approval",
        "downgraded_verdict",
    ],
)
def test_resealed_or_transplanted_ledgers_never_verify(
    mutate: Callable[[HistoricalExecutionEconomicsResult], dict],
) -> None:
    result = default_result()
    verification = verify_historical_execution_economics(_reseal(result, **mutate(result)))
    assert verification.intact is False
    assert verification.reason_codes


# --- numeric authority --------------------------------------------------------------------------------------------------


def test_multiplication_overflow_fails_as_out_of_representation() -> None:
    big = Fraction(10) ** 40

    def mark(j: int) -> Values | None:
        return {"mark_price": d(big)}

    def book(j: int) -> Values | None:
        return {
            "best_bid_price": d(big - 1),
            "best_ask_price": d(big + 1),
            "best_bid_quantity": d(1_000),
            "best_ask_quantity": d(1_000),
        }

    w = world(
        records=market_records(mark=mark, book=book),
        spec_changes={"risk_caps": {"max_leverage": 3}},
        parameters=prof.params(unit=d(14)),
    )
    policy = polt.cited_policy(initial_equity=d(5 * big))
    _blocked(economics(w, policy=policy), EdgeGateVerdict.FAIL, "economic_value_out_of_representation:fill_notional")


def test_cumulative_equity_overflow_fails_as_out_of_representation() -> None:
    def mark(j: int) -> Values | None:
        return {"mark_price": d(price(j) + (100 if j > 60 else 0))}

    policy = polt.cited_policy(initial_equity=polt.SIXTY_POSITIVE)
    _blocked(
        economics(world(records=market_records(mark=mark)), policy=policy),
        EdgeGateVerdict.FAIL,
        "economic_value_out_of_representation:equity",
    )


def test_every_emitted_amount_is_canonical_scale18() -> None:
    for result in (partial_result(), exact_basis_result("long")):
        payload = historical_execution_economics_to_dict(result)

        def walk(value: object) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in ("run_binding", "policy_binding"):
                        continue
                    if isinstance(item, str) and "." in item and item.replace(".", "").replace("-", "").isdigit():
                        assert polt.historical_execution_decimal_is_canonical(item), (key, item)
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(payload)


@pytest.mark.parametrize("context_name", sorted(prof._AMBIENT_CONTEXTS))
def test_result_bytes_are_independent_of_the_ambient_decimal_context(context_name: str) -> None:
    baseline = default_result()
    with decimal.localcontext(prof._AMBIENT_CONTEXTS[context_name]()) as active:
        before = prof.context_state(active)
        result = economics()
        verification = verify_historical_execution_economics(result)
        assert prof.context_state(decimal.getcontext()) == before
    assert result.result_digest == baseline.result_digest
    assert verification.intact is True
    assert verification.canonical_json == verify_historical_execution_economics(baseline).canonical_json


def test_result_is_byte_identical_deterministic() -> None:
    first = economics()
    second = economics()
    assert edge_canonical_json(historical_execution_economics_to_dict(first)) == edge_canonical_json(
        historical_execution_economics_to_dict(second)
    )


# --- malformed input, totality and parity -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"result_id": "result scheduler"}, "result_id"),
        ({"result_id": ""}, "result_id_invalid"),
        ({"correlation_id": None}, "correlation_id_invalid"),
        ({"economics_approval": "approved"}, "economics_approval_malformed"),
        ({"expected_run_digest": "x"}, "run_expected_digest_invalid"),
        ({"expected_economics_policy_digest": None}, "policy_expected_digest_invalid"),
    ],
)
def test_malformed_caller_input_is_a_construction_error(overrides: dict[str, object], code: str) -> None:
    with pytest.raises(HistoricalExecutionEconomicsError, match=code):
        economics(**overrides)


def test_foreign_upstream_objects_are_construction_errors() -> None:
    w = default_world()
    for run, policy, code in (
        (w.dataset, default_policy(), "run_malformed"),
        (
            w.run,
            polt.approval_for(
                default_policy(), strategy_spec_digest="e" * 64, data_requirement_registry_digest="f" * 64
            ),
            "policy_malformed",
        ),
        (object.__new__(HistoricalDecisionRun), default_policy(), "run_not_serializable"),
        (w.run, object.__new__(HistoricalExecutionEconomicsPolicy), "policy_not_serializable"),
    ):
        with pytest.raises(HistoricalExecutionEconomicsError, match=code):
            build_historical_execution_economics(
                run,  # type: ignore[arg-type]
                expected_run_digest=w.run.run_digest,
                economics_policy=policy,  # type: ignore[arg-type]
                expected_economics_policy_digest=default_policy().policy_digest,
                economics_approval=None,
                result_id="result-1",
                correlation_id="corr-1",
            )


def _corrupted(**changes: object) -> HistoricalExecutionEconomicsResult:
    copy = replace(default_result())
    for name, value in changes.items():
        object.__setattr__(copy, name, value)
    return copy


class _LyingEquality:
    def __eq__(self, other: object) -> bool:
        return True

    def __hash__(self) -> int:
        raise RuntimeError("hostile hash")


class _RaisingIterator:
    def __iter__(self):
        raise RuntimeError("hostile iterator")


@pytest.mark.parametrize(
    "artifact",
    [
        None,
        7,
        True,
        "result",
        b"result",
        {},
        [],
        object(),
        object.__new__(HistoricalExecutionEconomicsResult),
        "dict_payload",
        _corrupted(fills=None),
        _corrupted(fills=({"fill_id": "x"},)),
        _corrupted(fills=_RaisingIterator()),
        _corrupted(run_binding=None),
        _corrupted(policy_binding="policy"),
        _corrupted(economics_approval="approved"),
        _corrupted(terminal_state=1),
        _corrupted(evaluation_end_ns=10**5000),
        _corrupted(status="ACCEPTED"),
        _corrupted(performance_metrics_computed=True),
        _corrupted(valuations=(object(),)),
        _corrupted(result_digest=_LyingEquality()),
        _corrupted(correlation_id=_LyingEquality()),
    ],
    ids=lambda value: type(value).__name__,
)
def test_public_verifier_is_total_for_any_object(artifact: object) -> None:
    if artifact == "dict_payload":
        artifact = historical_execution_economics_to_dict(default_result())
    verification = verify_historical_execution_economics(artifact)
    assert type(verification) is EdgeEvidenceVerification
    assert verification.intact is False
    assert verification.reason_codes


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("fills", 0, "fill_price"), 100.5),
        (("fills", 0, "fill_price"), polt.SIXTY_ONE),
        (("fills", 0, "outcome"), "MAYBE"),
        (("fills", 0, "execution_time_ns"), 9223372036854775808),
        (("valuations", 0, "time_ns"), -1),
        (("intents", 0, "close_only_clamped"), "false"),
        (("terminal_state", "equity"), "1.5"),
        (("economics_approval", "approval_kind"), "SELF"),
        (("run_binding", "snapshot"), {}),
        (("policy_binding",), None),
        (("parameter_approval",), {"approval_reference": "x"}),
        (("conformance", "almgren_chriss_modeled"), "false"),
        (("venue_fill_truth_proven",), 0),
    ],
    ids=lambda value: str(value)[:32],
)
def test_parser_refuses_states_the_builder_cannot_produce(path: tuple[object, ...], value: object) -> None:
    payload = historical_execution_economics_to_dict(default_result())
    target: object = payload
    for step in path[:-1]:
        target = target[step]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    assert historical_execution_economics_payload_is_well_formed(payload) is False


def test_every_builder_state_round_trips_through_the_verifier() -> None:
    inverse = world(spec_changes={"market_type": "inverse_perp"})
    for result in (
        default_result(),
        partial_result(),
        exact_basis_result("short"),
        economics(inverse, economics_approval=approval(inverse, default_policy(), market_type="inverse_perp")),
        economics(policy=build_historical_execution_economics_policy(**polt.policy_args())),  # type: ignore[arg-type]
        economics(economics_approval=None),
        economics(correlation_id="corr-2"),
    ):
        _assert_receipt_invariants(result)


# --- scope, non-claims and purity ---------------------------------------------------------------------------------------

_METRIC_TOKENS = (
    "sharpe",
    "sortino",
    "hit_rate",
    "expectancy",
    "profit_factor",
    "drawdown",
    "win_rate",
    "calmar",
    "pbo",
)


def test_no_metric_or_later_gate_fields_exist() -> None:
    flags = {name for name, _ in HISTORICAL_EXECUTION_NON_CLAIM_FLAGS}
    for cls in (
        HistoricalExecutionEconomicsResult,
        *(
            getattr(economics_module, name)
            for name in economics_module.__all__
            if name.startswith("HistoricalExecution")
        ),
    ):
        if not isinstance(cls, type) or not hasattr(cls, "__dataclass_fields__"):
            continue
        for item in fields(cls):
            if item.name in flags:
                continue
            assert not [token for token in _METRIC_TOKENS if token in item.name], (cls.__name__, item.name)
            assert "ef5" not in item.name and "ef6" not in item.name and "stress" not in item.name


def test_structural_non_claims_are_defaults_no_builder_parameter_can_set() -> None:
    flags = dict(HISTORICAL_EXECUTION_NON_CLAIM_FLAGS)
    assert set(dict(EDGE_STRUCTURAL_NON_CLAIM_FLAGS)) <= set(flags)
    for name in (
        "edge_proven",
        "profitability_proven",
        "candidate_admitted_to_paper",
        "pbo_passed",
        "stress_passed",
        "performance_metrics_computed",
        "operational_readiness",
        "live_ready",
        "shadow_ready",
        "private_api_ready",
        "real_orders_enabled",
        "real_money_enabled",
        "real_capital_reserved",
        "external_archive_truth_proven",
        "venue_fill_truth_proven",
    ):
        assert flags[name] is False
    defaults = {item.name: item.default for item in fields(HistoricalExecutionEconomicsResult) if item.name in flags}
    assert defaults == flags
    result = default_result()
    assert all(getattr(result, name) is value for name, value in flags.items())


@pytest.mark.parametrize("flag", ["edge_proven", "profitability_proven", "venue_fill_truth_proven", "live_ready"])
def test_forged_non_claim_flags_fail_verification(flag: str) -> None:
    verification = verify_historical_execution_economics(_reseal(default_result(), **{flag: True}))
    assert verification.intact is False
    assert _code(f"field_mismatch:{flag}") in verification.reason_codes


def test_conformance_false_fields_remain_false_in_the_result() -> None:
    conformance = default_result().conformance
    assert conformance is not None
    assert (
        conformance.almgren_chriss_modeled,
        conformance.maker_rebate_modeled,
        conformance.lot_tick_rounding_modeled,
        conformance.margin_liquidation_modeled,
        conformance.inverse_contract_modeled,
    ) == (False, False, False, False, False)
    assert (
        conformance.same_observation_fill_prohibited,
        conformance.fill_ratio_model_enforced,
        conformance.zero_slippage_prohibited,
        conformance.positive_latency_enforced,
        conformance.visible_depth_cap_enforced,
        conformance.time_varying_spread_enforced,
        conformance.actual_final_funding_stream_required,
        conformance.exact_internal_cost_basis_enforced,
    ) == (True,) * 8


_FORBIDDEN_IDENTIFIERS = (
    "bist",
    "borsa",
    "paperorderintent",
    "place_order",
    "submit_order",
    "int_max_str_digits",
    "mt4",
    "machine_time",
    "sharpe",
    "expectancy",
    "profit_factor",
    "hit_rate",
    "drawdown",
    "almgren",
)
_ALLOWED_CRYPTO_IMPORTS = {
    "crypto_core.strategy.spec",
    "crypto_core.validation.edge_artifact_core",
    "crypto_core.validation.edge_strategy_spec_admission",
    "crypto_core.validation.historical_decision_run",
    "crypto_core.validation.historical_execution_economics_policy",
    "crypto_core.validation.historical_pit_dataset",
    "crypto_core.validation.strategy_executable_binding",
}


def test_module_is_pure_and_imports_no_paper_or_runtime_authority() -> None:
    source = Path(economics_module.__file__).read_text(encoding="utf-8")
    crypto_imports: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(alias.name == mod or alias.name.startswith(f"{mod}.") for mod in pit.FORBIDDEN_MODULES)
                assert not alias.name.startswith("crypto_core")
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(node.module == mod or node.module.startswith(f"{mod}.") for mod in pit.FORBIDDEN_MODULES)
            if node.module.startswith("crypto_core"):
                crypto_imports.add(node.module)
                assert not {alias.name for alias in node.names if alias.name.startswith("_")}
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            assert name not in pit.FORBIDDEN_CALLS, name
            assert not (isinstance(node.func, ast.Name) and name in pit.FORBIDDEN_BUILTINS), name
        if isinstance(node, ast.Constant):
            assert type(node.value) is not float
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"environ", "__globals__", "__code__"}
    assert crypto_imports == _ALLOWED_CRYPTO_IMPORTS
    lowered = source.lower()
    assert not [token for token in _FORBIDDEN_IDENTIFIERS if token in lowered]
    assert "decimal" not in {
        alias.name for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Import) for alias in node.names
    }


def test_single_assembly_path_serves_builder_and_verifier() -> None:
    pit.assert_single_assembly_path(
        economics_module,
        "HistoricalExecutionEconomicsResult",
        "_assemble_result",
        "build_historical_execution_economics",
        "_reassemble_result",
    )
