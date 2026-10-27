"""Protective position lifecycle tests on the one economics engine (PROTECTIVE_POSITION_LIFECYCLE_V1).

SYNTHETIC TEST VALUES ONLY. Every price, mark, book, bar, funding rate, latency, delay, policy value and approval here is
a synthetic fixture that exercises structure. None is a production threshold, venue truth, a qualified source or a real
human decision. The DEC-9 tightening reading runs only under TEST_ONLY_SYNTHETIC position-management approvals.

The worlds run on real time scales: final funding every 8 h, published 10 s after its settlement (the H2 decision
instant); a mark every 15 min (visible 1 s after its event); a 10 bps book of depth 100 at 30 s past every mark slot
(visible 1 s later); and flat SYNTHETIC 4 h mark-price bars from four days before the first decision, so ATR_4h is exactly
the declared bar range (2) and the stop distance is 3. The carry profile (lookback 1) enters SHORT on a final rate above
the entry threshold, LONG below its negative, and holds while the rate stays beyond the exit threshold. Section B2 swaps
in long SYNTHETIC histories whose exact full-run ATR is not 2, checked against the independent literal-recurrence oracle
of ``test_historical_ohlc_bar_archive.py`` rather than against the engine itself. Section G checks the governed decision
portfolio (S1_NO_TRADE_NATIVE_MEASUREMENT_CLOSURE_V1) against an independent oracle built from the outcome's public
ledgers, the archive's publication instants and the public visible-mark rule; every amount of these worlds is exactly
representable at scale 18, so the oracle is exact. Section H checks information-time admission (schedule v4): archives
that differ only in a final rate not yet published admit the same intents and fills, and record the same snapshots,
before its publication, also where an admission on the booked equity would differ (an independent exact oracle shows
it); and every exposure-increasing fill is bounded at 25% of its publication-visible equity, at the exact boundary.
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
    HISTORICAL_EXECUTION_INFORMATION_TIME_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    HISTORICAL_EXECUTION_POSITION_CONCENTRATION_CAP,
    HISTORICAL_EXECUTION_PROTECTIVE_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    HistoricalExecutionAdmissionSchedule,
    HistoricalExecutionAdmissionWindow,
    HistoricalExecutionDecisionPortfolioSnapshot,
    HistoricalExecutionEconomicsError,
    HistoricalExecutionEconomicsResult,
    HistoricalExecutionFillOutcome,
    HistoricalExecutionGovernedPaperDecisionPortfolio,
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
    historical_execution_governed_paper_decision_portfolio_digest,
    historical_execution_governed_paper_decision_portfolio_to_dict,
    historical_execution_governed_paper_outcome_digest,
    historical_execution_governed_paper_outcome_to_dict,
    historical_execution_governed_paper_prefix_digest,
    historical_execution_latest_visible_mark,
    simulate_historical_execution_governed_paper,
    simulate_historical_execution_governed_paper_decision_portfolio,
    simulate_historical_execution_stress,
    verify_historical_execution_economics,
)
from crypto_core.validation.historical_execution_economics_policy import HistoricalExecutionApprovalKind
from crypto_core.validation.historical_ohlc_bar_archive import (
    WILDER_ATR_METHOD_ID,
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
    STOP_ATR_MULTIPLE,
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
    import test_historical_ohlc_bar_archive as ohlct
    import test_strategy_executable_binding as bind
    import test_strategy_executable_profiles as prof
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_historical_decision_run as runt
    from tests.crypto_core.validation import test_historical_execution_economics as econ
    from tests.crypto_core.validation import test_historical_execution_economics_policy as polt
    from tests.crypto_core.validation import test_historical_ohlc_bar_archive as ohlct
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


@functools.cache
def tiny_range_archive() -> HistoricalOhlcBarArchive:
    """SYNTHETIC bars -24..24: ONE true range of a single scale-18 unit (bar -23), every other true range 0.

    The exact ATR at D_0 is ``(1/14) x (13/14)^11`` units: strictly positive, and below half a unit at scale 18.
    """

    bars = []
    for k in range(-24, 25):
        opened = ANCHOR + k * H4
        low = Fraction(100) - Fraction(1, 10**18) if k == -23 else Fraction(100)
        bars.append(
            build_historical_ohlc_bar(
                interval_ns=H4,
                open_time_ns=opened,
                open_price=d(100),
                high_price=d(100),
                low_price=d(low),
                close_price=d(100),
                available_at_ns=opened + H4 + SECOND,
                finalized_at_ns=opened + H4 + SECOND,
            )
        )
    return build_historical_ohlc_bar_archive(archive_id="ohlc-protective-tiny", source=ohlc_source(), bars=tuple(bars))


@pytest.mark.parametrize(
    ("archive", "reason"),
    [
        (lambda: ohlc_archive(30, 40), "atr_no_visible_bar"),
        (lambda: ohlc_archive(0, 24), "atr_warmup_insufficient"),
        (lambda: ohlc_archive(-24, -1), "atr_bar_stale"),
        (lambda: ohlc_archive(-24, 24, missing=(-5,)), "atr_warmup_insufficient"),
        (tiny_range_archive, "atr_rounds_to_zero"),  # P2-POSITIVE-ATR-RENDER-ZERO
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
    assert first.atr_method_id == pm_policy().atr_method_id == WILDER_ATR_METHOD_ID


# --- B2. the exact full-history ATR on the public engine, verifier and governed replay (P2-DEC7-280-TR-RESEED) ------------

END_2D = ANCHOR + 2 * DAY
RATES = {"SHORT": (POSITIVE,) * 6, "LONG": (NEGATIVE,) * 6}
SIGN = {"SHORT": -1, "LONG": 1}


@functools.cache
def long_archive(first_range: int, tail: int = 280) -> HistoricalOhlcBarArchive:
    """SYNTHETIC 4 h bars ``-tail .. 1`` (bar 1 closes at 8 h): the first true range ``first_range``, every later one 2.

    At D_0 every bar is visible and contiguous: the run is all ``tail + 2`` bars, so ``tail + 1`` true ranges. The
    withdrawn 280-true-range re-seed read exactly 2 for these histories, whatever ``first_range`` is.
    """

    bars = tuple(bar(k, true_range=first_range if k == 1 - tail else 2) for k in range(-tail, 2))
    return build_historical_ohlc_bar_archive(
        archive_id=f"ohlc-protective-long-{first_range}", source=ohlc_source(), bars=bars
    )


@functools.cache
def opening_basis(direction: str) -> Fraction:
    """The executed price of D_0's opening fill: it never depends on the ATR or on any mark after slot 32."""

    protection = computed(managed(world(Path(rates=RATES[direction]), end=END_2D))).excursion_protections[0]
    assert (protection.direction, protection.opened_at_ns) == (direction, F0)
    return Fraction(protection.basis_price)


def beyond(mark: Fraction, level: Fraction, direction: str) -> bool:
    """Whether ``mark`` is at or beyond the stop ``level`` (SHORT: at or above, LONG: at or below)."""

    return mark >= level if direction == "SHORT" else mark <= level


def first_mark_beyond(level: Fraction, direction: str) -> Fraction:
    """The first scale-18 mark at or beyond an off-grid stop ``level``."""

    units = level * 10**18
    assert units.denominator != 1  # the exact full-history stop lies strictly between two scale-18 marks
    whole = -(-units.numerator // units.denominator) if direction == "SHORT" else units.numerator // units.denominator
    return Fraction(whole, 10**18)


@pytest.mark.parametrize("crossing", [True, False])
@pytest.mark.parametrize("first_range", [0, 198])
@pytest.mark.parametrize("direction", ["SHORT", "LONG"])
def test_the_stop_is_1_5_times_the_exact_full_history_atr_and_its_first_crossing_mark_triggers(
    direction: str, first_range: int, crossing: bool
) -> None:
    archive = long_archive(first_range)
    atr = ohlct.wilder_oracle(archive.bars)  # the INDEPENDENT oracle, never the engine
    assert atr != 2 and (atr < 2) is (first_range == 0)
    basis, sign = opening_basis(direction), SIGN[direction]
    stop = basis - sign * STOP_ATR_MULTIPLE * atr
    withdrawn = basis - sign * 3  # the stop of the 280-true-range re-seed, whose ATR was exactly 2
    trigger_mark = first_mark_beyond(stop, direction)
    inside_mark = trigger_mark + sign * Fraction(1, 10**18)
    assert beyond(trigger_mark, stop, direction) and not beyond(inside_mark, stop, direction)
    if first_range == 0:  # a later stop: the re-seed missed this crossing and held to the 24 h deadline
        assert not beyond(trigger_mark, withdrawn, direction)
    else:  # an earlier stop: the re-seed stopped inside the approved one
        assert beyond(inside_mark, withdrawn, direction)
    mark = trigger_mark if crossing else inside_mark
    result = computed(managed(world(Path(rates=RATES[direction], mark=jump(48, mark)), end=END_2D), archive=archive))
    protection = result.excursion_protections[0]
    assert (protection.direction, protection.opened_at_ns, Fraction(protection.basis_price)) == (direction, F0, basis)
    assert (protection.atr_method_id, protection.atr_value, protection.atr_run_bar_count) == (
        WILDER_ATR_METHOD_ID,
        d(atr),
        282,
    )
    assert protection.atr_window_digest == ohlct.window_of(archive.bars)  # every one of the 282 bars is bound
    assert [(item.stop_distance, item.stop_price) for item in protection.stop_levels] == [
        (d(STOP_ATR_MULTIPLE * atr), d(stop))
    ]
    obligation = result.protective_obligations[0]
    close = protective_fills(result)[0]
    if crossing:
        (trigger,) = obligation.triggers
        assert (trigger.trigger_kind, trigger.trigger_time_ns, trigger.mark_price, trigger.stop_price) == (
            HistoricalExecutionProtectiveTriggerKind.STOP,
            slot(48) + VISIBLE,  # 12 h 1 s
            d(mark),
            d(stop),
        )
        assert close.execution_time_ns == book_visible(48)
    else:
        assert [(item.trigger_kind, item.trigger_time_ns) for item in obligation.triggers] == [
            (HistoricalExecutionProtectiveTriggerKind.MAX_HOLD, F0 + DAY)  # 32 h 31 s
        ]
        assert close.execution_time_ns == book_visible(129)
    assert (close.outcome, obligation.status) == (
        HistoricalExecutionFillOutcome.FILLED,
        HistoricalExecutionProtectiveObligationStatus.DISCHARGED,
    )
    transitions = {item.fill_digest: item for item in result.position_transitions}
    assert transitions[close.fill_digest].transition_kind is HistoricalExecutionTransitionKind.CLOSE
    assert transitions[close.fill_digest].post_quantity == d(0)
    # governed paper re-runs the one engine and reaches the same exact stop
    outcome = governed(result, windows=((ANCHOR, END_2D, 1, 1),), protective=((ANCHOR, END_2D + DAY),))
    assert outcome.fills == result.fills and outcome.position_transitions == result.position_transitions
    assert outcome.excursion_protections == result.excursion_protections
    assert outcome.protective_obligations == result.protective_obligations


def test_a_full_history_stop_after_the_day_boundary_settles_funding_first_and_closes_partially_then_fully() -> None:
    archive = long_archive(0)
    stop = basis() + STOP_ATR_MULTIPLE * ohlct.wilder_oracle(archive.bars)
    mark = first_mark_beyond(stop, "SHORT")
    assert mark < basis() + 3  # inside the re-seed's stop: that method held this SHORT to the 24 h deadline

    def book(j: int, mid: Fraction) -> dict[str, str]:
        return book_at(mid, depth=25 if j in (100, 101) else 100)  # 2% of 25: each close fills 0.5

    triggered_at = slot(100) + VISIBLE  # 25 h 1 s: after the UTC day boundary and the 24 h settlement
    path = Path(rates=(POSITIVE,) * 6, mark=jump(100, mark), book=book)
    result = computed(managed(world(path, end=END_2D), archive=archive))
    settled = [(item.liability_time_ns, item.position_quantity) for item in result.funding_cashflows]
    assert settled[:2] == [(ANCHOR + 16 * HOUR, d(-1)), (ANCHOR + 24 * HOUR, d(-1))]
    boundary = [
        item
        for item in result.valuations
        if item.time_ns == ANCHOR + DAY and item.valuation_kind is HistoricalExecutionValuationKind.UTC_DAY_BOUNDARY
    ]
    assert len(boundary) == 1 and boundary[0].position_quantity == d(-1)
    obligation = result.protective_obligations[0]
    assert [(item.trigger_kind, item.trigger_time_ns) for item in obligation.triggers] == [
        (HistoricalExecutionProtectiveTriggerKind.STOP, triggered_at)
    ]
    fills = protective_fills(result)[:2]
    assert [(item.outcome, item.filled_quantity, item.execution_time_ns) for item in fills] == [
        (HistoricalExecutionFillOutcome.PARTIALLY_FILLED, d("0.5"), book_visible(100)),
        (HistoricalExecutionFillOutcome.FILLED, d("0.5"), book_visible(101)),
    ]
    assert [(item.requested_quantity, item.position_quantity) for item in result.protective_attempts[:2]] == [
        (d(1), d(-1)),
        (d("0.5"), d("-0.5")),
    ]
    assert (obligation.status, obligation.discharged_at_ns, obligation.breach_duration_ns) == (
        HistoricalExecutionProtectiveObligationStatus.DISCHARGED,
        book_visible(101),
        book_visible(101) - triggered_at,
    )
    kinds = [item.transition_kind for item in result.position_transitions[:3]]
    assert kinds == [
        HistoricalExecutionTransitionKind.OPEN,
        HistoricalExecutionTransitionKind.REDUCE,
        HistoricalExecutionTransitionKind.CLOSE,
    ]
    # the same evaluation ending while the first attempt waits for its book: an OUTSTANDING obligation, a pending
    # attempt carried by the governed replay, and the exact breach to the end
    end = triggered_at + 10 * SECOND
    pending = computed(managed(world(path, end=end), archive=archive))
    (open_obligation,) = pending.protective_obligations
    assert (open_obligation.status, open_obligation.breach_duration_ns, open_obligation.outstanding_quantity) == (
        HistoricalExecutionProtectiveObligationStatus.OUTSTANDING,
        end - triggered_at,
        d(-1),
    )
    (unfilled,) = protective_fills(pending)
    assert (unfilled.outcome, unfilled.reason) == (HistoricalExecutionFillOutcome.UNFILLED, "execution_window_closed")
    replay = governed(pending, windows=((ANCHOR, end, 0, 1),), protective=((ANCHOR, end + DAY),))
    assert replay.pending_protective_attempt_time_ns == triggered_at
    assert replay.protective_obligations == pending.protective_obligations


@pytest.mark.parametrize(("offset", "stopped"), [(Fraction(0), True), (-Fraction(1, 10**18), False)])
def test_a_2002_bar_history_of_equal_true_ranges_keeps_the_exact_stop_equality_boundary(
    offset: Fraction, stopped: bool
) -> None:
    archive = ohlc_archive(-2000, 1)  # every true range 2: the exact ATR over all 2,001 of them is exactly 2
    level = basis() + 3 + offset
    result = computed(managed(world(Path(rates=(POSITIVE,) * 6, mark=jump(48, level)), end=END_2D), archive=archive))
    protection = result.excursion_protections[0]
    assert (protection.atr_value, protection.atr_run_bar_count) == (d(2), 2002)
    kinds = [item.trigger_kind for item in result.protective_obligations[0].triggers]
    if stopped:
        assert kinds == [HistoricalExecutionProtectiveTriggerKind.STOP]
    else:
        assert kinds == [HistoricalExecutionProtectiveTriggerKind.MAX_HOLD]


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


def test_a_v3_or_v4_schedule_is_required_exactly_for_a_position_managed_baseline() -> None:
    result = hold_result()
    legacy = replace(schedule(), schema_version="historical-execution-admission-schedule.v2", protective_windows=())
    with pytest.raises(HistoricalExecutionEconomicsError, match=code("admission_schedule_version_mismatch")):
        simulate_historical_execution_governed_paper(
            result, expected_result_digest=result.result_digest, schedule=legacy
        )
    unmanaged = econ.default_result()  # no position management: only the v2 schedule re-runs it
    for version in (V3, INFORMATION_TIME):
        with pytest.raises(HistoricalExecutionEconomicsError, match=code("admission_schedule_version_mismatch")):
            simulate_historical_execution_governed_paper(
                unmanaged,
                expected_result_digest=unmanaged.result_digest,
                schedule=replace(schedule(), schema_version=version),
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


# --- G. the governed decision portfolio (S1_NO_TRADE_NATIVE_MEASUREMENT_CLOSURE_V1) -----------------------------------------

# The accepted-main identities (main 99518b37) of the world this section reuses: recording a decision portfolio
# changes neither the economics nor the governed outcome.
ACCEPTED_MAIN_HOLD_RESULT = "d106c6899663fc63d31158cedd65b9387b64c8c5189d5ae91025f0df159e47dc"
ACCEPTED_MAIN_HOLD_GOVERNED = "4e77e8e5f74edcb0532936a8aec8b54f9bdb979f9c6d5f45f8ed7371e6b37f72"
FLAT_PATH = Path(rates=(POSITIVE,) * 6)
STOPPED_OUT = Path(rates=(POSITIVE,) * 6, mark=jump(48, 310))  # SYNTHETIC: the D_0 SHORT stops out ~2.1% of NAV down
# SYNTHETIC: a 60-character mark visible at 16 h 6 s, before D_1 at 16 h 10 s, values the open SHORT outside the domain
NAV_SPIKE = Path(rates=(POSITIVE,) * 6, extra_marks=((ANCHOR + 2 * FUNDING + 5 * SECOND, Fraction(9 * 10**40)),))
STALE_D1 = ((1, 2 * HOUR),)  # SYNTHETIC: record 1 published 2 h after its 16 h settlement: D_1 decides at 18 h


def mark_gap(j: int) -> Fraction | None:
    return None if 63 <= j < 73 else Fraction(100)  # SYNTHETIC: no mark from 15 h 45 min to 18 h


MARK_GAP = Path(rates=(POSITIVE,) * 6, mark=mark_gap)


def published_records(path: Path, published: tuple[tuple[int, int], ...]) -> tuple:
    """``records_of(path)`` with final funding record ``k`` visible ``delay`` after its liability, per ``(k, delay)``."""

    delays = dict(published)
    rows = []
    for record in records_of(path):
        if record.series_id != "funding-final" or record.sequence_id not in delays:
            rows.append(record)
            continue
        visible = ANCHOR + (record.sequence_id + 1) * FUNDING + delays[record.sequence_id]
        rows.append(
            build_historical_pit_record(
                series_id=record.series_id,
                data_requirement_key="funding_rate",
                instrument=INS,
                sequence_id=record.sequence_id,
                event_time_ns=record.event_time_ns,
                available_at_ns=visible,
                finalized_at_ns=visible,
                revision_vintage_id=None,
                values=record.values,
            )
        )
    return tuple(rows)


@functools.cache
def variant_world(
    path: Path, *, end: int, published: tuple[tuple[int, int], ...] = (), start: int = ANCHOR
) -> econ.World:
    """A SYNTHETIC world of ``path`` with the given final-rate publication instants and evaluation start."""

    manifest, admission, registry = _chain()
    dataset = build_historical_pit_dataset(
        manifest,
        expected_source_manifest_digest=manifest.source_packet_evidence_digest,
        expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
        dataset_id="dataset-protective-variant",
        correlation_id="corr-1",
        source_reference="archive:history",
        rights_status="own_research",
        rights_reference="license-1",
        records=published_records(path, published),
    )
    binding = bind.executable_binding(admission, binding_id="binding-1")
    run = runt.decision_run(
        dataset,
        binding,
        instrument=INS,
        evaluation_start_ns=start,
        evaluation_end_ns=end,
        parameter_assignment=prof.params(n="1"),
    )
    return econ.World(run, dataset, registry)


INFORMATION_TIME = HISTORICAL_EXECUTION_INFORMATION_TIME_ADMISSION_SCHEDULE_SCHEMA_VERSION
V3 = HISTORICAL_EXECUTION_PROTECTIVE_ADMISSION_SCHEDULE_SCHEMA_VERSION


def both_sides(
    start: int = ANCHOR, end: int = END_2D, refused: tuple[int, ...] = (), *, version: str = INFORMATION_TIME
) -> HistoricalExecutionAdmissionSchedule:
    """SYNTHETIC schedule (information-time v4 unless ``version`` says otherwise): one LONG and SHORT cycle window over
    ``[start, end)``, protected a day past it."""

    return replace(
        schedule(windows=((start, end, 1, 1),), protective=((start, end + DAY),)),
        schema_version=version,
        entry_refused_decision_sequences=refused,
    )


def governed_under(
    result: HistoricalExecutionEconomicsResult, admission: HistoricalExecutionAdmissionSchedule
) -> HistoricalExecutionGovernedPaperOutcome:
    outcome = simulate_historical_execution_governed_paper(
        result, expected_result_digest=result.result_digest, schedule=admission
    )
    assert outcome.simulated is True, outcome.reason_codes
    return outcome


def portfolio_of(
    result: HistoricalExecutionEconomicsResult, admission: HistoricalExecutionAdmissionSchedule
) -> HistoricalExecutionGovernedPaperDecisionPortfolio:
    portfolio = simulate_historical_execution_governed_paper_decision_portfolio(
        result, expected_result_digest=result.result_digest, schedule=admission
    )
    assert portfolio.simulated is True, portfolio.reason_codes
    return portfolio


def snapshot_at(
    portfolio: HistoricalExecutionGovernedPaperDecisionPortfolio, at_ns: int
) -> HistoricalExecutionDecisionPortfolioSnapshot:
    (found,) = [item for item in portfolio.snapshots if item.decision_time_ns == at_ns]
    return found


def midnight_equity(outcome: HistoricalExecutionGovernedPaperOutcome, day_ns: int) -> str:
    (found,) = [
        item.equity
        for item in outcome.valuations
        if item.time_ns == day_ns and item.valuation_kind is HistoricalExecutionValuationKind.UTC_DAY_BOUNDARY
    ]
    return found


def nav_oracle(w: econ.World, outcome: HistoricalExecutionGovernedPaperOutcome, at_ns: int) -> tuple[str | None, int]:
    """INDEPENDENT ORACLE: ``(NAV known at a decision instant, unpublished settlement count)`` from public facts only.

    The state is the outcome's latest valuation before the decision in the engine's equal-instant order (the initial
    and settlement valuations of that instant precede it; its fills and its day boundary follow it). A settlement whose
    final record is not yet visible at the instant is removed, and an open position is valued at the public visible
    mark of the instant (no NAV when there is none).
    """

    visible = {
        item.record_digest: max(item.available_at_ns, item.finalized_at_ns)  # type: ignore[type-var]
        for item in w.dataset.records
        if item.series_id == "funding-final"
    }
    first = (HistoricalExecutionValuationKind.INITIAL, HistoricalExecutionValuationKind.FUNDING_SETTLEMENT)
    state = [
        item
        for item in outcome.valuations
        if item.time_ns < at_ns or (item.time_ns == at_ns and item.valuation_kind in first)
    ][-1]
    unpublished = [
        Fraction(item.cashflow_amount)
        for item in outcome.funding_cashflows
        if item.liability_time_ns <= at_ns and visible[item.funding_record_digest] > at_ns
    ]
    cash = (
        Fraction(economics_policy().initial_equity)
        + Fraction(state.cumulative_realized_gross_pnl)
        - Fraction(state.cumulative_fees)
        + Fraction(state.cumulative_funding)
        - sum(unpublished, Fraction(0))
    )
    quantity = Fraction(state.position_quantity)
    if quantity == 0:
        return d(cash), len(unpublished)
    mark = historical_execution_latest_visible_mark(w.dataset, policy=economics_policy(), instrument=INS, at_ns=at_ns)
    if mark is None:
        return None, len(unpublished)
    average = Fraction(state.average_entry_price)  # type: ignore[arg-type]
    return d(cash + quantity * (Fraction(mark[1]) - average)), len(unpublished)


def candidate_oracle(
    outcome: HistoricalExecutionGovernedPaperOutcome,
    snapshot: HistoricalExecutionDecisionPortfolioSnapshot,
    mark: tuple[str, str] | None,
) -> tuple[str, str | None, str]:
    """INDEPENDENT ORACLE: ``(candidate, projected NAV, reason)`` of one decision from its public intent and mark.

    The candidate is the position after the decision's intent filled in full (its own position without an intent); an
    entry, which increases the magnitude, is projected at the public visible mark net of its taker fee.
    """

    intents = [item for item in outcome.intents if item.decision_sequence == snapshot.decision_sequence]
    if not intents:
        return snapshot.position_quantity, None, ""
    (intent,) = intents
    candidate = Fraction(intent.actual_quantity) + Fraction(intent.delta_quantity)
    if abs(candidate) <= abs(Fraction(snapshot.position_quantity)):
        return d(candidate), None, ""
    if mark is None:
        return d(candidate), None, "no_fresh_visible_mark"
    fee = abs(Fraction(intent.delta_quantity)) * Fraction(mark[1]) * Fraction(economics_policy().taker_fee_bps) / 10_000
    return d(candidate), d(Fraction(snapshot.nav) - fee), ""  # type: ignore[arg-type]


# The governed ledgers of an outcome: every one but the schedule's own identity.
LEDGERS = (
    "intents",
    "fills",
    "position_transitions",
    "fee_cashflows",
    "funding_cashflows",
    "valuations",
    "trades",
    "terminal_state",
    "excursion_protections",
    "protective_obligations",
    "protective_attempts",
)


def test_the_decision_portfolio_is_the_one_governed_run_and_changes_no_accepted_identity() -> None:
    result = hold_result()
    assert result.result_digest == ACCEPTED_MAIN_HOLD_RESULT
    accepted = governed(result)
    assert accepted.outcome_digest == ACCEPTED_MAIN_HOLD_GOVERNED
    information = replace(schedule(), schema_version=INFORMATION_TIME)
    outcome = governed_under(result, information)
    # every final rate here is visible 10 s after its settlement, before any admission, and one unit is ~1% of NAV:
    # information time admits exactly what the accepted v3 re-run admits; only the schedule identity differs
    assert [getattr(outcome, name) for name in LEDGERS] == [getattr(accepted, name) for name in LEDGERS]
    assert outcome.schedule_digest != accepted.schedule_digest
    portfolio = portfolio_of(result, information)
    assert (portfolio.outcome_digest, portfolio.schedule_digest, portfolio.reason_codes) == (
        outcome.outcome_digest,
        outcome.schedule_digest,
        (),
    )
    decisions = world(HOLD, end=HOLD_END).run.decisions
    assert [(item.decision_sequence, item.decision_time_ns, item.decision_digest) for item in portfolio.snapshots] == [
        (item.decision_sequence, item.decision_time_ns, item.decision_digest) for item in decisions
    ]
    assert portfolio.portfolio_digest == historical_execution_governed_paper_decision_portfolio_digest(portfolio)
    payload = historical_execution_governed_paper_decision_portfolio_to_dict(portfolio)
    assert (payload["portfolio_digest"], len(payload["snapshots"])) == (portfolio.portfolio_digest, len(decisions))  # type: ignore[arg-type]
    assert portfolio_of(result, information) == portfolio  # deterministic
    forged = replace(portfolio, snapshots=(replace(portfolio.snapshots[0], nav=d(1)), *portfolio.snapshots[1:]))
    assert historical_execution_governed_paper_decision_portfolio_digest(forged) != portfolio.portfolio_digest
    assert (portfolio.paper_only, portfolio.execution_authorized, portfolio.venue_fill_truth_proven) == (
        True,
        False,
        False,
    )
    # a snapshot is information-time only where the admissions it conditions on are: no v3 decision portfolio exists
    for legacy in (schedule(), both_sides(version=V3)):
        with pytest.raises(
            HistoricalExecutionEconomicsError, match=code("decision_portfolio_needs_the_information_time_schedule")
        ):
            simulate_historical_execution_governed_paper_decision_portfolio(
                result, expected_result_digest=result.result_digest, schedule=legacy
            )


@pytest.mark.parametrize("path", [HOLD, STOPPED_OUT], ids=["hold", "stopped_out"])
def test_every_snapshot_is_the_exact_nav_known_before_its_decision(path: Path) -> None:
    w = world(path, end=HOLD_END if path is HOLD else END_2D)
    admission = replace(schedule(), schema_version=INFORMATION_TIME) if path is HOLD else both_sides()
    result = computed(managed(w))
    outcome = governed_under(result, admission)
    portfolio = portfolio_of(result, admission)
    assert portfolio.outcome_digest == outcome.outcome_digest
    entries = 0
    for item in portfolio.snapshots:
        assert (item.nav, item.unpublished_settlement_count) == nav_oracle(w, outcome, item.decision_time_ns), item
        assert (item.nav_reason, item.day_start_reason) == ("", ""), item  # every mark is fresh, every day valued
        mark = historical_execution_latest_visible_mark(
            w.dataset, policy=economics_policy(), instrument=INS, at_ns=item.decision_time_ns
        )
        assert (item.mark_record_digest, item.mark_price) == (mark or (None, None)), item  # open position or not
        assert item.order_in_flight is False
        expected = candidate_oracle(outcome, item, mark)
        assert (item.candidate_position_quantity, item.candidate_nav, item.candidate_nav_reason) == expected, item
        entries += item.candidate_nav is not None
    assert entries  # not vacuous: every world holds an entry candidate projected at its mark


def test_a_same_day_stop_out_loss_is_in_the_next_decisions_nav_and_its_day_start_is_the_midnight_valuation() -> None:
    result = computed(managed(world(STOPPED_OUT, end=END_2D)))
    outcome = governed_under(result, both_sides())
    opened, after_stop, next_day = (
        snapshot_at(portfolio_of(result, both_sides()), decision_instant(k)) for k in range(3)
    )
    # day 0 starts at the run's start, a UTC midnight: its initial valuation is the day-start NAV
    assert (opened.position_quantity, opened.nav, opened.day_start_ns, opened.day_start_nav) == (
        d(0),
        d(10_000),
        ANCHOR,
        d(10_000),
    )
    close = protective_fills(outcome)[0]
    assert close.execution_time_ns == book_visible(48) < decision_instant(1)  # the stop-out precedes D_1
    assert (after_stop.position_quantity, after_stop.day_start_ns, after_stop.day_start_nav) == (
        d(0),
        ANCHOR,
        d(10_000),
    )
    assert Fraction(after_stop.nav) - 10_000 < -200  # type: ignore[arg-type]  # the realized loss and both fees
    assert (next_day.day_start_ns, next_day.day_start_nav, next_day.day_start_reason) == (
        ANCHOR + DAY,
        midnight_equity(outcome, ANCHOR + DAY),
        "",
    )


def test_a_final_rate_published_after_the_decision_never_reaches_its_snapshot() -> None:
    """Ex-post settlement accounting: record 1 settles at 16 h but is published only at 25 h, after the D_2 decision."""

    w = variant_world(FLAT_PATH, end=END_2D, published=((1, 9 * HOUR),))
    result = computed(managed(w))
    outcome = governed_under(result, both_sides())
    portfolio = portfolio_of(result, both_sides())
    (late,) = [item for item in outcome.funding_cashflows if item.liability_time_ns == ANCHOR + 2 * FUNDING]
    before, after = snapshot_at(portfolio, decision_instant(2)), snapshot_at(portfolio, ANCHOR + 25 * HOUR)
    assert before.unpublished_settlement_count == 1  # liable and counted, its amount unknown and recorded nowhere
    assert (before.nav, 1) == nav_oracle(w, outcome, before.decision_time_ns)
    midnight = midnight_equity(outcome, ANCHOR + DAY)  # the booked equity, which already holds that settlement
    assert Fraction(before.day_start_nav) == Fraction(midnight) - Fraction(late.cashflow_amount)  # type: ignore[arg-type]
    # once published, the same settlement is known: in the NAV and in the day-start NAV alike
    assert (after.unpublished_settlement_count, after.day_start_nav) == (0, midnight)
    assert (after.nav, 0) == nav_oracle(w, outcome, after.decision_time_ns)
    assert Fraction(after.nav) - Fraction(before.nav) == Fraction(late.cashflow_amount)  # type: ignore[arg-type]


def test_the_day_start_is_never_substituted_on_a_partial_first_day_or_at_the_boundary_itself() -> None:
    start = ANCHOR + HOUR  # the run starts an hour after the first UTC midnight
    partial = portfolio_of(computed(managed(variant_world(FLAT_PATH, end=END_2D, start=start))), both_sides(start))
    first_day = [item for item in partial.snapshots if item.decision_time_ns < ANCHOR + DAY]
    assert [(item.day_start_ns, item.day_start_nav, item.day_start_reason) for item in first_day] == [
        (ANCHOR, None, "partial_first_utc_day")
    ] * 2
    later = [item for item in partial.snapshots if item.decision_time_ns >= ANCHOR + DAY]
    assert later and all(item.day_start_nav is not None and item.day_start_reason == "" for item in later)
    w = variant_world(FLAT_PATH, end=END_2D, published=((2, 0),))  # record 2 visible exactly at the second midnight
    result = computed(managed(w))
    outcome = governed_under(result, both_sides())
    at_midnight = snapshot_at(portfolio_of(result, both_sides()), ANCHOR + DAY)
    assert (at_midnight.day_start_ns, at_midnight.day_start_nav, at_midnight.day_start_reason) == (
        ANCHOR + DAY,
        None,
        "day_start_valued_after_the_decision",
    )
    # the settlement liable at that nanosecond precedes the decision, and its final rate is visible at it
    assert any(item.liability_time_ns == ANCHOR + DAY for item in outcome.funding_cashflows)
    assert (at_midnight.nav, at_midnight.unpublished_settlement_count) == nav_oracle(w, outcome, ANCHOR + DAY)
    assert at_midnight.unpublished_settlement_count == 0


def test_a_fill_at_the_decision_nanosecond_follows_it_and_a_pending_protective_exit_is_in_flight() -> None:
    def book(j: int, mid: Fraction) -> dict[str, str] | None:
        return None if 60 <= j < 64 else book_at(mid)  # the stop's first eligible book is slot 64's (16 h 31 s)

    path = Path(rates=(POSITIVE,) * 6, mark=jump(60, 104), book=book)
    w = variant_world(path, end=END_2D, published=((1, 31 * SECOND),))  # D_1 decides at that book's instant
    result = computed(managed(w))
    outcome = governed_under(result, both_sides())
    decided = ANCHOR + 2 * FUNDING + 31 * SECOND
    attempt, close = outcome.protective_attempts[0], protective_fills(outcome)[0]
    assert attempt.attempt_time_ns == slot(60) + VISIBLE < decided == close.execution_time_ns == book_visible(64)
    portfolio = portfolio_of(result, both_sides())
    snapshot = snapshot_at(portfolio, decided)
    assert (snapshot.position_quantity, snapshot.order_in_flight, snapshot.mark_price) == (d(-1), True, d(104))
    assert (snapshot.nav, snapshot.unpublished_settlement_count) == nav_oracle(w, outcome, decided)
    following = snapshot_at(portfolio, decision_instant(2))  # the close filled after D_1: D_2 decides FLAT
    assert (following.position_quantity, following.order_in_flight) == (d(0), False)


def test_rejected_and_unfilled_intents_leave_no_portfolio_state() -> None:
    def book(j: int, mid: Fraction) -> dict[str, str] | None:
        return None if 32 <= j < 64 else book_at(mid)  # no book from 8 h to 16 h: D_0's entry expires unfilled

    unfilled = computed(managed(world(Path(rates=(POSITIVE,) * 6, book=book), end=END_2D)))
    assert [item.outcome for item in unfilled.fills[:1]] == [HistoricalExecutionFillOutcome.UNFILLED]
    expired = snapshot_at(portfolio_of(unfilled, both_sides()), decision_instant(1))
    assert (expired.position_quantity, expired.order_in_flight, expired.nav) == (d(0), False, d(10_000))
    flat_ = computed(managed(world(FLAT_PATH, end=END_2D)))
    first = flat_.intents[0].decision_sequence
    refused = both_sides(refused=(first,))
    assert [item.outcome for item in governed_under(flat_, refused).fills[:1]] == [
        HistoricalExecutionFillOutcome.REJECTED
    ]
    rejected = snapshot_at(portfolio_of(flat_, refused), decision_instant(1))
    assert (rejected.position_quantity, rejected.order_in_flight, rejected.nav) == (d(0), False, d(10_000))
    neutral = snapshot_at(portfolio_of(flat_, both_sides()), decision_instant(1))
    assert neutral.position_quantity == d(-1) and Fraction(neutral.nav) < 10_000  # type: ignore[arg-type]


def test_a_nav_outside_the_numeric_domain_is_an_explicit_unavailable_reading_never_a_failed_run() -> None:
    """A SYNTHETIC mark spike visible just before D_1 values the open SHORT outside the scale-18 domain at that instant.

    The spike also triggers the stop, whose close fills at the next book (16 h 31 s) with the position already valued
    nowhere else, so the run completes and only the snapshot at D_1 cannot render its NAV.
    """

    result = computed(managed(world(NAV_SPIKE, end=END_2D)))
    portfolio = portfolio_of(result, both_sides())
    snapshot = snapshot_at(portfolio, decision_instant(1))
    assert (snapshot.position_quantity, snapshot.mark_price, snapshot.nav, snapshot.nav_reason) == (
        d(-1),
        d(9 * 10**40),
        None,
        "nav_unrepresentable",
    )
    assert snapshot.order_in_flight is True  # the stop the spike triggered still waits for its book
    assert (snapshot.day_start_nav, snapshot.day_start_reason) == (d(10_000), "")
    assert all(item.nav is not None and item.nav_reason == "" for item in portfolio.snapshots if item is not snapshot)


def test_an_open_position_without_a_fresh_mark_has_no_nav_and_never_a_substituted_one() -> None:
    """D_1 decides at 18 h on an open SHORT whose latest visible mark (15 h 30 min) is older than the 1 h staleness bound.

    The 16 h settlement still reads a fresh mark (30 min old), so the run completes; only the decision snapshot, which
    never reaches back to a stale price, cannot value the position.
    """

    w = variant_world(MARK_GAP, end=END_2D, published=STALE_D1)
    snapshot = snapshot_at(portfolio_of(computed(managed(w)), both_sides()), ANCHOR + 18 * HOUR)
    assert (snapshot.position_quantity, snapshot.mark_record_digest, snapshot.mark_price) == (d(-1), None, None)
    assert (snapshot.nav, snapshot.nav_reason) == (None, "no_fresh_visible_mark")
    visible = historical_execution_latest_visible_mark(
        w.dataset, policy=economics_policy(), instrument=INS, at_ns=ANCHOR + 18 * HOUR
    )
    assert visible is None  # the public visible-mark rule agrees: there is no fresh mark at the decision
    assert (snapshot.day_start_nav, snapshot.day_start_reason) == (d(10_000), "")  # the day start needs no mark


# --- H. information-time admission and the entry candidate (schedule v4) -----------------------------------------------------

UNIT18 = Fraction(1, 10**18)
CAP = HISTORICAL_EXECUTION_POSITION_CONCENTRATION_CAP
FILLED, REJECTED = HistoricalExecutionFillOutcome.FILLED, HistoricalExecutionFillOutcome.REJECTED
CONCENTRATION = "governed_paper_position_concentration_exceeded_at_fill"
JUMP = jump(80, 104)  # SYNTHETIC: a mark of 104 from 20 h stops an open SHORT out
LATE = ((1, 17 * HOUR),)  # SYNTHETIC (the audit's world): record 1 settles at 16 h and is published only at 33 h
PUBLICATION = ANCHOR + 33 * HOUR
# SYNTHETIC: record 1 (liable at 16 h) published at 33 h, record 2 (liable at the 24 h UTC midnight) at 34 h
TWO_LATE = ((1, 17 * HOUR), (2, 10 * HOUR))
SECOND_PUBLICATION = ANCHOR + 34 * HOUR
# Each world of this section covers only its own evaluation window: one day, or 36 h past both publications.
ONE_DAY, LONG_RUN = ANCHOR + DAY, ANCHOR + 36 * HOUR
# Identifiers derived from the run digest: two archives are two runs, so these differ by construction.
RUN_DERIVED = frozenset(
    {
        "intent_id",
        "intent_digest",
        "fill_id",
        "fill_digest",
        "decision_digest",
        "transition_id",
        "transition_digest",
        "fee_id",
        "fee_digest",
        "attempt_id",
        "attempt_digest",
        "attempt_ids",
        "obligation_id",
        "obligation_digest",
        "protection_id",
        "protection_digest",
        "trade_id",
        "opening_intent_id",
        "opening_fill_digest",
        "closing_fill_digest",
        "discharging_fill_digest",
    }
)


def path_to(end: int, rates: tuple[str, ...], **changes: object) -> Path:
    """A SYNTHETIC path whose marks and books cover exactly its evaluation window ``[ANCHOR, end]``."""

    return Path(rates=rates, slots=(end - ANCHOR) // SLOT + 4, **changes)  # type: ignore[arg-type]


@functools.cache
def equity_policy(initial_equity: str):  # noqa: ANN201
    """``economics_policy()`` at another SYNTHETIC initial equity."""

    return polt.cited_policy(
        latency_ns=100_000_000,
        max_execution_delay_ns=5 * MINUTE,
        max_mark_staleness_ns=HOUR,
        funding_interval_ns=FUNDING,
        initial_equity=initial_equity,
    )


@functools.cache
def funded(
    path: Path, end: int, published: tuple[tuple[int, int], ...] = (), initial_equity: object = 10_000
) -> tuple[econ.World, HistoricalExecutionEconomicsResult]:
    """The SYNTHETIC world of ``path`` until ``end`` with these final-rate publications, and its economics at
    ``initial_equity``. Every governed re-run re-proves the result against its digest, so it is not re-verified here."""

    w = variant_world(path, end=end, published=published)
    policy = equity_policy(d(initial_equity))
    result = build_historical_execution_economics(
        w.run,
        expected_run_digest=w.run.run_digest,
        economics_policy=policy,
        expected_economics_policy_digest=policy.policy_digest,
        economics_approval=econ.approval(w, policy),
        result_id="result-information-time",
        correlation_id="corr-1",
        position_management=pm_inputs(w),
    )
    assert (result.status, result.gate_verdict, result.simulated_economics_computed) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.PASS,
        True,
    ), result.verdict_reason_codes
    return w, result


@functools.cache
def governed_of(
    path: Path,
    end: int,
    published: tuple[tuple[int, int], ...] = (),
    initial_equity: object = 10_000,
    version: str = INFORMATION_TIME,
) -> HistoricalExecutionGovernedPaperOutcome:
    return governed_under(funded(path, end, published, initial_equity)[1], both_sides(end=end, version=version))


@functools.cache
def portfolio_at(
    path: Path, end: int, published: tuple[tuple[int, int], ...] = (), initial_equity: object = 10_000
) -> HistoricalExecutionGovernedPaperDecisionPortfolio:
    portfolio = portfolio_of(funded(path, end, published, initial_equity)[1], both_sides(end=end))
    assert portfolio.outcome_digest == governed_of(path, end, published, initial_equity).outcome_digest
    return portfolio


def admission_facts(outcome: HistoricalExecutionGovernedPaperOutcome, before_ns: int) -> dict[str, list]:
    """INDEPENDENT VIEW: every admission record of the public payload strictly before ``before_ns``, without identifiers.

    Intents decided, fill outcomes (at their execution, else their decision or attempt instant), transitions, fees and
    protective attempts before the instant, and the protections closed and the obligations discharged before it. The
    settlement ledger (funding cashflows, valuations, trades, terminal state) books a liability at its liability instant
    from its final rate, ex post, and is never an admission fact.
    """

    payload = historical_execution_governed_paper_outcome_to_dict(outcome)
    issued = {item.intent_id: item.decision_time_ns for item in outcome.intents}
    issued.update({item.attempt_id: item.attempt_time_ns for item in outcome.protective_attempts})
    instants: dict[str, list[int | None]] = {
        "intents": [item.decision_time_ns for item in outcome.intents],
        "fills": [
            issued[item.intent_id] if item.execution_time_ns is None else item.execution_time_ns
            for item in outcome.fills
        ],
        "position_transitions": [item.time_ns for item in outcome.position_transitions],
        "fee_cashflows": [item.time_ns for item in outcome.fee_cashflows],
        "protective_attempts": [item.attempt_time_ns for item in outcome.protective_attempts],
        "excursion_protections": [item.closed_at_ns for item in outcome.excursion_protections],
        "protective_obligations": [item.discharged_at_ns for item in outcome.protective_obligations],
    }
    return {
        name: [
            {key: value for key, value in row.items() if key not in RUN_DERIVED}
            for row, instant in zip(payload[name], times, strict=True)  # type: ignore[call-overload]
            if instant is not None and instant < before_ns
        ]
        for name, times in instants.items()
    }


def snapshots_before(portfolio: HistoricalExecutionGovernedPaperDecisionPortfolio, before_ns: int) -> list:
    return [item for item in portfolio.snapshots if item.decision_time_ns < before_ns]


def decision_fill(outcome: HistoricalExecutionGovernedPaperOutcome, decided_ns: int):  # noqa: ANN201
    """The last fill outcome of the intent decided at ``decided_ns``."""

    (intent,) = [item for item in outcome.intents if item.decision_time_ns == decided_ns]
    return [item for item in outcome.fills if item.intent_id == intent.intent_id][-1]


def candidate_equities(
    w: econ.World, outcome: HistoricalExecutionGovernedPaperOutcome, fill: object, initial_equity: object
) -> tuple[Fraction, Fraction, Fraction]:
    """INDEPENDENT ORACLE: ``(post-fill notional, publication-visible equity, booked equity)`` of one SELL entry from flat.

    The fill model is recomputed from the fill's public quote (``visible_depth_linear_v1``, the policy's slippage floor
    and impact coefficient), the mark from the public visible-mark rule at the fill, the earlier ledgers from the
    outcome, and every settlement liable by the fill split by its final rate's publication in the archive.
    """

    policy = equity_policy(d(initial_equity))
    instant = fill.execution_time_ns  # type: ignore[attr-defined]
    bid, ask = Fraction(fill.best_bid_price), Fraction(fill.best_ask_price)  # type: ignore[attr-defined]
    depth = Fraction(fill.side_visible_quantity)  # type: ignore[attr-defined]
    quantity = min(Fraction(fill.requested_quantity), Fraction(fill.max_executable_quantity))  # type: ignore[attr-defined]
    mid = (bid + ask) / 2
    impact = Fraction(policy.impact_coefficient_bps_per_participation_pct) * quantity / depth * 100
    slippage = max(Fraction(policy.slippage_floor_bps), (ask - bid) / mid * 10_000 / 2 + impact)
    price = mid * (1 - slippage / 10_000)
    if fill.fill_price is not None:  # type: ignore[attr-defined]
        assert Fraction(fill.fill_price) == price  # type: ignore[attr-defined]
    mark = historical_execution_latest_visible_mark(w.dataset, policy=policy, instrument=INS, at_ns=instant)
    assert mark is not None
    visible = {
        item.record_digest: max(item.available_at_ns, item.finalized_at_ns)  # type: ignore[type-var]
        for item in w.dataset.records
        if item.series_id == "funding-final"
    }
    liable = [item for item in outcome.funding_cashflows if item.liability_time_ns <= instant]
    known = [Fraction(item.cashflow_amount) for item in liable if visible[item.funding_record_digest] <= instant]
    unknown = [Fraction(item.cashflow_amount) for item in liable if visible[item.funding_record_digest] > instant]
    earlier = [item for item in outcome.position_transitions if item.time_ns < instant]
    equity = (
        Fraction(initial_equity)  # type: ignore[arg-type]
        + sum((Fraction(item.realized_gross_pnl) for item in earlier), Fraction(0))
        - sum((Fraction(item.fee_amount) for item in outcome.fee_cashflows if item.time_ns < instant), Fraction(0))
        - price * quantity * Fraction(policy.taker_fee_bps) / 10_000  # this fill's own taker fee
        + sum(known, Fraction(0))
        - quantity * (Fraction(mark[1]) - price)  # the SHORT's mark-to-market at the fill mark
    )
    return quantity * Fraction(mark[1]), equity, equity + sum(unknown, Fraction(0))


def audit_path(rate: str) -> Path:
    return path_to(LONG_RUN, (POSITIVE, rate, *(POSITIVE,) * 4), mark=JUMP)


def test_the_audit_world_admits_nothing_on_an_unpublished_rate_and_v3_keeps_its_accepted_admission() -> None:
    """P2-PIT-UNPUBLISHED-FUNDING-ADMISSION, the audit's exact world: initial equity 108.27, record 1 hidden at 0.001 or
    0.0002 until 33 h. On the old head its 24 h entry FILLED on one rate and was REJECTED on the other, and the 32 h
    position, NAV, NT-R03 and NT-R04 followed. Under schedule v4 no admission, snapshot or position before 33 h depends
    on the rate. The accepted v3 re-run keeps its booked-equity admission, as on accepted main.
    """

    paths = [audit_path(rate) for rate in (d("0.001"), POSITIVE)]
    facts = [admission_facts(governed_of(item, LONG_RUN, LATE, d("108.27")), PUBLICATION) for item in paths]
    assert facts[0] == facts[1]
    # every SHORT entry of ~100 against an equity of ~108 is above 25% of NAV: it is refused at its fill
    assert {(row["outcome"], row["reason"]) for row in facts[0]["fills"]} == {("REJECTED", CONCENTRATION)}
    portfolios = [portfolio_at(item, LONG_RUN, LATE, d("108.27")) for item in paths]
    assert snapshots_before(portfolios[0], PUBLICATION) == snapshots_before(portfolios[1], PUBLICATION)
    at_32 = [snapshot_at(item, decision_instant(3)) for item in portfolios]
    assert at_32[0] == at_32[1] and (at_32[0].position_quantity, at_32[0].nav) == (d(0), d("108.27"))
    legacy = [governed_of(item, LONG_RUN, LATE, d("108.27"), V3) for item in paths]
    assert [(item.outcome, item.reason) for item in (decision_fill(each, decision_instant(2)) for each in legacy)] == [
        (FILLED, "filled"),
        (REJECTED, "risk_limit_exceeded"),
    ]


@pytest.mark.parametrize("direction", ["SHORT", "LONG"])
def test_unpublished_rates_reach_no_admission_snapshot_or_day_start_before_their_publication(direction: str) -> None:
    """The D_0 position (8 h) is held through the 16 h and the 24 h (UTC midnight) settlements to its 24 h deadline
    close (32 h 15 min 31 s); their final rates are published only at 33 h and 34 h. Variants of those two rates: the
    reference and zero with a sign flip, and (SHORT) a larger second rate and a first rate one scale-18 unit away."""

    base = Fraction(RATES[direction][0])
    variants = [(base, base), (Fraction(0), -base)]
    if direction == "SHORT":
        variants += [(base, 15 * base), (base + UNIT18, base)]
    paths = [path_to(LONG_RUN, (d(base), d(first), d(second), *(d(base),) * 3)) for first, second in variants]
    outcomes = [governed_of(item, LONG_RUN, TWO_LATE) for item in paths]
    portfolios = [portfolio_at(item, LONG_RUN, TWO_LATE) for item in paths]
    reference = admission_facts(outcomes[0], PUBLICATION)
    assert [row["reason"] for row in reference["fills"]] == ["filled", "filled"]  # the entry and its deadline close
    assert all(admission_facts(item, PUBLICATION) == reference for item in outcomes)
    held = snapshots_before(portfolios[0], PUBLICATION)
    assert all(snapshots_before(item, PUBLICATION) == held for item in portfolios)
    # at 32 h 10 s both settlements are liable and unknown, the midnight one in that midnight's day-start NAV as well
    w, outcome = funded(paths[0], LONG_RUN, TWO_LATE)[0], outcomes[0]
    late = snapshot_at(portfolios[0], decision_instant(3))
    assert (late.unpublished_settlement_count, late.day_start_ns) == (2, ANCHOR + DAY)
    assert (late.nav, 2) == nav_oracle(w, outcome, late.decision_time_ns)
    booked = [
        item for item in outcome.funding_cashflows if item.liability_time_ns in (ANCHOR + 2 * FUNDING, ANCHOR + DAY)
    ]
    unknown = sum((Fraction(item.cashflow_amount) for item in booked), Fraction(0))
    assert len(booked) == 2 and unknown != 0
    assert Fraction(late.day_start_nav) == Fraction(midnight_equity(outcome, ANCHOR + DAY)) - unknown  # type: ignore[arg-type]
    # from 33 h record 1 is known and record 2 still is not: the variants sharing the first rate agree until 34 h
    if direction == "SHORT":
        second = SECOND_PUBLICATION
        assert admission_facts(outcomes[2], second) == admission_facts(outcomes[0], second)
        assert snapshots_before(portfolios[2], second) == snapshots_before(portfolios[0], second)
    # at and after each publication the rate is known, in the NAV of every decision that reads it
    for item, each, portfolio in zip(paths, outcomes, portfolios, strict=True):
        world_ = funded(item, LONG_RUN, TWO_LATE)[0]
        for snapshot in portfolio.snapshots:
            if snapshot.decision_time_ns >= PUBLICATION:
                expected = nav_oracle(world_, each, snapshot.decision_time_ns)
                assert (snapshot.nav, snapshot.unpublished_settlement_count) == expected


@pytest.mark.parametrize(
    ("initial_equity", "rate", "filled"),
    [(421, d("-0.01"), True), (420, d("0.01"), False)],
    ids=["visible_admits_booked_would_refuse", "visible_refuses_booked_would_admit"],
)
def test_an_entry_fill_admits_on_the_publication_visible_equity_never_on_the_booked_one(
    initial_equity: int, rate: str, filled: bool
) -> None:
    """The D_0 SHORT (8 h) is liable for record 1's 16 h settlement and stops out at 20 h (mark 104); the D_2 re-entry
    fills at 24 h 31 s, while record 1 is published only at 33 h. Every admission before 33 h is the reference world's
    (record 1 at the base rate), and the independent oracle shows that an admission on the booked equity would differ."""

    outcome = governed_of(audit_path(rate), LONG_RUN, LATE, initial_equity)
    reference = governed_of(audit_path(POSITIVE), LONG_RUN, LATE, initial_equity)
    assert admission_facts(outcome, PUBLICATION) == admission_facts(reference, PUBLICATION)
    entry = decision_fill(outcome, decision_instant(2))
    assert (entry.outcome, entry.reason) == ((FILLED, "filled") if filled else (REJECTED, CONCENTRATION))
    w = funded(audit_path(rate), LONG_RUN, LATE, initial_equity)[0]
    notional, visible, booked = candidate_equities(w, outcome, entry, initial_equity)
    assert (notional <= CAP * visible) is filled  # the engine admits on the publication-visible equity
    assert booked - visible == 100 * Fraction(rate)  # the SHORT's hidden 16 h settlement at mark 100
    assert (notional <= CAP * booked) is not filled  # the booked equity would tip the very same fill the other way


# The D_0 SHORT fills 1 at 99.945 against mark 100 (fee 0.0499725, mark-to-market -0.055): at this SYNTHETIC initial
# equity its post-fill notional is exactly 25% of the candidate equity E - 0.1049725.
BOUNDARY = Fraction("400.1049725")
FLAT_DAY = path_to(ONE_DAY, (POSITIVE,) * 3)


@pytest.mark.parametrize(
    ("offset", "filled"), [(Fraction(0), True), (-UNIT18, False), (UNIT18, True)], ids=["equal", "above", "below"]
)
def test_an_entry_fill_is_refused_strictly_above_25pct_of_its_equity_at_the_exact_boundary(
    offset: Fraction, filled: bool
) -> None:
    initial = BOUNDARY + offset
    outcome = governed_of(FLAT_DAY, ONE_DAY, (), initial)
    entry = decision_fill(outcome, decision_instant(0))
    notional, equity, booked = candidate_equities(funded(FLAT_DAY, ONE_DAY, (), initial)[0], outcome, entry, initial)
    assert (notional, equity, booked) == (100, initial - Fraction("0.1049725"), initial - Fraction("0.1049725"))
    assert (notional <= CAP * equity) is filled
    assert (entry.outcome, entry.reason) == ((FILLED, "filled") if filled else (REJECTED, CONCENTRATION))
    if not filled:
        # the decision projects the candidate at its mark with its fee and no slippage, within 25% here: only the exact
        # fill-time bound refuses it; the accepted v3 re-run has no such bound and fills it
        projected = snapshot_at(portfolio_at(FLAT_DAY, ONE_DAY, (), initial), decision_instant(0))
        assert Fraction(projected.candidate_nav) == initial - Fraction("0.05")  # type: ignore[arg-type]
        assert 100 <= CAP * Fraction(projected.candidate_nav)  # type: ignore[arg-type]
        assert decision_fill(governed_of(FLAT_DAY, ONE_DAY, (), initial, V3), decision_instant(0)).outcome is FILLED


def test_a_mark_that_moves_between_the_decision_and_its_fill_is_bounded_at_the_fill() -> None:
    """A SYNTHETIC mark of 110 (event 8 h 20 s) is visible between the D_0 decision (8 h 10 s, mark 100) and its fill
    (8 h 31 s): the candidate is within 25% at the decision and above it at the fill, where it is refused."""

    path = path_to(ONE_DAY, (POSITIVE,) * 3, extra_marks=((ANCHOR + FUNDING + 20 * SECOND, Fraction(110)),))
    decided = snapshot_at(portfolio_at(path, ONE_DAY, (), 420), decision_instant(0))
    assert (decided.mark_price, decided.candidate_position_quantity, decided.candidate_nav) == (
        d(100),
        d(-1),
        d("419.95"),
    )
    assert 100 <= CAP * Fraction(decided.candidate_nav)  # type: ignore[arg-type]
    outcome = governed_of(path, ONE_DAY, (), 420)
    entry = decision_fill(outcome, decision_instant(0))
    assert (entry.outcome, entry.reason) == (REJECTED, CONCENTRATION)
    notional, equity, _ = candidate_equities(funded(path, ONE_DAY, (), 420)[0], outcome, entry, 420)
    assert notional == 110 and notional > CAP * equity


def half_book(j: int, mid: Fraction) -> dict[str, str] | None:
    return book_at(mid, depth=25) if j == 32 else book_at(mid)  # the D_0 fill is capped at half a unit


HALF_DAY = path_to(ONE_DAY, (POSITIVE,) * 3, book=half_book)


def test_a_partial_fill_is_bounded_on_the_quantity_it_actually_fills() -> None:
    """At a SYNTHETIC equity of 300 the full D_0 unit projects above 25% of NAV, while its depth-capped fill of half a
    unit (book depth 25 at 8 h 31 s) holds about 16.7%: the fill-time bound admits the smaller fill it proves safe (the
    governed gate refuses the full candidate at its decision; this run evaluates no gate). The next decision targets
    the full unit again: an add, whose candidate holds the half position already open."""

    portfolio = portfolio_at(HALF_DAY, ONE_DAY, (), 300)
    decided = snapshot_at(portfolio, decision_instant(0))
    assert (decided.candidate_position_quantity, decided.candidate_nav) == (d(-1), d("299.95"))
    assert 100 > CAP * Fraction(decided.candidate_nav)  # type: ignore[arg-type]
    outcome = governed_of(HALF_DAY, ONE_DAY, (), 300)
    entry = decision_fill(outcome, decision_instant(0))
    assert (entry.outcome, entry.filled_quantity) == (HistoricalExecutionFillOutcome.PARTIALLY_FILLED, d("0.5"))
    notional, equity, _ = candidate_equities(funded(HALF_DAY, ONE_DAY, (), 300)[0], outcome, entry, 300)
    assert notional == 50 and notional <= CAP * equity
    added = snapshot_at(portfolio, decision_instant(1))
    assert (added.position_quantity, added.candidate_position_quantity) == (d("-0.5"), d(-1))
    fee = Fraction(1, 2) * Fraction(added.mark_price) * Fraction(economics_policy().taker_fee_bps) / 10_000  # type: ignore[arg-type]
    assert Fraction(added.candidate_nav) == Fraction(added.nav) - fee  # type: ignore[arg-type]


def test_a_clamped_reversal_targets_flat_and_is_no_entry_candidate() -> None:
    flip = snapshot_at(
        portfolio_at(path_to(ONE_DAY, (POSITIVE, NEGATIVE, NEGATIVE)), ONE_DAY), decision_instant(1)
    )  # D_1 targets LONG while SHORT: its intent closes the SHORT only
    assert (
        flip.position_quantity,
        flip.candidate_position_quantity,
        flip.candidate_nav,
        flip.candidate_nav_reason,
    ) == (
        d(-1),
        d(0),
        None,
        "",
    )


def test_a_close_is_never_bounded_even_above_25pct_of_nav() -> None:
    """At a SYNTHETIC equity of 410 the D_0 SHORT fills within 25%; the 20 h mark jump to 104 lifts it above 25% of
    NAV and stops it out, and its close-only fill reduces exposure, so the bound never reaches it."""

    outcome = governed_of(path_to(ONE_DAY, (POSITIVE,) * 3, mark=JUMP), ONE_DAY, (), 410)
    entry, close = decision_fill(outcome, decision_instant(0)), protective_fills(outcome)[0]
    assert (entry.outcome, close.outcome) == (FILLED, FILLED)
    funding = sum(
        (
            Fraction(item.cashflow_amount)
            for item in outcome.funding_cashflows
            if item.liability_time_ns < close.execution_time_ns  # type: ignore[operator]
        ),
        Fraction(0),
    )
    fee = Fraction(entry.fill_notional) * Fraction(economics_policy().taker_fee_bps) / 10_000  # type: ignore[arg-type]
    held = 410 - fee + funding - (104 - Fraction(entry.fill_price))  # type: ignore[arg-type]
    assert 104 > CAP * held  # the SHORT held more than 25% of NAV when its close filled
