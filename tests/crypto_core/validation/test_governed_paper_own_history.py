"""S1_OWN_HISTORY_UNIFIED_CONSTRUCTION_V1: the own-history authority (C-1 to C-6) and its rule set v13 consumers (C-7).

Clause map (FA-n: the residual decision's acceptance items; "PR451": the measurement decision's construction cases):

* the shared numerical contract: ``test_the_surd_sign_*``, ``test_scores_*``, ``test_ehs_*``;
* E-1 and P-2 completeness: ``test_a_coverage_context_*``, ``test_admission_*``, ``test_completeness_*``;
* D6's five categories: ``test_d6_*``; D1 (PR451 returns table): ``test_sharpe_*``; D2/P-1 and FA-1: ``test_fa1_*``,
  ``test_p1_*``; D4/D5/P-4 (PR451 execution table, FA-3, FA-8 to FA-12, RD-11, RD-12): ``test_fill_rate_*``,
  ``test_rd11_*``, ``test_rd12_*``, ``test_fa8_*`` to ``test_fa12_*``, ``test_starved_*``; P-5 (FA-13, FA-14):
  ``test_drawdown_*``; P-6 (FA-15 to FA-17): ``test_hit_rate_*``, ``test_fa15_*``; P-3 (PR451 state-machine table, FA-4
  to FA-6): ``test_state_machine_*``; C-6: ``test_coverage_ends_*``, ``test_incubation_v13_*``;
* C-7 (FA-7, FA-18, D6 "FAIL dominates"): ``test_fa7_*``, ``test_fa18_*``, ``test_cold_start_*``, ``test_scale_1_*``,
  ``test_fb_activation_*``, ``test_the_own_history_facts_*``; the decided allocation (R-1): ``test_allocation_*``;
* X1 and FA-2: ``test_fa2_*``, ``test_x1_*``; caller input and tampering: ``test_the_derivation_*``; production refusal:
  ``test_production_*``. The day-seal lineage (seal v14, evidence v14, the legacy bytes of FA-19) is
  ``test_governed_paper_own_history_lineage``.

Engine worlds are the SYNTHETIC lifecycle worlds of ``test_historical_execution_protective_lifecycle`` under the policy v2
and a SYNTHETIC schedule v10 whose sizing, CVaR, Kelly and incubation bounds are permissive, so the engine admits exactly
what the accepted PR452 probes admitted (the policy v1 cannot prove R-5 at a schedule v7+ fill). The test-only own-history
table is installed per test; the production table admits no claim. WHITE-BOX tests (named so in their docstrings) call
the module's private helpers over SYNTHETIC facts to pin exact boundaries.
"""

from __future__ import annotations

import contextlib
import functools
import heapq
import itertools
from collections.abc import Iterator
from dataclasses import replace
from decimal import Decimal, localcontext
from fractions import Fraction
from types import SimpleNamespace

import pytest

import crypto_core.validation.governed_paper_own_history as own
from crypto_core.validation.governed_paper_allocation_envelope import (
    GovernedPaperAllocationActivation,
    GovernedPaperAllocationDecidedCandidate,
    GovernedPaperAllocationEligibility,
    GovernedPaperAllocationError,
    GovernedPaperAllocationStatus,
    derive_governed_paper_allocation_decided,
)
from crypto_core.validation.governed_paper_entry_safety import (
    GovernedPaperEntrySafetyError,
    GovernedPaperEntrySafetyIncubation,
    GovernedPaperEntrySafetyOwnHistory,
    GovernedPaperEntrySafetyStatus,
    evaluate_governed_paper_entry_safety,
    governed_paper_entry_safety_a9_multipliers,
)
from crypto_core.validation.governed_paper_incubation_authority import (
    GovernedPaperIncubationError,
    GovernedPaperIncubationState,
    build_governed_paper_incubation_reading,
    derive_governed_paper_incubation_authority,
    governed_paper_incubation_record_digest,
)
from crypto_core.validation.governed_paper_own_history import (
    GOVERNED_PAPER_OWN_HISTORY_COVERAGE_SCHEMA,
    GOVERNED_PAPER_OWN_HISTORY_HUMAN_CHANNEL,
    GOVERNED_PAPER_OWN_HISTORY_PRODUCTION_TABLE,
    GOVERNED_PAPER_OWN_HISTORY_TEST_CHANNEL,
    GovernedPaperOwnHistoryCheck,
    GovernedPaperOwnHistoryContext,
    GovernedPaperOwnHistoryCoverage,
    GovernedPaperOwnHistoryEhsStatus,
    GovernedPaperOwnHistoryError,
    GovernedPaperOwnHistoryOutcome,
    GovernedPaperOwnHistoryReading,
    GovernedPaperOwnHistoryState,
    GovernedPaperOwnHistoryStatus,
    GovernedPaperOwnHistoryTable,
    GovernedPaperOwnHistoryTruth,
    canonical_governed_paper_own_history_context,
    derive_governed_paper_own_history_evidence,
    governed_paper_own_history_coverage_cuts,
    governed_paper_own_history_coverage_digest,
    governed_paper_own_history_evidence_digest,
    governed_paper_own_history_prefix_digest,
    governed_paper_own_history_reading,
    governed_paper_own_history_reading_digest,
    verify_governed_paper_own_history_evidence,
)
from crypto_core.validation.historical_execution_economics import (
    HISTORICAL_EXECUTION_INCUBATION_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    HISTORICAL_EXECUTION_OWN_HISTORY_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    HistoricalExecutionAdmissionWindow,
    HistoricalExecutionCvarBound,
    HistoricalExecutionDepthCap,
    HistoricalExecutionExposureEnvelope,
    HistoricalExecutionFillOutcome,
    HistoricalExecutionFlattenWindow,
    HistoricalExecutionIncubationWindow,
    HistoricalExecutionProtectiveWindow,
    HistoricalExecutionSide,
    HistoricalExecutionTradeStatus,
    build_historical_execution_economics,
    simulate_historical_execution_governed_paper,
    simulate_historical_execution_governed_paper_derivation,
)
from crypto_core.validation.strategy_executable_profiles import (
    PASSIVE_FUNDING_CARRY_V1,
    get_strategy_executable_profile,
)

try:  # the module objects pytest collects (basename import), so cached worlds are shared
    import test_governed_paper_incubation_authority as ita
    import test_governed_paper_protective_ledger as plt
    import test_governed_paper_risk_measurement as rmt
    import test_governed_paper_system_safety as sst
    import test_historical_execution_protective_lifecycle as lifet
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_governed_paper_incubation_authority as ita
    from tests.crypto_core.validation import test_governed_paper_protective_ledger as plt
    from tests.crypto_core.validation import test_governed_paper_risk_measurement as rmt
    from tests.crypto_core.validation import test_governed_paper_system_safety as sst
    from tests.crypto_core.validation import test_historical_execution_protective_lifecycle as lifet

S, E, T, St, Out = (
    GovernedPaperOwnHistoryStatus,
    GovernedPaperOwnHistoryEhsStatus,
    GovernedPaperOwnHistoryTruth,
    GovernedPaperOwnHistoryState,
    GovernedPaperOwnHistoryOutcome,
)
GATE = GovernedPaperEntrySafetyStatus
V9 = HISTORICAL_EXECUTION_INCUBATION_ADMISSION_SCHEDULE_SCHEMA_VERSION
V10 = HISTORICAL_EXECUTION_OWN_HISTORY_ADMISSION_SCHEDULE_SCHEMA_VERSION
SECOND, MINUTE, HOUR, DAY = lifet.SECOND, lifet.MINUTE, lifet.HOUR, lifet.DAY
ANCHOR = lifet.ANCHOR  # a UTC midnight
PRE, FUNDING, PROTECTIVE, DECISION, FILL, BOUNDARY = -1, 0, 1, 2, 3, 4
TEST_TABLE = GovernedPaperOwnHistoryTable("test_only", GOVERNED_PAPER_OWN_HISTORY_TEST_CHANNEL, ())
HALT = lifet.book_visible(63)  # PR452 probe 1: the halt and flatten start that issues the child
X_CHILD = 1_641_657_631_000_000_000  # PR452 B1: the child's partial fill at a DECISION instant (ANCHOR + 16 h + 31 s)
X_ATTEMPT = 1_641_716_131_000_000_000  # PR452 B1: the v1 MAX_HOLD attempt's partial fill (ANCHOR + 32 h 15 min 31 s)
FOUR_DAYS = ANCHOR + 4 * DAY


@contextlib.contextmanager
def own_table(value: GovernedPaperOwnHistoryTable = TEST_TABLE) -> Iterator[None]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(own, "_TABLE", value)
        yield


# --- SYNTHETIC engine worlds ------------------------------------------------------------------------------------------------


def economics_v2(w: object):  # noqa: ANN201
    """The one engine's economics of ``w`` under the SYNTHETIC policy v2 (the governed inputs of the policy v1)."""

    policy = lifet.equity_policy(lifet.d(10_000))
    result = build_historical_execution_economics(
        w.run,  # type: ignore[attr-defined]
        expected_run_digest=w.run.run_digest,  # type: ignore[attr-defined]
        economics_policy=policy,
        expected_economics_policy_digest=policy.policy_digest,
        economics_approval=lifet.econ.approval(w, policy),
        result_id="result-own-history",
        correlation_id="corr-1",
        position_management=lifet.pm_inputs(w, policy=sst.pm_v2()),  # type: ignore[arg-type]
    )
    assert result.simulated_economics_computed is True, result.verdict_reason_codes
    return result


def schedule_v10(w: object, end: int, *, halt: int | None = None, flatten: tuple = (), **changes: object):  # noqa: ANN201
    """A SYNTHETIC schedule v10 over ``[ANCHOR, end)``: one LONG/SHORT window, an envelope of 1 and a cap of 1,000 on every
    book and side, unit CVaR 0, every entry decision an incubation decision inside one fill window with U5 covered."""

    caps = tuple(
        sorted(
            (
                HistoricalExecutionDepthCap(record.record_digest, side, "1000")
                for record in w.dataset.records  # type: ignore[attr-defined]
                if record.series_id == "book"
                for side in (HistoricalExecutionSide.BUY, HistoricalExecutionSide.SELL)
            ),
            key=lambda item: (item.book_record_digest, item.side.value),
        )
    )
    entries = tuple(
        item.decision_sequence
        for item in w.run.decisions  # type: ignore[attr-defined]
        if item.resulting_direction in ("LONG", "SHORT")
    )
    return replace(
        lifet.both_sides(end=end),
        schema_version=V10,
        exposure_envelopes=(HistoricalExecutionExposureEnvelope(ANCHOR, end, "1"),),
        depth_caps=caps,
        exposure_halt_from_ns=halt,
        flatten_windows=tuple(HistoricalExecutionFlattenWindow(start, stop, plt.AUTHORITY) for start, stop in flatten),
        cvar_bounds=(HistoricalExecutionCvarBound(ANCHOR, end, "0", "0"),),
        incubation_decision_sequences=entries,
        incubation_fill_windows=(HistoricalExecutionIncubationWindow(ANCHOR, end),),
        incubation_kelly_covered=True,
        **changes,
    )


def derivation_of(result: object, schedule: object):  # noqa: ANN201
    found = simulate_historical_execution_governed_paper_derivation(
        result,  # type: ignore[arg-type]
        expected_result_digest=result.result_digest,  # type: ignore[attr-defined]
        schedule=schedule,  # type: ignore[arg-type]
    )
    assert found.outcome.simulated is True, found.outcome.reason_codes
    return found


@functools.cache
def child_world(end: int = lifet.LONG_RUN) -> tuple:
    """PR452 probe 1: a flatten child in flight at the DECISION instant X_CHILD, partially filled there (0.5 of 1)."""

    w = lifet.variant_world(plt.THIN, end=end, published=((1, 31 * SECOND),))
    result = economics_v2(w)
    return w, result, derivation_of(result, schedule_v10(w, end, halt=HALT, flatten=((HALT, end),)))


@functools.cache
def attempt_world() -> tuple:
    """PR452 probe 2: a v1 MAX_HOLD protective attempt partially filled at X_ATTEMPT."""

    w = lifet.variant_world(plt.THIN, end=lifet.LONG_RUN)
    result = economics_v2(w)
    return w, result, derivation_of(result, schedule_v10(w, lifet.LONG_RUN))


@functools.cache
def refused_child_world() -> tuple:
    """PR452 probe 3: a flatten child refused at its attempt-time protective admission (no protective window at TAU)."""

    w = plt.baseline()[0]
    result = economics_v2(w)
    tau = plt.TAU
    windows = (
        HistoricalExecutionProtectiveWindow(ANCHOR, tau - HOUR, "a" * 64),
        HistoricalExecutionProtectiveWindow(tau + HOUR, lifet.LONG_RUN, "a" * 64),
    )
    schedule = schedule_v10(w, lifet.LONG_RUN, halt=tau, flatten=((tau, lifet.LONG_RUN),), protective_windows=windows)
    return w, result, derivation_of(result, schedule)


@functools.cache
def refused_at_fill_world() -> tuple:
    """Probe 1's world under the policy v1: R-5 is unproven at the entry's fill, a post-submission refusal (FA-9)."""

    w, result = lifet.funded(plt.THIN, lifet.LONG_RUN, published=((1, 31 * SECOND),))
    return (
        w,
        result,
        derivation_of(result, schedule_v10(w, lifet.LONG_RUN, halt=HALT, flatten=((HALT, lifet.LONG_RUN),))),
    )


@functools.cache
def clamp_world() -> tuple:
    """D_1 exits the SHORT (FLAT): its close-only intent requests exactly the open quantity (FA-11)."""

    path = lifet.path_to(lifet.ONE_DAY, (lifet.POSITIVE, lifet.NEGATIVE, lifet.NEGATIVE))
    w = lifet.variant_world(path, end=lifet.ONE_DAY)
    result = economics_v2(w)
    return w, result, derivation_of(result, schedule_v10(w, lifet.ONE_DAY))


def _no_book_after(slot: int):  # noqa: ANN202
    def book(j: int, mid: Fraction) -> dict[str, str] | None:
        return None if j >= slot else lifet.book_at(mid)

    return book


@functools.cache
def no_book_world() -> tuple:
    """No book from 8 h on: D_0's intent expires unfilled at D_0 + 5 min, a decision intent that never reached a book."""

    path = lifet.path_to(lifet.LONG_RUN, (lifet.POSITIVE,) * 6, book=_no_book_after(32))
    w = lifet.variant_world(path, end=lifet.LONG_RUN)
    result = economics_v2(w)
    return w, result, derivation_of(result, schedule_v10(w, lifet.LONG_RUN))


@functools.cache
def starved_world() -> tuple:
    """Four days without a book from 8 h on: every decision's intent is conclusively unfilled at its window close."""

    path = lifet.path_to(FOUR_DAYS, (lifet.POSITIVE,) * 16, book=_no_book_after(32))
    w = lifet.variant_world(path, end=FOUR_DAYS)
    result = economics_v2(w)
    return w, result, derivation_of(result, schedule_v10(w, FOUR_DAYS))


def hold_schedule(w: object, end: int):  # noqa: ANN201
    entries = tuple(
        item.decision_sequence
        for item in w.run.decisions  # type: ignore[attr-defined]
        if item.resulting_direction in ("LONG", "SHORT")
    )
    return rmt.v7_schedule(
        w,
        (HistoricalExecutionCvarBound(ANCHOR, end, "0", "0"),),
        schema_version=V10,
        windows=(HistoricalExecutionAdmissionWindow(ANCHOR, end, lifet.d(0), lifet.d(1), lifet.d(10_000)),),
        protective_windows=(HistoricalExecutionProtectiveWindow(ANCHOR, end + DAY, "a" * 64),),
        exposure_envelopes=(HistoricalExecutionExposureEnvelope(ANCHOR, end, "1"),),
        incubation_decision_sequences=entries,
        incubation_fill_windows=(HistoricalExecutionIncubationWindow(ANCHOR, end),),
        incubation_kelly_covered=True,
    )


@functools.cache
def hold_world(end: int = lifet.HOLD_END) -> tuple:
    """The lifecycle HOLD world under the policy v2: one SHORT entry, its MAX_HOLD close, a second entry and close."""

    result = sst.run_under(lifet.HOLD, end, "v2")
    w = lifet.world(lifet.HOLD, end=end)
    return w, result, derivation_of(result, hold_schedule(w, end))


# --- the own-history derivation over a world ------------------------------------------------------------------------------


def lineage_of(w: object, result: object, candidates: tuple[str, ...] = ("s1",)) -> own._Lineage:
    return own._Lineage(
        genesis_id="own-history-synthetic",
        genesis_digest="0" * 64,
        instrument=w.run.instrument,  # type: ignore[attr-defined]
        start_ns=w.run.evaluation_start_ns,  # type: ignore[attr-defined]
        sleeve_id="s1",
        candidates=candidates,
        executable_binding_digest=w.run.executable_binding_digest,  # type: ignore[attr-defined]
        source_manifest_digest=w.dataset.source_manifest_digest,  # type: ignore[attr-defined]
        economics_policy_digest=result.economics_policy_digest,  # type: ignore[attr-defined]
    )


def claim(  # noqa: PLR0913
    w: object,
    series: str,
    start: int,
    end: int,
    published: int,
    channel: str = GOVERNED_PAPER_OWN_HISTORY_TEST_CHANNEL,
    **changes: object,
) -> GovernedPaperOwnHistoryCoverage:
    """A SYNTHETIC coverage claim over the world's archive."""

    values: dict[str, object] = {
        "schema": GOVERNED_PAPER_OWN_HISTORY_COVERAGE_SCHEMA,
        "source_manifest_digest": w.dataset.source_manifest_digest,  # type: ignore[attr-defined]
        "instrument": w.run.instrument,  # type: ignore[attr-defined]
        "series_id": series,
        "start_ns": start,
        "end_ns": end,
        "channel": channel,
        "published_at_ns": published,
        "coverage_digest": "",
    }
    values.update(changes)
    seed = GovernedPaperOwnHistoryCoverage(**values)  # type: ignore[arg-type]
    return replace(seed, coverage_digest=governed_paper_own_history_coverage_digest(seed))


def series_of(w: object, result: object) -> tuple[str, str, str]:
    return (w.run.funding_series_id, result.mark_series_id, result.order_book_series_id)  # type: ignore[attr-defined]


def covered(
    world: tuple,
    published: int = ANCHOR,
    *,
    through: int | None = None,
    channel: str = GOVERNED_PAPER_OWN_HISTORY_TEST_CHANNEL,
) -> GovernedPaperOwnHistoryContext:
    """SYNTHETIC claims covering every series the economics reads from G, published at ``published``."""

    w, result, _ = world
    stop = (w.run.evaluation_end_ns if through is None else through) + DAY
    return GovernedPaperOwnHistoryContext(
        tuple(claim(w, item, ANCHOR, stop, published, channel) for item in series_of(w, result))
    )


def evidence_of(
    world: tuple,
    context: GovernedPaperOwnHistoryContext | None = None,
    table: GovernedPaperOwnHistoryTable = TEST_TABLE,
    candidates: tuple[str, ...] = ("s1",),
):  # noqa: ANN201
    w, result, derivation = world
    with own_table(table):
        return own._derive(
            lineage=lineage_of(w, result, candidates),
            run=w.run,
            dataset=w.dataset,
            result=result,
            expected_result_digest=result.result_digest,
            outcome=derivation.outcome,
            context=covered(world) if context is None else context,
        )


@functools.cache
def hold_evidence():  # noqa: ANN201
    return evidence_of(hold_world())


@functools.cache
def starved_evidence():  # noqa: ANN201
    return evidence_of(starved_world())


def facts_of(world: tuple, context: GovernedPaperOwnHistoryContext | None = None) -> own._Derivation:
    """WHITE-BOX: the derivation's facts over a world's own engine re-run."""

    w, result, derivation = world
    context = covered(world) if context is None else context
    return own._Derivation(
        lineage=lineage_of(w, result),
        run=w.run,
        dataset=w.dataset,
        result=result,
        derivation=derivation,
        coverage=own._Coverage(context.coverages, series_of(w, result)),
    )


def reading_at(evidence: object, instant: int) -> GovernedPaperOwnHistoryReading:
    (found,) = [item for item in evidence.readings if item.decision_time_ns == instant]  # type: ignore[attr-defined]
    return found


# --- the shared numerical contract ----------------------------------------------------------------------------------------


def _decimal(value: Fraction) -> Decimal:
    return Decimal(value.numerator) / Decimal(value.denominator)


def oracle(constant: Fraction, terms: tuple[tuple[Fraction, Fraction], ...]) -> int | None:
    """An independent 80-digit decimal sign; None where it cannot decide (an exact zero lies within the noise)."""

    with localcontext() as context:
        context.prec = 80
        value = _decimal(constant) + sum((_decimal(c) * _decimal(x).sqrt() for c, x in terms), Decimal(0))
    if abs(value) < Decimal("1e-40"):
        return None
    return 1 if value > 0 else -1


def test_the_surd_sign_is_exact_at_every_equality_and_next_to_it() -> None:
    """WHITE-BOX: the shared contract's exact comparison, never a float or an epsilon."""

    f = Fraction
    assert own._sign_root(f(2), f(-1), f(4)) == 0  # 2 - sqrt(4) = 0
    assert own._sign_root(f(3, 2), f(-1), f(2)) == 1  # 1.5 > sqrt(2)
    assert own._sign_root(f(7, 5), f(-1), f(2)) == -1  # 1.4 < sqrt(2)
    assert own._sign_root(f(-7, 5), f(1), f(2)) == 1
    assert own._sign_surd(f(-3), ((f(1), f(4)), (f(1), f(1)))) == 0  # -3 + 2 + 1
    assert own._sign_surd(f(0), ((f(1), f(8)), (f(-2), f(2)))) == 0  # sqrt(8) = 2 sqrt(2)
    assert own._sign_surd(f(-3), ((f(1), f(2)), (f(1), f(3)))) == 1  # sqrt(2) + sqrt(3) = 3.146...
    assert own._sign_surd(f(-4), ((f(1), f(2)), (f(1), f(3)))) == -1
    assert own._sign_surd(f(0), ((f(0), f(2)), (f(5), f(0)))) == 0  # zero coefficients and radicands drop out
    values = (f(0), f(1), f(-1), f(3, 2), f(-7, 5), f(2), f(1, 3))
    radicands = (f(2), f(3), f(4), f(5, 4), f(1, 2))
    for constant, a, x, b, y in itertools.product(values, values, radicands, values, radicands):  # metamorphic
        found = own._sign_surd(constant, ((a, x), (b, y)))
        expected = oracle(constant, ((a, x), (b, y)))
        assert found == (0 if expected is None else expected), (constant, a, x, b, y)
        assert own._sign_surd(-constant, ((-a, x), (-b, y))) == -found  # negation symmetry
    with pytest.raises(GovernedPaperOwnHistoryError, match="surd_with_more_than_two_radicals$"):
        own._sign_surd(f(0), ((f(1), f(2)), (f(1), f(3)), (f(1), f(5))))


def test_scores_clip_exactly_at_their_bounds() -> None:
    """WHITE-BOX: S_sharpe = min(1, max(0, Sharpe / 2)) and S_stability = min(1, max(0, 1 - CV / 2)), exact."""

    f = Fraction
    assert own._Sharpe(f(2), f(1)).score() == own._Surd(f(1))  # Sharpe / 2 = 1 exactly: the cap
    assert own._Sharpe(f(1), f(3)).score() == own._Surd(f(0), ((f(1, 2), f(3)),))  # sqrt(3) / 2 < 1
    assert own._Sharpe(f(0), f(3)).score() == own._Surd(f(0)) == own._Sharpe(f(-1), f(3)).score()
    assert own._Stability(f(1), f(0)).score() == own._Surd(f(1))  # a constant positive window: CV = 0
    assert own._Stability(f(1), f(4)).score() == own._Surd(f(0))  # CV = 2 exactly: S = 0
    half = own._Stability(f(1), f(1)).score()  # CV = 1: S = 1/2
    assert half.compare(f(1, 2)) == 0 and half.compare(f(1, 2) + f(1, 10**18)) == -1
    assert own._sharpe_of([f(100), f(101), f(10201, 100)]) is None  # constant +1% returns: zero variance is undefined
    navs = [f(100), f(101), f(99), f(100)]
    returns = [b / a - 1 for a, b in itertools.pairwise(navs)]
    mean = sum(returns, f(0)) / 3
    variance = sum(((item - mean) ** 2 for item in returns), f(0)) / 2  # n - 1
    assert own._sharpe_of(navs) == own._Sharpe(mean, f(365) / variance)


class _Fixed(own._Derivation):
    """WHITE-BOX: a derivation whose component readings are fixed, so ``inputs`` composes the EHS exactly."""

    def __init__(
        self, sharpe: own._Sharpe | None, hit: Fraction, drawdown: Fraction, stability: own._Stability
    ) -> None:
        self.values = (sharpe, hit, drawdown, stability)

    def complete(self, through_ns: int, at_ns: int) -> bool:
        return True

    def sharpe(self, key, days, complete, at_ns):  # noqa: ANN001, ANN201, ARG002
        found = self.values[0]
        return ((S.INSUFFICIENT, None) if found is None else (S.DEFINED, found)), 30

    def hit(self, key, complete, at_ns, window=0):  # noqa: ANN001, ANN201, ARG002
        return S.DEFINED, self.values[1], 0, None

    def drawdown(self, key, complete, at_ns):  # noqa: ANN001, ANN201, ARG002
        return S.DEFINED, self.values[2], self.values[2], self.values[2] >= Fraction(1, 20)

    def stability(self, key, complete):  # noqa: ANN001, ANN201, ARG002
        return S.DEFINED, self.values[3], 2


def test_ehs_thresholds_are_decided_exactly_at_0_70_0_50_and_0_30() -> None:
    """WHITE-BOX: EHS = 0.30 S_sharpe + 0.25 S_hitrate + 0.25 S_drawdown + 0.20 S_stability, every comparison exact."""

    f = Fraction
    capped, constant = own._Sharpe(f(4), f(1)), own._Stability(f(1), f(0))  # S_sharpe = 1, S_stability = 1
    key = (ANCHOR, DECISION, -1)
    exact = _Fixed(capped, f(1, 2), f(7, 200), constant).inputs(key)  # S_drawdown = 3/10: EHS = 7/10 exactly
    assert exact.ehs[0] is E.DEFINED and exact.ehs[1].compare(f(7, 10)) == 0  # type: ignore[union-attr]
    e01, e04, alpha = own._ehs_checks(exact, exclusive=True)
    assert (e01.outcome, e04.outcome, alpha.outcome) == (Out.PASS, Out.PASS, Out.PASS)
    below = _Fixed(capped, f(1, 2), f(7, 200) + f(1, 10**18), constant).inputs(key)
    assert own._ehs_checks(below, exclusive=True)[2] == GovernedPaperOwnHistoryCheck(
        Out.FAIL, "", "alpha_edge_proven_below_1", ()
    )
    assert own._ehs_checks(exact, exclusive=False)[1].reason == "asset_edge_universe_unproven"
    # an irrational S_sharpe at the 0.30 boundary: sqrt(3) / 4 = 0.433 (S_sharpe), hit 0, drawdown breach, stability 0
    irrational = _Fixed(own._Sharpe(f(1, 2), f(3)), f(0), f(1, 20), own._Stability(f(1), f(4))).inputs(key)
    ehs = irrational.ehs[1]
    assert ehs == own._Surd(f(0), ((f(3, 10) * f(1, 4), f(3)),))  # type: ignore[comparison-overlap]
    assert (ehs.compare(f(13, 100)), ehs.compare(f(12, 100))) == (-1, 1)  # type: ignore[union-attr]
    assert irrational.disable_condition() is True  # the 5% breach (and EHS < 0.30)
    insufficient = _Fixed(None, f(1, 2), f(0), constant).inputs(key)  # U1 insufficient only
    assert insufficient.ehs[0] is E.U1_INSUFFICIENT_ONLY
    e01, e04, alpha = own._ehs_checks(insufficient, exclusive=True)
    assert (e01.outcome, e01.covered) == (Out.COVERED, ("U1",))  # every completion keeps EHS >= 0.30
    assert (e04.outcome, alpha.outcome) == (Out.COVERED, Out.COVERED)  # 0.30 + 0.70 x ... can exceed 0.70
    poor = _Fixed(None, f(0), f(1, 20), own._Stability(f(1), f(4))).inputs(key)  # best completion: EHS = 0.30
    e01, e04, alpha = own._ehs_checks(poor, exclusive=True)
    assert (e04.reason, alpha.reason) == (
        "every_completion_leaves_edge_health_score_at_most_0_50",
        "every_completion_leaves_alpha_edge_below_1",
    )


# --- E-1 and P-2: the coverage authority ------------------------------------------------------------------------------------


def test_a_coverage_context_is_exact_typed_digest_bound_ordered_and_duplicate_free() -> None:
    w = hold_world()[0]
    first = claim(w, "funding", ANCHOR, ANCHOR + DAY, ANCHOR)
    second = claim(w, "mark", ANCHOR, ANCHOR + DAY, ANCHOR + 1)
    context = GovernedPaperOwnHistoryContext((first, second))
    assert canonical_governed_paper_own_history_context(context) is context
    for bad, reason in (
        (object(), "context_malformed"),
        (GovernedPaperOwnHistoryContext([first]), "context_malformed"),  # type: ignore[arg-type]
        (GovernedPaperOwnHistoryContext((replace(first, schema="other"),)), "coverage_malformed"),
        (GovernedPaperOwnHistoryContext((replace(first, source_manifest_digest="x"),)), "coverage_malformed"),
        (GovernedPaperOwnHistoryContext((claim(w, "funding", -1, DAY, 0),)), "coverage_malformed"),
        (GovernedPaperOwnHistoryContext((claim(w, "funding", ANCHOR, ANCHOR, ANCHOR),)), "coverage_interval_empty"),
        (
            GovernedPaperOwnHistoryContext((claim(w, "funding", ANCHOR, ANCHOR + DAY, ANCHOR, "OTHER"),)),
            "coverage_channel_unknown",
        ),
        (GovernedPaperOwnHistoryContext((replace(first, end_ns=ANCHOR + 2 * DAY),)), "coverage_digest_mismatch"),
        (GovernedPaperOwnHistoryContext((first, first)), "coverage_duplicated"),
        (GovernedPaperOwnHistoryContext((second, first)), "coverage_not_in_publication_order"),
    ):
        with pytest.raises(GovernedPaperOwnHistoryError, match=f"{reason}$"):
            canonical_governed_paper_own_history_context(bad)


def test_admission_names_why_a_claim_confers_no_completeness() -> None:
    """WHITE-BOX: the active table decides; production needs a listed HUMAN_GOVERNANCE claim AND an M1 source (E-1)."""

    w, result, _ = hold_world()
    required = series_of(w, result)
    archive = {"source_manifest_digest": w.dataset.source_manifest_digest, "instrument": w.run.instrument}
    test = claim(w, required[0], ANCHOR, ANCHOR + DAY, ANCHOR)
    human = claim(w, required[0], ANCHOR, ANCHOR + DAY, ANCHOR, GOVERNED_PAPER_OWN_HISTORY_HUMAN_CHANNEL)
    listed = GovernedPaperOwnHistoryTable(
        "production", GOVERNED_PAPER_OWN_HISTORY_HUMAN_CHANNEL, (human.coverage_digest,)
    )
    production = GOVERNED_PAPER_OWN_HISTORY_PRODUCTION_TABLE
    for table, item, reason in (
        (TEST_TABLE, test, ""),
        (
            TEST_TABLE,
            claim(w, required[0], ANCHOR, ANCHOR + DAY, ANCHOR, source_manifest_digest="f" * 64),
            "coverage_of_another_archive_or_instrument",
        ),
        (
            TEST_TABLE,
            claim(w, required[0], ANCHOR, ANCHOR + DAY, ANCHOR, instrument="OTHER"),
            "coverage_of_another_archive_or_instrument",
        ),
        (
            TEST_TABLE,
            claim(w, "open_interest", ANCHOR, ANCHOR + DAY, ANCHOR),
            "coverage_of_a_series_the_economics_does_not_read",
        ),
        (TEST_TABLE, human, "coverage_channel_not_admitted_by_the_active_table"),
        (production, test, "coverage_channel_not_admitted_by_the_active_table"),
        (production, human, "coverage_not_listed_by_the_production_table"),
        (listed, human, "coverage_source_not_m1_qualified"),
    ):
        assert own._admission(table, item, required=required, **archive) == reason
    for table in (
        GovernedPaperOwnHistoryTable("test_only", GOVERNED_PAPER_OWN_HISTORY_TEST_CHANNEL, (test.coverage_digest,)),
        GovernedPaperOwnHistoryTable("production", GOVERNED_PAPER_OWN_HISTORY_TEST_CHANNEL, ()),
        GovernedPaperOwnHistoryTable("other", GOVERNED_PAPER_OWN_HISTORY_TEST_CHANNEL, ()),
    ):
        with own_table(table), pytest.raises(GovernedPaperOwnHistoryError, match="table_malformed$"):
            own.governed_paper_own_history_active_table()


def test_completeness_needs_every_series_covered_from_g_by_claims_known_at_the_instant() -> None:
    """WHITE-BOX: "no events observed does not prove no events occurred": a half-open claim, a later publication and a
    one-nanosecond gap each decide completeness (P-2, E-1)."""

    w = hold_world()[0]
    g = ANCHOR
    claims = (
        claim(w, "funding", g, g + DAY, g),
        claim(w, "mark", g, g + 2 * DAY, g),
        claim(w, "book", g, g + DAY, g),
        claim(w, "funding", g + DAY, g + 2 * DAY, g + DAY),  # adjacent, published only at g + DAY
        claim(w, "book", g + DAY + 1, g + 2 * DAY, g),  # a one-nanosecond gap at g + DAY
    )
    coverage = own._Coverage(claims, ("funding", "mark", "book"))
    assert coverage.covered("funding", g, g + DAY - 1, g) is True
    assert coverage.covered("funding", g, g + DAY, g) is False  # [g, g + DAY) ends before g + DAY
    assert coverage.covered("funding", g, g + DAY, g + DAY - 1) is False  # the adjacent claim is not yet known
    assert coverage.covered("funding", g, g + DAY, g + DAY) is True
    assert coverage.covered("book", g, g + DAY + 5, g + DAY) is False  # the gap is never bridged
    assert coverage.known_from("funding", g, g + DAY) == g + DAY
    assert coverage.known_from("book", g, g + DAY + 5) is None
    assert coverage.complete(g, g + DAY - 1, g) is True
    assert coverage.complete(g, g + DAY, g + 2 * DAY) is False  # the book's gap


# --- D6: five evidence categories, each on its own fixture ------------------------------------------------------------------


def test_d6_proven_insufficient_missing_and_undefined_history_on_the_engine_world() -> None:
    evidence = hold_evidence()
    first, second = evidence.readings[0], evidence.readings[1]
    # proven insufficient history (U1 and U3): covered, never failing under every completion
    assert (first.complete, first.sharpe_30d_status, first.completed_days) == (True, S.INSUFFICIENT, 0)
    assert (first.fr_10_status, first.nt_x02.outcome, first.nt_x02.covered) == (S.INSUFFICIENT, Out.COVERED, ("U3",))
    assert (second.ehs_status, second.nt_e01.outcome, second.nt_e01.covered) == (
        E.U1_INSUFFICIENT_ONLY,
        Out.COVERED,
        ("U1",),
    )
    # complete but mathematically undefined: one signal value, P-1 needs two
    assert (first.stability_status, first.signal_count, first.ehs_status) == (S.UNDEFINED, 1, E.UNDEFINED)
    assert first.nt_e01 == GovernedPaperOwnHistoryCheck(Out.BLOCKED, "", "edge_health_score_undefined", ())
    # defined inputs: the neutral hit rate below 10 known trades and the exact drawdown from G
    assert (second.hit_rate_status, second.s_hitrate, second.trade_count) == (S.DEFINED, "1/2", 0)
    assert second.drawdown_status is S.DEFINED and second.drawdown == second.drawdown_lower_bound
    # missing or unproven: without an admitted claim no reading is complete
    unproven = evidence_of(hold_world(), GovernedPaperOwnHistoryContext(()))
    assert {item.complete for item in unproven.readings} == {False}
    for item in unproven.readings:
        assert (item.sharpe_30d_status, item.fr_10_status, item.hit_rate_status, item.stability_status) == (
            S.UNPROVEN,
            S.UNPROVEN,
            S.UNPROVEN,
            S.UNPROVEN,
        )
        assert item.nt_x02 == GovernedPaperOwnHistoryCheck(Out.BLOCKED, "", "last_10_fill_rate_unproven", ())
        assert item.state is St.LIFECYCLE_UNPROVEN


def test_d6_defined_pass_and_defined_fail_are_exact_and_a_proven_fail_is_never_covered() -> None:
    """WHITE-BOX: the defined categories at their exact boundaries (PR451 "Exactly 0.50, 0.70 and 0.90")."""

    def rate(value: Fraction, size: int) -> tuple:
        return (S.DEFINED, value, value * size, size, 0)

    insufficient = (S.INSUFFICIENT, None, Fraction(0), 4, 0)
    for fr10, fr20, x02, leg in (
        (rate(Fraction(1, 2), 10), rate(Fraction(18, 20), 20), (Out.PASS, "1/2"), (Out.BLOCKED, "9/10")),
        (rate(Fraction(9, 20), 10), rate(Fraction(19, 20), 20), (Out.FAIL, "9/20"), (Out.BLOCKED, "19/20")),
        (rate(Fraction(1, 2), 10), rate(Fraction(7, 10), 20), (Out.PASS, "1/2"), (Out.FAIL, "7/10")),
        (rate(Fraction(1, 2), 10), rate(Fraction(15, 20), 20), (Out.PASS, "1/2"), (Out.BLOCKED, "3/4")),
        (insufficient, insufficient, (Out.COVERED, ""), (Out.BLOCKED, "")),
    ):
        found_x02, found_leg, forbidden = own._fill_checks(fr10, fr20)
        assert (found_x02.outcome, found_x02.observed) == x02
        assert (found_leg.outcome, found_leg.observed) == leg
        assert forbidden is (T.TRUE if leg[0] is Out.FAIL else T.UNKNOWN)  # the latency and API legs stay X-H1
    # proven insufficient, yet failing under every completion: FAIL, never COVERED (FA-18)
    hopeless = (S.INSUFFICIENT, None, Fraction(0), 6, 0)
    assert (
        own._fill_checks(hopeless, insufficient)[0].reason == "every_completion_leaves_the_last_10_fill_rate_below_0_50"
    )


# --- D1 (U1, U2): the PR451 returns table -----------------------------------------------------------------------------------


def point(
    time_ns: int, kind: str, nav: Fraction | None, *, known: int | None = None, phase: int = -1, sequence: int = -1
):  # noqa: ANN201, PLR0913
    return SimpleNamespace(
        time_ns=time_ns, phase=phase, native_sequence=sequence, kind=kind, quantity=Fraction(0), nav=nav,
        known_ns=time_ns if known is None else known,
    )  # fmt: skip


def synthetic(  # noqa: PLR0913
    *,
    start: int = ANCHOR,
    points: tuple = (),
    trades: tuple = (),
    subs: tuple = (),
    claims: tuple = (),
    exclusive: bool = True,
) -> own._Derivation:
    """WHITE-BOX: the derivation's facts over SYNTHETIC engine facts (valuation path, closed trades, submissions)."""

    lineage = own._Lineage(
        "own-history-synthetic", "0" * 64, "SYN", start, "s1", ("s1",) if exclusive else ("s1", "s2"), "e" * 64,
        "f" * 64, "c" * 64,
    )  # fmt: skip
    run = SimpleNamespace(
        evaluation_end_ns=start + 400 * DAY, profile_id="unregistered", profile_semantics_digest="", decisions=()
    )
    derivation = SimpleNamespace(
        valuation_path=points,
        outcome=SimpleNamespace(
            trades=tuple(
                SimpleNamespace(status=HistoricalExecutionTradeStatus.CLOSED, end_time_ns=row[0]) for row in trades
            )
        ),
        trade_close_phases=tuple(row[1] for row in trades),
        trade_close_sequences=tuple(row[2] for row in trades),
        trade_exact_values=tuple(SimpleNamespace(realized_net_pnl=row[3], knowledge_ns=row[4]) for row in trades),
        submissions=subs,
    )
    return own._Derivation(
        lineage=lineage,
        run=run,  # type: ignore[arg-type]
        dataset=None,  # type: ignore[arg-type]
        result=SimpleNamespace(order_book_series_id="book"),  # type: ignore[arg-type]
        derivation=derivation,
        coverage=own._Coverage(claims, ("funding", "mark", "book")),
    )


def day_path(navs: list[Fraction], *, start: int = ANCHOR, known: dict[int, int] | None = None) -> tuple:
    """The genesis anchor at ``start`` and one UTC day-boundary valuation per later NAV (``known``: late knowledge)."""

    first_midnight = -(-start // DAY) * DAY if start % DAY else start + DAY
    rows = [point(start, "INITIAL", navs[0], phase=-1, sequence=0)]
    for index, nav in enumerate(navs[1:], start=1):
        instant = first_midnight + (index - 1) * DAY
        rows.append(
            point(instant, "UTC_DAY_BOUNDARY", nav, known=(known or {}).get(index), phase=BOUNDARY, sequence=index)
        )
    return tuple(rows)


def zigzag(count: int) -> list[Fraction]:
    return [Fraction(100 + (index % 3)) for index in range(count)]


def sharpe_at(
    facts: own._Derivation, instant: int, days: int, *, complete: bool = True, at: int | None = None
) -> tuple:
    return facts.sharpe((instant, DECISION, -1), days, complete, instant if at is None else at)


def independent_sharpe(navs: list[Fraction]) -> tuple[Fraction, Fraction]:
    returns = [later / earlier - 1 for earlier, later in itertools.pairwise(navs)]
    mean = sum(returns, Fraction(0)) / len(returns)
    variance = sum(((item - mean) ** 2 for item in returns), Fraction(0)) / (len(returns) - 1)
    return mean, Fraction(365) / variance


def test_sharpe_30_and_90_need_exactly_that_many_completed_known_days_of_the_latest_window() -> None:
    """WHITE-BOX on the real derivation constructor: 29 -> INSUFFICIENT, 30 -> DEFINED over the latest 30 returns."""

    navs = zigzag(95)
    facts = synthetic(points=day_path(navs))
    for days, completed, status in (
        (30, 29, S.INSUFFICIENT),
        (30, 30, S.DEFINED),
        (30, 31, S.DEFINED),
        (90, 89, S.INSUFFICIENT),
        (90, 90, S.DEFINED),
    ):
        (found, value), counted = sharpe_at(facts, ANCHOR + completed * DAY + HOUR, days)
        assert (found, counted) == (status, completed), (days, completed)
        if status is S.DEFINED:
            window = navs[completed - days : completed + 1]  # the latest days + 1 boundary NAVs
            assert (value.mean, value.radicand) == independent_sharpe(window)  # type: ignore[union-attr]
    # a decision at a UTC midnight precedes that midnight's boundary valuation (UTC_DAY_BOUNDARY follows DECISION)
    (found, _), counted = sharpe_at(facts, ANCHOR + 30 * DAY, 30)
    assert (found, counted) == (S.INSUFFICIENT, 29)


def test_sharpe_partial_genesis_zero_variance_non_positive_nav_unpublished_day_and_foreign_history() -> None:
    """WHITE-BOX: the PR451 returns table, case by case."""

    partial = synthetic(start=ANCHOR + 6 * HOUR, points=day_path(zigzag(32), start=ANCHOR + 6 * HOUR))
    (found, _), counted = sharpe_at(partial, ANCHOR + 31 * DAY + HOUR, 30)
    assert (found, counted) == (S.DEFINED, 30)  # 31 midnights: the partial genesis day is never a completed day
    (found, _), counted = sharpe_at(partial, ANCHOR + 30 * DAY + HOUR, 30)
    assert (found, counted) == (S.INSUFFICIENT, 29)
    constant = synthetic(points=day_path([Fraction(100) * Fraction(101, 100) ** index for index in range(31)]))
    assert sharpe_at(constant, ANCHOR + 30 * DAY + HOUR, 30)[0] == (S.UNDEFINED, None)  # zero variance
    navs = zigzag(31)
    navs[12] = Fraction(0)
    assert sharpe_at(synthetic(points=day_path(navs)), ANCHOR + 30 * DAY + HOUR, 30)[0] == (S.UNDEFINED, None)
    navs[12] = Fraction(-5)
    assert sharpe_at(synthetic(points=day_path(navs)), ANCHOR + 5 * DAY + HOUR, 30)[0] == (S.INSUFFICIENT, None)
    assert sharpe_at(synthetic(points=day_path(navs)), ANCHOR + 13 * DAY + HOUR, 30)[0] == (S.UNDEFINED, None)
    late = synthetic(points=day_path(zigzag(31), known={30: ANCHOR + 30 * DAY + 5 * HOUR}))
    instant = ANCHOR + 30 * DAY + HOUR
    assert sharpe_at(late, instant, 30)[0] == (S.UNPROVEN, None)  # the latest day awaits a settlement's publication
    assert sharpe_at(late, instant, 30, at=ANCHOR + 30 * DAY + 5 * HOUR)[0][0] is S.DEFINED  # known from then on
    assert sharpe_at(synthetic(points=day_path(zigzag(31)), exclusive=False), instant, 30)[0] == (S.UNPROVEN, None)
    assert sharpe_at(synthetic(points=day_path(zigzag(31))), instant, 30, complete=False)[0] == (S.UNPROVEN, None)
    negative = zigzag(31)
    negative[3:6] = [Fraction(99), Fraction(98), Fraction(97)]  # negative daily returns are ordinary members
    assert sharpe_at(synthetic(points=day_path(negative)), instant, 30)[0][0] is S.DEFINED


def test_decay_alert_compares_two_irrational_sharpe_readings_exactly() -> None:
    """WHITE-BOX: DECAY_ALERT is Sharpe_30d < 0.5 x Sharpe_90d, the sign of a two-radical surd."""

    f = Fraction

    def inputs(s30: own._Sharpe | None, s90: own._Sharpe | None) -> own._Inputs:
        pair = lambda value: (S.INSUFFICIENT, None) if value is None else (S.DEFINED, value)  # noqa: E731
        return own._Inputs(
            True,
            pair(s30),
            30,
            pair(s90),
            (S.DEFINED, f(1, 2), 0),
            (S.DEFINED, f(0), f(0), False),
            (S.DEFINED, None, 2),
            (E.UNDEFINED, None),
        )

    # Sharpe_30 = 1 x sqrt(2), Sharpe_90 = 1 x sqrt(8) = 2 sqrt(2): exactly 0.5 x Sharpe_90, so no alert
    assert own._decay(inputs(own._Sharpe(f(1), f(2)), own._Sharpe(f(1), f(8))))[0] is T.FALSE
    assert own._decay(inputs(own._Sharpe(f(1) - f(1, 10**18), f(2)), own._Sharpe(f(1), f(8))))[0] is T.TRUE
    unknown, check = own._decay(inputs(None, own._Sharpe(f(1), f(8))))
    assert (unknown, check.outcome, check.covered) == (T.UNKNOWN, Out.COVERED, ("U1",))
    assert own._decay(inputs(None, None))[1].covered == ("U1", "U2")


# --- D2 and P-1: the signal population --------------------------------------------------------------------------------------


def test_fa1_the_signal_population_is_every_scheduled_evaluation_not_only_the_entries() -> None:  # FA-1
    w, _, derivation = hold_world()
    evidence = hold_evidence()
    assert [item.decision_sequence for item in evidence.signals] == [item.decision_sequence for item in w.run.decisions]
    submitted = {item.submitted_ns for item in evidence.submissions if item.order_kind == "DECISION_INTENT"}
    holding = [item for item in w.run.decisions if item.decision_time_ns not in submitted]
    assert holding  # evaluations made while positioned: no order, still members of the window
    assert [item.signal_count for item in evidence.readings] == list(range(1, len(evidence.readings) + 1))
    w2 = child_world()[0]
    child = evidence_of(child_world())
    assert [item.decision_sequence for item in child.signals] == [item.decision_sequence for item in w2.run.decisions]
    refused = [item for item in child_world()[2].outcome.fills if item.reason == "governed_paper_exposure_halted"]
    assert refused and len(child.signals) == len(w2.run.decisions)  # refused entries are members too


def test_p1_each_scalar_is_the_exact_mean_of_the_decisions_own_latest_n_final_rates() -> None:
    w = hold_world()[0]
    evidence = hold_evidence()
    name = get_strategy_executable_profile(PASSIVE_FUNDING_CARRY_V1).required_value_names[0]
    records = {item.record_digest: item for item in w.dataset.records}
    for decision, signal in zip(w.run.decisions, evidence.signals, strict=True):
        rates = [
            Fraction(next(value.value for value in records[digest].values if value.name == name))
            for digest in decision.input_record_digests
        ]
        assert Fraction(signal.scalar) == sum(rates, Fraction(0)) / len(rates)  # type: ignore[arg-type]
        assert signal.reason == "" and signal.evaluation_ns == decision.decision_time_ns


def test_stability_is_undefined_below_two_values_or_on_a_non_positive_mean() -> None:
    """WHITE-BOX: the PR451 stability table on the real reading (a constant positive window has CV 0)."""

    facts = facts_of(hold_world())
    keys = [(item.decision_time_ns, DECISION, -1) for item in hold_world()[0].run.decisions]
    assert facts.stability(keys[0], True)[0] is S.UNDEFINED  # one value
    status, value, count = facts.stability(keys[2], True)
    assert (status, count) == (S.DEFINED, 3) and value.mean > 0  # type: ignore[union-attr]
    if value.variance == 0:  # type: ignore[union-attr]
        assert value.score() == own._Surd(Fraction(1))  # type: ignore[union-attr]
    facts.eval_values = [-item for item in facts.eval_values]  # type: ignore[operator]
    facts.stability_cache.clear()
    assert facts.stability(keys[2], True)[0] is S.UNDEFINED  # a negative mean is never made eligible
    assert facts.stability(keys[2], False)[0] is S.UNPROVEN


# --- D4, D5, P-4: the submission boundary ------------------------------------------------------------------------------------


def sub(  # noqa: PLR0913
    time_ns: int,
    phase: str,
    sequence: int,
    requested: object = 1,
    filled: object | None = None,
    resolved: tuple[int, str, int] | None = None,
    *,
    window: tuple[int, int] | None = None,
    in_horizon: bool = True,
    kind: str = "DECISION_INTENT",
):  # noqa: ANN201
    return SimpleNamespace(
        order_kind=kind, order_identity=(time_ns, sequence), native_sequence=sequence, submitted_ns=time_ns,
        submitted_phase=phase, side="SELL", exposure_increasing=True, requested_quantity=Fraction(requested),
        reached_book=resolved is not None, filled_quantity=None if filled is None else Fraction(filled),
        resolved_ns=None if resolved is None else resolved[0], resolved_phase=None if resolved is None else resolved[1],
        resolved_sequence=None if resolved is None else resolved[2], window_open_ns=None if window is None else window[0],
        window_close_ns=None if window is None else window[1], window_close_in_horizon=in_horizon, reason="synthetic",
    )  # fmt: skip


def filled_subs(fractions: list[tuple[object, object]]) -> tuple:
    """One resolved decision intent per hour: (requested, filled)."""

    return tuple(
        sub(
            ANCHOR + index * HOUR,
            "DECISION",
            2 * index,
            requested,
            filled,
            (ANCHOR + index * HOUR + MINUTE, "FILL", 2 * index + 1),
        )
        for index, (requested, filled) in enumerate(fractions)
    )


def test_fill_rate_boundaries_equal_order_weighting_and_unresolved_members() -> None:
    """WHITE-BOX: FR_10 and FR_20 over the logical submissions (PR451 execution table)."""

    at = (ANCHOR + 30 * HOUR, DECISION, -1)
    half = synthetic(subs=filled_subs([(1, 1)] * 5 + [(1, 0)] * 5))
    assert half.fill_rate(at, 10, True) == (S.DEFINED, Fraction(1, 2), Fraction(5), 10, 0)
    weighted = synthetic(subs=filled_subs([(2, 1)] * 5 + [(1, 1)] * 5))
    assert weighted.fill_rate(at, 10, True)[1] == Fraction(3, 4)  # equal order weighting, never 10/15 by quantity
    nine = synthetic(subs=filled_subs([(1, 1)] * 9))
    assert nine.fill_rate(at, 10, True)[0] is S.INSUFFICIENT and nine.fill_rate(at, 10, False)[0] is S.UNPROVEN
    rows = list(filled_subs([(1, 1)] * 11))
    rows[-1] = sub(ANCHOR + 30 * HOUR, "PROTECTIVE", 99, 1, 1, (ANCHOR + 30 * HOUR, "FILL", 100))
    pending = synthetic(subs=tuple(rows))
    status, value, _, known, unresolved = pending.fill_rate(at, 10, True)
    assert (status, value, known, unresolved) == (S.UNPROVEN, None, 9, 1)  # resolves at (t, FILL): never skipped (FA-3)
    assert pending.fill_rate((ANCHOR + 30 * HOUR + 1, PRE, -1), 10, True)[0] is S.DEFINED
    twenty = synthetic(subs=filled_subs([(1, 1)] * 14 + [(1, 0)] * 6))
    assert twenty.fill_rate((ANCHOR + 30 * HOUR, DECISION, -1), 20, True)[1] == Fraction(7, 10)


def test_rd12_a_no_book_window_close_is_a_conclusive_zero_only_on_book_coverage_known_at_the_reading() -> None:
    """WHITE-BOX: RD-12 over the engine's own no-book decision intent."""

    world = no_book_world()
    (intent, *_) = world[2].submissions
    assert (intent.order_kind, intent.reached_book, intent.window_close_in_horizon) == ("DECISION_INTENT", False, True)
    assert intent.window_close_ns == intent.submitted_ns + 5 * MINUTE  # min(d + max_delay, window end)
    assert intent.reason == "no_eligible_book_observation"
    w, result, _ = world
    funding, mark, book = series_of(w, result)
    end = w.run.evaluation_end_ns + DAY
    late = intent.window_close_ns + HOUR
    context = GovernedPaperOwnHistoryContext(
        (claim(w, funding, ANCHOR, end, ANCHOR), claim(w, mark, ANCHOR, end, ANCHOR), claim(w, book, ANCHOR, end, late))
    )
    facts = facts_of(world, context)
    first = facts.subs[0]
    assert facts.fraction(first, (intent.window_close_ns - 1, PRE, -1)) is None  # the window is still open
    assert facts.fraction(first, (intent.window_close_ns, DECISION, -1)) is None  # the book coverage is not yet known
    assert facts.fraction(first, (late, PRE, -1)) == Fraction(0)
    assert facts_of(world).fraction(first, (intent.window_close_ns, PRE, -1)) == Fraction(0)


def test_rd11_a_child_in_flight_at_a_decision_is_unresolved_there_and_its_remainder_follows_the_fill() -> None:  # B1
    """PR452 B1 at X_CHILD: the DECISION sees the child in flight; it fills 0.5 at (X, FILL) and the 0.5 remainder child
    is submitted in that fill's continuation, after the fill; every refused decision of the halt is no submission."""

    w, _, derivation = child_world()
    intent, child, remainder = derivation.submissions
    assert (child.order_kind, child.submitted_ns, child.submitted_phase, child.requested_quantity) == (
        "FLATTEN_CHILD",
        HALT,
        "PROTECTIVE",
        Fraction(1),
    )
    assert (child.resolved_ns, child.resolved_phase, child.filled_quantity) == (X_CHILD, "FILL", Fraction(1, 2))
    assert (remainder.submitted_ns, remainder.submitted_phase, remainder.requested_quantity) == (
        X_CHILD,
        "FILL",
        Fraction(1, 2),
    )
    assert child.resolved_sequence < remainder.native_sequence  # issued after the fill, in native order
    assert X_CHILD in [item.decision_time_ns for item in w.run.decisions]  # a decision at the very instant
    halted = [item for item in derivation.outcome.fills if item.reason == "governed_paper_exposure_halted"]
    assert len(halted) == 2 and all(item.execution_time_ns is None for item in halted)  # refused before submission
    evidence = evidence_of(child_world())
    at_x = reading_at(evidence, X_CHILD)
    assert (at_x.resolved_observations, at_x.unresolved_submissions, at_x.fr_10_status) == (1, 1, S.UNPROVEN)
    assert at_x.nt_x02.outcome is Out.BLOCKED
    later = evidence.readings[-1]
    assert (later.resolved_observations, later.unresolved_submissions, later.fr_10_status) == (3, 0, S.INSUFFICIENT)
    identities = [item.identity_digest for item in evidence.submissions]
    assert len(set(identities)) == len(identities) == 3  # distinct identities at one nanosecond: distinct observations


def test_rd11_a_v1_max_hold_remainder_attempt_is_submitted_at_its_partial_fill() -> None:  # B1
    _, _, derivation = attempt_world()
    intent, attempt, remainder = derivation.submissions
    assert (attempt.order_kind, attempt.submitted_phase, attempt.requested_quantity) == (
        "PROTECTIVE_ATTEMPT",
        "PROTECTIVE",
        Fraction(1),
    )
    assert (attempt.resolved_ns, attempt.resolved_phase, attempt.filled_quantity) == (X_ATTEMPT, "FILL", Fraction(1, 2))
    assert (remainder.submitted_ns, remainder.submitted_phase, remainder.requested_quantity) == (
        X_ATTEMPT,
        "FILL",
        Fraction(1, 2),
    )
    assert attempt.resolved_sequence < remainder.native_sequence


def test_rd11_a_child_refused_at_its_protective_admission_is_a_ledger_row_not_a_submission() -> None:
    _, _, derivation = refused_child_world()
    refused, admitted = derivation.outcome.protective_children
    fills = {item.intent_id: item for item in derivation.outcome.fills}
    assert (fills[refused.child_id].outcome, fills[refused.child_id].reason) == (
        HistoricalExecutionFillOutcome.REJECTED,
        "governed_paper_protective_authority_missing",
    )
    kinds = [(item.order_kind, item.submitted_ns) for item in derivation.submissions]
    assert kinds == [("DECISION_INTENT", kinds[0][1]), ("FLATTEN_CHILD", admitted.attempt_time_ns)]


def test_fa8_and_fa9_a_pre_submission_refusal_is_excluded_and_a_post_submission_refusal_counts_zero() -> None:
    _, _, derivation = refused_at_fill_world()
    (entry,) = derivation.submissions  # the halted decisions after HALT never reach the submission boundary (FA-8)
    assert (entry.reached_book, entry.filled_quantity, entry.reason) == (
        True,
        Fraction(0),
        "governed_paper_open_risk_unproven_at_fill",
    )
    facts = facts_of(refused_at_fill_world())
    assert facts.fraction(facts.subs[0], (entry.resolved_ns + 1, PRE, -1)) == Fraction(0)  # FA-9


def test_fa10_and_fa12_a_pending_order_is_unknown_at_the_end_and_an_extension_keeps_its_identity() -> None:
    truncated, full = child_world(X_CHILD - SECOND), child_world()
    short = evidence_of(truncated)
    long = evidence_of(full)
    pending = short.submissions[1]
    assert (pending.reached_book, pending.resolved_ns, pending.window_close_in_horizon) == (False, None, False)
    facts = facts_of(truncated)
    end_key = (X_CHILD - SECOND, PRE, -1)
    assert facts.fraction(facts.subs[1], end_key) is None  # UNKNOWN, never terminal by truncation (FA-10)
    assert facts.fill_rate(end_key, 10, True)[0] is S.UNPROVEN  # it blocks every latest-N window holding it
    resolved = long.submissions[1]
    for name in (
        "order_kind",
        "identity_digest",
        "native_sequence",
        "submitted_ns",
        "submitted_phase",
        "requested_quantity",
    ):
        assert getattr(pending, name) == getattr(resolved, name), name  # FA-12: same identity and coordinate
    assert (resolved.resolved_ns, resolved.resolved_phase) == (X_CHILD, "FILL")  # its actual terminal coordinate
    for before in (X_CHILD - SECOND, HALT, ANCHOR + 8 * HOUR):
        assert governed_paper_own_history_prefix_digest(
            short, before_ns=before
        ) == governed_paper_own_history_prefix_digest(long, before_ns=before)
    assert evidence_of(full) == long  # a replay adds no observation


def test_fa11_a_close_only_order_divides_by_its_own_requested_quantity() -> None:  # FA-11
    """The S1 profile (passive_funding_carry.v1) never targets LONG, so the engine's SHORT-to-LONG close-only clamp is not
    reachable on the S1 path. Every close-only order that is reachable (an exit intent, a protective remainder) records
    its own requested quantity (the engine intent's ``requested``, or the open remainder), never a target delta."""

    w, _, derivation = clamp_world()
    exit_intent = derivation.outcome.intents[1]
    assert (exit_intent.action.value, exit_intent.close_only_clamped) == ("CLOSE_SHORT", False)
    assert [item.resulting_direction for item in w.run.decisions][:2] == ["SHORT", "FLAT"]
    close = derivation.submissions[1]
    assert (close.requested_quantity, close.filled_quantity, close.exposure_increasing) == (
        Fraction(1),
        Fraction(1),
        False,
    )
    remainder = child_world()[2].submissions[2]
    assert (remainder.requested_quantity, remainder.filled_quantity, remainder.exposure_increasing) == (
        Fraction(1, 2),
        Fraction(1, 2),
        False,
    )
    facts = facts_of(child_world())
    assert facts.fraction(facts.subs[2], (remainder.resolved_ns + 1, PRE, -1)) == Fraction(1)  # never 1/2 over 1


def test_starved_fill_rates_cross_every_exact_boundary_on_the_engines_own_unfilled_intents() -> None:
    """Every decision's intent finds no book and is conclusively unfilled at its window close on complete coverage: the
    completion bounds, the FR_10 = 0 reading, the U3 coverage end and the activation FAIL, at their exact boundaries."""

    evidence = starved_evidence()
    readings = evidence.readings
    assert all(item.order_kind == "DECISION_INTENT" and not item.reached_book for item in evidence.submissions)
    assert [item.resolved_observations for item in readings] == list(range(len(readings)))
    by_count = {item.resolved_observations: item for item in readings}
    assert by_count[5].nt_x02.outcome is Out.COVERED  # (0 + 5) / 10 = 0.50 is not below 0.50
    assert by_count[6].nt_x02.reason == "every_completion_leaves_the_last_10_fill_rate_below_0_50"
    assert by_count[5].fill_leg.outcome is Out.BLOCKED  # 15 / 20 = 0.75 > 0.70
    assert (by_count[6].fill_leg.outcome, by_count[6].execution_forbidden) == (Out.FAIL, T.TRUE)  # 14 / 20 = 0.70
    assert (by_count[10].fr_10_status, by_count[10].fr_10, by_count[10].nt_x02.reason) == (
        S.DEFINED,
        "0",
        "last_10_fill_rate_below_0_50",
    )
    ends = governed_paper_own_history_coverage_cuts(evidence)
    tenth_close = evidence.submissions[9].window_close_ns
    assert ends == {"U1": None, "U2": None, "U3": tenth_close, "U4": None}  # cut at the 10th conclusive resolution
    ended = [item.coverage_ended for item in readings]
    assert ended == [("U3",) if item.decision_time_ns >= tenth_close else () for item in readings]  # irreversible
    after = by_count[8]
    assert (after.allocation_eligibility, after.allocation_reason) == (
        GovernedPaperAllocationEligibility.NON_MEMBER,
        "no_allocation:activation_proven_fail",
    )


# --- P-5: the drawdown ------------------------------------------------------------------------------------------------------


def test_drawdown_exactly_5pct_breaches_inclusively_and_its_score_is_zero() -> None:  # FA-14
    """WHITE-BOX: DD = 1 - NAV / peak over the valuation path from G, the peak never reset."""

    def at(*marks: tuple[int, Fraction]) -> tuple:
        rows = (
            point(ANCHOR, "INITIAL", Fraction(100)),
            *(point(ANCHOR + hours * HOUR, "MARK", nav) for hours, nav in marks),
        )
        return synthetic(points=rows).drawdown((ANCHOR + 10 * HOUR, DECISION, -1), True, ANCHOR + 10 * HOUR)

    assert at((1, Fraction(110)), (2, Fraction(1045, 10))) == (S.DEFINED, Fraction(1, 20), Fraction(1, 20), True)
    status, value, _, breach = at((1, Fraction(110)), (2, Fraction(1046, 10)))
    assert (status, breach) == (S.DEFINED, False) and value < Fraction(1, 20)
    assert at((1, Fraction(110)), (2, Fraction(108)), (3, Fraction(1045, 10)))[3] is True  # the peak is never reset
    inputs = _Fixed(
        own._Sharpe(Fraction(4), Fraction(1)), Fraction(1), Fraction(1, 20), own._Stability(Fraction(1), Fraction(0))
    ).inputs((ANCHOR, DECISION, -1))
    assert inputs.disable_condition() is True  # S_drawdown = 0 and DISABLED, whatever Sharpe becomes


def test_drawdown_a_stale_or_unknown_valuation_leaves_only_a_lower_bound_that_can_prove_fail_never_pass() -> (
    None
):  # FA-13
    """WHITE-BOX: RD-9 over a path with a stale mark interval since G."""

    def at(nav: Fraction, *, known: int | None = None, exclusive: bool = True) -> tuple:
        rows = (
            point(ANCHOR, "INITIAL", Fraction(100)),
            point(ANCHOR + HOUR, "MARK", Fraction(110)),
            point(ANCHOR + 90 * MINUTE, "MARK_STALE", None),
            point(ANCHOR + 2 * HOUR, "MARK", nav, known=known),
        )
        return synthetic(points=rows, exclusive=exclusive).drawdown(
            (ANCHOR + 3 * HOUR, DECISION, -1), True, ANCHOR + 3 * HOUR
        )

    assert at(Fraction(1045, 10)) == (S.UNPROVEN, None, Fraction(1, 20), True)  # the lower bound proves the breach
    status, value, lower, breach = at(Fraction(106))
    assert (status, value, breach) == (S.UNPROVEN, None, None) and lower is not None  # never a PASS
    assert at(Fraction(106), known=ANCHOR + 4 * HOUR) == (S.UNPROVEN, None, None, None)  # not yet known
    assert at(Fraction(106), exclusive=False) == (S.UNPROVEN, None, None, None)  # shared equity is not the edge's own


# --- P-6: the hit rate -----------------------------------------------------------------------------------------------------


def test_hit_rate_window_zero_net_neutral_knowledge_and_clipping() -> None:  # FA-16, FA-17
    """WHITE-BOX: one closed excursion per trade, membership by its closing coordinate in (t - 30d, t]."""

    t = ANCHOR + 40 * DAY
    key = (t, DECISION, -1)

    def trades(nets: list[int], *, first: int = t - 20 * DAY, known_delay: int = 0) -> tuple:
        return tuple(
            (first + index * HOUR, "FILL", index, Fraction(net), first + index * HOUR + known_delay)
            for index, net in enumerate(nets)
        )

    mixed = synthetic(trades=trades([1, 1, 1, 1, 0, -1, -1, -1, -1, -1]))
    assert mixed.hit(key, True, t) == (S.DEFINED, Fraction(1, 6), 10, Fraction(2, 5))  # (0.40 - 0.35) / 0.30
    assert synthetic(trades=trades([1] * 9)).hit(key, True, t)[:3] == (S.DEFINED, Fraction(1, 2), 9)
    assert synthetic().hit(key, True, t) == (S.DEFINED, Fraction(1, 2), 0, None)
    assert synthetic(trades=trades([1] * 10)).hit(key, True, t)[1] == Fraction(1)
    assert synthetic(trades=trades([1] * 7 + [-1] * 13)).hit(key, True, t)[1] == Fraction(0)  # 0.35 exactly
    edge = synthetic(
        trades=(
            (t - 30 * DAY, "FILL", 0, Fraction(1), t - 30 * DAY),
            (t - 30 * DAY + 1, "FILL", 1, Fraction(1), t - 30 * DAY + 1),
        )
    )
    assert edge.hit(key, True, t)[2] == 1  # the trade closed exactly 30 days earlier is outside (t - 30d, t]
    same = synthetic(trades=((t, "FILL", 0, Fraction(1), t),))
    assert same.hit(key, True, t)[2] == 0  # a close at (t, FILL) follows the DECISION of t
    late = synthetic(trades=trades([1] * 10, known_delay=30 * DAY))  # known only at a later settlement publication
    assert late.hit(key, True, t)[0] is S.UNPROVEN
    assert late.hit(key, True, t + 15 * DAY)[0] is S.DEFINED  # admissible once known; earlier readings never change
    assert mixed.hit(key, False, t)[0] is S.UNPROVEN


def test_fa15_partial_fills_inside_one_excursion_are_one_trade() -> None:  # FA-15
    for world in (child_world(), attempt_world()):
        evidence = evidence_of(world)
        closed = [item for item in world[2].outcome.trades if item.status is HistoricalExecutionTradeStatus.CLOSED]
        assert len(evidence.trades) == len(closed) == 1  # an entry fill and two partial close fills: one trade


# --- P-3: the state machine ------------------------------------------------------------------------------------------------


UNKNOWN_INPUTS = own._Inputs(
    False, (S.UNPROVEN, None), 0, (S.UNPROVEN, None), (S.UNPROVEN, None, None), (S.UNPROVEN, None, None, None),
    (S.UNPROVEN, None, 0), (E.UNPROVEN, None),
)  # fmt: skip


def ehs(value: Fraction | None, *, breach: bool | None = False) -> own._Inputs:
    """SYNTHETIC inputs with a defined EHS of ``value`` (None: an undefined EHS)."""

    pair = (E.UNDEFINED, None) if value is None else (E.DEFINED, own._Surd(value))
    return own._Inputs(
        True, (S.DEFINED, None), 30, (S.DEFINED, None), (S.DEFINED, Fraction(1, 2), 0),
        (S.DEFINED, Fraction(0), Fraction(0), breach), (S.DEFINED, None, 2), pair,
    )  # fmt: skip


class Knowledge:
    """SYNTHETIC facts for the state machine: piecewise-constant inputs from each start on, each known from an instant."""

    def __init__(self, *segments: tuple[int, own._Inputs, int | None]) -> None:
        self.segments = segments

    def inputs(self, key: tuple[int, int, int], at_ns: int | None = None) -> own._Inputs:
        at = key[0] if at_ns is None else at_ns
        found = None
        for start, value, known in self.segments:
            if start <= key[0]:
                found = (value, start if known is None else known)
        if found is None or found[1] > at:
            return UNKNOWN_INPUTS
        return found[0]


def replay(knowledge: Knowledge, instants: list[int]) -> tuple[own._Machine, dict[int, GovernedPaperOwnHistoryState]]:
    """The derivation's loop over SYNTHETIC coordinates: each processed once, recovery deadlines scheduled."""

    machine, heap, seen, states = own._Machine(), [(item, PRE, -1) for item in instants], set(), {}
    heapq.heapify(heap)
    while heap:
        key = heapq.heappop(heap)
        if key in seen:
            continue
        seen.add(key)
        for deadline in machine.advance(knowledge, key, knowledge.inputs(key)):  # type: ignore[arg-type]
            heapq.heappush(heap, (deadline, PRE, -1))
        states[key[0]] = machine.state if machine.proven else St.LIFECYCLE_UNPROVEN
    return machine, states


def moves(machine: own._Machine) -> list[tuple[int, GovernedPaperOwnHistoryState, str]]:
    return [(item.time_ns, item.state_to, item.reason) for item in machine.transitions]


def test_state_machine_starts_at_the_first_fully_defined_ehs_exactly_and_has_no_default_state() -> None:
    f = Fraction
    t0 = ANCHOR
    undefined = replay(Knowledge((t0, ehs(None), None)), [t0, t0 + HOUR])[0]
    assert (undefined.state, undefined.transitions) == (St.STATE_NOT_ESTABLISHED, [])  # no EHS transition
    active, _ = replay(Knowledge((t0, ehs(None), None), (t0 + HOUR, ehs(f(7, 10)), None)), [t0, t0 + HOUR])
    assert moves(active) == [(t0 + HOUR, St.ACTIVE, "first_fully_defined_edge_health_score")]  # 0.70 exactly
    warning, _ = replay(Knowledge((t0, ehs(f(7, 10) - f(1, 10**18)), None)), [t0])
    assert moves(warning) == [(t0, St.WARNING, "first_fully_defined_edge_health_score")]


def test_state_machine_two_disable_episodes_within_30_days_enter_quarantine_which_is_never_released() -> (
    None
):  # FA-5, FA-6
    f = Fraction
    t0 = ANCHOR
    good, bad = ehs(f(4, 5)), ehs(f(1, 5))

    def lineage(second: int) -> own._Machine:
        knowledge = Knowledge(
            (t0, good, None),
            (t0 + DAY, bad, None),
            (t0 + DAY + HOUR, ehs(f(1, 10)), None),  # the same episode observed again counts once
            (t0 + 2 * DAY, ehs(f(1, 2)), None),
            (second, bad, None),
            (second + HOUR, good, None),
        )
        instants = [t0, t0 + DAY, t0 + DAY + HOUR, t0 + 2 * DAY, second, second + HOUR, second + 20 * DAY]
        return replay(knowledge, instants)[0]

    quarantined = lineage(t0 + DAY + 30 * DAY - 1)
    assert [item[1] for item in moves(quarantined)] == [St.ACTIVE, St.DISABLED, St.WARNING, St.QUARANTINE]
    assert moves(quarantined)[-1][2] == "second_disable_episode_within_30d:edge_health_score_below_0_30"
    assert quarantined.state is St.QUARANTINE and quarantined.pending == []  # 20 days of EHS 0.80 release nothing
    outside = lineage(t0 + DAY + 30 * DAY)  # exactly 30 days later: outside (t - 30d, t]
    assert [item[1] for item in moves(outside)] == [
        St.ACTIVE,
        St.DISABLED,
        St.WARNING,
        St.DISABLED,
        St.WARNING,
        St.ACTIVE,  # a later coordinate than the recovery (RD-3)
    ]


def test_state_machine_recovery_needs_48_continuous_hours_and_restarts_on_every_interruption() -> (
    None
):  # FA-4, RD-3, RD-4
    f = Fraction
    t0, t2 = ANCHOR, ANCHOR + DAY
    disabled = (t0, ehs(f(1, 5)), None)
    exact, _ = replay(Knowledge(disabled, (t2, ehs(f(2, 5)), None)), [t0, t2])  # EHS 0.40 exactly qualifies
    assert moves(exact) == [
        (t0, St.DISABLED, "edge_health_score_below_0_30"),
        (t2 + 48 * HOUR, St.WARNING, "recovery_ehs_at_least_0_40_for_48h"),
    ]
    interrupted, _ = replay(
        Knowledge(
            disabled,
            (t2, ehs(f(1, 2)), None),
            (t2 + 24 * HOUR, ehs(f(39, 100)), None),
            (t2 + 25 * HOUR, ehs(f(1, 2)), None),
        ),
        [t0, t2, t2 + 24 * HOUR, t2 + 25 * HOUR, t2 + 48 * HOUR],
    )
    assert moves(interrupted)[-1][:2] == (t2 + 25 * HOUR + 48 * HOUR, St.WARNING)  # restarted at 25 h
    breach, _ = replay(
        Knowledge(
            disabled,
            (t2, ehs(f(1, 2)), None),
            (t2 + HOUR, ehs(f(1, 2), breach=True), None),
            (t2 + 2 * HOUR, ehs(f(1, 2)), None),
        ),
        [t0, t2, t2 + HOUR, t2 + 2 * HOUR],
    )
    assert moves(breach)[-1][:2] == (t2 + 2 * HOUR + 48 * HOUR, St.WARNING)
    direct, _ = replay(Knowledge(disabled, (t2, ehs(f(9, 10)), None)), [t0, t2, t2 + 48 * HOUR, t2 + 49 * HOUR])
    assert [item[:2] for item in moves(direct)][1:] == [
        (t2 + 48 * HOUR, St.WARNING),
        (t2 + 49 * HOUR, St.ACTIVE),
    ]  # never direct


def test_state_machine_an_unknown_disable_condition_waits_and_its_transition_is_dated_when_known() -> None:
    f = Fraction
    t0 = ANCHOR
    knowledge = Knowledge((t0, ehs(f(4, 5)), None), (t0 + HOUR, ehs(f(1, 5)), t0 + 10 * HOUR))  # published late
    machine, states = replay(knowledge, [t0, t0 + HOUR, t0 + 5 * HOUR, t0 + 10 * HOUR])
    assert states[t0 + HOUR] is St.LIFECYCLE_UNPROVEN and states[t0 + 5 * HOUR] is St.LIFECYCLE_UNPROVEN
    assert moves(machine)[-1][:2] == (t0 + 10 * HOUR, St.DISABLED)  # dated at its knowledge, never earlier (X1)
    gap = Knowledge(
        (t0, ehs(f(1, 5)), None), (t0 + HOUR, ehs(f(1, 2)), None), (t0 + 2 * HOUR, ehs(f(1, 2)), t0 + 400 * DAY)
    )
    stuck, states = replay(gap, [t0, t0 + HOUR, t0 + 2 * HOUR, t0 + 60 * HOUR])
    assert stuck.state is St.DISABLED and states[t0 + 60 * HOUR] is St.DISABLED  # proven, and never recovers across it
    late = Knowledge(
        (t0, ehs(f(1, 5)), None), (t0 + HOUR, ehs(f(1, 2)), None), (t0 + 2 * HOUR, ehs(f(1, 2)), t0 + 60 * HOUR)
    )
    recovered, _ = replay(late, [t0, t0 + HOUR, t0 + 2 * HOUR, t0 + 60 * HOUR])
    assert moves(recovered)[-1][:2] == (t0 + 60 * HOUR, St.WARNING)  # the clock never advanced before the knowledge


def test_state_check_a_proven_disable_condition_fails_first_and_quarantine_or_disabled_fail() -> None:
    f = Fraction
    machine = own._Machine()
    state, _, check = own._state_check(ehs(f(1, 2), breach=True), machine)
    assert (state, check.outcome, check.reason) == (
        St.STATE_NOT_ESTABLISHED,
        Out.FAIL,
        "disable_condition_proven:drawdown_breach_family_b_5pct",
    )
    machine.state = St.QUARANTINE
    assert own._state_check(ehs(f(9, 10)), machine)[2].reason == "edge_state_quarantine"
    machine.state = St.ACTIVE
    assert own._state_check(ehs(f(9, 10)), machine)[2].outcome is Out.PASS
    machine.pending.append((ANCHOR, PRE, -1))
    state, reason, check = own._state_check(ehs(f(9, 10)), machine)
    assert (state, check.outcome) == (St.LIFECYCLE_UNPROVEN, Out.BLOCKED)


# --- C-6: coverage ends and the incubation authority v13 ---------------------------------------------------------------------


def test_coverage_ends_cut_after_a_same_instant_decision() -> None:
    """WHITE-BOX: a reading ended at a FILL-phase (or later) coordinate is read as ended only from the next nanosecond."""

    t = ANCHOR
    assert [own._cut((t, phase, 3)) for phase in (PRE, FUNDING, PROTECTIVE, DECISION, FILL, BOUNDARY)] == [
        t,
        t,
        t,
        t + 1,
        t + 1,
        t + 1,
    ]
    hold = hold_evidence()
    assert [item.reading_id for item in hold.coverage_ends] == ["U1", "U2", "U3", "U4"]
    assert all(item.cut_ns is None for item in hold.coverage_ends)  # three days, four submissions: nothing ends


def test_incubation_v13_graduates_only_once_every_selected_reading_coverage_has_ended() -> None:
    day = ita.DAY
    rec = ita.record(covered=("U1", "U5"))
    digest = governed_paper_incubation_record_digest(rec)
    ctx = ita.context((ita.approval(0, rec),), ita.all_bases(digest=digest))
    trades = ((ita.S + day, "WIN"), (ita.S + 2 * day, "LOSS"))
    ends: dict[str, int | None] = dict.fromkeys(("U1", "U2", "U3", "U4"))
    u5 = ita.context((ita.approval(0),), ita.all_bases())
    with ita.table(ita.TEST_TABLE):
        completion = ita.derive(u5, known_trades=trades).graduation_ns
        legacy = ita.derive(ctx, known_trades=trades)
        never = ita.derive(ctx, known_trades=trades, coverage_ends=ends)
        later = ita.derive(ctx, known_trades=trades, coverage_ends={**ends, "U1": ita.S + 5 * day})
        earlier = ita.derive(ctx, known_trades=trades, coverage_ends={**ends, "U1": ita.S + day // 2})
        same_u5 = ita.derive(u5, known_trades=trades, coverage_ends=ends)
        for bad in ({"U1": None}, {**ends, "U1": "x"}, {**ends, "U5": 1}):
            with pytest.raises(GovernedPaperIncubationError, match="coverage_ends_malformed$"):
                ita.derive(ctx, known_trades=trades, coverage_ends=bad)
    assert completion is not None and legacy.graduation_ns is None  # rule set v12: no producer of U1 exists
    assert never.graduation_ns is None  # a selected reading whose coverage never ends keeps it from graduating
    assert later.graduation_ns == ita.S + 5 * day
    assert earlier.graduation_ns == completion  # the later of every selected reading's end, S and P_A
    assert same_u5.graduation_ns == completion  # a U5-only record graduates exactly as before
    assert (legacy.schema, later.schema) == (
        "governed-paper-incubation-evidence.v1",
        "governed-paper-incubation-evidence.v2",
    )


# --- C-7: the rule set v13 entry gate -----------------------------------------------------------------------------------------


def blocked(reason: str = "synthetic_blocked") -> GovernedPaperOwnHistoryCheck:
    return GovernedPaperOwnHistoryCheck(Out.BLOCKED, "", reason, ())


def gate_reading(observation: object, **changes: object) -> GovernedPaperOwnHistoryReading:
    """A SYNTHETIC own-history reading of the observation's decision (every check BLOCKED unless changed)."""

    values: dict[str, object] = {
        "decision_sequence": observation.decision_sequence,  # type: ignore[attr-defined]
        "decision_time_ns": observation.decision_time_ns,  # type: ignore[attr-defined]
        "complete": True, "sharpe_30d_status": S.INSUFFICIENT, "completed_days": 3, "sharpe_90d_status": S.INSUFFICIENT,
        "decay_alert": T.UNKNOWN, "fr_10_status": S.INSUFFICIENT, "fr_10": None, "fr_20_status": S.INSUFFICIENT,
        "fr_20": None, "resolved_observations": 2, "unresolved_submissions": 0, "hit_rate_status": S.DEFINED,
        "s_hitrate": "1/2", "trade_count": 0, "hit_rate_alert": T.UNKNOWN, "drawdown_status": S.DEFINED, "drawdown": "0",
        "drawdown_lower_bound": "0", "s_drawdown": "1", "drawdown_breach": T.FALSE, "stability_status": S.DEFINED,
        "signal_count": 3, "ehs_status": E.U1_INSUFFICIENT_ONLY, "ehs_at_least_0_30": T.UNKNOWN,
        "ehs_above_0_50": T.UNKNOWN, "ehs_at_least_0_70": T.UNKNOWN, "ehs_above_0_80": T.UNKNOWN,
        "state": St.STATE_NOT_ESTABLISHED, "state_reason": "state_not_established", "disable_condition": T.FALSE,
        "coverage_ended": (), "execution_forbidden": T.UNKNOWN, "nt_e01": blocked(), "nt_e02": blocked(),
        "nt_e04": blocked(), "nt_x02": blocked(), "fill_leg": blocked(), "alpha_edge": blocked(), "de_weight": blocked(),
        "allocation_rebalance_ns": None, "allocation_eligibility": GovernedPaperAllocationEligibility.UNKNOWN,
        "allocation_weight": None, "allocation_reason": "synthetic", "reading_digest": "",
    }  # fmt: skip
    values.update(changes)
    seed = GovernedPaperOwnHistoryReading(**values)  # type: ignore[arg-type]
    return replace(seed, reading_digest=governed_paper_own_history_reading_digest(seed))


def incubation_observation(active: bool, covered_readings: tuple[str, ...] = ("U5",)):  # noqa: ANN201, FBT001
    """A SYNTHETIC rule set v12 observation (``ita.v12``) whose ACTIVE or HOLD record selects ``covered_readings``."""

    observation = ita.kt.v11("BLOCKED")
    kelly = observation.kelly.reading  # type: ignore[union-attr]
    instant = kelly.decision_time_ns
    start, genesis = instant - ita.DAY, instant - 10 * ita.DAY
    rec = ita.record(start=start, covered=covered_readings, genesis_start_ns=genesis)
    digest = governed_paper_incubation_record_digest(rec)
    bases = tuple(ita.basis(kind, ((start, start + 5 * ita.DAY),), start - ita.DAY, digest=digest) for kind in ita.K)
    ctx = ita.context((ita.approval(0, rec, published=start - ita.DAY),), bases if active else ())
    lin = ita.lineage(genesis_start_ns=genesis, bootstrap_end_ns=genesis + ita.H_DAYS * ita.DAY)
    with ita.table(ita.TEST_TABLE):
        authority = derive_governed_paper_incubation_authority(ctx, lineage=lin, horizon_ns=instant + ita.DAY)
        reading = build_governed_paper_incubation_reading(authority, kelly=kelly, attempts_before=())
    expected = GovernedPaperIncubationState.ACTIVE if active else GovernedPaperIncubationState.HOLD
    assert reading.state is expected
    return replace(observation, incubation=GovernedPaperEntrySafetyIncubation(reading, authority.authority_digest))


@functools.cache
def _incubation_observation(active: bool, covered_readings: tuple[str, ...]):  # noqa: ANN202, FBT001
    return incubation_observation(active, covered_readings)


def v13(active: bool = True, covered_readings: tuple[str, ...] = ("U1", "U3", "U5"), **changes: object):  # noqa: ANN201, FBT001, FBT002
    observation = _incubation_observation(active, covered_readings)
    return replace(
        observation, own_history=GovernedPaperEntrySafetyOwnHistory(gate_reading(observation, **changes), "e" * 64)
    )


def checks_of(observation: object) -> dict[str, object]:
    return {item.check_id: item for item in evaluate_governed_paper_entry_safety(observation).checks}  # type: ignore[arg-type]


def reason_of(check: object) -> str:
    """A recorded check reason without its ``<module>:<check id>:`` prefix."""

    return check.reason.split(":", 2)[2]  # type: ignore[attr-defined]


def test_fa18_a_proven_fail_refuses_the_entry_whatever_is_cold_start_excepted() -> None:  # FA-18
    covered_u1 = GovernedPaperOwnHistoryCheck(
        Out.COVERED, "", "u1_insufficient_own_history_not_failing_under_every_completion", ("U1",)
    )
    failing = GovernedPaperOwnHistoryCheck(Out.FAIL, "9/20", "last_10_fill_rate_below_0_50", ())
    observation = v13(nt_e01=covered_u1, nt_x02=failing)
    checks = checks_of(observation)
    assert checks["NT-E01"].status is GATE.COLD_START_EXCEPTED  # type: ignore[attr-defined]
    assert (checks["NT-X02"].status, checks["NT-X02"].observed) == (GATE.FAIL, "9/20")  # type: ignore[attr-defined]
    assert evaluate_governed_paper_entry_safety(observation).entry_permitted is False
    breach = GovernedPaperOwnHistoryCheck(
        Out.FAIL, "DISABLED", "disable_condition_proven:drawdown_breach_family_b_5pct", ()
    )
    assert checks_of(v13(nt_e01=covered_u1, nt_e02=breach))["NT-E02"].status is GATE.FAIL  # type: ignore[attr-defined]


def test_cold_start_exception_needs_an_active_record_selecting_the_reading_before_its_coverage_end() -> None:
    covered_u3 = GovernedPaperOwnHistoryCheck(Out.COVERED, "", "u3_insufficient_own_history", ("U3",))
    for active, selected, ended, status, reason in (
        (True, ("U3", "U5"), (), GATE.COLD_START_EXCEPTED, "cold_start_excepted:u3_insufficient_own_history"),
        (
            False,
            ("U3", "U5"),
            (),
            GATE.BLOCKED_ON_MISSING_INPUT,
            "u3_insufficient_own_history:no_active_incubation_record",
        ),
        (
            True,
            ("U5",),
            (),
            GATE.BLOCKED_ON_MISSING_INPUT,
            "u3_insufficient_own_history:covered_reading_not_selected_by_the_record:u3",
        ),
        (
            True,
            ("U3", "U5"),
            ("U3",),
            GATE.BLOCKED_ON_MISSING_INPUT,
            "u3_insufficient_own_history:covered_reading_coverage_ended:u3",
        ),
    ):
        found = checks_of(v13(active, selected, nt_x02=covered_u3, coverage_ended=ended))["NT-X02"]
        assert (found.status, reason_of(found)) == (status, reason), (active, selected, ended)  # type: ignore[attr-defined]


def test_fa7_an_ef8_successor_refuses_whatever_the_own_history_state() -> None:  # FA-7
    active = GovernedPaperOwnHistoryCheck(Out.PASS, "ACTIVE", "edge_state_active", ())
    observation = v13(nt_e02=active, state=St.ACTIVE, state_reason="active")
    assert checks_of(observation)["NT-E02"].status is GATE.PASS  # type: ignore[attr-defined]
    found = checks_of(replace(observation, lifecycle_invalidated=True))["NT-E02"]
    assert (found.status, found.observed, reason_of(found)) == (  # type: ignore[attr-defined]
        GATE.FAIL,
        "EF8_DISABLED_OR_QUARANTINE",
        "edge_lifecycle_disabled_at_or_before_the_decision",
    )


def test_fb_activation_reads_the_execution_column_and_never_passes() -> None:
    legacy = checks_of(_incubation_observation(True, ("U1", "U3", "U5")))["FB-ACTIVATION"]
    forbidden = GovernedPaperOwnHistoryCheck(
        Out.FAIL, "7/10", "last_20_fill_rate_at_most_0_70_execution_impaired_or_halted", ()
    )
    failing = checks_of(v13(fill_leg=forbidden))["FB-ACTIVATION"]
    unproven = checks_of(v13(fill_leg=blocked("execution_latency_and_api_legs_unproven_x_h1")))["FB-ACTIVATION"]
    if legacy.status is GATE.FAIL:  # type: ignore[attr-defined]
        assert failing == legacy == unproven  # the regime reading's FAIL comes first, with its reason
    else:
        assert (failing.status, reason_of(failing)) == (  # type: ignore[attr-defined]
            GATE.FAIL,
            "execution_column:last_20_fill_rate_at_most_0_70_execution_impaired_or_halted",
        )
        assert unproven.status is GATE.BLOCKED_ON_MISSING_INPUT  # type: ignore[attr-defined]
        assert reason_of(unproven).endswith(":execution_column:execution_latency_and_api_legs_unproven_x_h1")


def test_scale_1_reads_alpha_edge_and_de_weight_from_the_own_history_reading() -> None:
    def terms(**changes: object) -> dict[str, tuple[str, str]]:
        return {item[0]: (item[1], item[2]) for item in governed_paper_entry_safety_a9_multipliers(v13(**changes))}

    found = terms(
        alpha_edge=GovernedPaperOwnHistoryCheck(Out.PASS, "", "alpha_edge_proven_1", ()),
        de_weight=GovernedPaperOwnHistoryCheck(
            Out.FAIL, "DECAY_ALERT", "decay_alert_de_weight_halves_the_allocation", ()
        ),
    )
    assert found["edge_health_alpha_1_6"] == ("PROVEN_ONE", "alpha_edge_proven_1")
    assert found["de_weight_1_7"] == ("PROVEN_BELOW_ONE", "decay_alert_de_weight_halves_the_allocation")
    covered_u1 = GovernedPaperOwnHistoryCheck(Out.COVERED, "", "u1_insufficient_own_history", ("U1",))
    assert terms(alpha_edge=covered_u1)["edge_health_alpha_1_6"] == (
        "COLD_START_EXCEPTED",
        "u1_insufficient_own_history",
    )
    assert terms(alpha_edge=covered_u1, coverage_ended=("U1",))["edge_health_alpha_1_6"][0] == "UNPROVEN"
    legacy = {
        item[0]: item[1]
        for item in governed_paper_entry_safety_a9_multipliers(_incubation_observation(True, ("U1", "U3", "U5")))
    }
    assert legacy["edge_health_alpha_1_6"] == "UNPROVEN"  # rule set v12: no edge health score exists


def test_the_own_history_facts_are_canonical_and_only_on_top_of_the_incubation_facts() -> None:
    observation = v13()
    facts = observation.own_history
    for changed, reason in (
        (replace(observation, incubation=None), "observation_malformed:own_history_without_the_incubation_facts"),
        (
            replace(observation, own_history=replace(facts, evidence_digest="x")),
            "observation_malformed:own_history_evidence_digest",
        ),
        (
            replace(observation, own_history=replace(facts, reading=replace(facts.reading, decision_sequence=99))),
            "observation_malformed:own_history_reading",
        ),
        (
            replace(
                observation,
                own_history=replace(
                    facts,
                    reading=replace(facts.reading, nt_x02=GovernedPaperOwnHistoryCheck(Out.PASS, "1", "forged", ())),
                ),
            ),
            "observation_malformed:own_history_reading_digest",
        ),
        (replace(observation, own_history=object()), "observation_malformed:own_history"),
    ):
        with pytest.raises(GovernedPaperEntrySafetyError, match=f"{reason}$"):
            evaluate_governed_paper_entry_safety(changed)  # type: ignore[arg-type]


# --- the decided allocation (R-1) ---------------------------------------------------------------------------------------------


def candidate(
    edge_id: str, activation: str = "PASS", member: bool | None = True, sharpe: bool = True
) -> GovernedPaperAllocationDecidedCandidate:  # noqa: FBT001, FBT002
    return GovernedPaperAllocationDecidedCandidate(
        edge_id, GovernedPaperAllocationActivation(activation), member, sharpe, "synthetic"
    )


def test_allocation_one_proven_member_weighs_exactly_two_fifths_and_two_members_are_blocked_on_r1() -> None:
    single = derive_governed_paper_allocation_decided((candidate("s1"),))
    (weight,) = single.weights
    assert (single.status, single.reason, single.member_count, single.residual) == (
        GovernedPaperAllocationStatus.ALLOCATED,
        "allocated_single_member",
        1,
        "3/5",
    )
    assert (weight.eligibility, weight.weight, weight.rendered) == (
        GovernedPaperAllocationEligibility.MEMBER,
        "2/5",
        "0.400000000000000000",
    )
    pair = derive_governed_paper_allocation_decided((candidate("s1"), candidate("s2")))
    assert (pair.status, pair.reason, pair.member_count) == (
        GovernedPaperAllocationStatus.BLOCKED,
        "r1_representation_of_irrational_shares_pending_human_decision",
        2,
    )
    assert all(item.weight is None for item in pair.weights)  # no general R-1 solution
    for rows, status, reasons in (
        ((candidate("s1", "FAIL"),), GovernedPaperAllocationStatus.NO_ALLOCATION, ["activation_proven_fail"]),
        (
            (candidate("s1", member=False),),
            GovernedPaperAllocationStatus.NO_ALLOCATION,
            ["edge_health_score_below_0_30_disabled"],
        ),
        ((candidate("s1", "UNKNOWN"),), GovernedPaperAllocationStatus.BLOCKED, ["activation_unproven"]),
        ((candidate("s1", member=None),), GovernedPaperAllocationStatus.BLOCKED, ["edge_health_score_undefined"]),
        ((candidate("s1", sharpe=False),), GovernedPaperAllocationStatus.BLOCKED, ["sharpe_30d_undefined"]),
        (
            (candidate("s1"), candidate("s2", "UNKNOWN")),
            GovernedPaperAllocationStatus.BLOCKED,
            ["allocation_unproven_another_candidate_is_unknown", "activation_unproven"],
        ),
    ):
        found = derive_governed_paper_allocation_decided(rows)
        assert (found.status, [item.reason for item in found.weights]) == (status, reasons)
    for bad in ([candidate("s1")], (candidate("s1"), candidate("s1")), (object(),)):
        with pytest.raises(GovernedPaperAllocationError):
            derive_governed_paper_allocation_decided(bad)  # type: ignore[arg-type]


def test_allocation_the_own_history_rebalance_reads_only_decided_readings() -> None:
    """WHITE-BOX: activation is never PASS (X-H1), so no member is reachable; a proven forbidden column is a NON_MEMBER."""

    f = Fraction
    defined = ehs(f(4, 5))
    assert own._allocation(defined, T.UNKNOWN, "s1", ("s1",)) == (
        GovernedPaperAllocationEligibility.UNKNOWN,
        None,
        "blocked:activation_unproven",
    )
    assert own._allocation(defined, T.TRUE, "s1", ("s1",)) == (
        GovernedPaperAllocationEligibility.NON_MEMBER,
        None,
        "no_allocation:activation_proven_fail",
    )
    assert (
        own._allocation(ehs(f(1, 5)), T.UNKNOWN, "s1", ("s1",))[2]
        == "no_allocation:edge_health_score_below_0_30_disabled"
    )
    assert own._allocation(defined, T.TRUE, "s1", ("s1", "s2"))[2] == "blocked:activation_proven_fail"


# --- X1 and FA-2 ---------------------------------------------------------------------------------------------------------------


def test_fa2_a_later_publication_never_rewrites_an_earlier_reading_or_prefix() -> None:  # FA-2
    world = hold_world()
    u = ANCHOR + 2 * DAY
    absent = evidence_of(world, GovernedPaperOwnHistoryContext(()))
    late = evidence_of(world, covered(world, u))
    early = [item for item in late.readings if item.decision_time_ns < u]
    assert early and early == [item for item in absent.readings if item.decision_time_ns < u]
    assert governed_paper_own_history_prefix_digest(late, before_ns=u) == governed_paper_own_history_prefix_digest(
        absent, before_ns=u
    )
    after = [item for item in late.readings if item.decision_time_ns >= u]
    assert after and all(item.complete for item in after)  # known from u on, and only from u on


def test_x1_a_longer_horizon_reproduces_every_earlier_reading_and_prefix() -> None:
    short_world, long_world = hold_world(ANCHOR + 2 * DAY), hold_world()
    context = covered(long_world)
    short, long = evidence_of(short_world, context), evidence_of(long_world, context)
    end = ANCHOR + 2 * DAY
    assert short.readings == tuple(item for item in long.readings if item.decision_time_ns < end)
    for before in sorted({ANCHOR, end, *(item.decision_time_ns for item in short.readings)}):
        assert governed_paper_own_history_prefix_digest(
            short, before_ns=before
        ) == governed_paper_own_history_prefix_digest(long, before_ns=before), before


# --- caller input, tampering and the public verifier ---------------------------------------------------------------------------


def test_the_derivation_takes_no_caller_fact_and_refuses_foreign_or_unreproduced_inputs() -> None:
    world = hold_world()
    w, result, derivation = world
    evidence = hold_evidence()
    assert governed_paper_own_history_evidence_digest(evidence) == evidence.evidence_digest
    assert all(governed_paper_own_history_reading_digest(item) == item.reading_digest for item in evidence.readings)
    v9 = simulate_historical_execution_governed_paper(
        result,
        expected_result_digest=result.result_digest,
        schedule=replace(hold_schedule(w, lifet.HOLD_END), schema_version=V9),
    )
    lineage = lineage_of(w, result)

    def derive(**changes: object) -> object:
        values: dict[str, object] = {
            "lineage": lineage, "run": w.run, "dataset": w.dataset, "result": result,
            "expected_result_digest": result.result_digest, "outcome": derivation.outcome, "context": covered(world),
        }  # fmt: skip
        values.update(changes)
        with own_table():
            return own._derive(**values)  # type: ignore[arg-type]

    for changes, reason in (
        ({"outcome": v9}, "own_history_needs_the_schedule_v10"),
        (
            {"outcome": replace(derivation.outcome, fills=derivation.outcome.fills[:-1])},
            "outcome_not_reproduced_by_the_replay_authority",
        ),
        ({"expected_result_digest": "0" * 64}, "replay_authority_not_authentic"),
        ({"lineage": replace(lineage, instrument="OTHER")}, "inputs_not_of_the_genesis"),
        ({"lineage": replace(lineage, start_ns=ANCHOR + 1)}, "inputs_not_of_the_genesis"),
        ({"dataset": child_world()[0].dataset}, "inputs_not_of_the_genesis"),
        ({"context": GovernedPaperOwnHistoryContext([])}, "context_malformed"),  # type: ignore[arg-type]
        ({"run": object()}, "inputs_malformed"),
        ({"outcome": object()}, "inputs_malformed"),
    ):
        with pytest.raises(GovernedPaperOwnHistoryError, match=f"{reason}$"):
            derive(**changes)
    with pytest.raises(GovernedPaperOwnHistoryError, match="inputs_malformed$"):
        derive_governed_paper_own_history_evidence(
            authority=object(), run=w.run, dataset=w.dataset, result=result,  # type: ignore[arg-type]
            expected_result_digest=result.result_digest, outcome=derivation.outcome, context=covered(world),
        )  # fmt: skip
    with pytest.raises(GovernedPaperOwnHistoryError, match="no_reading_of_the_decision$"):
        governed_paper_own_history_reading(evidence, 10**6)
    with pytest.raises(GovernedPaperOwnHistoryError, match="prefix_instant_invalid$"):
        governed_paper_own_history_prefix_digest(evidence, before_ns=-1)
    with pytest.raises(GovernedPaperOwnHistoryError, match="evidence_malformed$"):
        governed_paper_own_history_coverage_cuts(object())  # type: ignore[arg-type]
    rejected = verify_governed_paper_own_history_evidence(
        object(), authority=None, run=w.run, dataset=w.dataset, result=result,  # type: ignore[arg-type]
        expected_result_digest=result.result_digest, outcome=derivation.outcome, context=covered(world),
    )  # fmt: skip
    assert (rejected.intact, rejected.reason_codes) == (False, ("governed_paper_own_history:evidence_malformed",))


# --- production refusal --------------------------------------------------------------------------------------------------------


def test_production_admits_no_coverage_claim_so_no_reading_is_ever_complete() -> None:
    world = hold_world()
    evidence = evidence_of(world, table=GOVERNED_PAPER_OWN_HISTORY_PRODUCTION_TABLE)
    assert (evidence.table_id, evidence.coverage_digests) == ("production", ())
    assert all(
        item.endswith(":coverage_channel_not_admitted_by_the_active_table") for item in evidence.coverage_refusals
    )
    assert {item.complete for item in evidence.readings} == {False}
    assert {item.state for item in evidence.readings} == {St.LIFECYCLE_UNPROVEN}
    assert evidence.lifecycle_reason == "disable_condition_not_known_by_the_horizon"
    for item in evidence.readings:
        assert {item.nt_e01.outcome, item.nt_e02.outcome, item.nt_e04.outcome, item.nt_x02.outcome} == {Out.BLOCKED}
        assert item.allocation_eligibility is GovernedPaperAllocationEligibility.UNKNOWN
    human = covered(world, channel=GOVERNED_PAPER_OWN_HISTORY_HUMAN_CHANNEL)
    unlisted = evidence_of(world, human, table=GOVERNED_PAPER_OWN_HISTORY_PRODUCTION_TABLE)
    assert all(item.endswith(":coverage_not_listed_by_the_production_table") for item in unlisted.coverage_refusals)
    listed = GovernedPaperOwnHistoryTable(
        "production", GOVERNED_PAPER_OWN_HISTORY_HUMAN_CHANNEL, tuple(item.coverage_digest for item in human.coverages)
    )
    qualified = evidence_of(world, human, table=listed)
    assert all(item.endswith(":coverage_source_not_m1_qualified") for item in qualified.coverage_refusals)  # E-1
    assert {item.complete for item in qualified.readings} == {False}
    assert evidence.paper_only is True and evidence.production_coverage_qualified is False
    assert (evidence.entry_authorized, evidence.quarantine_release_authorized, evidence.edge_proven) == (
        False,
        False,
        False,
    )
