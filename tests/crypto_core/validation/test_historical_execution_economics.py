"""Tests for deterministic historical execution economics (DETERMINISTIC_HISTORICAL_EXECUTION_ECONOMICS_V1)."""

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
    HistoricalExecutionIntentAction,
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


def default_mark(j: int) -> Values | None:
    return {"mark_price": d(price(j))}


def book_with(*, half_spread: object = "0.05", quantity: object = 100) -> Callable[[int], Values | None]:
    def book(j: int) -> Values | None:
        mid = price(j)
        return {
            "best_bid_price": d(mid - Fraction(str(half_spread))),
            "best_ask_price": d(mid + Fraction(str(half_spread))),
            "best_bid_quantity": d(quantity),
            "best_ask_quantity": d(quantity),
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
) -> tuple[HistoricalPitRecord, ...]:
    """Funding every INTERVAL; marks and books every 1000 ns; extras renumbered by time.

    ``funding_times`` and ``funding_overrides`` are ``(available, finalized)`` offsets from the funding window open
    (``event_time``). The default publishes and finalizes a record after its own cycle closes, as
    ``finality=funding_cycle_closed`` requires; a ``None`` finalized offset is a record that never becomes final.
    """

    records = [
        _record(
            "funding-final",
            "funding_rate",
            k,
            BASE + k * INTERVAL,
            {"funding_rate": rate},
            *(funding_overrides or {}).get(k, funding_times),
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


# --- happy path: frozen H1 trace executed under the approved policy ----------------------------------------------------


def test_default_result_is_ready_pass_and_re_proves() -> None:
    result = default_result()
    _assert_receipt_invariants(result)
    assert (result.status, result.gate_verdict, result.advances) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.PASS,
        True,
    )
    run = default_world().run
    assert result.run_digest == run.run_digest
    assert result.dataset_digest == run.dataset_digest
    assert result.source_manifest_digest == run.source_manifest_digest
    assert result.data_requirement_registry_digest == default_world().registry_digest
    assert result.executable_binding_digest == run.executable_binding_digest
    assert result.strategy_spec_digest == run.strategy_spec_digest
    assert result.profile_semantics_digest == run.profile_semantics_digest
    assert result.parameter_assignment_digest == run.parameter_assignment_digest
    assert result.parameter_approval == run.parameter_approval
    assert result.economics_policy_digest == default_policy().policy_digest
    assert (result.instrument, result.market_type) == (INS, "usdt_perp")
    assert (result.funding_series_id, result.mark_series_id, result.order_book_series_id) == (
        "funding-final",
        "mark",
        "book",
    )
    assert result.synthetic_test_facts_used is True
    assert result.synthetic_test_approval_used is True


def test_intents_follow_only_the_frozen_decision_targets() -> None:
    result = default_result()
    decisions = {decision.decision_digest: decision for decision in default_world().run.decisions}
    assert [(intent.action, intent.requested_quantity) for intent in result.intents] == [
        (HistoricalExecutionIntentAction.SELL, d(1)),
        (HistoricalExecutionIntentAction.CLOSE_SHORT, d(1)),
        (HistoricalExecutionIntentAction.BUY, d(1)),
    ]
    assert [decisions[intent.decision_digest].action for intent in result.intents] == ["SHORT", "EXIT", "LONG"]
    for intent in result.intents:
        assert intent.decision_time_ns == decisions[intent.decision_digest].decision_time_ns
        assert intent.earliest_execution_time_ns == intent.decision_time_ns + default_policy().latency_ns
    hold_or_idle = [d for d in default_world().run.decisions if d.action in ("HOLD", "NO_ACTION")]
    assert hold_or_idle
    assert not {d.decision_digest for d in hold_or_idle} & {intent.decision_digest for intent in result.intents}


def test_fill_prices_follow_the_governed_cost_composition() -> None:
    fill = default_result().fills[0]
    assert (fill.outcome, fill.reason, fill.side.value) == (HistoricalExecutionFillOutcome.FILLED, "filled", "SELL")
    mid = price(20)
    spread_bps = Fraction("0.1") / mid * 10_000
    effective = max(Fraction(5), spread_bps / 2 + Fraction("0.5") * 1)
    assert fill.mid_price == d(mid)
    assert fill.spread_bps == d(spread_bps)
    assert fill.participation_pct == d(1)
    assert fill.impact_bps == d("0.5")
    assert fill.effective_slippage_bps == d(effective)
    assert fill.fill_price == d(mid * (1 - effective / 10_000))
    assert (fill.filled_quantity, fill.cancelled_quantity, fill.fill_ratio) == (d(1), d(0), d(1))
    assert _t(fill.execution_time_ns) == 20_502
    assert fill.book_event_time_ns > default_world().run.decisions[1].decision_time_ns


def test_slippage_floor_applies_when_spread_and_impact_are_small() -> None:
    result = economics(world(records=market_records(book=book_with(half_spread="0.001"))))
    fill = result.fills[0]
    assert Fraction(fill.half_spread_bps) + Fraction(fill.impact_bps) < 5
    assert fill.effective_slippage_bps == d(5)


def test_static_spread_is_impossible_prices_track_the_observed_book() -> None:
    narrow = economics(world(records=market_records(book=book_with(half_spread="0.05")))).fills[0]
    wide = economics(world(records=market_records(book=book_with(half_spread="0.2")))).fills[0]
    assert narrow.spread_bps != wide.spread_bps
    assert Fraction(wide.effective_slippage_bps) > Fraction(narrow.effective_slippage_bps)
    policy_fields = {item.name for item in fields(HistoricalExecutionEconomicsPolicy)}
    assert not {"static_spread_bps", "fixed_spread_bps", "spread_bps"} & policy_fields


# --- funding ------------------------------------------------------------------------------------------------------------


def test_funding_signs_and_liability_semantics() -> None:
    result = default_result()
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
        record = next(r for r in default_world().dataset.records if r.record_digest == cashflow.funding_record_digest)
        assert cashflow.liability_time_ns == record.event_time_ns + INTERVAL
        assert cashflow.funding_event_time_ns == record.event_time_ns


def test_long_pays_positive_funding() -> None:
    rates = ("-0.000200000000000000", "-0.000300000000000000", "0.000100000000000000") + RATES[3:]
    result = economics(world(records=market_records(rates=rates)))
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
    def book(j: int) -> Values | None:
        return None if 20 <= j < 30 else default_book(j)

    extra = ((BASE + 29_998, 1, default_book(29)),)  # visible exactly at the liability instant BASE + 30_000
    policy = polt.cited_policy(max_execution_delay_ns=10_000)
    result = economics(world(records=market_records(book=book, extra_books=extra)), policy=policy)
    _assert_receipt_invariants(result)
    entry = result.fills[0]
    assert _t(entry.execution_time_ns) == 30_000
    assert entry.outcome is HistoricalExecutionFillOutcome.FILLED
    assert 30_000 not in [_t(c.liability_time_ns) for c in result.funding_cashflows]
    kinds = [(v.valuation_kind, _t(v.time_ns)) for v in result.valuations if _t(v.time_ns) == 30_000]
    assert kinds == [(HistoricalExecutionValuationKind.FILL, 30_000)]


def test_missing_funding_coverage_fails_without_interpolation() -> None:
    records = market_records(rates=RATES[:8])
    result = economics(world(records=records, end=BASE + 9 * INTERVAL + 5_000))
    _blocked(result, EdgeGateVerdict.FAIL, "funding_coverage_incomplete")


def test_funding_interval_must_match_the_approved_interval() -> None:
    policy = polt.cited_policy(funding_interval_ns=INTERVAL - 1)
    _blocked(economics(policy=policy), EdgeGateVerdict.FAIL, "funding_interval_inconsistent")


def test_duplicate_funding_records_never_reach_economics() -> None:
    records = market_records()
    duplicate = replace(records[3], values=(HistoricalPitValue("funding_rate", RATES[0]),))
    duplicate = replace(
        duplicate, record_digest=runt.historical_pit_record_digest(replace(duplicate, record_digest=""))
    )
    w = world(records=records + (duplicate,))
    assert w.dataset.status is EdgeEvidenceStatus.REJECTED
    result = economics(w)
    _assert_receipt_invariants(result)
    assert result.integrity_reason_codes == (_code("run_rejected"),)


# --- funding cycle finality ---------------------------------------------------------------------------------------------


def test_funding_final_before_its_own_cycle_closes_fails_before_any_simulation() -> None:
    w = world(records=market_records(funding_times=(0, 0)))  # published and "final" already at the window open
    assert (w.run.status, w.run.gate_verdict) == (EdgeEvidenceStatus.READY, EdgeGateVerdict.PASS)
    entry_decision = next(d for d in w.run.decisions if d.resulting_direction == "SHORT")
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


def test_never_final_funding_keeps_its_coverage_failure() -> None:
    w = world(records=market_records(funding_overrides={2: (INTERVAL + 10, None)}))
    _blocked(economics(w), EdgeGateVerdict.FAIL, "funding_coverage_incomplete")


def test_a_liability_instant_outside_the_wire_domain_fails_closed() -> None:
    edge = build_historical_pit_record(
        series_id="funding-final",
        data_requirement_key="funding_rate",
        instrument=INS,
        sequence_id=len(RATES),
        event_time_ns=polt.INT64_MAX,
        available_at_ns=polt.INT64_MAX,
        finalized_at_ns=polt.INT64_MAX,
        revision_vintage_id=None,
        values=(HistoricalPitValue("funding_rate", RATES[0]),),
    )
    w = world(records=market_records() + (edge,))
    assert w.run.gate_verdict is EdgeGateVerdict.PASS
    _blocked(economics(w), EdgeGateVerdict.FAIL, "economic_value_out_of_representation:funding_liability_time_ns")


def test_no_settlement_pays_a_rate_its_own_entry_decision_could_not_know() -> None:
    for w in (default_world(), world(records=market_records(funding_times=(INTERVAL, INTERVAL)))):
        result = economics(w)
        assert result.advances is True
        decisions = {d.decision_digest: d for d in w.run.decisions}
        fills = {f.fill_digest: f for f in result.fills}
        for cashflow in result.funding_cashflows:
            liable = [t for t in result.position_transitions if t.time_ns < cashflow.liability_time_ns]
            decision = decisions[fills[liable[-1].fill_digest].decision_digest]
            if decision.decision_time_ns < cashflow.liability_time_ns:
                assert cashflow.funding_record_digest not in decision.input_record_digests


def test_the_funding_finality_failure_is_re_derived_and_cannot_be_resealed_away() -> None:
    failed = economics(world(records=market_records(funding_times=(0, 0))))
    assert verify_historical_execution_economics(failed).intact is True
    good = default_result()
    upgraded = _reseal(
        failed,
        gate_verdict=EdgeGateVerdict.PASS,
        advances=True,
        simulated_economics_computed=True,
        verdict_reason_codes=(),
        fills=good.fills,
        funding_cashflows=good.funding_cashflows,
        valuations=good.valuations,
        terminal_state=good.terminal_state,
    )
    assert verify_historical_execution_economics(upgraded).intact is False


def test_the_funding_repair_never_re_runs_the_frozen_decision_trace() -> None:
    w = world(records=market_records(funding_times=(0, 0)))
    failed = economics(w)
    snapshot = json.loads(failed.run_binding.snapshot_json)
    expected = json.loads(edge_canonical_json(runt.historical_decision_run_to_dict(w.run)))
    assert snapshot["decisions"] == expected["decisions"]
    assert (failed.intents, failed.position_transitions) == ((), ())


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
        assert Fraction(valuation.equity) == expected
        if Fraction(valuation.position_quantity) == 0:
            assert (valuation.mark_price, valuation.unrealized_pnl) == (None, d(0))
        else:
            assert valuation.mark_price is not None
            assert Fraction(valuation.unrealized_pnl) == Fraction(valuation.position_quantity) * (
                Fraction(valuation.mark_price) - Fraction(valuation.average_entry_price)
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
    executed = [
        f
        for f in result.fills
        if f.outcome in (HistoricalExecutionFillOutcome.FILLED, HistoricalExecutionFillOutcome.PARTIALLY_FILLED)
    ]
    assert [f.fill_digest for f in result.fee_cashflows] == [f.fill_digest for f in executed]
    for fee, fill in zip(result.fee_cashflows, executed, strict=True):
        assert fee.taker_fee_bps == default_policy().taker_fee_bps
        assert Fraction(fee.fee_amount) == Fraction(fill.fill_price) * Fraction(fill.filled_quantity) * 5 / 10_000
        assert Fraction(fee.fee_amount) >= 0
    assert Fraction(result.terminal_state.cumulative_fees) == sum(Fraction(f.fee_amount) for f in result.fee_cashflows)


# --- partial fills, divergence reconciliation, close-only clamp --------------------------------------------------------


@functools.cache
def partial_result() -> HistoricalExecutionEconomicsResult:
    return economics(world(records=market_records(book=book_with(quantity=10))))


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
    assert Fraction(reduce.realized_gross_pnl) == Fraction(reduce.closed_quantity) * (
        Fraction(reduce.prior_average_entry_price) - Fraction(result.fills[3].fill_price)
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
    rates = tuple(r[1:] if r.startswith("-") else "-" + r for r in RATES)
    result = economics(world(records=market_records(rates=rates, book=book_with(quantity=10))))
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


# --- risk ---------------------------------------------------------------------------------------------------------------


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


# --- risk: the cap binds the candidate POST-fill state, including this fill's own fee and mark-to-market ---------------

_UNIT = Fraction(1, 10**18)
_REFERENCE_EQUITY = Fraction(10_000)


def _first_fill_valuation(result: HistoricalExecutionEconomicsResult) -> HistoricalExecutionValuation:
    return next(v for v in result.valuations if v.valuation_kind is HistoricalExecutionValuationKind.FILL)


def _candidate_carry(w: World | None = None, **policy_overrides: object) -> tuple[Fraction, Fraction]:
    """``(post-fill notional, carry)`` of the first fill, where carry is its own fee plus mark-to-market.

    The carry does not depend on initial equity, so ``notional - carry`` is the exact initial equity at which the
    accepted FILL valuation would sit precisely on the authenticated ``max_leverage`` boundary of 1x.
    """

    policy = polt.cited_policy(initial_equity=d(_REFERENCE_EQUITY), **policy_overrides)
    valuation = _first_fill_valuation(economics(w, policy=policy))
    notional = abs(Fraction(valuation.position_quantity)) * Fraction(valuation.mark_price)
    return notional, Fraction(valuation.equity) - _REFERENCE_EQUITY


def _risk_reasons(result: HistoricalExecutionEconomicsResult) -> list[str]:
    return [f.reason for f in result.fills]


def test_pre_fill_equity_alone_no_longer_authorizes_a_fill() -> None:
    notional, carry = _candidate_carry()
    assert carry < 0  # the fee and the adverse fill-versus-mark move both cost equity
    result = economics(policy=polt.cited_policy(initial_equity=d(notional)))  # the old pre-fill boundary
    _assert_receipt_invariants(result)
    assert _risk_reasons(result) == ["risk_limit_exceeded"] * len(result.fills)
    assert (result.position_transitions, result.fee_cashflows) == ((), ())


def test_the_exact_post_fill_boundary_is_accepted_and_one_scale_unit_below_is_rejected() -> None:
    notional, carry = _candidate_carry()
    boundary = notional - carry
    accepted = economics(policy=polt.cited_policy(initial_equity=d(boundary)))
    _assert_receipt_invariants(accepted)
    assert accepted.fills[0].outcome is HistoricalExecutionFillOutcome.FILLED
    valuation = _first_fill_valuation(accepted)
    assert abs(Fraction(valuation.position_quantity)) * Fraction(valuation.mark_price) == Fraction(valuation.equity)
    rejected = economics(policy=polt.cited_policy(initial_equity=d(boundary - _UNIT)))
    assert rejected.fills[0].reason == "risk_limit_exceeded"


def test_a_high_taker_fee_is_charged_to_the_candidate_state() -> None:
    expensive = {"taker_fee_bps": d(500)}
    notional, carry = _candidate_carry()
    on_the_cheap_boundary = economics(policy=polt.cited_policy(initial_equity=d(notional - carry), **expensive))
    assert on_the_cheap_boundary.fills[0].reason == "risk_limit_exceeded"
    expensive_notional, expensive_carry = _candidate_carry(**expensive)
    assert expensive_carry < carry
    accepted = economics(policy=polt.cited_policy(initial_equity=d(expensive_notional - expensive_carry), **expensive))
    assert accepted.fills[0].outcome is HistoricalExecutionFillOutcome.FILLED


def test_the_adverse_fill_versus_mark_alone_can_breach_the_cap() -> None:
    free = {"taker_fee_bps": d(0)}
    notional, carry = _candidate_carry(**free)
    assert carry < 0  # no fee at all: the fill price is worse than the mark
    rejected = economics(policy=polt.cited_policy(initial_equity=d(notional), **free))
    assert rejected.fills[0].reason == "risk_limit_exceeded"
    accepted = economics(policy=polt.cited_policy(initial_equity=d(notional - carry), **free))
    assert accepted.fills[0].outcome is HistoricalExecutionFillOutcome.FILLED


def test_fee_and_mark_to_market_are_both_required_to_clear_the_cap() -> None:
    free_notional, free_carry = _candidate_carry(**{"taker_fee_bps": d(0)})
    covers_only_the_mark_to_market = free_notional - free_carry
    result = economics(policy=polt.cited_policy(initial_equity=d(covers_only_the_mark_to_market)))
    assert result.fills[0].reason == "risk_limit_exceeded"


@pytest.mark.parametrize(
    "gap", [Fraction(0), -_UNIT, Fraction(-1, 20)], ids=["zero", "one_unit_below_zero", "negative"]
)
def test_a_candidate_post_fill_equity_at_or_below_zero_is_rejected(gap: Fraction) -> None:
    _, carry = _candidate_carry()
    result = economics(policy=polt.cited_policy(initial_equity=d(gap - carry)))  # post-fill equity lands on gap
    _assert_receipt_invariants(result)
    assert result.advances is True
    assert _risk_reasons(result) == ["risk_limit_exceeded"] * len(result.fills)
    assert result.position_transitions == ()


def test_the_partial_fill_boundary_uses_the_filled_quantity_and_its_own_fee() -> None:
    w = world(records=market_records(book=book_with(quantity=10)))
    notional, carry = _candidate_carry(w)
    reference = economics(w, policy=polt.cited_policy(initial_equity=d(_REFERENCE_EQUITY)))
    assert reference.fills[0].outcome is HistoricalExecutionFillOutcome.PARTIALLY_FILLED
    assert Fraction(reference.fills[0].filled_quantity) == Fraction("0.2")
    accepted = economics(w, policy=polt.cited_policy(initial_equity=d(notional - carry)))
    assert accepted.fills[0].outcome is HistoricalExecutionFillOutcome.PARTIALLY_FILLED
    rejected = economics(w, policy=polt.cited_policy(initial_equity=d(notional - carry - _UNIT)))
    assert rejected.fills[0].reason == "risk_limit_exceeded"


@pytest.mark.parametrize("direction", ["short", "long"], ids=["short", "long"])
def test_increases_are_capped_while_reductions_and_closes_still_execute(direction: str) -> None:
    rates = RATES if direction == "short" else tuple(r[1:] if r.startswith("-") else "-" + r for r in RATES)
    w = world(records=market_records(rates=rates, book=book_with(quantity=10)))
    notional, carry = _candidate_carry(w)
    result = economics(w, policy=polt.cited_policy(initial_equity=d(notional - carry)))
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


@pytest.mark.parametrize("scenario", ["default", "tight", "partial", "long", "leverage_3x"])
def test_every_accepted_exposure_increase_respects_the_cap_in_its_own_valuation(scenario: str) -> None:
    max_leverage = Fraction(1)
    w, policy = None, None
    if scenario == "tight":
        notional, carry = _candidate_carry()
        policy = polt.cited_policy(initial_equity=d(notional - carry))
    elif scenario == "partial":
        w = world(records=market_records(book=book_with(quantity=10)))
    elif scenario == "long":
        rates = tuple(r[1:] if r.startswith("-") else "-" + r for r in RATES)
        w = world(records=market_records(rates=rates))
    elif scenario == "leverage_3x":
        max_leverage = Fraction(3)
        w = world(spec_changes={"risk_caps": {"max_leverage": 3}})
        notional, carry = _candidate_carry(w)
        policy = polt.cited_policy(initial_equity=d(notional / 3 - carry + Fraction(1, 1_000)))
    result = economics(w, policy=policy)
    _assert_receipt_invariants(result)
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
        assert abs(Fraction(valuation.position_quantity)) * Fraction(valuation.mark_price) <= max_leverage * equity


# --- external facts and governance --------------------------------------------------------------------------------------


def test_missing_citation_needs_external_facts_with_zero_execution() -> None:
    policy = polt.cited_policy(skip=(HistoricalExecutionFactId.TAKER_FEE_BPS,))
    _blocked(economics(policy=policy), EdgeGateVerdict.NEEDS_EXTERNAL_FACTS, "policy_not_advanced:NEEDS_EXTERNAL_FACTS")


def test_tampered_citation_rejects_the_result() -> None:
    policy = polt.cited_policy()
    tampered = [replace(c, evidence_digest="c" * 64) for c in policy.external_fact_citations]
    rejected = build_historical_execution_economics_policy(**polt.policy_args(external_fact_citations=tampered))  # type: ignore[arg-type]
    result = economics(policy=rejected)
    _assert_receipt_invariants(result)
    assert result.integrity_reason_codes == (_code("policy_rejected"),)


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
    mismatched = approval(default_world(), default_policy(), **{field_name: value})
    _blocked(
        economics(economics_approval=mismatched),
        EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL,
        f"economics_approval_{field_name}_mismatch",
    )


def test_human_governance_approval_with_deep_research_citations_is_not_flagged_synthetic() -> None:
    policy = polt.cited_policy(kind=HistoricalExecutionCitationKind.DEEP_RESEARCH_CITED)
    human = approval(default_world(), policy, approval_kind=HistoricalExecutionApprovalKind.HUMAN_GOVERNANCE)
    result = economics(policy=policy, economics_approval=human)
    assert result.advances is True
    assert (result.synthetic_test_facts_used, result.synthetic_test_approval_used) == (False, False)


@pytest.mark.parametrize(
    "change",
    [{"taker_fee_bps": d(6)}, {"slippage_floor_bps": d(6)}, {"funding_interval_ns": INTERVAL + 1}],
    ids=["fee", "slippage", "funding"],
)
def test_policy_substitution_cannot_reuse_the_old_approval(change: dict[str, object]) -> None:
    substituted = polt.cited_policy(**change)
    old = approval(default_world(), default_policy())
    result = economics(policy=substituted, economics_approval=old)
    assert result.advances is False
    assert _code("economics_approval_approved_economics_policy_digest_mismatch") in result.verdict_reason_codes
    carried = _reseal(
        default_result(), policy_binding=result.policy_binding, economics_policy_digest=substituted.policy_digest
    )
    assert verify_historical_execution_economics(carried).intact is False


def test_approval_from_another_strategy_spec_is_refused() -> None:
    other = world(spec_changes={"latency_sensitivity": "low", "expected_regime": "negative_funding_regime"})
    foreign = approval(other, default_policy())
    assert foreign.approved_strategy_spec_digest != default_world().run.strategy_spec_digest
    _blocked(
        economics(economics_approval=foreign),
        EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL,
        "economics_approval_approved_strategy_spec_digest_mismatch",
    )


# --- compatibility FAILs ------------------------------------------------------------------------------------------------


def test_inverse_perp_fails_closed_without_economics() -> None:
    w = world(spec_changes={"market_type": "inverse_perp"})
    assert w.run.advances is True
    result = economics(w, economics_approval=approval(w, default_policy(), market_type="inverse_perp"))
    _blocked(result, EdgeGateVerdict.FAIL, "market_type_unsupported_for_economics_v1")


def test_policy_must_explicitly_satisfy_the_spec_requirements() -> None:
    policy = polt.cited_policy(satisfies_fee_model_requirement="flat_fee_schedule")
    _blocked(economics(policy=policy), EdgeGateVerdict.FAIL, "spec_fee_model_requirement_unsatisfied")
    policy = polt.cited_policy(satisfies_slippage_model_requirement="zero_impact")
    _blocked(economics(policy=policy), EdgeGateVerdict.FAIL, "spec_slippage_model_requirement_unsatisfied")
    policy = polt.cited_policy(satisfies_latency_sensitivity="high")
    _blocked(economics(policy=policy), EdgeGateVerdict.FAIL, "spec_latency_sensitivity_unsatisfied")


def test_policy_for_another_instrument_fails() -> None:
    policy = polt.cited_policy(instrument="ETH-USDT-PERP")
    _blocked(economics(policy=policy), EdgeGateVerdict.FAIL, "economics_policy_instrument_mismatch")


def test_vintage_revised_economic_series_fails() -> None:
    w = world(revision={"mark_price": "revised_with_point_in_time_vintages"})
    _blocked(economics(w), EdgeGateVerdict.FAIL, "economic_series_revision_semantics_unsupported")


def test_non_advancing_run_propagates_without_economics() -> None:
    w = world(parameter_approval=None)
    assert w.run.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    _blocked(economics(w), EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL, "run_not_advanced:NEEDS_GOVERNANCE_APPROVAL")


# --- authority and transplants ------------------------------------------------------------------------------------------


def test_forged_or_mis_anchored_run_is_rejected() -> None:
    run = default_world().run
    forged = replace(run, decisions=run.decisions[:1] + run.decisions[2:])
    result = build_historical_execution_economics(
        forged,
        expected_run_digest=run.run_digest,
        economics_policy=default_policy(),
        expected_economics_policy_digest=default_policy().policy_digest,
        economics_approval=approval(default_world(), default_policy()),
        result_id="result-1",
        correlation_id="corr-1",
    )
    _assert_receipt_invariants(result)
    assert all(code.startswith(_code("run_integrity_failure:")) for code in result.integrity_reason_codes)
    wrong_anchor = economics(expected_run_digest="a" * 64)
    assert wrong_anchor.integrity_reason_codes == (_code("run_digest_mismatch"),)
    wrong_policy_anchor = economics(expected_economics_policy_digest="a" * 64)
    assert wrong_policy_anchor.integrity_reason_codes == (_code("policy_digest_mismatch"),)
    wrong_correlation = economics(correlation_id="corr-2")
    assert wrong_correlation.integrity_reason_codes == (_code("run_correlation_mismatch"),)


@pytest.mark.parametrize("field_name", ["dataset_binding", "executable_binding", "parameter_approval"])
def test_resealed_run_with_transplanted_authority_is_rejected(field_name: str) -> None:
    run = default_world().run
    other = world(binding_id="binding-2", intake_id="intake-2").run
    forged = replace(run, **{field_name: getattr(other, field_name)})
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
    result = partial_result()
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


@pytest.mark.parametrize(
    "artifact",
    [
        None,
        7,
        "result",
        b"result",
        {},
        object(),
        object.__new__(HistoricalExecutionEconomicsResult),
        "dict_payload",
        _corrupted(fills=None),
        _corrupted(fills=({"fill_id": "x"},)),
        _corrupted(run_binding=None),
        _corrupted(policy_binding="policy"),
        _corrupted(economics_approval="approved"),
        _corrupted(terminal_state=1),
        _corrupted(evaluation_end_ns=10**5000),
        _corrupted(status="ACCEPTED"),
        _corrupted(performance_metrics_computed=True),
        _corrupted(valuations=(object(),)),
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
    ) == (True,) * 7


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
