"""Protective position lifecycle tests on the one economics engine (PROTECTIVE_POSITION_LIFECYCLE_V1).

SYNTHETIC TEST VALUES ONLY. Every price, mark, book, bar, funding rate, latency, delay, policy value and approval here is
a synthetic fixture that exercises structure. None is a production threshold, venue truth, a qualified source or a real
human decision. The DEC-9 tightening reading runs only under TEST_ONLY_SYNTHETIC position-management approvals.

The worlds run on real time scales: final funding every 8 h, published 10 s after its settlement (the H2 decision
instant); a mark every 15 min (visible 1 s after its event); a 10 bps book of depth 100 at 30 s past every mark slot
(visible 1 s later); and flat SYNTHETIC 4 h mark-price bars from four days before the first decision, so ATR_4h is exactly
the declared bar range (2) and the stop distance is 3. The carry profile (lookback 1) enters SHORT on a final rate above
the entry threshold, LONG below its negative, and holds while the rate stays beyond the exit threshold.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from dataclasses import dataclass, replace
from fractions import Fraction

import pytest

from crypto_core.data.requirements import data_requirement_registry_digest
from crypto_core.strategy.source_packet import SourcePacketRightsStatus
from crypto_core.validation.edge_artifact_core import EdgeEvidenceStatus, EdgeGateVerdict
from crypto_core.validation.historical_execution_economics import (
    HISTORICAL_EXECUTION_PROTECTIVE_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    HistoricalExecutionAdmissionSchedule,
    HistoricalExecutionAdmissionWindow,
    HistoricalExecutionEconomicsError,
    HistoricalExecutionEconomicsResult,
    HistoricalExecutionFillOutcome,
    HistoricalExecutionGovernedPaperOutcome,
    HistoricalExecutionPositionManagementInputs,
    HistoricalExecutionProtectiveObligationStatus,
    HistoricalExecutionProtectiveTriggerKind,
    HistoricalExecutionProtectiveWindow,
    HistoricalExecutionSide,
    HistoricalExecutionStressScenario,
    HistoricalExecutionStressScenarioKind,
    HistoricalExecutionTradeStatus,
    HistoricalExecutionTransitionKind,
    HistoricalExecutionValuationKind,
    build_historical_execution_economics,
    historical_execution_economics_digest,
    historical_execution_economics_from_payload,
    historical_execution_economics_to_dict,
    historical_execution_governed_paper_outcome_digest,
    historical_execution_governed_paper_prefix_digest,
    simulate_historical_execution_governed_paper,
    simulate_historical_execution_stress,
    verify_historical_execution_economics,
)
from crypto_core.validation.historical_execution_economics_policy import HistoricalExecutionApprovalKind
from crypto_core.validation.historical_ohlc_bar_archive import (
    HistoricalOhlcBar,
    HistoricalOhlcBarArchive,
    HistoricalOhlcPriceSemantics,
    HistoricalOhlcSourceDeclaration,
    build_historical_ohlc_bar,
    build_historical_ohlc_bar_archive,
)
from crypto_core.validation.historical_pit_dataset import (
    HistoricalPitValue,
    build_historical_pit_dataset,
    build_historical_pit_record,
)
from crypto_core.validation.historical_position_management_policy import (
    TIGHTENING_DEC9_READING_V1,
    TIGHTENING_NOT_APPLIED_PENDING_DEC9,
    HistoricalPositionManagementApproval,
    HistoricalPositionManagementPolicy,
    build_historical_position_management_policy,
)

try:  # the module objects pytest collects (basename import), so cached worlds are shared
    import test_historical_decision_run as runt
    import test_historical_execution_economics as econ
    import test_historical_execution_economics_policy as polt
    import test_strategy_executable_binding as bind
    import test_strategy_executable_profiles as prof
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_historical_decision_run as runt
    from tests.crypto_core.validation import test_historical_execution_economics as econ
    from tests.crypto_core.validation import test_historical_execution_economics_policy as polt
    from tests.crypto_core.validation import test_strategy_executable_binding as bind
    from tests.crypto_core.validation import test_strategy_executable_profiles as prof

SECOND = 1_000_000_000
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE
DAY = 24 * HOUR
FUNDING = 8 * HOUR
SLOT = 15 * MINUTE
H4 = 4 * HOUR
ANCHOR = 19_000 * DAY  # SYNTHETIC: a UTC midnight, the open of funding window 0
INS = polt.INSTRUMENT
d = polt.d
PUBLISHED = 10 * SECOND  # SYNTHETIC: a final rate is published 10 s after its settlement
BOOK_OFFSET = 30 * SECOND  # SYNTHETIC: a book 30 s past every mark slot
VISIBLE = SECOND  # SYNTHETIC: every mark and book is visible 1 s after its event
UNIT = Fraction(1)
POSITIVE, NEGATIVE, NEUTRAL = "0.000200000000000000", "-0.000200000000000000", "0.000010000000000000"
_PREFIX = "historical_execution_economics"


def code(text: str) -> str:
    return f"{_PREFIX}:{text}"


def slot(j: int) -> int:
    return ANCHOR + j * SLOT


def book_visible(j: int) -> int:
    """The instant the book of mark slot ``j`` becomes visible (an engine fill instant)."""

    return slot(j) + BOOK_OFFSET + VISIBLE


def decision_instant(k: int) -> int:
    """The H2 decision instant of final funding record ``k`` (its window opens at ANCHOR + k * FUNDING)."""

    return ANCHOR + (k + 1) * FUNDING + PUBLISHED


def flat(_: int) -> Fraction:
    return Fraction(100)


def book_at(mid: Fraction, *, half_spread: Fraction = Fraction(5, 100), depth: object = 100) -> dict[str, str]:
    return {
        "best_bid_price": d(mid - half_spread),
        "best_ask_price": d(mid + half_spread),
        "best_bid_quantity": d(depth),
        "best_ask_quantity": d(depth),
    }


@dataclass(frozen=True)
class Path:
    """A SYNTHETIC world: funding rates, the mark per slot, book overrides per slot and extra mark observations."""

    rates: tuple[str, ...]
    mark: Callable[[int], Fraction | None] = flat  # None: no mark observation in that slot
    book: Callable[[int, Fraction], dict[str, str] | None] = lambda _, mid: book_at(mid)
    slots: int = 4 * 96
    extra_marks: tuple[tuple[int, Fraction], ...] = ()  # (event instant, price), visible VISIBLE after the event


def records_of(path: Path) -> tuple:
    rows = []
    for k, rate in enumerate(path.rates):
        visible = ANCHOR + (k + 1) * FUNDING + PUBLISHED
        rows.append(
            build_historical_pit_record(
                series_id="funding-final",
                data_requirement_key="funding_rate",
                instrument=INS,
                sequence_id=k,
                event_time_ns=ANCHOR + k * FUNDING,
                available_at_ns=visible,
                finalized_at_ns=visible,
                revision_vintage_id=None,
                values=(HistoricalPitValue("funding_rate", rate),),
            )
        )
    observed = [(slot(j), path.mark(j)) for j in range(path.slots)]
    marks = sorted([(event, price) for event, price in observed if price is not None] + list(path.extra_marks))
    for seq, (event, price) in enumerate(marks):
        rows.append(econ._record("mark", "mark_price", seq, event, {"mark_price": d(price)}, VISIBLE, VISIBLE))  # noqa: SLF001
    books = 0
    for j in range(path.slots):
        mid = path.mark(j)
        values = path.book(j, Fraction(100) if mid is None else mid)
        if values is not None:
            event = slot(j) + BOOK_OFFSET
            rows.append(econ._record("book", "order_book", books, event, values, VISIBLE, VISIBLE))  # noqa: SLF001
            books += 1
    return tuple(rows)


@functools.cache
def _chain():  # noqa: ANN202
    return econ.chain()


@functools.cache
def world(path: Path, *, end: int) -> econ.World:
    manifest, admission, registry = _chain()
    dataset = build_historical_pit_dataset(
        manifest,
        expected_source_manifest_digest=manifest.source_packet_evidence_digest,
        expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
        dataset_id="dataset-protective",
        correlation_id="corr-1",
        source_reference="archive:history",
        rights_status="own_research",
        rights_reference="license-1",
        records=records_of(path),
    )
    binding = bind.executable_binding(admission, binding_id="binding-1")
    run = runt.decision_run(
        dataset,
        binding,
        instrument=INS,
        evaluation_start_ns=ANCHOR,
        evaluation_end_ns=end,
        parameter_assignment=prof.params(n="1"),
    )
    return econ.World(run, dataset, registry)


@functools.cache
def economics_policy():  # noqa: ANN201
    return polt.cited_policy(
        latency_ns=100_000_000,  # SYNTHETIC 100 ms
        max_execution_delay_ns=5 * MINUTE,
        max_mark_staleness_ns=HOUR,
        funding_interval_ns=FUNDING,
    )


# --- the OHLC archive and the position-management policy ------------------------------------------------------------------


def ohlc_source(**changes: object) -> HistoricalOhlcSourceDeclaration:
    base = HistoricalOhlcSourceDeclaration(
        source_id="synthetic-ohlc-1",
        source_reference="archive:synthetic-ohlc",
        rights_status=SourcePacketRightsStatus.OWN_RESEARCH,
        rights_reference="license-1",
        instrument=INS,
        price_semantics=HistoricalOhlcPriceSemantics.MARK_PRICE,
        bar_intervals_ns=(H4,),
    )
    return replace(base, **changes)


def bar(k: int, *, true_range: object = 2, mid: object = 100) -> HistoricalOhlcBar:
    half = Fraction(true_range) / 2  # type: ignore[arg-type]
    opened = ANCHOR + k * H4
    return build_historical_ohlc_bar(
        interval_ns=H4,
        open_time_ns=opened,
        open_price=d(mid),
        high_price=d(Fraction(mid) + half),  # type: ignore[arg-type]
        low_price=d(Fraction(mid) - half),  # type: ignore[arg-type]
        close_price=d(mid),
        available_at_ns=opened + H4 + SECOND,
        finalized_at_ns=opened + H4 + SECOND,
    )


@functools.cache
def ohlc_archive(first: int = -24, last: int = 24, *, missing: tuple[int, ...] = ()) -> HistoricalOhlcBarArchive:
    """Flat SYNTHETIC 4 h bars ``first..last`` (bar 0 opens at ANCHOR): every true range is exactly 2."""

    bars = tuple(bar(k) for k in range(first, last + 1) if k not in missing)
    return build_historical_ohlc_bar_archive(archive_id="ohlc-protective", source=ohlc_source(), bars=bars)


@functools.cache
def pm_policy(
    tightening: str = TIGHTENING_NOT_APPLIED_PENDING_DEC9, *, max_bar_age_ns: int = 8 * HOUR
) -> HistoricalPositionManagementPolicy:
    return build_historical_position_management_policy(
        policy_id="pm-policy-1",
        policy_version="synthetic-v1",
        instrument=INS,
        atr_bar_price_semantics=HistoricalOhlcPriceSemantics.MARK_PRICE,
        atr_max_bar_age_ns=max_bar_age_ns,
        stop_tightening_method_id=tightening,
    )


def pm_approval(
    w: econ.World,
    policy: HistoricalPositionManagementPolicy,
    archive: HistoricalOhlcBarArchive,
    **changes: object,
) -> HistoricalPositionManagementApproval:
    values: dict[str, object] = {
        "approval_reference": "synthetic-pm-approval-1",
        "approval_digest": "e" * 64,
        "approval_kind": HistoricalExecutionApprovalKind.TEST_ONLY_SYNTHETIC,
        "approved_policy_digest": policy.policy_digest,
        "approved_rule_set_digest": policy.rule_set_digest,
        "approved_instrument": INS,
        "approved_strategy_spec_digest": w.run.strategy_spec_digest,
        "approved_ohlc_source_digest": archive.source_digest,
    }
    values.update(changes)
    return HistoricalPositionManagementApproval(**values)  # type: ignore[arg-type]


def pm_inputs(
    w: econ.World,
    *,
    policy: HistoricalPositionManagementPolicy | None = None,
    archive: HistoricalOhlcBarArchive | None = None,
    approval: object = "auto",
) -> HistoricalExecutionPositionManagementInputs:
    policy = pm_policy() if policy is None else policy
    archive = ohlc_archive() if archive is None else archive
    return HistoricalExecutionPositionManagementInputs(
        policy=policy,
        expected_policy_digest=policy.policy_digest,
        approval=pm_approval(w, policy, archive) if approval == "auto" else approval,  # type: ignore[arg-type]
        ohlc_archive=archive,
        expected_ohlc_archive_digest=archive.archive_digest,
    )


def managed(
    w: econ.World, *, position_management: object = "auto", **pm_changes: object
) -> HistoricalExecutionEconomicsResult:
    policy = economics_policy()
    return build_historical_execution_economics(
        w.run,
        expected_run_digest=w.run.run_digest,
        economics_policy=policy,
        expected_economics_policy_digest=policy.policy_digest,
        economics_approval=econ.approval(w, policy),
        result_id="result-protective",
        correlation_id="corr-1",
        position_management=pm_inputs(w, **pm_changes) if position_management == "auto" else position_management,  # type: ignore[arg-type]
    )


def computed(result: HistoricalExecutionEconomicsResult) -> HistoricalExecutionEconomicsResult:
    assert (result.status, result.gate_verdict, result.simulated_economics_computed) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.PASS,
        True,
    ), result.verdict_reason_codes
    verification = verify_historical_execution_economics(result)
    assert verification.intact, verification.reason_codes
    return result


def executed(result: HistoricalExecutionEconomicsResult | HistoricalExecutionGovernedPaperOutcome) -> list:
    return [
        item
        for item in result.fills
        if item.outcome in (HistoricalExecutionFillOutcome.FILLED, HistoricalExecutionFillOutcome.PARTIALLY_FILLED)
    ]


def protective_fills(result: HistoricalExecutionEconomicsResult | HistoricalExecutionGovernedPaperOutcome) -> list:
    attempts = {item.attempt_id for item in result.protective_attempts}
    return [item for item in result.fills if item.intent_id in attempts]


# --- the worlds -------------------------------------------------------------------------------------------------------------

HOLD = Path(rates=(POSITIVE,) * 12)  # SHORT from D_0, held: only the 24 h deadline closes it
HOLD_END = ANCHOR + 3 * DAY
F0 = book_visible(32)  # the opening fill of D_0 (ANCHOR + 8 h + 31 s)


def jump(at: int, price: object) -> Callable[[int], Fraction]:
    return lambda j: Fraction(price) if j >= at else Fraction(100)  # type: ignore[arg-type]


@functools.cache
def hold_result() -> HistoricalExecutionEconomicsResult:
    return computed(managed(world(HOLD, end=HOLD_END)))


@functools.cache
def basis() -> Fraction:
    return Fraction(hold_result().excursion_protections[0].basis_price)


# --- A. max hold (24 h from the first FLAT -> NONZERO fill) ---------------------------------------------------------------


def test_the_24h_deadline_discharges_a_close_only_obligation_and_re_entry_needs_a_fresh_decision() -> None:
    result = hold_result()
    first, second = result.excursion_protections
    assert (first.direction, first.opened_at_ns, first.max_hold_deadline_ns) == ("SHORT", F0, F0 + DAY)
    obligation = result.protective_obligations[0]
    assert obligation.status is HistoricalExecutionProtectiveObligationStatus.DISCHARGED
    assert [(item.trigger_kind, item.trigger_time_ns) for item in obligation.triggers] == [
        (HistoricalExecutionProtectiveTriggerKind.MAX_HOLD, F0 + DAY)
    ]
    attempt = result.protective_attempts[0]
    assert (attempt.attempt_time_ns, attempt.side, attempt.requested_quantity, attempt.position_quantity) == (
        F0 + DAY,
        HistoricalExecutionSide.BUY,
        d(1),
        d(-1),
    )
    close = protective_fills(result)[0]
    # the book of the deadline's own slot is not newer than the attempt: the next slot's book prices the close
    assert (close.outcome, close.execution_time_ns, close.decision_digest) == (
        HistoricalExecutionFillOutcome.FILLED,
        book_visible(129),
        obligation.obligation_id,
    )
    assert obligation.breach_duration_ns == book_visible(129) - (F0 + DAY)
    assert (obligation.discharged_at_ns, obligation.discharging_fill_digest) == (
        close.execution_time_ns,
        close.fill_digest,
    )
    assert (first.closed_at_ns, first.closing_fill_digest, first.obligation_id) == (
        close.execution_time_ns,
        close.fill_digest,
        obligation.obligation_id,
    )
    # re-entry only at the next decision, through a fresh admission: a new excursion with its own clock
    assert second.opened_at_ns == book_visible(160) and second.max_hold_deadline_ns == book_visible(160) + DAY
    assert second.opening_intent_id != first.opening_intent_id
    assert [item.status for item in result.trades] == [HistoricalExecutionTradeStatus.CLOSED] * 2
    assert result.terminal_state.position_quantity == d(0)  # type: ignore[union-attr]


def test_the_protection_survives_the_utc_day_boundary_and_funding_settles_on_the_open_position() -> None:
    result = hold_result()
    boundary = [
        item
        for item in result.valuations
        if item.time_ns == ANCHOR + DAY and item.valuation_kind is HistoricalExecutionValuationKind.UTC_DAY_BOUNDARY
    ]
    assert len(boundary) == 1 and boundary[0].position_quantity == d(-1)  # the first excursion spans the boundary
    settled = [(item.liability_time_ns, item.position_quantity) for item in result.funding_cashflows]
    assert settled == [
        (ANCHOR + 16 * HOUR, d(-1)),
        (ANCHOR + 24 * HOUR, d(-1)),
        (ANCHOR + 32 * HOUR, d(-1)),  # before the deadline at 32 h 31 s: the open position still settles
        (ANCHOR + 48 * HOUR, d(-1)),
        (ANCHOR + 56 * HOUR, d(-1)),
        (ANCHOR + 64 * HOUR, d(-1)),
    ]
    for item in result.funding_cashflows:
        assert Fraction(item.cashflow_amount) == -Fraction(item.position_quantity) * Fraction(
            item.mark_price
        ) * Fraction(item.funding_rate)


def test_an_increase_never_resets_the_clock() -> None:
    def book(j: int, mid: Fraction) -> dict[str, str]:
        return book_at(mid, depth=25 if j == 32 else 100)  # the opening fill is capped at 0.5

    result = computed(managed(world(Path(rates=(POSITIVE,) * 6, book=book), end=ANCHOR + 2 * DAY)))
    protection = result.excursion_protections[0]
    kinds = [item.transition_kind for item in result.position_transitions]
    assert kinds[:3] == [
        HistoricalExecutionTransitionKind.OPEN,
        HistoricalExecutionTransitionKind.INCREASE,
        HistoricalExecutionTransitionKind.CLOSE,
    ]
    assert (protection.opened_at_ns, protection.max_hold_deadline_ns) == (F0, F0 + DAY)
    assert Fraction(protection.basis_price) == Fraction(executed(result)[0].fill_price)  # the opening fill, not the add
    attempt = result.protective_attempts[0]
    assert (attempt.attempt_time_ns, attempt.requested_quantity) == (F0 + DAY, d(1))  # the whole position, once
    assert len(result.trades[0].entry_fill_digests) == 2


def test_a_reduction_never_resets_the_clock_and_an_unresolved_intent_defers_the_attempt() -> None:
    rates = (POSITIVE, NEUTRAL, NEUTRAL, NEUTRAL, NEUTRAL, NEUTRAL)

    def book(j: int, mid: Fraction) -> dict[str, str] | None:
        if 96 <= j <= 128:  # no book from 24 h to 32 h 30 s: the exits of D_2 and D_3 expire unfilled
            return None
        return book_at(mid, depth=25 if j == 64 else 100)  # the first exit only reduces

    result = computed(managed(world(Path(rates=rates, book=book), end=ANCHOR + 2 * DAY)))
    (protection,) = result.excursion_protections
    kinds = [item.transition_kind for item in result.position_transitions]
    assert kinds == [
        HistoricalExecutionTransitionKind.OPEN,
        HistoricalExecutionTransitionKind.REDUCE,
        HistoricalExecutionTransitionKind.CLOSE,
    ]
    assert protection.max_hold_deadline_ns == F0 + DAY
    expired = [item.reason for item in result.fills if item.outcome is HistoricalExecutionFillOutcome.UNFILLED]
    assert expired == ["execution_delay_expired", "execution_delay_expired"]
    (attempt,) = result.protective_attempts
    # D_3's intent waits until D_3 + max_delay: the deadline obligation issues its attempt only then
    assert attempt.attempt_time_ns == decision_instant(3) + 5 * MINUTE
    assert attempt.requested_quantity == d("0.5")
    assert protective_fills(result)[0].execution_time_ns == book_visible(129)


def test_an_unfilled_close_stays_an_outstanding_obligation_with_its_exact_breach() -> None:
    end = ANCHOR + 34 * HOUR

    def book(j: int, mid: Fraction) -> dict[str, str] | None:
        return None if j >= 128 else book_at(mid)

    result = computed(managed(world(Path(rates=(POSITIVE,) * 5, book=book), end=end)))
    (protection,) = result.excursion_protections
    (obligation,) = result.protective_obligations
    assert protection.closed_at_ns is None and protection.closing_fill_digest is None
    assert obligation.status is HistoricalExecutionProtectiveObligationStatus.OUTSTANDING
    assert (obligation.breach_duration_ns, obligation.outstanding_quantity) == (end - (F0 + DAY), d(-1))
    assert (obligation.discharged_at_ns, obligation.discharging_fill_digest) == (None, None)
    (unfilled,) = protective_fills(result)
    assert (unfilled.outcome, unfilled.reason) == (
        HistoricalExecutionFillOutcome.UNFILLED,
        "no_eligible_book_observation",
    )
    assert result.terminal_state.position_quantity == d(-1)  # type: ignore[union-attr]
    assert result.trades[-1].status is HistoricalExecutionTradeStatus.OPEN  # never reclassified as a success


def test_a_standing_obligation_waits_for_the_next_eligible_book() -> None:
    def book(j: int, mid: Fraction) -> dict[str, str] | None:
        return None if 129 <= j < 140 else book_at(mid)

    result = computed(managed(world(Path(rates=(POSITIVE,) * 9, book=book), end=ANCHOR + 2 * DAY)))
    obligation = result.protective_obligations[0]
    assert len(obligation.attempt_ids) == 1
    assert protective_fills(result)[0].execution_time_ns == book_visible(140)
    assert obligation.breach_duration_ns == book_visible(140) - (F0 + DAY)


def test_a_fill_model_rejection_re_attempts_at_every_later_book() -> None:
    def book(j: int, mid: Fraction) -> dict[str, str]:
        return book_at(mid, half_spread=Fraction(1)) if 129 <= j < 133 else book_at(mid)  # 200 bps > max 50 bps

    result = computed(managed(world(Path(rates=(POSITIVE,) * 9, book=book), end=ANCHOR + 2 * DAY)))
    obligation = result.protective_obligations[0]
    fills = protective_fills(result)
    assert [item.reason for item in fills[:5]] == ["spread_exceeds_max"] * 4 + ["filled"]
    assert [item.execution_time_ns for item in fills[:5]] == [book_visible(j) for j in range(129, 134)]
    assert len(obligation.attempt_ids) == 5
    assert [item.attempt_sequence for item in result.protective_attempts[:5]] == [0, 1, 2, 3, 4]


def test_a_partial_close_re_attempts_the_remainder_and_never_crosses_zero() -> None:
    def book(j: int, mid: Fraction) -> dict[str, str]:
        return book_at(mid, depth=25 if j in (129, 130) else 100)  # 2% of 25: 0.5 per fill

    result = computed(managed(world(Path(rates=(POSITIVE,) * 9, book=book), end=ANCHOR + 2 * DAY)))
    fills = protective_fills(result)[:2]
    assert [(item.outcome, item.filled_quantity) for item in fills] == [
        (HistoricalExecutionFillOutcome.PARTIALLY_FILLED, d("0.5")),
        (HistoricalExecutionFillOutcome.FILLED, d("0.5")),
    ]
    attempts = result.protective_attempts[:2]
    assert [(item.requested_quantity, item.position_quantity) for item in attempts] == [
        (d(1), d(-1)),
        (d("0.5"), d("-0.5")),
    ]
    transitions = {item.fill_digest: item for item in result.position_transitions}
    assert [transitions[item.fill_digest].post_quantity for item in fills] == [d("-0.5"), d(0)]
    assert result.excursion_protections[0].closed_at_ns == book_visible(130)


# --- B. the ATR_4h stop ----------------------------------------------------------------------------------------------------


def test_a_short_stop_triggers_on_a_pit_visible_mark_and_a_gap_never_guarantees_the_stop_price() -> None:
    result = computed(managed(world(Path(rates=(POSITIVE,) * 6, mark=jump(48, 104)), end=ANCHOR + 2 * DAY)))
    first = result.excursion_protections[0]
    stop = basis() + 3
    assert (first.atr_value, first.stop_atr_multiple) == (d(2), d("1.5"))
    assert [(item.milestone, Fraction(item.stop_price)) for item in first.stop_levels] == [(0, stop)]
    obligation = result.protective_obligations[0]
    (trigger,) = obligation.triggers
    assert (trigger.trigger_kind, trigger.trigger_time_ns, trigger.mark_price) == (
        HistoricalExecutionProtectiveTriggerKind.STOP,
        slot(48) + VISIBLE,
        d(104),
    )
    assert Fraction(trigger.stop_price) == stop  # type: ignore[arg-type]
    close = protective_fills(result)[0]
    assert close.execution_time_ns == book_visible(48)
    assert Fraction(close.fill_price) > stop  # type: ignore[arg-type]  # executed at the book, beyond the stop
    # the next decision re-enters at the new level: a new basis, a new stop, closed only by its deadline
    second = result.excursion_protections[1]
    assert Fraction(second.basis_price) > 103 and second.opened_at_ns == book_visible(64)
    assert [item.trigger_kind for item in result.protective_obligations[1].triggers] == [
        HistoricalExecutionProtectiveTriggerKind.MAX_HOLD
    ]


def test_a_long_stop_triggers_at_or_below_the_stop() -> None:
    rates = (NEGATIVE,) * 6
    result = computed(managed(world(Path(rates=rates, mark=jump(48, 96)), end=ANCHOR + 2 * DAY)))
    first = result.excursion_protections[0]
    assert first.direction == "LONG"
    stop = Fraction(first.basis_price) - 3
    trigger = result.protective_obligations[0].triggers[0]
    assert (trigger.trigger_kind, trigger.trigger_time_ns) == (
        HistoricalExecutionProtectiveTriggerKind.STOP,
        slot(48) + VISIBLE,
    )
    assert Fraction(trigger.stop_price) == stop  # type: ignore[arg-type]
    close = protective_fills(result)[0]
    assert close.side is HistoricalExecutionSide.SELL and Fraction(close.fill_price) < stop  # type: ignore[arg-type]


@pytest.mark.parametrize(("offset", "stopped"), [(Fraction(0), True), (-Fraction(1, 10**18), False)])
def test_the_exact_stop_boundary_triggers_and_one_unit_inside_does_not(offset: Fraction, stopped: bool) -> None:
    level = basis() + 3 + offset
    result = computed(managed(world(Path(rates=(POSITIVE,) * 6, mark=jump(48, level)), end=ANCHOR + 2 * DAY)))
    kinds = [item.trigger_kind for item in result.protective_obligations[0].triggers]
    if stopped:
        assert kinds == [HistoricalExecutionProtectiveTriggerKind.STOP]
    else:
        assert kinds == [HistoricalExecutionProtectiveTriggerKind.MAX_HOLD]


def test_the_stop_reads_the_mark_never_the_execution_book() -> None:
    def book(j: int, mid: Fraction) -> dict[str, str]:
        return book_at(Fraction(110) if j >= 48 else mid)  # the book alone moves beyond the stop

    result = computed(managed(world(Path(rates=(POSITIVE,) * 6, book=book), end=ANCHOR + 2 * DAY)))
    kinds = [item.trigger_kind for item in result.protective_obligations[0].triggers]
    assert kinds == [HistoricalExecutionProtectiveTriggerKind.MAX_HOLD]


def test_a_future_mark_never_triggers_before_it_is_visible() -> None:
    late = ANCHOR + 12 * HOUR + 7 * SECOND
    path = Path(rates=(POSITIVE,) * 6, extra_marks=((late, Fraction(104)),))
    result = computed(managed(world(path, end=ANCHOR + 2 * DAY)))
    trigger = result.protective_obligations[0].triggers[0]
    assert (trigger.trigger_kind, trigger.trigger_time_ns) == (
        HistoricalExecutionProtectiveTriggerKind.STOP,
        late + VISIBLE,
    )


@pytest.mark.parametrize(
    ("archive", "reason"),
    [
        (lambda: ohlc_archive(30, 40), "atr_no_visible_bar"),
        (lambda: ohlc_archive(0, 24), "atr_warmup_insufficient"),
        (lambda: ohlc_archive(-24, -1), "atr_bar_stale"),
        (lambda: ohlc_archive(-24, 24, missing=(-5,)), "atr_warmup_insufficient"),
    ],
)
def test_an_unavailable_atr_refuses_the_entry_and_never_estimates_a_stop(archive, reason: str) -> None:  # noqa: ANN001
    result = computed(managed(world(Path(rates=(POSITIVE,) * 3), end=ANCHOR + DAY), archive=archive()))
    refused = [item for item in result.fills if item.outcome is HistoricalExecutionFillOutcome.REJECTED]
    assert refused and {item.reason for item in refused} == {f"position_management_atr_unavailable:{reason}"}
    assert executed(result) == [] and result.excursion_protections == ()


def test_the_atr_is_read_at_the_opening_decision_and_bound_into_the_protection() -> None:
    first = hold_result().excursion_protections[0]
    assert (first.atr_at_ns, first.atr_interval_ns, first.atr_run_bar_count) == (decision_instant(0), H4, 26)
    assert first.atr_latest_bar_close_ns == ANCHOR + 8 * HOUR  # the bar closing at 8 h is visible at 8 h 1 s
    assert first.atr_method_id == pm_policy().atr_method_id


# --- C. DEC-9 tightening (a reading no human approved: synthetic approvals only) -------------------------------------------


@functools.cache
def tightened(tightening: str) -> HistoricalExecutionEconomicsResult:
    path = Path(rates=(POSITIVE,) * 6, mark=jump(52, "102.5"))
    return computed(managed(world(path, end=ANCHOR + 2 * DAY), policy=pm_policy(tightening)))


def test_the_dec9_reading_tightens_at_8h_and_16h_and_never_loosens() -> None:
    result = tightened(TIGHTENING_DEC9_READING_V1)
    assert result.stop_tightening_applied is True and result.synthetic_position_management_approval_used is True
    first = result.excursion_protections[0]
    levels = [(item.milestone, item.effective_from_ns, Fraction(item.stop_distance)) for item in first.stop_levels]
    assert levels == [(0, F0, Fraction(3)), (1, F0 + 8 * HOUR, Fraction(12, 5)), (2, F0 + 16 * HOUR, Fraction(48, 25))]
    prices = [Fraction(item.stop_price) for item in first.stop_levels]
    assert prices == sorted(prices, reverse=True)  # a SHORT stop only ever moves down, toward the price
    # 102.5 is inside the initial 3.0 stop and beyond the tightened 2.4 one: the milestone itself triggers
    trigger = result.protective_obligations[0].triggers[0]
    assert (trigger.trigger_kind, trigger.trigger_time_ns, trigger.stop_milestone) == (
        HistoricalExecutionProtectiveTriggerKind.STOP,
        F0 + 8 * HOUR,
        1,
    )


def test_without_the_dec9_reading_the_same_path_is_closed_only_by_the_deadline() -> None:
    result = tightened(TIGHTENING_NOT_APPLIED_PENDING_DEC9)
    assert result.stop_tightening_applied is False
    assert [item.milestone for item in result.excursion_protections[0].stop_levels] == [0]
    assert [item.trigger_kind for item in result.protective_obligations[0].triggers] == [
        HistoricalExecutionProtectiveTriggerKind.MAX_HOLD
    ]


def test_a_human_approval_of_the_dec9_reading_needs_governance_and_computes_nothing() -> None:
    w = world(Path(rates=(POSITIVE,) * 3), end=ANCHOR + DAY)
    policy = pm_policy(TIGHTENING_DEC9_READING_V1)
    approval = pm_approval(w, policy, ohlc_archive(), approval_kind=HistoricalExecutionApprovalKind.HUMAN_GOVERNANCE)
    result = managed(w, policy=policy, approval=approval)
    assert result.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL and not result.simulated_economics_computed
    assert code(f"position_management_method_requires_human_approval:{TIGHTENING_DEC9_READING_V1}") in (
        result.verdict_reason_codes
    )


# --- D. equal-time priority, duplicates and re-entry ------------------------------------------------------------------------


def test_funding_settles_before_a_protective_trigger_at_the_same_instant() -> None:
    liability = ANCHOR + 16 * HOUR
    path = Path(rates=(POSITIVE,) * 6, extra_marks=((liability - VISIBLE, Fraction(104)),))
    result = computed(managed(world(path, end=ANCHOR + 2 * DAY)))
    trigger = result.protective_obligations[0].triggers[0]
    assert (trigger.trigger_kind, trigger.trigger_time_ns) == (HistoricalExecutionProtectiveTriggerKind.STOP, liability)
    settlement = [item for item in result.funding_cashflows if item.liability_time_ns == liability][0]
    assert (settlement.position_quantity, settlement.mark_price) == (d(-1), d(104))  # the open position settles first
    assert result.protective_attempts[0].attempt_time_ns == liability


def test_a_protective_attempt_precedes_a_decision_at_the_same_instant_and_no_close_is_duplicated() -> None:
    rates = (POSITIVE, NEGATIVE, NEGATIVE, NEGATIVE, NEGATIVE, NEGATIVE)  # D_1 would exit the SHORT
    path = Path(rates=rates, extra_marks=((decision_instant(1) - VISIBLE, Fraction(104)),))
    result = computed(managed(world(path, end=ANCHOR + 2 * DAY)))
    trigger = result.protective_obligations[0].triggers[0]
    assert trigger.trigger_time_ns == decision_instant(1)
    refused = [item for item in result.fills if item.outcome is HistoricalExecutionFillOutcome.REJECTED]
    assert [item.reason for item in refused] == ["position_management_protective_close_in_flight"]
    closes = [
        item for item in result.position_transitions if item.transition_kind is HistoricalExecutionTransitionKind.CLOSE
    ]
    assert (
        len(closes) == 1 and closes[0].fill_digest == protective_fills(result)[0].fill_digest
    )  # one close, protective
    short, long_ = result.excursion_protections
    # D_2 re-enters LONG only through a fresh admission, never across zero; its deadline lies past the end
    assert (short.direction, long_.direction, long_.opened_at_ns, long_.closed_at_ns) == (
        "SHORT",
        "LONG",
        book_visible(96),
        None,
    )
    for item in result.position_transitions:
        prior, post = Fraction(item.prior_quantity), Fraction(item.post_quantity)
        assert prior * post >= 0  # no fill ever crosses zero


def test_a_trigger_while_a_decision_fill_is_in_flight_waits_for_that_fill() -> None:
    rates = (POSITIVE, POSITIVE, POSITIVE, NEUTRAL, NEUTRAL, NEUTRAL)  # D_3's exit fills at the deadline instant
    result = computed(managed(world(Path(rates=rates), end=ANCHOR + 2 * DAY)))
    (obligation,) = result.protective_obligations
    assert obligation.triggers[0].trigger_time_ns == F0 + DAY == book_visible(128)
    # the decision fill at the same instant (FILL after PROTECTIVE) discharges the obligation: no attempt was needed
    assert obligation.attempt_ids == () and obligation.breach_duration_ns == 0
    assert obligation.discharging_fill_digest == executed(result)[1].fill_digest
    assert result.protective_attempts == ()


# --- E. the governed simulation: DEC-1 protective windows and parity ---------------------------------------------------------


def schedule(
    *,
    windows: tuple[tuple[int, int, int, int], ...] = ((ANCHOR, HOLD_END, 0, 1),),
    protective: tuple[tuple[int, int], ...] = ((ANCHOR, HOLD_END + DAY),),
    invalidated_from_ns: int | None = None,
) -> HistoricalExecutionAdmissionSchedule:
    """SYNTHETIC v3 schedule: (start, end, max_long, max_short) cycle windows and DEC-1 protective windows."""

    return HistoricalExecutionAdmissionSchedule(
        schema_version=HISTORICAL_EXECUTION_PROTECTIVE_ADMISSION_SCHEDULE_SCHEMA_VERSION,
        schedule_id="protective-schedule",
        windows=tuple(
            HistoricalExecutionAdmissionWindow(start, end, d(long_), d(short), d(1000))
            for start, end, long_, short in windows
        ),
        invalidated_from_ns=invalidated_from_ns,
        protective_windows=tuple(
            HistoricalExecutionProtectiveWindow(start, end, "a" * 64) for start, end in protective
        ),
    )


def governed(result: HistoricalExecutionEconomicsResult, **changes: object) -> HistoricalExecutionGovernedPaperOutcome:
    outcome = simulate_historical_execution_governed_paper(
        result,
        expected_result_digest=result.result_digest,
        schedule=schedule(**changes),  # type: ignore[arg-type]
    )
    assert outcome.simulated is True, outcome.reason_codes
    assert outcome.outcome_digest == historical_execution_governed_paper_outcome_digest(outcome)
    return outcome


def test_backtest_and_governed_paper_apply_one_protective_semantics() -> None:
    result = hold_result()
    outcome = governed(result)  # a SHORT-only cycle (max_long 0): the protective BUY needs no direction authority
    assert outcome.fills == result.fills and outcome.position_transitions == result.position_transitions
    assert outcome.excursion_protections == result.excursion_protections
    assert outcome.protective_obligations == result.protective_obligations
    assert outcome.protective_attempts == result.protective_attempts
    assert outcome.funding_cashflows == result.funding_cashflows and outcome.governance_rejected_fill_digests == ()


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"invalidated_from_ns": ANCHOR + 20 * HOUR}, "governed_paper_lifecycle_invalidated"),
        ({"windows": ((ANCHOR, ANCHOR + 12 * HOUR, 0, 1),)}, "governed_paper_no_cycle_authority"),
    ],
)
def test_dec1_closes_through_invalidation_and_without_a_cycle_while_entries_stay_refused(
    changes: dict[str, object], reason: str
) -> None:
    outcome = governed(hold_result(), **changes)
    close = protective_fills(outcome)[0]
    assert (close.outcome, close.execution_time_ns) == (HistoricalExecutionFillOutcome.FILLED, book_visible(129))
    refused = [item for item in outcome.fills if item.outcome is HistoricalExecutionFillOutcome.REJECTED]
    decided = {item.intent_id: item.decision_time_ns for item in outcome.intents}
    # every later entry (D_4 .. D_7) is refused: DEC-1 never opens a position
    assert [(decided[item.intent_id], item.reason) for item in refused] == [
        (decision_instant(k), reason) for k in range(4, 8)
    ]
    assert outcome.terminal_state.position_quantity == d(0)  # type: ignore[union-attr]


def test_a_missing_protective_window_refuses_the_attempt_and_records_the_breach() -> None:
    outcome = governed(hold_result(), protective=())
    (attempt,) = outcome.protective_attempts
    (refused,) = protective_fills(outcome)
    assert (refused.outcome, refused.reason) == (
        HistoricalExecutionFillOutcome.REJECTED,
        "governed_paper_protective_authority_missing",
    )
    (obligation,) = outcome.protective_obligations
    assert obligation.status is HistoricalExecutionProtectiveObligationStatus.OUTSTANDING
    assert obligation.breach_duration_ns == HOLD_END - attempt.attempt_time_ns
    assert outcome.terminal_state.position_quantity == d(-1)  # type: ignore[union-attr]
    assert refused.fill_digest in outcome.governance_rejected_fill_digests


def test_an_expired_window_refuses_and_a_later_window_resumes_the_standing_obligation() -> None:
    expired = governed(hold_result(), protective=((ANCHOR, F0 + DAY),))  # it ends exactly at the deadline
    assert protective_fills(expired)[0].reason == "governed_paper_protective_authority_missing"
    assert expired.protective_obligations[0].status is HistoricalExecutionProtectiveObligationStatus.OUTSTANDING
    resumed = governed(hold_result(), protective=((ANCHOR, F0 + DAY), (ANCHOR + 34 * HOUR, HOLD_END + DAY)))
    fills = protective_fills(resumed)
    assert [item.reason for item in fills[:2]] == ["governed_paper_protective_authority_missing", "filled"]
    assert resumed.protective_attempts[1].attempt_time_ns == ANCHOR + 34 * HOUR
    assert resumed.protective_obligations[0].status is HistoricalExecutionProtectiveObligationStatus.DISCHARGED


def test_an_outstanding_obligation_refuses_an_exposure_increasing_entry() -> None:
    def book(j: int, mid: Fraction) -> dict[str, str] | None:
        if j == 32:
            return book_at(mid, depth=25)  # the opening fill is capped at 0.5
        return None if 32 < j < 160 else book_at(mid)  # no book from 8 h 15 min to 39 h 45 min

    result = computed(managed(world(Path(rates=(POSITIVE,) * 6, book=book), end=ANCHOR + 2 * DAY)))
    # no protective window: the deadline attempt is refused and its obligation stays outstanding; D_4 would top the
    # half position up to the full unit, and that increase is refused while the obligation is outstanding
    outcome = governed(result, windows=((ANCHOR, ANCHOR + 2 * DAY, 0, 1),), protective=())
    reasons = [
        item.reason
        for item in outcome.fills
        if item.outcome in (HistoricalExecutionFillOutcome.UNFILLED, HistoricalExecutionFillOutcome.REJECTED)
    ]
    assert reasons == [
        "governed_paper_same_side_add_unsupported",  # D_1, D_2 and D_3: governed paper never adds to a position
        "governed_paper_same_side_add_unsupported",
        "governed_paper_same_side_add_unsupported",
        "governed_paper_protective_authority_missing",  # the deadline attempt
        "position_management_protective_obligation_outstanding",  # D_4's increase, refused before any cycle rule
    ]
    (obligation,) = outcome.protective_obligations
    assert (obligation.status, obligation.outstanding_quantity) == (
        HistoricalExecutionProtectiveObligationStatus.OUTSTANDING,
        d("-0.5"),
    )
    assert outcome.terminal_state.position_quantity == d("-0.5")  # type: ignore[union-attr]
    # the backtest: D_1 to D_3 expire unfilled, D_3's wait defers the attempt to D_3 + max_delay, and the standing
    # attempt is still in flight at D_4, which is refused as a close in flight
    expired = [item.reason for item in result.fills if item.outcome is HistoricalExecutionFillOutcome.UNFILLED]
    assert expired == ["execution_delay_expired"] * 3
    assert result.protective_attempts[0].attempt_time_ns == decision_instant(3) + 5 * MINUTE
    base = [item.reason for item in result.fills if item.outcome is HistoricalExecutionFillOutcome.REJECTED]
    assert base == ["position_management_protective_close_in_flight"]
    assert result.terminal_state.position_quantity == d(0)  # type: ignore[union-attr]


def test_a_mark_gap_beyond_the_staleness_bound_fails_the_whole_result_closed() -> None:
    def mark(j: int) -> Fraction | None:
        return None if 40 <= j <= 64 else Fraction(100)  # no mark from 10 h to 16 h with the SHORT open

    result = managed(world(Path(rates=(POSITIVE,) * 6, mark=mark), end=ANCHOR + 2 * DAY))
    assert (result.gate_verdict, result.simulated_economics_computed) == (EdgeGateVerdict.FAIL, False)
    assert any(item.startswith(code("mark_stale:")) for item in result.verdict_reason_codes)
    assert result.excursion_protections == () and result.protective_obligations == ()


def test_a_v3_schedule_is_required_exactly_for_a_position_managed_baseline() -> None:
    result = hold_result()
    legacy = replace(schedule(), schema_version="historical-execution-admission-schedule.v2", protective_windows=())
    with pytest.raises(HistoricalExecutionEconomicsError, match=code("admission_schedule_version_mismatch")):
        simulate_historical_execution_governed_paper(
            result, expected_result_digest=result.result_digest, schedule=legacy
        )
    with pytest.raises(
        HistoricalExecutionEconomicsError, match=code("admission_schedule_malformed:protective_windows")
    ):
        simulate_historical_execution_governed_paper(
            result,
            expected_result_digest=result.result_digest,
            schedule=replace(legacy, protective_windows=schedule().protective_windows),
        )


def test_the_prefix_excludes_a_pending_attempt_by_its_instant_across_replays() -> None:
    short_end = F0 + DAY + 40 * SECOND  # the deadline attempt is in flight at this end
    short = governed(computed(managed(world(HOLD, end=short_end))), windows=((ANCHOR, short_end, 0, 1),))
    attempt = short.pending_protective_attempt_time_ns
    assert (
        attempt == F0 + DAY and short.pending_protective_attempt_digest == short.protective_attempts[0].attempt_digest
    )
    long = governed(hold_result())
    assert long.pending_protective_attempt_time_ns is None
    excluded = {"excluded_protective_attempt_times": (attempt,)}
    assert historical_execution_governed_paper_prefix_digest(
        long, before_ns=short_end, **excluded
    ) == historical_execution_governed_paper_prefix_digest(short, before_ns=short_end, **excluded)
    assert historical_execution_governed_paper_prefix_digest(
        long, before_ns=short_end
    ) != historical_execution_governed_paper_prefix_digest(short, before_ns=short_end)


# --- F. identity, versioning and authority binding ---------------------------------------------------------------------------


def test_a_managed_result_is_schema_v2_digest_bound_and_round_trips() -> None:
    result = hold_result()
    assert result.schema_version == "historical-execution-economics.v2"
    assert result.position_management_policy_digest == pm_policy().policy_digest
    assert result.ohlc_archive_digest == ohlc_archive().archive_digest
    assert result.result_digest == historical_execution_economics_digest(result)
    assert historical_execution_economics_from_payload(historical_execution_economics_to_dict(result)) == result


def test_a_legacy_result_carries_no_position_management_field() -> None:
    legacy = econ.default_result()
    payload = historical_execution_economics_to_dict(legacy)
    assert legacy.schema_version == "historical-execution-economics.v1"
    assert "excursion_protections" not in payload and "position_management_policy_binding" not in payload
    forged = replace(legacy, stop_tightening_applied=True)
    assert not verify_historical_execution_economics(forged).intact


@pytest.mark.parametrize(
    "name",
    ["excursion_protections", "protective_obligations", "protective_attempts", "stop_tightening_applied"],
)
def test_a_resealed_protective_ledger_never_verifies(name: str) -> None:
    result = hold_result()
    value = True if name == "stop_tightening_applied" else getattr(result, name)[:1]
    forged = replace(result, **{name: value})
    forged = replace(forged, result_digest=historical_execution_economics_digest(forged))
    assert not verify_historical_execution_economics(forged).intact


def test_tampered_or_foreign_position_management_inputs_never_reach_the_engine() -> None:
    w = world(HOLD, end=HOLD_END)
    archive = ohlc_archive()
    tampered = managed(
        w, position_management=replace(pm_inputs(w), ohlc_archive=replace(archive, archive_id="ohlc-forged"))
    )
    assert (tampered.status, tampered.simulated_economics_computed) == (EdgeEvidenceStatus.REJECTED, False)
    assert any(item.startswith(code("ohlc_archive_integrity_failure:")) for item in tampered.integrity_reason_codes)
    anchored = managed(w, position_management=replace(pm_inputs(w), expected_policy_digest="0" * 64))
    assert anchored.integrity_reason_codes == (code("position_management_policy_digest_mismatch"),)
    with pytest.raises(HistoricalExecutionEconomicsError, match=code("position_management_inputs_malformed")):
        managed(w, position_management=replace(pm_inputs(w), policy=archive))
    missing = managed(w, approval=None)
    assert missing.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert code("position_management_approval_missing") in missing.verdict_reason_codes
    foreign = managed(w, approval=pm_approval(w, pm_policy(), archive, approved_ohlc_source_digest="c" * 64))
    assert code("position_management_approval_approved_ohlc_source_digest_mismatch") in foreign.verdict_reason_codes
    last_trade = build_historical_ohlc_bar_archive(
        archive_id="ohlc-last",
        source=ohlc_source(price_semantics=HistoricalOhlcPriceSemantics.LAST_TRADE),
        bars=archive.bars,
    )
    wrong = managed(w, archive=last_trade)
    assert wrong.gate_verdict is EdgeGateVerdict.FAIL
    assert code("ohlc_archive_not_of_the_position_management_policy") in wrong.verdict_reason_codes


def test_stress_refuses_a_position_managed_baseline() -> None:
    result = hold_result()
    one = d(1)
    scenario = HistoricalExecutionStressScenario(
        HistoricalExecutionStressScenarioKind.LOW_LIQUIDITY, one, d(2), d("0.2"), d(0), 0, d(0)
    )
    with pytest.raises(HistoricalExecutionEconomicsError, match=code("stress_position_management_unsupported")):
        simulate_historical_execution_stress(result, expected_result_digest=result.result_digest, scenario=scenario)
