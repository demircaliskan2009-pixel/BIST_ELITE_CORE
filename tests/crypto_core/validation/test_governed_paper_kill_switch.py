"""Governed paper kill-switch proven escalation tests (S1_KILL_SWITCH_PROVEN_ESCALATION_CLOSURE_V1).

SYNTHETIC TEST VALUES ONLY. Every price, mark, rate, latency, instant and policy here is a synthetic fixture that
exercises structure; none is a production threshold, venue truth, a qualified source or a real human decision. No test
grants or simulates a governed kill-switch recovery approval: none exists in this contract.

The PRODUCTION entry gate stays in force throughout (no rule table is replaced). It proves:

* A. the lower bound over (nanosecond, engine equal-instant phase) instants:
  - one proven standard trigger is KS-1, two simultaneous KS-2, three or any critical KS-3, at once and skipping levels;
  - a trigger counts once, however many readings or overlapping intervals prove it (Sol B1), and malformed or
    conflicting reading identities are refused;
  - triggers count only while simultaneous in one phase;
  - below KS-3 the bound follows the triggers proven at each instant and never claims a de-escalation, because the two
    readings of §1.19's cool-down (from the clearing, from the level's entry) disagree on any persistence after an
    earlier unproven entry;
  - KS-3 is absorbing and no input exists to clear it;
  - over every small history, repetitions and overlaps included, the bound is exactly the level of the distinct proven
    triggers (an independent oracle) and never exceeds the true level of any history that adds triggers, under either
    reading (two more independent oracles), nor that history's own bound;
* B. the native readers on engine-derived SYNTHETIC worlds (the protective lifecycle worlds: 8 h funding, 15 min marks,
  H2 decisions at each publication, 10 s after each settlement):
  - a mark jump that values the open SHORT 16% below the initial equity at a decision proves T1, T2 and T11 (KS-3,
    while its protective stop still closes it), and one 11% below proves T1 and T2 (KS-2) at that decision only;
  - five stopped-out SHORTs prove T5 from the fill phase of the fifth close until the next close, and with T6 KS-2;
  - four consecutive final rates strictly beyond 0.1% on the 8 h grid prove T6 from the fourth publication;
  - a governed latency strictly above 1 s proves T7 strictly after 60 s;
  - each threshold is strict at its exact boundary;
  - a late publication delays a reading, a record unknown by the horizon is never read, and a shorter evaluation is
    exactly the prefix of a longer one;
  - Sol B3: Sol's reproducer (an exact NAV just above -15% whose scale-18 rendering is below it) never proves T11, an
    exact value proves a strict threshold at equality and adjacent values, and a rendered amount without its exact
    engine value proves nothing;
  - Sol B4: a decision never reads a fill of its own nanosecond (the fifth close at the decision instant is T5 from the
    fill phase, after the decision's T1), no false KS-3 reaches the next decisions, and a genuine overlap in one phase
    (the close and its funding published before the decision) proves an absorbing KS-3;
* C. rule set v5: it adds only its kill-switch rule to rule set v4 (v1-v4 keep their accepted identities); NT-R01 FAILs
  exactly on a proven KS-2 or more and is BLOCKED otherwise, naming every unproven trigger; NT-T02 stays BLOCKED; no
  PASS branch exists; without kill-switch facts both keep their accepted outcomes; malformed facts are refused;
* D. the sequential admission with the ladder in the loop: under a TEST-ONLY reading in which only a proven level
  refuses, every entry after a proven KS-3 is refused at its decision while the open SHORT's protective close-only stop
  still fills, and the schedule is the unique fixed point;
* E. world G's kill-switch lineage (seal v6, evidence v6):
  - it is one from day 0 or never, and only on a market-data lineage;
  - against the v5 lineage it changes only its version, its rule set and the bound ladder;
  - every seal re-verifies and chains its ladder prefix;
  - forged or substituted kill-switch facts, a rewritten prefix and relabelled versions never verify;
  - no v2-v5 payload carries a v6 field;
* F. the engine derivation returns one re-run's decision portfolio and governed outcome byte-identical to their own
  functions, the exact values behind every rendered NAV and the phase of every close; the ladder is derived from it and
  never accepted (Sol B2): it takes no portfolio or outcome, so a resealed forged portfolio has no entry point, and a
  malformed, forged or foreign policy, archive, economics or schedule is refused with a contract-specific reason.
"""

from __future__ import annotations

import functools
import inspect
import itertools
import math
from dataclasses import replace
from fractions import Fraction

import pytest

import crypto_core.validation.governed_paper_entry_safety as entry_safety
import crypto_core.validation.governed_paper_kill_switch as kill_switch
import crypto_core.validation.historical_execution_economics as engine
from crypto_core.validation.edge_artifact_core import edge_canonical_json, edge_sha256_text
from crypto_core.validation.governed_admitted_variant_paper_execution import (
    GovernedPaperDaySealStatus,
    GovernedPaperExecutionStatus,
    build_governed_paper_day_seal,
    governed_paper_day_seal_to_dict,
    verify_governed_paper_execution_evidence,
)
from crypto_core.validation.governed_paper_entry_safety import (
    GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET,
    GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET_ID,
    GOVERNED_PAPER_ENTRY_SAFETY_MARKET_DATA_RULE_SET,
    GOVERNED_PAPER_ENTRY_SAFETY_MARKET_DATA_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_PORTFOLIO_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_DIGEST,
    GovernedPaperEntrySafetyError,
    GovernedPaperEntrySafetyKillSwitch,
    GovernedPaperEntrySafetyPortfolio,
    GovernedPaperEntrySafetyStatus,
    build_governed_paper_entry_safety_evidence,
    evaluate_governed_paper_entry_safety,
    governed_paper_entry_safety_entry_sequences,
    governed_paper_entry_safety_kill_switch_facts,
    governed_paper_entry_safety_rule_set,
    governed_paper_entry_safety_rule_set_digest,
    governed_paper_entry_safety_sequential_refusals,
)
from crypto_core.validation.governed_paper_kill_switch import (
    GOVERNED_PAPER_KILL_SWITCH_DECISION_PHASE,
    GOVERNED_PAPER_KILL_SWITCH_NON_CLAIM_FLAGS,
    GOVERNED_PAPER_KILL_SWITCH_RULE,
    GOVERNED_PAPER_KILL_SWITCH_RULE_DIGEST,
    GOVERNED_PAPER_KILL_SWITCH_TRIGGER_IDS,
    GovernedPaperKillSwitchError,
    GovernedPaperKillSwitchMeasurement,
    derive_governed_paper_kill_switch_ladder,
    governed_paper_kill_switch_ladder_digest,
    governed_paper_kill_switch_ladder_to_dict,
    governed_paper_kill_switch_level_at,
    governed_paper_kill_switch_prefix_digest,
    governed_paper_kill_switch_proven_at,
    governed_paper_kill_switch_transitions,
    governed_paper_kill_switch_unproven_at,
)
from crypto_core.validation.historical_execution_economics import (
    HISTORICAL_EXECUTION_EQUAL_INSTANT_PHASES,
    HistoricalExecutionDecisionExactValues,
    HistoricalExecutionEconomicsError,
    HistoricalExecutionFillOutcome,
    HistoricalExecutionTradeStatus,
    build_historical_execution_economics,
    historical_execution_admission_schedule_digest,
    historical_execution_economics_digest,
    historical_execution_governed_paper_decision_portfolio_digest,
    historical_execution_governed_paper_outcome_digest,
    simulate_historical_execution_governed_paper,
    simulate_historical_execution_governed_paper_decision_portfolio,
    simulate_historical_execution_governed_paper_derivation,
)
from crypto_core.validation.historical_execution_economics_policy import historical_execution_render_amount

try:  # the module objects pytest collects (basename import): the shared synthetic worlds and their exact memos
    import test_governed_admitted_variant_paper_execution as gpe
    import test_governed_paper_entry_safety as est
    import test_governed_paper_protective_lineage as lineage
    import test_historical_execution_protective_lifecycle as lifet
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_governed_admitted_variant_paper_execution as gpe
    from tests.crypto_core.validation import test_governed_paper_entry_safety as est
    from tests.crypto_core.validation import test_governed_paper_protective_lineage as lineage
    from tests.crypto_core.validation import test_historical_execution_protective_lifecycle as lifet

PRODUCTION_CHECKS = entry_safety._CHECKS  # noqa: SLF001 - captured at import, before any fixture could patch it
S = GovernedPaperEntrySafetyStatus
BLOCKED = S.BLOCKED_ON_MISSING_INPUT
CLOSED = HistoricalExecutionTradeStatus.CLOSED
SECOND = 1_000_000_000
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE
G0 = 1_800_000_000 * SECOND  # SYNTHETIC lineage start of the pure ladder tests
HORIZON = G0 + 48 * HOUR
ORDER = GOVERNED_PAPER_KILL_SWITCH_TRIGGER_IDS.index
ALWAYS_UNMEASURED = ("T3", "T8", "T9", "T10", "T12", "KS4", "DTL")
PHASE = HISTORICAL_EXECUTION_EQUAL_INSTANT_PHASES.index
F, P, D, X = "FUNDING", "PROTECTIVE", "DECISION", "FILL"  # the equal-instant phases these tests name
render = historical_execution_render_amount


@pytest.fixture(autouse=True, scope="module")
def _production_gate_with_exact_memos():
    """Only the exact upstream memos (pure re-proofs): the PRODUCTION rule table stays in force throughout."""

    with pytest.MonkeyPatch.context() as patch:
        gpe.apply_memos(patch)
        assert entry_safety._CHECKS is PRODUCTION_CHECKS  # noqa: SLF001
        yield


def code(text: str) -> str:
    return f"governed_paper_kill_switch:{text}"


def ratio(value: Fraction) -> str:
    """The exact observed ratio of a drawdown reading: never a rounded rendering."""

    return f"{value.numerator}/{value.denominator}"


# --- A. the lower-bound ladder -------------------------------------------------------------------------------------------

reading = kill_switch._reading  # noqa: SLF001 - the reading constructor of the module under test


def point(trigger: str, at: int, tag: str = "f"):  # noqa: ANN201
    """A SYNTHETIC proven reading of ``trigger`` at the DECISION phase of ``at`` alone (one distinct reading per tag)."""

    return reading(trigger, (at, D), (at, X), "synthetic", (tag * 64,))


def held(trigger: str, start: int, end: int | None, tag: str = "e"):  # noqa: ANN201
    """A SYNTHETIC proven reading of ``trigger`` from the first phase of ``start`` to the first phase of ``end`` (None:
    still proven at the horizon)."""

    return reading(trigger, (start, F), None if end is None else (end, F), "synthetic", (tag * 64,))


def flow_of(*readings: object, start: int = G0, horizon: int = HORIZON) -> tuple:
    return governed_paper_kill_switch_transitions(readings, start_ns=start, horizon_ns=horizon)  # type: ignore[arg-type]


def level_after(transitions: tuple, at: int, phase: str = D) -> int:
    level = 0
    for item in transitions:
        if (item.time_ns, PHASE(item.phase)) > (at, PHASE(phase)):
            break
        level = item.to_level
    return level


def changes(transitions: tuple) -> list[tuple[int, str, int, int, tuple[str, ...]]]:
    return [(item.time_ns, item.phase, item.from_level, item.to_level, item.proven_trigger_ids) for item in transitions]


def test_one_proven_standard_trigger_is_ks1_two_simultaneous_ks2_three_or_any_critical_ks3_at_once() -> None:
    at = G0 + HOUR
    for readings, level in (
        ((point("T1", at),), 1),
        ((point("T1", at), point("T2", at)), 2),
        ((point("T1", at), point("T2", at), point("T5", at)), 3),
        ((point("T11", at),), 3),
        ((point("T9", at),), 3),
        ((point("T6", at), point("T12", at)), 3),
    ):
        flow = flow_of(*readings)
        proven = tuple(sorted({item.trigger_id for item in readings}, key=ORDER))
        assert changes(flow)[0] == (at, D, 0, level, proven)  # immediate, skipping levels
        assert (level_after(flow, at - 1), level_after(flow, at, P), level_after(flow, at)) == (0, 0, level)
        assert flow[0].reading_ids == tuple(sorted({item.reading_id for item in readings}))


def test_a_trigger_counts_once_however_many_readings_or_overlapping_intervals_prove_it() -> None:
    """Sol B1 (P2-DUPLICATE-TRIGGER-COUNT) regression. The pre-repair machine counted readings: T1 listed twice proved
    KS-2, three times an absorbing KS-3, and two overlapping T5 intervals KS-2. Simultaneity is over distinct trigger
    identities."""

    at = G0 + HOUR
    one = changes(flow_of(point("T1", at)))
    assert one == [(at, D, 0, 1, ("T1",)), (at, X, 1, 0, ())]
    for count in (2, 3):
        assert changes(flow_of(*(point("T1", at) for _ in range(count)))) == one  # one reading listed again
        assert changes(flow_of(*(point("T1", at, tag) for tag in "abc"[:count]))) == one  # distinct readings
    distinct = tuple(point("T1", at, tag) for tag in "abc")
    assert flow_of(*distinct)[0].reading_ids == tuple(sorted(item.reading_id for item in distinct))  # every one named
    # overlapping intervals of one trigger never raise the level: one KS-1 over their union
    assert changes(flow_of(held("T5", at, at + 2 * HOUR, "a"), held("T5", at + HOUR, at + 3 * HOUR, "b"))) == [
        (at, F, 0, 1, ("T5",)),
        (at + 3 * HOUR, F, 1, 0, ()),
    ]
    # distinct triggers still count, at once and skipping levels, whatever their repetitions
    assert changes(flow_of(point("T1", at), point("T2", at)))[0] == (at, D, 0, 2, ("T1", "T2"))
    assert changes(flow_of(point("T1", at), point("T2", at), point("T6", at)))[0] == (at, D, 0, 3, ("T1", "T2", "T6"))
    doubled = (point("T1", at), point("T1", at, "a"), point("T2", at), point("T2", at, "b"))
    assert changes(flow_of(*doubled))[0] == (at, D, 0, 2, ("T1", "T2"))
    # the order and repetition of the readings never change a transition or its evidence
    mixed = (point("T1", at), held("T5", at, at + HOUR), point("T2", at, "b"), point("T1", at, "a"))
    reference = flow_of(*mixed)
    for order in itertools.permutations(mixed):
        assert flow_of(*order, order[0]) == reference


def test_triggers_count_only_while_simultaneous_in_one_phase_and_readings_are_half_open() -> None:
    at = G0 + HOUR
    # T1 ends exactly where T2 starts: never two at once, and the supported KS-1 never falls in between
    flow = flow_of(held("T1", at, at + HOUR), held("T2", at + HOUR, at + 2 * HOUR))
    assert changes(flow) == [(at, F, 0, 1, ("T1",)), (at + 2 * HOUR, F, 1, 0, ())]
    # one nanosecond of overlap proves KS-2 for exactly that nanosecond
    flow = flow_of(held("T1", at, at + HOUR + 1), held("T2", at + HOUR, at + 2 * HOUR))
    assert changes(flow) == [
        (at, F, 0, 1, ("T1",)),
        (at + HOUR, F, 1, 2, ("T1", "T2")),
        (at + HOUR + 1, F, 2, 1, ("T2",)),
        (at + 2 * HOUR, F, 1, 0, ()),
    ]
    # phases are half-open too: a reading that ends at the DECISION phase of an instant is not proven at that decision,
    # one that ends at its FILL phase is; and a reading from the FILL phase of an instant never reaches its decision
    before = reading("T5", (at - HOUR, F), (at, D), "synthetic", ("a" * 64,))
    through = reading("T5", (at - HOUR, F), (at, X), "synthetic", ("b" * 64,))
    after = reading("T5", (at, X), None, "synthetic", ("c" * 64,))
    assert level_after(flow_of(before, point("T1", at)), at) == 1
    assert level_after(flow_of(through, point("T1", at)), at) == 2
    assert level_after(flow_of(after, point("T1", at)), at) == 1
    assert changes(flow_of(after, point("T1", at), point("T2", at))) == [
        (at, D, 0, 2, ("T1", "T2")),
        (at, X, 2, 1, ("T5",)),
    ]


def test_below_ks3_the_bound_follows_the_proven_triggers_and_never_claims_a_de_escalation() -> None:
    at = G0 + 2 * HOUR
    # a supported level holds however long it lasts, and the bound falls the instant its proof ends
    flow = flow_of(held("T5", at, at + 20 * HOUR), held("T6", at, at + 20 * HOUR))
    assert changes(flow) == [(at, F, 0, 2, ("T5", "T6")), (at + 20 * HOUR, F, 2, 0, ())]
    flow = flow_of(point("T1", at), held("T5", at, at + 10 * HOUR))
    assert changes(flow) == [
        (at, F, 0, 1, ("T5",)),
        (at, D, 1, 2, ("T1", "T5")),
        (at, X, 2, 1, ("T5",)),
        (at + 10 * HOUR, F, 1, 0, ()),
    ]
    # why no persistence is claimed: two point readings prove KS-2 at ``at``, but a true history that also held two
    # unproven triggers for the half hour before keeps KS-2 for 4 h under the reading that counts the cool-down from the
    # clearing and for 3 h 30 min under the one that counts it from the level's entry. No persistence holds under both.
    proven = (point("T1", at), point("T2", at))
    true = (*proven, held("T5", at - U, at), held("T6", at - U, at))
    probe = (at - U, at, at + 3 * HOUR + 45 * MINUTE)
    assert [level_after(flow_of(*proven), instant) for instant in probe] == [0, 2, 0]
    assert [oracle_levels(true, probe, from_entry=False)[2], oracle_levels(true, probe, from_entry=True)[2]] == [2, 1]


def test_ks3_is_absorbing_and_no_input_can_authorize_a_recovery() -> None:
    at = G0 + HOUR
    flow = flow_of(point("T11", at), held("T1", at + 2 * HOUR, at + 3 * HOUR))
    assert changes(flow) == [(at, D, 0, 3, ("T11",))]
    assert level_after(flow, HORIZON - 1, "EVALUATION_END") == 3
    # the machine and the ladder take no approval, revocation, recovery, reading or ladder input of any kind
    assert list(inspect.signature(governed_paper_kill_switch_transitions).parameters) == [
        "readings",
        "start_ns",
        "horizon_ns",
    ]
    assert list(inspect.signature(derive_governed_paper_kill_switch_ladder).parameters) == [
        "policy",
        "dataset",
        "economics",
        "schedule",
        "single_instrument_portfolio",
    ]


SAMPLE = held("T5", G0 + 5, G0 + 10)
BACKWARDS = reading("T1", (G0 + 5, X), (G0 + 5, D), "synthetic", ("f" * 64,))  # ends one phase before it starts


@pytest.mark.parametrize(
    ("readings", "start", "horizon", "reason"),
    [
        ([], G0, HORIZON, "readings_malformed"),
        ((object(),), G0, HORIZON, "reading_malformed"),
        ((point("KS4", G0 + 1),), G0, HORIZON, "reading_malformed"),  # no §1.19 ladder semantics
        ((point("DTL", G0 + 1),), G0, HORIZON, "reading_malformed"),
        ((replace(SAMPLE, trigger_id=["T5"]),), G0, HORIZON, "reading_malformed"),
        ((replace(SAMPLE, start_phase="LUNCH"),), G0, HORIZON, "reading_malformed"),
        ((replace(SAMPLE, evidence_digests=["e" * 64]),), G0, HORIZON, "reading_malformed"),
        ((point("T1", G0 - 1),), G0, HORIZON, "reading_outside_the_evaluation"),
        ((point("T1", HORIZON),), G0, HORIZON, "reading_outside_the_evaluation"),
        ((held("T1", G0 + 5, G0 + 5),), G0, HORIZON, "reading_interval_malformed"),
        ((BACKWARDS,), G0, HORIZON, "reading_interval_malformed"),
        ((held("T1", G0 + 5, HORIZON),), G0, HORIZON, "reading_interval_malformed"),  # proven at the horizon: open
        ((replace(SAMPLE, end_phase=None),), G0, HORIZON, "reading_interval_malformed"),
        ((replace(SAMPLE, end_phase="LUNCH"),), G0, HORIZON, "reading_interval_malformed"),
        ((replace(SAMPLE, reading_id="0" * 64),), G0, HORIZON, "reading_identity_malformed"),
        ((replace(SAMPLE, observed="forged"),), G0, HORIZON, "reading_identity_malformed"),
        ((SAMPLE, replace(SAMPLE, end_ns=G0 + 20)), G0, HORIZON, "reading_identity_conflict"),  # one identity, two ends
        ((), HORIZON, HORIZON, "evaluation_window_malformed"),
        ((), True, HORIZON, "evaluation_window_malformed"),
    ],
)
def test_a_malformed_or_conflicting_reading_or_window_is_refused(
    readings: object, start: object, horizon: int, reason: str
) -> None:
    with pytest.raises(GovernedPaperKillSwitchError, match=f"^{code(reason)}$"):
        governed_paper_kill_switch_transitions(readings, start_ns=start, horizon_ns=horizon)  # type: ignore[arg-type]


U = 30 * MINUTE  # the grid of the exhaustive checks
COOLDOWN = {1: HOUR, 2: 4 * HOUR}
TEMPLATES = (
    point("T1", G0 + 2 * U),
    point("T2", G0 + 2 * U),
    held("T5", G0 + 4 * U, G0 + 12 * U),
    held("T6", G0 + 6 * U, None),
    held("T2", G0 + 10 * U, G0 + 11 * U),
    point("T1", G0 + 16 * U),
    held("T7", G0 + 14 * U, G0 + 30 * U),
    point("T11", G0 + 24 * U),
    held("T1", G0 + 20 * U, G0 + 22 * U),
    point("T5", G0 + 21 * U),
)
# repetitions of a trigger: a second reading at the same instant, an overlapping interval, a point inside an interval
REPEATS = (
    point("T1", G0 + 2 * U, "a"),
    held("T5", G0 + 8 * U, G0 + 16 * U, "b"),
    point("T2", G0 + 10 * U, "c"),
)
FAMILY = (*TEMPLATES, *REPEATS)
GRID = tuple(G0 + k * U for k in range(40))


def proven_at_decision(readings: tuple, at: int) -> set[str]:
    """INDEPENDENT: the distinct triggers the readings prove at the DECISION phase of ``at``."""

    decision = (at, PHASE(D))
    return {
        item.trigger_id
        for item in readings
        if (item.start_ns, PHASE(item.start_phase)) <= decision
        and (item.end_ns is None or decision < (item.end_ns, PHASE(item.end_phase)))
    }


def level_of(active: set[str]) -> int:
    critical = len(active & {"T9", "T10", "T11", "T12"})
    standard = len(active) - critical
    return 3 if critical or standard >= 3 else standard


def oracle_levels(readings: tuple, grid: tuple[int, ...], *, from_entry: bool) -> list[int]:
    """INDEPENDENT ORACLE: the true level under one reading of §1.19's de-escalation clause, at the grid decisions.

    Both readings escalate at once to the level of the distinct simultaneous triggers and keep KS-3 (no approval
    exists). A level falls one step at a time once every trigger has cleared and its cool-down has elapsed, counted from
    the clearing (``from_entry=False``) or from the level's entry (``from_entry=True``); the next step's from that step.
    Clearing is observed at the grid only, which never makes either reading fall earlier.
    """

    level, since, levels = 0, None, []
    for at in grid:
        active = proven_at_decision(readings, at)
        target = level_of(active)
        if level != 3 and target > level:
            level, since = target, (at if from_entry else None)
        if active and not from_entry:
            since = None
        elif not active and level in COOLDOWN:
            since = at if since is None else since
            while level in COOLDOWN and at - since >= COOLDOWN[level]:
                since, level = (at if from_entry else since + COOLDOWN[level]), level - 1
        levels.append(level)
    return levels


def oracle_bound(readings: tuple, grid: tuple[int, ...]) -> list[int]:
    """INDEPENDENT ORACLE of the bound itself: the level of the distinct triggers proven at each grid decision, held at
    3 from the first 3 on. Every reading of the family starts and ends on the grid and no phase of a grid instant proves
    more than its decision phase, so the grid decisions see every level the bound takes."""

    level, levels = 0, []
    for at in grid:
        level = 3 if level == 3 else level_of(proven_at_decision(readings, at))
        levels.append(level)
    return levels


def bound_levels(readings: tuple) -> list[int]:
    flow = flow_of(*readings, horizon=G0 + 40 * U)
    return [level_after(flow, at) for at in GRID]


def test_the_bound_is_exactly_the_level_of_the_distinct_proven_triggers_over_every_small_history() -> None:
    """Sol B1 oracle comparison, exhaustive over every history of at most four of the thirteen SYNTHETIC readings,
    repetitions and overlaps of one trigger included: the bound equals the independent oracle at every grid decision."""

    histories = repeated = 0
    for size in range(5):
        for chosen in itertools.combinations(FAMILY, size):
            assert bound_levels(chosen) == oracle_bound(chosen, GRID), chosen
            histories += 1
            repeated += len({item.trigger_id for item in chosen}) < size
    assert histories == sum(math.comb(len(FAMILY), size) for size in range(5)) == 1093
    assert repeated == 630  # the histories that repeat a trigger: the failure class of the pre-repair machine


def test_the_bound_never_exceeds_the_true_level_under_either_reading_and_never_falls_when_a_reading_is_added() -> None:
    """Exhaustive over the thirteen SYNTHETIC readings: for every proven history of at most two and every true history
    that adds at most two more, the bound of the proven one never exceeds the true level under either de-escalation
    reading, nor the bound of the true one (monotonicity), at any grid decision."""

    pairs = 0
    for size in range(3):
        for chosen in itertools.combinations(FAMILY, size):
            bound = bound_levels(chosen)
            rest = [item for item in FAMILY if item not in chosen]
            for extra in itertools.chain.from_iterable(itertools.combinations(rest, count) for count in range(3)):
                true = (*chosen, *extra)
                for upper in (
                    oracle_levels(true, GRID, from_entry=False),
                    oracle_levels(true, GRID, from_entry=True),
                    bound_levels(true),
                ):
                    assert all(low <= high for low, high in zip(bound, upper, strict=True)), (chosen, extra)
                pairs += 1
    assert pairs == 1 * (1 + 13 + 78) + 13 * (1 + 12 + 66) + 78 * (1 + 11 + 55)


# --- B. the native readers on engine-derived SYNTHETIC worlds ---------------------------------------------------------------

SPIKE = "0.002000000000000000"  # SYNTHETIC: strictly beyond 0.1% per 8 h (§1.19 trigger 6)
POSITIVE = lifet.POSITIVE
ANCHOR, END_2D = lifet.ANCHOR, lifet.END_2D
END_3D = ANCHOR + 3 * lifet.DAY


def stairs(j: int) -> Fraction:
    """SYNTHETIC marks: +4 one hour after each of the first nine opening fills, so every SHORT stops out (distance 3)."""

    return Fraction(100 + 4 * sum(1 for k in range(9) if j >= 32 * (k + 1) + 4))


def same_instant_mark(j: int) -> Fraction:
    """SYNTHETIC marks: SHORTs 0-3 stop out one hour after opening (as ``stairs``) and SHORT 4 at 48 h, 600 down."""

    base = 100 + 4 * sum(1 for k in range(4) if j >= 32 * (k + 1) + 4)
    return Fraction(base + 600) if j >= 192 else Fraction(base)


CRASH = lifet.Path(rates=(POSITIVE,) * 6, mark=lifet.jump(64, 1700))  # the D_0 SHORT valued ~16% of NAV down at D_1
DROP = lifet.Path(rates=(POSITIVE,) * 6, mark=lifet.jump(64, 1200))  # ~11% down at D_1
SPIKES = lifet.Path(rates=(SPIKE,) * 4 + (POSITIVE,) * 2)
STAIRS_SPIKE = lifet.Path(rates=(SPIKE,) * 9, mark=stairs)
SAME_INSTANT = lifet.Path(rates=(SPIKE,) * 6 + (POSITIVE,) * 3, mark=same_instant_mark)
AT_THE_STOP = ((5, 31 * SECOND),)  # record 5 published, so D_5 decides, at the instant SHORT 4's protective stop fills
AFTER_THE_STOP = ((5, 2 * HOUR),)  # record 5 published 2 h after its 48 h settlement: D_5 decides after the stop


def decided(k: int) -> int:
    return lifet.decision_instant(k)


@functools.cache
def derived(path: lifet.Path, end: int = END_2D, published: tuple = (), refused: tuple = ()):  # noqa: ANN201
    """One world's managed economics and the ladder derived from it under the SYNTHETIC two-sided schedule refusing
    ``refused``: the ladder, the decision portfolio and the governed outcome of ONE engine re-run."""

    world = lifet.variant_world(path, end=end, published=published) if published else lifet.world(path, end=end)
    result = lifet.computed(lifet.managed(world))
    derivation = derive_governed_paper_kill_switch_ladder(
        policy=lifet.economics_policy(),
        dataset=world.dataset,
        economics=result,
        schedule=lifet.both_sides(end=end, refused=refused),
        single_instrument_portfolio=True,
    )
    assert derivation.outcome.simulated is True, derivation.outcome.reason_codes
    return world, result, derivation


def governed_world(path: lifet.Path, end: int = END_2D, published: tuple = (), refused: tuple = ()):  # noqa: ANN201
    world, result, derivation = derived(path, end, published, refused)
    return world, result, derivation.portfolio, derivation.outcome


def ladder_of(path: lifet.Path, end: int = END_2D, published: tuple = (), refused: tuple = ()):  # noqa: ANN201
    return derived(path, end, published, refused)[2].ladder


@functools.cache
def engine_derivation(path: lifet.Path, end: int = END_2D, published: tuple = ()):  # noqa: ANN201
    """The engine's own derivation of the same re-run: its exact values and the phases of its closes."""

    _, result, _ = derived(path, end, published)
    return simulate_historical_execution_governed_paper_derivation(
        result, expected_result_digest=result.result_digest, schedule=lifet.both_sides(end=end)
    )


def exact_at(derivation: object, at: int) -> HistoricalExecutionDecisionExactValues:
    (sequence,) = [item.decision_sequence for item in derivation.portfolio.snapshots if item.decision_time_ns == at]  # type: ignore[attr-defined]
    (values,) = [item for item in derivation.exact_values if item.decision_sequence == sequence]  # type: ignore[attr-defined]
    return values


def span(item: object) -> tuple:
    end = None if item.end_ns is None else (item.end_ns, item.end_phase)  # type: ignore[attr-defined]
    return (item.start_ns, item.start_phase), end, item.observed  # type: ignore[attr-defined]


def readings_of(ladder: object, trigger: str) -> list[tuple]:
    return [span(item) for item in ladder.readings if item.trigger_id == trigger]  # type: ignore[attr-defined]


def test_a_crash_at_a_decision_proves_t1_t2_t11_ks3_absorbs_and_the_protective_stop_still_closes() -> None:
    _, _, portfolio, outcome = governed_world(CRASH)
    ladder = ladder_of(CRASH)
    policy = lifet.economics_policy()
    at = decided(1)
    snapshot = lifet.snapshot_at(portfolio, at)
    values = exact_at(engine_derivation(CRASH), at)
    drop = (values.nav - 10_000) / 10_000  # type: ignore[operator]
    assert Fraction(-17, 100) < drop < Fraction(-15, 100) and values.day_start_nav == 10_000
    assert (snapshot.nav, snapshot.day_start_nav) == (render(values.nav), lifet.d(10_000))  # type: ignore[arg-type]
    for name in ("T1", "T2", "T11"):
        assert readings_of(ladder, name)[0] == ((at, D), (at, X), ratio(drop))
    by_name = {item.trigger_id: item for item in ladder.readings if item.start_ns == at}
    assert by_name["T1"].evidence_digests == (snapshot.snapshot_digest,)
    assert by_name["T2"].evidence_digests == (snapshot.snapshot_digest, policy.policy_digest)  # the peak: G's equity
    assert changes(ladder.transitions) == [(at, D, 0, 3, ("T1", "T2", "T11"))]
    assert governed_paper_kill_switch_level_at(ladder, at - 1, phase=D) == (0, None)
    assert governed_paper_kill_switch_level_at(ladder, at, phase=P) == (0, None)  # before its decision phase
    assert governed_paper_kill_switch_level_at(ladder, END_2D - 1, phase=D) == (3, ladder.transitions[0])
    # the drawdown persists after the stop realized it: T2 and T11 again at D_2 (a new UTC day: no intraday T1)
    assert [entry[0][0] for entry in readings_of(ladder, "T11")] == [decided(k) for k in (1, 2, 3, 4)]
    assert [entry[0][0] for entry in readings_of(ladder, "T1")] == [at]
    # the open SHORT's protective close-only stop fills 21 s after the proven KS-3: the ladder never touches an exit
    (close,) = lifet.protective_fills(outcome)
    assert close.outcome is HistoricalExecutionFillOutcome.FILLED and close.execution_time_ns > at
    assert governed_paper_kill_switch_proven_at(ladder, at, phase=D) == ("T1", "T2", "T11")
    assert governed_paper_kill_switch_proven_at(ladder, at, phase=X) == ()  # a point reading holds at its decision only
    assert governed_paper_kill_switch_unproven_at(ladder, at, phase=D) == (
        "T3",
        "T5",
        "T6",
        "T7",
        "T8",
        "T9",
        "T10",
        "T12",
        "KS4",
        "DTL",
    )


def test_an_11pct_drop_proves_t1_and_t2_ks2_at_its_decision_only() -> None:
    ladder = ladder_of(DROP)
    at = decided(1)
    assert readings_of(ladder, "T11") == []  # -11% is not beyond -15%
    assert [entry[0][0] for entry in readings_of(ladder, "T1")] == [at]
    assert [entry[0][0] for entry in readings_of(ladder, "T2")] == [decided(k) for k in (1, 2, 3, 4)]
    assert changes(ladder.transitions)[:5] == [
        (at, D, 0, 2, ("T1", "T2")),
        (at, X, 2, 0, ()),
        (decided(2), D, 0, 1, ("T2",)),
        (decided(2), X, 1, 0, ()),
        (decided(3), D, 0, 1, ("T2",)),
    ]
    # at the next decision the realized drawdown still proves T2, so the bound is KS-1 there; KS-2 is never carried over
    level, setting = governed_paper_kill_switch_level_at(ladder, decided(2), phase=D)
    assert (level, setting.proven_trigger_ids) == (1, ("T2",))  # type: ignore[union-attr]
    assert governed_paper_entry_safety_kill_switch_facts(ladder, decided(2)).proving_trigger_ids == ("T2",)
    assert governed_paper_entry_safety_kill_switch_facts(ladder, at).proving_trigger_ids == ("T1", "T2")


def test_five_stopped_out_shorts_prove_t5_from_the_fifth_close_until_the_next_and_with_t6_ks2() -> None:
    _, _, _, outcome = governed_world(STAIRS_SPIKE, END_3D)
    ladder = ladder_of(STAIRS_SPIKE, END_3D)
    closes = [item.end_time_ns for item in outcome.trades]
    assert len(closes) == 8 and all(
        Fraction(item.realized_gross_pnl) < 0 and Fraction(item.realized_net_pnl) < 0 for item in outcome.trades
    )
    assert closes[4] == lifet.book_visible(32 * 5 + 4)  # the fifth stop-out close
    assert engine_derivation(STAIRS_SPIKE, END_3D).trade_close_phases == (X,) * 8  # every close is a fill
    assert readings_of(ladder, "T5") == [
        ((closes[4], X), (closes[5], X), "5"),
        ((closes[5], X), (closes[6], X), "5"),
        ((closes[6], X), (closes[7], X), "5"),
        ((closes[7], X), None, "5"),
    ]
    (first,) = [item for item in ladder.readings if item.trigger_id == "T5" and item.start_ns == closes[4]]
    trades = {item.trade_digest for item in outcome.trades[:5]}
    assert set(first.evidence_digests) == trades  # no funding settled inside any of these one-hour SHORTs
    assert changes(ladder.transitions) == [(decided(3), F, 0, 1, ("T6",)), (closes[4], X, 1, 2, ("T5", "T6"))]
    assert governed_paper_kill_switch_level_at(ladder, decided(5), phase=D)[0] == 2
    # only four closes before the horizon prove nothing
    assert readings_of(ladder_of(STAIRS_SPIKE, ANCHOR + 40 * HOUR), "T5") == []


def loss_readings(outcome: object, phases: tuple | None = None, **trade_changes: dict[str, str]) -> list[tuple]:
    """T5 over ``outcome`` with the given trades (by index) changed and every close at the FILL phase unless ``phases``
    says otherwise; every funding record visible at its liability."""

    trades = list(outcome.trades)  # type: ignore[attr-defined]
    for index, values in trade_changes.items():
        trades[int(index[1:])] = replace(trades[int(index[1:])], **values)
    closed = sum(1 for item in trades if item.status is CLOSED)
    found = kill_switch._loss_streak_readings(  # noqa: SLF001 - the reader at its exact boundaries
        replace(outcome, trades=tuple(trades)),
        (X,) * closed if phases is None else phases,
        {},
        start_ns=ANCHOR,
        horizon_ns=END_3D,
    )
    return [(item.start_ns, item.end_ns) for item in found]


def test_a_losing_trade_is_strictly_negative_gross_and_net_and_an_unknown_one_breaks_the_streak() -> None:
    _, _, _, outcome = governed_world(STAIRS_SPIKE, END_3D)
    closes = [item.end_time_ns for item in outcome.trades]
    assert loss_readings(outcome) == [
        (closes[4], closes[5]),
        (closes[5], closes[6]),
        (closes[6], closes[7]),
        (closes[7], None),
    ]
    zero, positive = lifet.d(0), lifet.d(Fraction(1, 10**18))
    for values in ({"realized_net_pnl": zero}, {"realized_net_pnl": positive}, {"realized_gross_pnl": zero}):
        assert loss_readings(outcome, t2=values) == [(closes[7], None)], values  # only trades 3-7 remain five in a row
    # a trade that settled funding whose record is not visible is not known losing: it breaks every window it is in
    unknown = {"funding_cashflow_digests": ("0" * 64,)}
    assert loss_readings(outcome, t2=unknown) == [(closes[7], None)]
    # without exactly one known engine phase per close, in the engine's close order, nothing is proven
    assert loss_readings(outcome, (X,) * 7) == []
    assert loss_readings(outcome, (X,) * 7 + ("LUNCH",)) == []
    assert loss_readings(outcome, t3={"end_time_ns": closes[1]}) == []  # closes out of order


def funding_readings(rates: list[tuple[int, str | None, int | None]], interval: int = lifet.FUNDING):  # noqa: ANN201
    """T6 over SYNTHETIC final rates ``(event, rate, visibility)`` at their exact boundaries; each reading starts and
    ends at the first phase of its instant (a publication)."""

    found = kill_switch._funding_spike_readings(  # noqa: SLF001
        [
            kill_switch._Rate(event, None if rate is None else Fraction(rate), visible, f"{index:064x}")  # noqa: SLF001
            for index, (event, rate, visible) in enumerate(rates)
        ],
        interval_ns=interval,
        start_ns=ANCHOR,
        horizon_ns=END_3D,
    )
    assert all(item.start_phase == F and item.end_phase in (F, None) for item in found)
    return [(item.start_ns, item.end_ns, item.observed) for item in found]


def grid(
    rates: tuple[str | None, ...], delays: dict[int, int] | None = None
) -> list[tuple[int, str | None, int | None]]:
    delays = delays or {}
    return [
        (ANCHOR + k * lifet.FUNDING, rate, ANCHOR + (k + 1) * lifet.FUNDING + delays.get(k, 10 * SECOND))
        for k, rate in enumerate(rates)
    ]


def test_t6_needs_four_consecutive_visible_rates_strictly_beyond_0_1pct_on_an_8h_grid() -> None:
    ladder = ladder_of(SPIKES)
    world = governed_world(SPIKES)[0]
    records = sorted(
        (item for item in world.dataset.records if item.series_id == "funding-final"), key=lambda item: item.sequence_id
    )
    assert readings_of(ladder, "T6") == [((decided(3), F), (decided(4), F), SPIKE)]
    (reading,) = [item for item in ladder.readings if item.trigger_id == "T6"]
    assert reading.evidence_digests == tuple(item.record_digest for item in records[:4])
    assert changes(ladder.transitions) == [(decided(3), F, 0, 1, ("T6",)), (decided(4), F, 1, 0, ())]
    beyond, at_threshold = "0.001000000000000001", "0.001000000000000000"
    assert funding_readings(grid((beyond,) * 4)) == [(decided(3), None, beyond)]
    assert funding_readings(grid((at_threshold,) * 6)) == []  # equality is not beyond
    assert funding_readings(grid(("-" + SPIKE,) * 4)) == [(decided(3), None, SPIKE)]  # the absolute value
    assert funding_readings(grid((SPIKE,) * 3 + (POSITIVE,) + (SPIKE,) * 3)) == []  # never four in a row
    assert funding_readings(grid((SPIKE, None, SPIKE, SPIKE, SPIKE))) == []  # an unreadable rate proves nothing
    off_grid = grid((SPIKE,) * 4)
    off_grid[2] = (off_grid[2][0] + 1, SPIKE, off_grid[2][2])
    assert funding_readings(off_grid) == []  # not consecutive on the exact grid
    assert funding_readings(grid((SPIKE,) * 4), interval=lifet.FUNDING + 1) == []


def test_a_late_publication_delays_t6_and_a_record_unknown_by_the_horizon_is_never_read() -> None:
    late = ANCHOR + 4 * lifet.FUNDING + 2 * HOUR  # record 3 published 2 h after its 32 h settlement
    assert readings_of(ladder_of(SPIKES, published=((3, 2 * HOUR),)), "T6") == [((late, F), (decided(4), F), SPIKE)]
    assert readings_of(ladder_of(SPIKES, published=((3, lifet.DAY),)), "T6") == []  # visible only at 56 h
    # out-of-order publication: the latest visible rate needs every one of the three before it visible too
    # (record 2 of the 16 h window is published at 33 h, after record 3 at 32 h 10 s: nothing is proven before 33 h)
    assert funding_readings(grid((SPIKE,) * 5, {2: 9 * HOUR})) == [
        (ANCHOR + 33 * HOUR, decided(4), SPIKE),
        (decided(4), None, SPIKE),
    ]


@functools.cache
def synthetic_policy(**changes: object):  # noqa: ANN201
    """A SYNTHETIC economics policy differing from the lifecycle worlds' only by ``changes``."""

    values: dict[str, object] = {
        "latency_ns": 100_000_000,
        "max_execution_delay_ns": 5 * MINUTE,
        "max_mark_staleness_ns": HOUR,
        "funding_interval_ns": lifet.FUNDING,
    }
    values.update(changes)
    return lifet.polt.cited_policy(**values)


@functools.cache
def derived_under(path: lifet.Path, **changes: object):  # noqa: ANN201
    """``path`` under ``synthetic_policy(**changes)``: the kill-switch derivation and the engine's own."""

    world = lifet.world(path, end=END_2D)
    policy = synthetic_policy(**changes)
    result = lifet.computed(
        build_historical_execution_economics(
            world.run,
            expected_run_digest=world.run.run_digest,
            economics_policy=policy,
            expected_economics_policy_digest=policy.policy_digest,
            economics_approval=lifet.econ.approval(world, policy),
            result_id="result-policy-variant",
            correlation_id="corr-1",
            position_management=lifet.pm_inputs(world),
        )
    )
    schedule = lifet.both_sides()
    ladder = derive_governed_paper_kill_switch_ladder(
        policy=policy, dataset=world.dataset, economics=result, schedule=schedule, single_instrument_portfolio=True
    ).ladder
    return ladder, simulate_historical_execution_governed_paper_derivation(
        result, expected_result_digest=result.result_digest, schedule=schedule
    )


def test_a_governed_latency_strictly_above_10x_the_t1_budget_proves_t7_strictly_after_60s() -> None:
    assert readings_of(derived_under(lifet.FLAT_PATH, latency_ns=1_000_000_000)[0], "T7") == []  # 10 x 100 ms exactly
    beyond = derived_under(lifet.FLAT_PATH, latency_ns=1_000_000_001)[0]
    assert readings_of(beyond, "T7") == [((ANCHOR + 60 * SECOND + 1, F), None, "1000000001")]
    assert changes(beyond.transitions) == [(ANCHOR + 60 * SECOND + 1, F, 0, 1, ("T7",))]


def drawdown_readings(
    *rows: tuple[int, Fraction | None, Fraction | None],
    initial: Fraction = Fraction(10_000),
    exact: tuple | None = None,
) -> list[tuple[str, int, str]]:
    """T1, T2 and T11 over SYNTHETIC snapshots ``(instant, nav, day_start_nav)`` of EXACT values, each snapshot carrying
    their half-even scale-18 renderings as the engine does; ``exact`` replaces the exact values the reader is given."""

    template = governed_world(CRASH)[2].snapshots[0]
    snapshots = tuple(
        replace(
            template,
            decision_sequence=index,
            decision_time_ns=at,
            nav=None if nav is None else render(nav),
            day_start_nav=None if start is None else render(start),
            snapshot_digest=f"{index:064x}",
        )
        for index, (at, nav, start) in enumerate(rows)
    )
    values = (
        tuple(HistoricalExecutionDecisionExactValues(index, nav, start) for index, (_, nav, start) in enumerate(rows))
        if exact is None
        else exact
    )
    found = kill_switch._drawdown_readings(  # noqa: SLF001
        snapshots, values, initial_equity=initial, initial_digest="f" * 64, start_ns=ANCHOR, horizon_ns=END_2D
    )
    return [(item.trigger_id, item.start_ns, item.observed) for item in found]


def names(*rows: tuple[int, Fraction | None, Fraction | None], **options: object) -> list[str]:
    return [name for name, *_ in drawdown_readings(*rows, **options)]  # type: ignore[arg-type]


def test_each_drawdown_threshold_is_strict_at_its_exact_boundary_and_needs_its_inputs() -> None:
    tiny = Fraction(1, 10**30)  # far below the scale-18 rendering: only an exact comparison sees it
    at = ANCHOR + HOUR
    assert names((at, Fraction(9_500), Fraction(10_000))) == []  # intraday exactly -5%
    assert names((at, 9_500 - tiny, Fraction(10_000))) == ["T1"]
    assert names((at, 9_500 + tiny, Fraction(10_000))) == []
    assert names((at, Fraction(9_000), None)) == []  # exactly -10% from the peak
    assert names((at, 9_000 - tiny, None)) == ["T2"]
    assert names((at, Fraction(8_500), None)) == ["T2"]  # exactly -15%: T2 only
    assert names((at, 8_500 - tiny, None)) == ["T2", "T11"]
    assert names((at, 8_500 + tiny, None)) == ["T2"]
    # the peak rises with the NAV observed; an unavailable NAV, a partial day or a non-positive day start proves nothing
    assert drawdown_readings((at, Fraction(11_000), None), (at + HOUR, Fraction(9_899), None)) == [
        ("T2", at + HOUR, ratio(Fraction(9_899 - 11_000, 11_000)))
    ]
    assert drawdown_readings((at, None, Fraction(10_000)), (at + HOUR, Fraction(8_000), Fraction(0))) == [
        ("T2", at + HOUR, ratio(Fraction(-1, 5))),
        ("T11", at + HOUR, ratio(Fraction(-1, 5))),
    ]


E0, FEE = "10667.233150000000000004", "5.000000000000000060"  # SYNTHETIC: Sol's B3 reproducer policy


def test_a_rounded_nav_never_proves_a_strict_drawdown_threshold() -> None:
    """Sol B3 (P2-ROUNDED-NAV-FALSE-CRITICAL) regression. The pre-repair reader compared the rendered scale-18 snapshot
    NAV: under Sol's policy the D_1 NAV is exactly 9067.14817750000000000340033, just above -15% of the initial equity,
    but renders 9067.148177500000000003, below it, so T11 proved an absorbing KS-3 at D_1."""

    initial = Fraction(E0)
    threshold = initial * Fraction(85, 100)
    at, unit = ANCHOR + HOUR, Fraction(1, 10**18)
    # two exact NAVs one text apart from nothing: the same rendering on either side of -15%, and equality
    above, below = threshold + Fraction(1, 10**22), threshold - Fraction(1, 10**22)
    assert render(above) == render(below) and Fraction(render(above)) < threshold  # type: ignore[arg-type]
    assert names((at, above, None), initial=initial) == ["T2"]
    assert names((at, below, None), initial=initial) == ["T2", "T11"]
    assert names((at, threshold, None), initial=initial) == ["T2"]
    # a rendered amount is never promoted to proof: without its exact engine value, nothing is proven there
    for exact in (
        (),  # no exact value
        (HistoricalExecutionDecisionExactValues(7, below, None),),  # another decision's
        (HistoricalExecutionDecisionExactValues(0, below + unit, None),),  # not the value the snapshot renders
        (HistoricalExecutionDecisionExactValues(0, render(below), None),),  # rendered text instead of a value
    ):
        assert names((at, below, None), initial=initial, exact=exact) == [], exact
    # Sol's reproducer on the engine: D_1 proves T1 and T2 only (KS-2), never T11
    ladder, derivation = derived_under(CRASH, initial_equity=E0, taker_fee_bps=FEE)
    values = exact_at(derivation, decided(1))
    snapshot = lifet.snapshot_at(derivation.portfolio, decided(1))
    assert values.nav == Fraction(906714817750000000000340033, 10**23)
    assert snapshot.nav == "9067.148177500000000003" and Fraction(snapshot.nav) < threshold < values.nav
    assert governed_paper_kill_switch_proven_at(ladder, decided(1), phase=D) == ("T1", "T2")
    assert changes(ladder.transitions)[:2] == [(decided(1), D, 0, 2, ("T1", "T2")), (decided(1), X, 2, 0, ())]
    # after the stop realized it at the ask with its slippage and fee, the D_2 drawdown is beyond -15% on exact values:
    # T11 is genuine there, and only there does KS-3 begin
    later = exact_at(derivation, decided(2)).nav
    assert (later - initial) / initial < Fraction(-15, 100)  # type: ignore[operator]
    assert changes(ladder.transitions)[2] == (decided(2), D, 0, 3, ("T2", "T11"))
    assert readings_of(ladder, "T11")[0] == ((decided(2), D), (decided(2), X), ratio((later - initial) / initial))  # type: ignore[operator]
    # one scale-18 unit of mark higher, the exact D_1 NAV is below -15%: T11 is genuine at D_1
    higher = lifet.Path(rates=(POSITIVE,) * 6, mark=lifet.jump(64, 1700 + unit))
    proven = governed_paper_kill_switch_proven_at(
        derived_under(higher, initial_equity=E0, taker_fee_bps=FEE)[0], decided(1), phase=D
    )
    assert proven == ("T1", "T2", "T11")


def test_a_decision_never_reads_a_fill_of_its_own_instant_and_triggers_overlap_only_in_one_phase() -> None:
    """Sol B4 (P2-SAME-INSTANT-PHASE-CONFLATION) regression. D_5 decides at 48 h 31 s, the instant SHORT 4's protective
    stop fills and closes the fifth loss: the decision proves T1 and T6, the fill T5 and T6. The pre-repair ladder read
    T1, T5 and T6 at one timestamp and proved an absorbing KS-3 there, carried to D_6 and D_7."""

    world, _, _, outcome = governed_world(SAME_INSTANT, END_3D, AT_THE_STOP)
    ladder = ladder_of(SAME_INSTANT, END_3D, AT_THE_STOP)
    instants = [item.decision_time_ns for item in world.run.decisions]
    at = ANCHOR + 6 * lifet.FUNDING + 31 * SECOND
    assert instants[5] == at == lifet.book_visible(192)
    closes = [item.end_time_ns for item in outcome.trades if item.status is CLOSED]
    assert closes[4] == at == [item.execution_time_ns for item in lifet.protective_fills(outcome)][4]
    assert engine_derivation(SAME_INSTANT, END_3D, AT_THE_STOP).trade_close_phases == (X,) * 5
    # the decision's snapshot precedes the fill: T1 at the decision phase alone, T5 from the fill phase on
    assert readings_of(ladder, "T5") == [((at, X), None, "5")]
    assert readings_of(ladder, "T1")[0][:2] == ((at, D), (at, X))
    assert governed_paper_kill_switch_proven_at(ladder, at, phase=D) == ("T1", "T6")
    assert governed_paper_kill_switch_proven_at(ladder, at, phase=X) == ("T5", "T6")
    assert changes(ladder.transitions) == [
        (decided(3), F, 0, 1, ("T6",)),
        (at, D, 1, 2, ("T1", "T6")),
        (instants[6], F, 2, 1, ("T5",)),
        (instants[6], D, 1, 2, ("T1", "T5")),
        (instants[6], X, 2, 1, ("T5",)),
        (instants[7], D, 1, 2, ("T1", "T5")),
        (instants[7], X, 2, 1, ("T5",)),
    ]
    # no false KS-3 at the decision or at the next ones: NT-R01 names each decision's own proven triggers
    for index, proving in ((5, ("T1", "T6")), (6, ("T1", "T5")), (7, ("T1", "T5"))):
        facts = governed_paper_entry_safety_kill_switch_facts(ladder, instants[index])
        assert (facts.level, facts.proving_trigger_ids) == (2, proving), index
    # published 2 h after its settlement, record 5 makes D_5 decide after the stop: the closed fifth loss is known from
    # the publication of its funding, never from the close alone, and with T1 and T6 in that one decision phase it
    # proves a genuine KS-3, absorbing from there
    late_world = governed_world(SAME_INSTANT, END_3D, AFTER_THE_STOP)[0]
    late = ladder_of(SAME_INSTANT, END_3D, AFTER_THE_STOP)
    late_instants = [item.decision_time_ns for item in late_world.run.decisions]
    published = ANCHOR + 6 * lifet.FUNDING + 2 * HOUR
    assert late_instants[5] == published
    assert readings_of(late, "T5") == [((published, F), None, "5")]
    assert changes(late.transitions) == [
        (decided(3), F, 0, 1, ("T6",)),
        (published, F, 1, 2, ("T5", "T6")),
        (published, D, 2, 3, ("T1", "T5", "T6")),
    ]
    for index in (5, 6, 7):
        facts = governed_paper_entry_safety_kill_switch_facts(late, late_instants[index])
        assert (facts.level, facts.proving_trigger_ids) == (3, ("T1", "T5", "T6")), index


def test_a_shorter_evaluation_is_exactly_the_prefix_of_a_longer_one() -> None:
    short, long = ladder_of(STAIRS_SPIKE, END_2D), ladder_of(STAIRS_SPIKE, END_3D)
    assert short.economics_result_digest != long.economics_result_digest  # two runs, two run-derived identities
    for instant in (decided(2), decided(3), END_2D):
        assert governed_paper_kill_switch_prefix_digest(
            short, before_ns=instant
        ) == governed_paper_kill_switch_prefix_digest(long, before_ns=instant)
    assert governed_paper_kill_switch_prefix_digest(long, before_ns=END_2D) != governed_paper_kill_switch_prefix_digest(
        long, before_ns=END_3D
    )
    empty = edge_sha256_text(
        edge_canonical_json(
            {
                "rule_digest": GOVERNED_PAPER_KILL_SWITCH_RULE_DIGEST,
                "start_ns": ANCHOR,
                "readings": [],
                "transitions": [],
            }
        )
    )
    assert governed_paper_kill_switch_prefix_digest(long, before_ns=ANCHOR) == empty


# --- C. rule set v5: NT-R01 and NT-T02 ----------------------------------------------------------------------------------

LADDER, TRANSITION = "6" * 64, "5" * 64
ALL_UNPROVEN = ("T1", "T2", "T3", "T5", "T6", "T7", "T8", "T9", "T10", "T11", "T12", "KS4", "DTL")


def ks(level: int = 0, **changes: object) -> GovernedPaperEntrySafetyKillSwitch:
    values: dict[str, object] = {
        "level": level,
        "proving_trigger_ids": ("T1", "T2") if level >= 2 else ("T1",) if level == 1 else (),
        "unproven_trigger_ids": ALL_UNPROVEN,
        "unmeasured_trigger_ids": ALWAYS_UNMEASURED,
        "ladder_digest": LADDER,
        "transition_digest": TRANSITION if level else None,
    }
    values.update(changes)
    return GovernedPaperEntrySafetyKillSwitch(**values)  # type: ignore[arg-type]


def test_rule_set_v5_adds_only_its_kill_switch_rule_and_v1_to_v4_keep_their_accepted_identities() -> None:
    assert (
        GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_PORTFOLIO_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_MARKET_DATA_RULE_SET_DIGEST,
    ) == (
        est.ACCEPTED_MAIN_RULE_SET_V1_DIGEST,
        est.ACCEPTED_MAIN_RULE_SET_V2_DIGEST,
        est.RULE_SET_V3_DIGEST,
        est.RULE_SET_V4_DIGEST,
    )
    v5, v4 = GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET, GOVERNED_PAPER_ENTRY_SAFETY_MARKET_DATA_RULE_SET
    added = ("rule_set_id", "contract_id", "kill_switch_rule")
    assert {key: value for key, value in v5.items() if key not in added} == {
        key: value for key, value in v4.items() if key not in added
    }
    assert (v5["rule_set_id"], v5["contract_id"]) == (
        GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET_ID,
        "S1_KILL_SWITCH_PROVEN_ESCALATION_CLOSURE_V1",
    )
    assert v5["kill_switch_rule"]["ladder_rule_digest"] == GOVERNED_PAPER_KILL_SWITCH_RULE_DIGEST  # type: ignore[index]
    assert GOVERNED_PAPER_KILL_SWITCH_RULE_DIGEST == edge_sha256_text(
        edge_canonical_json(GOVERNED_PAPER_KILL_SWITCH_RULE)
    )
    assert (
        GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET_DIGEST
        == edge_sha256_text(edge_canonical_json(v5))
        == governed_paper_entry_safety_rule_set_digest(
            protective=True, portfolio=True, market_data=True, kill_switch=True
        )
    )
    with pytest.raises(GovernedPaperEntrySafetyError, match="kill_switch_rule_set_needs_the_market_data_rule_set$"):
        governed_paper_entry_safety_rule_set(protective=True, portfolio=True, kill_switch=True)
    # the ladder rule names every §1.19 trigger once, PRDV4's thresholds and the unmeasured ones with their reasons, and
    # how it counts, orders and compares: distinct triggers, engine phases, exact values, a derivation never accepted
    rule = GOVERNED_PAPER_KILL_SWITCH_RULE
    assert [item["trigger_id"] for item in rule["triggers"]] == list(GOVERNED_PAPER_KILL_SWITCH_TRIGGER_IDS)  # type: ignore[union-attr, index]
    assert rule["thresholds"]["T11"] == lifet.d(Fraction(-15, 100))  # type: ignore[index]
    assert rule["cooldown"] == "never_claimed_nor_denied" and rule["persistence"].startswith("none_below_ks3")  # type: ignore[union-attr]
    assert sorted(rule["unmeasured"]) == sorted(ALWAYS_UNMEASURED)  # type: ignore[arg-type]
    assert rule["levels"]["KS-2"] == "any_2_distinct_simultaneous_proven_standard_triggers"  # type: ignore[index]
    assert rule["simultaneity"].startswith("distinct_trigger_identities")  # type: ignore[union-attr]
    assert rule["instants"]["phases"] == list(HISTORICAL_EXECUTION_EQUAL_INSTANT_PHASES)  # type: ignore[index]
    assert rule["exactness"].startswith("every_threshold_compares_exact_engine_values")  # type: ignore[union-attr]
    assert rule["derivation"].endswith("never_accepted")  # type: ignore[union-attr]


def r01_t02(facts: GovernedPaperEntrySafetyKillSwitch | None):  # noqa: ANN201
    decision = evaluate_governed_paper_entry_safety(est.measured(kill_switch=facts))
    return decision, est.check_of(decision, "NT-R01"), est.check_of(decision, "NT-T02")


def test_nt_r01_fails_exactly_on_a_proven_ks2_or_more_names_every_unproven_trigger_and_never_passes() -> None:
    unproven = "t1_t2_t3_t5_t6_t7_t8_t9_t10_t11_t12_ks4_dtl"
    expected = {
        0: (BLOCKED, "0", f"kill_switch_lower_bound_0_unproven_{unproven}", (LADDER,)),
        1: (BLOCKED, "1", f"kill_switch_lower_bound_1_unproven_{unproven}", (LADDER, TRANSITION)),
        2: (S.FAIL, "2", "kill_switch_level_ge_2_proven_by_t1_t2", (LADDER, TRANSITION)),
        3: (S.FAIL, "3", "kill_switch_level_ge_2_proven_by_t1_t2", (LADDER, TRANSITION)),
    }
    for level, (status, observed, reason, evidence) in expected.items():
        decision, r01, t02 = r01_t02(ks(level))
        assert (r01.status, r01.observed, r01.reason, r01.evidence_record_digests) == (
            status,
            observed,
            est.code(f"NT-R01:{reason}"),
            evidence,
        )
        assert (t02.status, t02.observed, t02.evidence_record_digests) == (BLOCKED, "", (LADDER,))
        assert t02.reason == est.code(
            "NT-T02:kill_switch_cooldown_history_unprovable_unmeasured_t3_t8_t9_t10_t12_ks4_dtl"
        )
        # the measured Data family passes: NT-R01 is the first refusal, whatever the bound
        assert (decision.entry_permitted, decision.first_failure_check_id) == (False, "NT-R01")
    # no fact combination passes either check
    for level, proven_now in itertools.product(range(4), ((), ("T6",), ("T1", "T6"))):
        unproven_now = tuple(name for name in ALL_UNPROVEN if name not in proven_now)
        _, r01, t02 = r01_t02(ks(level, unproven_trigger_ids=unproven_now))
        assert r01.status in (S.FAIL, BLOCKED) and t02.status is BLOCKED


def test_without_kill_switch_facts_both_checks_keep_their_accepted_outcomes() -> None:
    _, r01, t02 = r01_t02(None)
    assert (r01.status, r01.observed, r01.reason, r01.evidence_record_digests) == (
        BLOCKED,
        "",
        est.code("NT-R01:kill_switch_ladder_level_not_produced"),
        (),
    )
    assert (t02.status, t02.observed, t02.reason, t02.evidence_record_digests) == (
        BLOCKED,
        "",
        est.code("NT-T02:kill_switch_cooldown_state_not_produced"),
        (),
    )


@pytest.mark.parametrize(
    ("build", "name"),
    [
        (lambda: est.measured(kill_switch=object()), "kill_switch"),
        (lambda: est.portfolio(kill_switch=ks()), "kill_switch_without_the_market_data_facts"),
        (lambda: est.measured(kill_switch=ks(level=True)), "kill_switch_level"),
        (lambda: est.measured(kill_switch=ks(level=4)), "kill_switch_level"),
        (lambda: est.measured(kill_switch=ks(level=-1)), "kill_switch_level"),
        (lambda: est.measured(kill_switch=ks(2, proving_trigger_ids=("T2", "T1"))), "kill_switch_proving_trigger_ids"),
        (lambda: est.measured(kill_switch=ks(2, proving_trigger_ids=("T1", "T1"))), "kill_switch_proving_trigger_ids"),
        (lambda: est.measured(kill_switch=ks(2, proving_trigger_ids=("T13",))), "kill_switch_proving_trigger_ids"),
        (lambda: est.measured(kill_switch=ks(2, proving_trigger_ids=["T1"])), "kill_switch_proving_trigger_ids"),
        (lambda: est.measured(kill_switch=ks(2, proving_trigger_ids=())), "kill_switch_proving_trigger_ids"),
        (lambda: est.measured(kill_switch=ks(1, proving_trigger_ids=())), "kill_switch_proving_trigger_ids"),
        (lambda: est.measured(kill_switch=ks(0, proving_trigger_ids=("T1",))), "kill_switch_proving_trigger_ids"),
        (lambda: est.measured(kill_switch=ks(1, transition_digest=None)), "kill_switch_transition"),
        (lambda: est.measured(kill_switch=ks(0, transition_digest=TRANSITION)), "kill_switch_transition"),
        (lambda: est.measured(kill_switch=ks(1, transition_digest="zz")), "kill_switch_transition"),
        (lambda: est.measured(kill_switch=ks(ladder_digest="x")), "kill_switch_ladder_digest"),
        (lambda: est.measured(kill_switch=ks(unproven_trigger_ids=("T1",))), "kill_switch_unmeasured_trigger_ids"),
        (lambda: est.measured(kill_switch=ks(unproven_trigger_ids=("T2", "T1"))), "kill_switch_unproven_trigger_ids"),
    ],
)
def test_malformed_kill_switch_facts_are_refused(build: object, name: str) -> None:
    with pytest.raises(GovernedPaperEntrySafetyError, match=f"^{est.code(f'observation_malformed:{name}')}$"):
        evaluate_governed_paper_entry_safety(build())  # type: ignore[operator]


# --- D. the sequential admission with the ladder in the loop --------------------------------------------------------------


def proven_level_refusals(refused: tuple[int, ...]) -> tuple[int, ...]:
    """TEST-ONLY READING: the CRASH entries whose NT-R01 FAILs on the ladder of the schedule refusing ``refused``.

    Every other fact of these observations is synthetic, so only the proven level decides here; no rule table is
    replaced. The production NT-R01 also refuses on a BLOCKED (unproven) level, so under it no entry could be admitted.
    """

    world = governed_world(CRASH)[0]
    ladder = ladder_of(CRASH, END_2D, (), refused)
    instants = {item.decision_sequence: item.decision_time_ns for item in world.run.decisions}
    refusing = []
    for sequence in governed_paper_entry_safety_entry_sequences(world.run):
        facts = governed_paper_entry_safety_kill_switch_facts(ladder, instants[sequence])
        _, r01, _ = r01_t02(facts)
        if r01.status is S.FAIL:
            refusing.append(sequence)
    return tuple(refusing)


def test_after_a_proven_ks3_every_entry_is_refused_while_the_protective_stop_still_closes() -> None:
    world = governed_world(CRASH)[0]
    entries = governed_paper_entry_safety_entry_sequences(world.run)
    rounds: list[tuple[int, ...]] = []

    def refusals_under(refused: tuple[int, ...]) -> tuple[int, ...]:
        rounds.append(refused)
        return proven_level_refusals(refused)

    fixed = governed_paper_entry_safety_sequential_refusals(entries, refusals_under)
    assert fixed == entries[1:] and proven_level_refusals(fixed) == fixed  # D_0 precedes any proven level
    assert rounds[0] == entries and len(rounds) <= len(entries) + 1
    _, _, _, outcome = governed_world(CRASH, END_2D, (), fixed)
    (close,) = lifet.protective_fills(outcome)
    assert close.outcome is HistoricalExecutionFillOutcome.FILLED and close.execution_time_ns > decided(1)
    instants = {item.decision_sequence: item.decision_time_ns for item in world.run.decisions}
    entry_fills = {
        instants[intent.decision_sequence]: [fill for fill in outcome.fills if fill.intent_id == intent.intent_id][-1]
        for intent in outcome.intents
    }
    assert entry_fills[decided(0)].outcome is HistoricalExecutionFillOutcome.FILLED
    for later in (decided(2), decided(3), decided(4)):  # flat after the stop: each SHORT is an entry, refused
        assert (entry_fills[later].outcome, entry_fills[later].reason) == (
            HistoricalExecutionFillOutcome.REJECTED,
            "governed_paper_entry_safety_refused",
        )


# --- E. world G's kill-switch lineage (seal v6, evidence v6) on the PRODUCTION table -------------------------------------

V5, V6 = "governed-paper-day-seal.v5", "governed-paper-day-seal.v6"
V6_FIELDS = ("kill_switch_ladder_digest", "kill_switch_prefix_digest_open", "kill_switch_prefix_digest_close")


@functools.cache
def kill_switch_days(count: int) -> tuple:
    """World G's first ``count`` days of the kill-switch lineage (seal v6), on the PRODUCTION table."""

    assert entry_safety._CHECKS is PRODUCTION_CHECKS  # noqa: SLF001
    if count == 0:
        return ()
    days = kill_switch_days(count - 1)
    return (
        *days,
        lineage.protective_day(days, portfolio_no_trade=True, market_data_integrity=True, kill_switch_escalation=True),
    )


def switched(item: object, **changes: object):  # noqa: ANN201
    inputs = item.seal_inputs  # type: ignore[attr-defined]
    return replace(inputs, protection=replace(inputs.protection, **changes))


def verify(seal: object, inputs: object):  # noqa: ANN201
    """The public seal verifier through the module attribute: the exact identity memo the lineage evidence shares."""

    return gpe.execution.verify_governed_paper_day_seal(seal, inputs)


def test_world_g_kill_switch_lineage_changes_only_its_version_rule_set_and_bound_ladder() -> None:
    days, market = kill_switch_days(4), est.market_data_days(4)
    for index, (item, old) in enumerate(zip(days, market, strict=True)):
        seal = item.seal
        assert (seal.schema_version, seal.status, seal.reason_codes) == (V6, GovernedPaperDaySealStatus.SEALED, ())
        assert seal.entry_safety_rule_set_digest == GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET_DIGEST
        for name in ("schedule", "governed_outcome_digest", "episodes", "funding_events", "sealed_history_digest"):
            assert getattr(seal, name) == getattr(old.seal, name), name
        if index:
            assert seal.kill_switch_prefix_digest_open == days[index - 1].seal.kill_switch_prefix_digest_close
        verification = verify(seal, item.seal_inputs)
        assert (verification.intact, verification.reason_codes) == (True, ())
    item = days[3]
    (entry,) = item.seal.entry_safety_decisions
    (old_entry,) = market[3].seal.entry_safety_decisions
    assert (entry.entry_permitted, entry.first_failure_check_id) == (False, "NT-D01")
    unproven = "t1_t2_t3_t5_t6_t7_t8_t9_t10_t11_t12_ks4_dtl"
    r01, t02 = est.check_of(entry, "NT-R01"), est.check_of(entry, "NT-T02")
    assert (r01.status, r01.observed, r01.reason) == (
        BLOCKED,
        "0",
        est.code(f"NT-R01:kill_switch_lower_bound_0_unproven_{unproven}"),
    )
    assert t02.reason == est.code(
        "NT-T02:kill_switch_cooldown_history_unprovable_unmeasured_t3_t6_t8_t9_t10_t12_ks4_dtl"
    )
    assert r01.evidence_record_digests == t02.evidence_record_digests == (item.seal.kill_switch_ladder_digest,)
    assert [check for check in entry.checks if check.check_id not in ("NT-R01", "NT-T02")] == [
        check for check in old_entry.checks if check.check_id not in ("NT-R01", "NT-T02")
    ]
    # the public builder re-derives exactly the sealed rule set v5 evaluation and its ladder
    authority, run, _ = est.run_and_evidence(item)
    economics = lineage.protected_replay(item)[0]
    evidence = build_governed_paper_entry_safety_evidence(
        authority=authority,
        run=run,
        dataset=item.seal_inputs.dataset,
        invalidated_from_ns=None,
        protection=est.seal_protection(item),
        portfolio=GovernedPaperEntrySafetyPortfolio(economics, item.seal.schedule),
        market_data=True,
        kill_switch=True,
    )
    ladder = evidence.kill_switch_ladder
    assert (evidence.rule_set_id, evidence.evidence_digest) == (
        GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET_ID,
        item.seal.entry_safety_evidence_digest,
    )
    assert (
        ladder.ladder_digest == item.seal.kill_switch_ladder_digest == governed_paper_kill_switch_ladder_digest(ladder)
    )
    assert ladder.schedule_digest == historical_execution_admission_schedule_digest(item.seal.schedule)
    assert (ladder.readings, ladder.transitions) == ((), ())  # no position ever opens: nothing is proven
    states = {state.trigger_id: (state.measurement, state.reason) for state in ladder.triggers}
    assert states["T6"] == (
        GovernedPaperKillSwitchMeasurement.UNMEASURED,
        "approved_funding_interval_is_not_8h_and_no_normalization_exists",  # world G's funding cycle is two days
    )
    assert states["T4"][0] is GovernedPaperKillSwitchMeasurement.NOT_APPLICABLE
    assert governed_paper_kill_switch_prefix_digest(ladder, before_ns=item.seal.window_end_ns) == (
        item.seal.kill_switch_prefix_digest_close
    )
    lineage_evidence = lineage.evidence_of(days)
    assert (lineage_evidence.schema_version, lineage_evidence.status) == (
        "governed-paper-execution-evidence.v6",
        GovernedPaperExecutionStatus.READY,
    )
    verification = verify_governed_paper_execution_evidence(lineage_evidence, gpe.evidence_inputs(days))
    assert (verification.intact, verification.reason_codes) == (True, ())
    assert set(V6_FIELDS) <= set(governed_paper_day_seal_to_dict(item.seal))
    assert not set(V6_FIELDS) & set(governed_paper_day_seal_to_dict(market[3].seal))


def test_a_kill_switch_lineage_is_one_from_day_0_or_never_and_only_on_a_market_data_lineage() -> None:
    days, market = kill_switch_days(2), est.market_data_days(2)
    with gpe.refused("kill_switch_escalation_lineage_switched"):
        build_governed_paper_day_seal(switched(days[1], kill_switch_escalation=False))
    with gpe.refused("kill_switch_escalation_lineage_switched"):
        build_governed_paper_day_seal(switched(market[1], kill_switch_escalation=True))
    with gpe.refused("kill_switch_escalation_needs_the_market_data_lineage"):
        build_governed_paper_day_seal(switched(days[0], market_data_integrity=False))
    with gpe.refused("protection_inputs_malformed:kill_switch_escalation"):
        build_governed_paper_day_seal(switched(days[1], kill_switch_escalation=1))
    with gpe.refused("market_data_integrity_lineage_switched"):
        build_governed_paper_day_seal(switched(days[1], market_data_integrity=False, kill_switch_escalation=False))
    # a relabelled version never verifies: a v6 seal labelled v5 cannot even be resealed (its v6 facts never hide behind
    # a v5 payload), and a v5 seal labelled v6 never matches its rebuild, resealed or not
    assert verify(replace(days[1].seal, schema_version=V5), days[1].seal_inputs).intact is False
    with pytest.raises(ValueError, match="legacy_schema_carries_an_extension_field:kill_switch_ladder_digest$"):
        gpe.reseal_seal(days[1].seal, schema_version=V5)
    for forged in (replace(market[1].seal, schema_version=V6), gpe.reseal_seal(market[1].seal, schema_version=V6)):
        assert verify(forged, market[1].seal_inputs).intact is False


def test_a_forged_or_substituted_kill_switch_fact_never_verifies_and_a_rewritten_prefix_is_refused() -> None:
    days = kill_switch_days(4)
    item = days[3]
    seal = item.seal
    (entry,) = seal.entry_safety_decisions
    forged_entry = replace(
        entry,
        checks=tuple(
            replace(check, status=S.FAIL, observed="3") if check.check_id == "NT-R01" else check
            for check in entry.checks
        ),
    )
    for changed in (
        {"kill_switch_ladder_digest": "0" * 64},
        {"kill_switch_prefix_digest_open": "0" * 64},
        {"kill_switch_prefix_digest_close": "0" * 64},
        {"entry_safety_decisions": (forged_entry,)},
        {"entry_safety_rule_set_digest": GOVERNED_PAPER_ENTRY_SAFETY_MARKET_DATA_RULE_SET_DIGEST},
    ):
        for forged in (replace(seal, **changed), gpe.reseal_seal(seal, **changed)):
            assert verify(forged, item.seal_inputs).intact is False
    # a predecessor whose sealed ladder prefix was rewritten (and resealed) is refused: no replay rewrites it
    rewritten = gpe.reseal_seal(days[2].seal, kill_switch_prefix_digest_close="0" * 64)
    with gpe.refused("kill_switch_prefix_rewritten"):
        build_governed_paper_day_seal(replace(item.seal_inputs, prior_seal=rewritten))
    # a v5 seal never carries a v6 fact, not even one that would verify elsewhere
    legacy = est.market_data_days(1)[0].seal
    with pytest.raises(ValueError, match="legacy_schema_carries_an_extension_field:kill_switch_ladder_digest$"):
        governed_paper_day_seal_to_dict(replace(legacy, kill_switch_ladder_digest=seal.kill_switch_ladder_digest))


# --- F. the engine derivation and the ladder's inputs --------------------------------------------------------------------


def test_one_re_run_derives_its_portfolio_outcome_exact_values_and_close_phases_byte_identically() -> None:
    _, result, portfolio, outcome = governed_world(CRASH)
    schedule = lifet.both_sides()
    derivation = engine_derivation(CRASH)
    assert (derivation.portfolio, derivation.outcome) == (portfolio, outcome)
    assert portfolio == simulate_historical_execution_governed_paper_decision_portfolio(
        result, expected_result_digest=result.result_digest, schedule=schedule
    )
    assert outcome == simulate_historical_execution_governed_paper(
        result, expected_result_digest=result.result_digest, schedule=schedule
    )
    assert portfolio.portfolio_digest == historical_execution_governed_paper_decision_portfolio_digest(portfolio)
    assert (
        portfolio.outcome_digest
        == outcome.outcome_digest
        == historical_execution_governed_paper_outcome_digest(outcome)
    )
    # every rendered NAV is the half-even rendering of its exact value, which is None exactly when the rendering is
    for snapshot, values in zip(portfolio.snapshots, derivation.exact_values, strict=True):
        assert values.decision_sequence == snapshot.decision_sequence
        assert snapshot.nav == (None if values.nav is None else render(values.nav))
        assert snapshot.day_start_nav == (None if values.day_start_nav is None else render(values.day_start_nav))
    # one phase per close, in the outcome's order; the phases are the engine's equal-instant classes, by priority
    closed = [item for item in outcome.trades if item.status is CLOSED]
    assert derivation.trade_close_phases == (X,) * len(closed) == (X,)
    assert HISTORICAL_EXECUTION_EQUAL_INSTANT_PHASES == (F, P, D, X, "UTC_DAY_BOUNDARY", "EVALUATION_END")
    priorities = [
        engine._PRIORITY_FUNDING,  # noqa: SLF001
        engine._PRIORITY_PROTECTIVE,  # noqa: SLF001
        engine._PRIORITY_DECISION,  # noqa: SLF001
        engine._PRIORITY_FILL,  # noqa: SLF001
        engine._PRIORITY_DAY_BOUNDARY,  # noqa: SLF001
        engine._PRIORITY_END,  # noqa: SLF001
    ]
    assert priorities == list(range(len(HISTORICAL_EXECUTION_EQUAL_INSTANT_PHASES)))
    assert GOVERNED_PAPER_KILL_SWITCH_DECISION_PHASE == D


sealed = engine._sealed  # noqa: SLF001 - the engine's own record sealing, to build self-consistent forgeries
ledger_digest = engine._ledger_digest  # noqa: SLF001


def forged_portfolio(portfolio: object, nav: str):  # noqa: ANN201
    """A RESEALED forgery: the first snapshot's NAV replaced and every digest recomputed, as Sol's B2 attack built it."""

    first = sealed(replace(portfolio.snapshots[0], nav=nav, snapshot_digest=""), "snapshot_digest")  # type: ignore[attr-defined]
    snapshots = (first, *portfolio.snapshots[1:])  # type: ignore[attr-defined]
    seed = replace(portfolio, snapshots=snapshots, snapshot_ledger_digest=ledger_digest(snapshots), portfolio_digest="")  # type: ignore[type-var]
    return replace(seed, portfolio_digest=historical_execution_governed_paper_decision_portfolio_digest(seed))


def forged_economics(result: object):  # noqa: ANN201
    """A RESEALED forgery with a consistent ledger: the first trade's net PnL replaced, the trade, its ledger and the
    result re-digested."""

    trade = sealed(replace(result.trades[0], realized_net_pnl=lifet.d(1), trade_digest=""), "trade_digest")  # type: ignore[attr-defined]
    trades = (trade, *result.trades[1:])  # type: ignore[attr-defined]
    seed = replace(result, trades=trades, trade_ledger_digest=ledger_digest(trades), result_digest="")  # type: ignore[type-var]
    return replace(seed, result_digest=historical_execution_economics_digest(seed))


def test_the_ladder_is_derived_never_accepted_and_refuses_a_malformed_forged_or_foreign_input() -> None:
    """Sol B2 (P2-RESEALED-PORTFOLIO-AUTHENTICATION) regression. The pre-repair builder accepted a decision portfolio and
    a governed outcome by their self-digests and mutual bindings, so a resealed copy whose first snapshot NAV was forged
    from 10 000 to 8 000 proved T1, T2 and T11 (KS-3), and a nonserializable NAV raised an uncontrolled TypeError. The
    ladder now takes no portfolio or outcome: it derives both, and the exact values it compares, from ONE engine re-run
    of the economics the engine re-proves, under the schedule it is given."""

    world, result, portfolio, outcome = governed_world(CRASH)
    policy, schedule = lifet.economics_policy(), lifet.both_sides()
    base = {
        "policy": policy,
        "dataset": world.dataset,
        "economics": result,
        "schedule": schedule,
        "single_instrument_portfolio": True,
    }
    derivation = derive_governed_paper_kill_switch_ladder(**base)  # type: ignore[arg-type]
    ladder = derivation.ladder
    assert derivation == derive_governed_paper_kill_switch_ladder(**base)  # type: ignore[arg-type]  # deterministic
    assert (derivation.portfolio, derivation.outcome) == (portfolio, outcome)
    assert ladder == ladder_of(CRASH) and ladder.ladder_digest == governed_paper_kill_switch_ladder_digest(ladder)
    assert (
        ladder.economics_result_digest,
        ladder.decision_portfolio_digest,
        ladder.governed_outcome_digest,
        ladder.schedule_digest,
    ) == (
        result.result_digest,
        portfolio.portfolio_digest,
        outcome.outcome_digest,
        historical_execution_admission_schedule_digest(schedule),
    )
    payload = governed_paper_kill_switch_ladder_to_dict(ladder)
    assert [(name, payload[name]) for name, _ in GOVERNED_PAPER_KILL_SWITCH_NON_CLAIM_FLAGS] == list(
        GOVERNED_PAPER_KILL_SWITCH_NON_CLAIM_FLAGS
    )
    # Sol's resealed forgery is self-consistent, but nothing takes it: the ladder reads the engine's own D_0 (NAV 10 000)
    first = portfolio.snapshots[0]
    assert (first.nav, first.day_start_nav) == (lifet.d(10_000), lifet.d(10_000))
    forged = forged_portfolio(portfolio, lifet.d(8_000))
    assert forged.portfolio_digest == historical_execution_governed_paper_decision_portfolio_digest(forged)
    assert forged.portfolio_digest != ladder.decision_portfolio_digest
    assert not {"portfolio", "outcome"} & set(inspect.signature(derive_governed_paper_kill_switch_ladder).parameters)
    assert governed_paper_kill_switch_proven_at(ladder, first.decision_time_ns, phase=D) == ()
    # and its forged rendered NAV alone is no proof: it is not the rendering of the engine's exact value
    assert [
        item.start_ns
        for item in kill_switch._drawdown_readings(  # noqa: SLF001
            forged.snapshots,
            engine_derivation(CRASH).exact_values,
            initial_equity=Fraction(10_000),
            initial_digest=policy.policy_digest,
            start_ns=ANCHOR,
            horizon_ns=END_2D,
        )
    ] == [decided(k) for k in (1, 1, 1, 2, 2, 3, 3, 4, 4)]
    # a malformed, forged or foreign policy or archive: a contract-specific refusal, never an uncontrolled TypeError
    other = governed_world(DROP)[0].dataset
    for changed, reason in (
        ({"policy": object()}, "input_malformed"),
        ({"dataset": object()}, "input_malformed"),
        ({"economics": object()}, "input_malformed"),
        ({"single_instrument_portfolio": 1}, "input_malformed"),
        ({"policy": replace(policy, initial_equity=object())}, "input_malformed"),  # no canonical form
        ({"dataset": replace(world.dataset, records=(object(),))}, "input_malformed"),
        ({"policy": replace(policy, policy_digest="0" * 64)}, "input_digest_mismatch"),
        ({"dataset": replace(world.dataset, dataset_digest="0" * 64)}, "input_digest_mismatch"),
        ({"dataset": other}, "inputs_not_of_one_governed_evaluation"),
        ({"policy": synthetic_policy(latency_ns=1_000_000_000)}, "inputs_not_of_one_governed_evaluation"),
    ):
        with pytest.raises(GovernedPaperKillSwitchError, match=f"^{code(reason)}$"):
            derive_governed_paper_kill_switch_ladder(**{**base, **changed})  # type: ignore[arg-type]
    # the engine re-proves the economics and the schedule itself: a resealed economics with a consistent forged ledger,
    # a forged self-digest, and a malformed, non-information-time or foreign schedule are its own refusals
    for changed, reason in (
        ({"economics": forged_economics(result)}, "governed_paper_baseline_not_authentic"),
        ({"economics": replace(result, result_digest="0" * 64)}, "governed_paper_baseline_not_authentic"),
        ({"schedule": object()}, "admission_schedule_malformed"),
        ({"schedule": lifet.both_sides(version=lifet.V3)}, "decision_portfolio_needs_the_information_time_schedule"),
        ({"schedule": lifet.both_sides(end=END_2D + lifet.DAY)}, "admission_schedule_outside_evaluation_window"),
    ):
        with pytest.raises(HistoricalExecutionEconomicsError, match=f"^{lifet.code(reason)}$"):
            derive_governed_paper_kill_switch_ladder(**{**base, **changed})  # type: ignore[arg-type]
    # another schedule is another re-run, bound by its own digest: never the ladder of this one
    refused = derive_governed_paper_kill_switch_ladder(**{**base, "schedule": lifet.both_sides(refused=(0,))}).ladder  # type: ignore[arg-type]
    assert refused.schedule_digest != ladder.schedule_digest and refused.transitions == ()
    single = {state.trigger_id: state.measurement for state in ladder.triggers}
    multi = derive_governed_paper_kill_switch_ladder(**{**base, "single_instrument_portfolio": False}).ladder  # type: ignore[arg-type]
    assert single["T4"] is GovernedPaperKillSwitchMeasurement.NOT_APPLICABLE
    assert {state.trigger_id: state.measurement for state in multi.triggers}[
        "T4"
    ] is GovernedPaperKillSwitchMeasurement.UNMEASURED
    # the queries read a well-formed ladder at a well-formed instant only
    malformed = replace(ladder, transitions=(replace(ladder.transitions[0], phase="LUNCH"),))
    for query in (
        governed_paper_kill_switch_level_at,
        governed_paper_kill_switch_proven_at,
        governed_paper_kill_switch_unproven_at,
    ):
        for target, instant, phase, reason in (
            (object(), ANCHOR, D, "ladder_malformed"),
            (malformed, ANCHOR, D, "ladder_malformed"),
            (ladder, -1, D, "instant_malformed"),
            (ladder, ANCHOR, "LUNCH", "instant_malformed"),
        ):
            with pytest.raises(GovernedPaperKillSwitchError, match=f"^{code(reason)}$"):
                query(target, instant, phase=phase)  # type: ignore[arg-type]
