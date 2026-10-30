"""Governed paper kill-switch proven escalation tests (S1_KILL_SWITCH_PROVEN_ESCALATION_CLOSURE_V1).

SYNTHETIC TEST VALUES ONLY. Every price, mark, rate, latency, instant and policy here is a synthetic fixture that
exercises structure; none is a production threshold, venue truth, a qualified source or a real human decision. No test
grants or simulates a governed kill-switch recovery approval: none exists in this contract.

The PRODUCTION entry gate stays in force throughout (no rule table is replaced). It proves:

* A. the lower bound: one proven standard trigger is KS-1, two simultaneous KS-2, three or any critical KS-3, at once
  and skipping levels; triggers count only while simultaneous; below KS-3 the bound follows the triggers proven at each
  instant and never claims a de-escalation, because the two readings of §1.19's cool-down (from the clearing, from the
  level's entry) disagree on any persistence after an earlier unproven entry; KS-3 is absorbing and no input exists to
  clear it; and, exhaustively over small histories, the bound of a proven history never exceeds the true level of any
  history that adds triggers, under either reading (two independent oracles), nor that history's own bound;
* B. the native readers on engine-derived SYNTHETIC worlds (the protective lifecycle worlds: 8 h funding, 15 min marks,
  H2 decisions 10 s after each publication): a mark jump that values the open SHORT 16% below the initial equity at a
  decision proves T1, T2 and T11 (KS-3, while its protective stop still closes it) and one 11% below proves T1 and T2
  (KS-2) at that decision only; five stopped-out SHORTs prove T5 until the next close, and with T6 KS-2;
  four consecutive final rates strictly beyond 0.1% on the 8 h grid prove T6 from the fourth publication; a governed
  latency strictly above 1 s proves T7 strictly after 60 s; each threshold is strict at its exact boundary; a late
  publication delays a reading, a record unknown by the horizon is never read, and a shorter evaluation is exactly the
  prefix of a longer one;
* C. rule set v5: it adds only its kill-switch rule to rule set v4 (v1-v4 keep their accepted identities); NT-R01 FAILs
  exactly on a proven KS-2 or more and is BLOCKED otherwise, naming every unproven trigger; NT-T02 stays BLOCKED; no
  PASS branch exists; without kill-switch facts both keep their accepted outcomes; malformed facts are refused;
* D. the sequential admission with the ladder in the loop: under a TEST-ONLY reading in which only a proven level
  refuses, every entry after a proven KS-3 is refused at its decision while the open SHORT's protective close-only stop
  still fills, and the schedule is the unique fixed point;
* E. world G's kill-switch lineage (seal v6, evidence v6): one from day 0 or never and only on a market-data lineage; it
  changes only its version, its rule set and the bound ladder against the v5 lineage; every seal re-verifies and chains
  its ladder prefix; forged or substituted kill-switch facts, a rewritten prefix and relabelled versions never verify;
  and no v2-v5 payload carries a v6 field;
* F. the engine API returns one re-run's decision portfolio and governed outcome byte-identical to their own functions,
  and the ladder refuses a foreign, forged or mismatched input.
"""

from __future__ import annotations

import functools
import inspect
import itertools
from dataclasses import replace
from fractions import Fraction

import pytest

import crypto_core.validation.governed_paper_entry_safety as entry_safety
import crypto_core.validation.governed_paper_kill_switch as kill_switch
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
    GOVERNED_PAPER_KILL_SWITCH_NON_CLAIM_FLAGS,
    GOVERNED_PAPER_KILL_SWITCH_RULE,
    GOVERNED_PAPER_KILL_SWITCH_RULE_DIGEST,
    GOVERNED_PAPER_KILL_SWITCH_TRIGGER_IDS,
    GovernedPaperKillSwitchError,
    GovernedPaperKillSwitchMeasurement,
    build_governed_paper_kill_switch_ladder,
    governed_paper_kill_switch_ladder_digest,
    governed_paper_kill_switch_ladder_to_dict,
    governed_paper_kill_switch_level_at,
    governed_paper_kill_switch_prefix_digest,
    governed_paper_kill_switch_proven_at,
    governed_paper_kill_switch_transitions,
    governed_paper_kill_switch_unproven_at,
)
from crypto_core.validation.historical_execution_economics import (
    HistoricalExecutionFillOutcome,
    build_historical_execution_economics,
    historical_execution_governed_paper_decision_portfolio_digest,
    historical_execution_governed_paper_outcome_digest,
    simulate_historical_execution_governed_paper,
    simulate_historical_execution_governed_paper_decision_portfolio,
    simulate_historical_execution_governed_paper_decision_portfolio_and_outcome,
)

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
SECOND = 1_000_000_000
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE
G0 = 1_800_000_000 * SECOND  # SYNTHETIC lineage start of the pure ladder tests
HORIZON = G0 + 48 * HOUR
ORDER = GOVERNED_PAPER_KILL_SWITCH_TRIGGER_IDS.index
ALWAYS_UNMEASURED = ("T3", "T8", "T9", "T10", "T12", "KS4", "DTL")


@pytest.fixture(autouse=True, scope="module")
def _production_gate_with_exact_memos():
    """Only the exact upstream memos (pure re-proofs): the PRODUCTION rule table stays in force throughout."""

    with pytest.MonkeyPatch.context() as patch:
        gpe.apply_memos(patch)
        assert entry_safety._CHECKS is PRODUCTION_CHECKS  # noqa: SLF001
        yield


def code(text: str) -> str:
    return f"governed_paper_kill_switch:{text}"


# --- A. the lower-bound ladder -------------------------------------------------------------------------------------------


def point(trigger: str, at: int):  # noqa: ANN201
    """A SYNTHETIC proven reading of ``trigger`` at the one instant ``at``."""

    return kill_switch._reading(trigger, at, at + 1, "synthetic", ("f" * 64,))  # noqa: SLF001


def held(trigger: str, start: int, end: int | None):  # noqa: ANN201
    """A SYNTHETIC proven reading of ``trigger`` over ``[start, end)`` (None: still proven at the horizon)."""

    return kill_switch._reading(trigger, start, end, "synthetic", ("e" * 64,))  # noqa: SLF001


def flow_of(*readings: object, start: int = G0, horizon: int = HORIZON) -> tuple:
    return governed_paper_kill_switch_transitions(readings, start_ns=start, horizon_ns=horizon)  # type: ignore[arg-type]


def level_after(transitions: tuple, at: int) -> int:
    level = 0
    for item in transitions:
        if item.time_ns > at:
            break
        level = item.to_level
    return level


def changes(transitions: tuple) -> list[tuple[int, int, int, tuple[str, ...]]]:
    return [(item.time_ns, item.from_level, item.to_level, item.proven_trigger_ids) for item in transitions]


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
        assert changes(flow)[0] == (at, 0, level, proven)  # immediate, skipping levels
        assert (level_after(flow, at - 1), level_after(flow, at)) == (0, level)
        assert flow[0].reading_ids == tuple(sorted({item.reading_id for item in readings}))


def test_triggers_count_only_while_simultaneous_and_readings_are_half_open() -> None:
    at = G0 + HOUR
    # T1 ends exactly where T2 starts: never two at once, and the supported KS-1 never falls in between
    flow = flow_of(held("T1", at, at + HOUR), held("T2", at + HOUR, at + 2 * HOUR))
    assert changes(flow) == [(at, 0, 1, ("T1",)), (at + 2 * HOUR, 1, 0, ())]
    # one nanosecond of overlap proves KS-2 for exactly that nanosecond
    flow = flow_of(held("T1", at, at + HOUR + 1), held("T2", at + HOUR, at + 2 * HOUR))
    assert changes(flow) == [
        (at, 0, 1, ("T1",)),
        (at + HOUR, 1, 2, ("T1", "T2")),
        (at + HOUR + 1, 2, 1, ("T2",)),
        (at + 2 * HOUR, 1, 0, ()),
    ]


def test_below_ks3_the_bound_follows_the_proven_triggers_and_never_claims_a_de_escalation() -> None:
    at = G0 + 2 * HOUR
    # a supported level holds however long it lasts, and the bound falls the instant its proof ends
    flow = flow_of(held("T5", at, at + 20 * HOUR), held("T6", at, at + 20 * HOUR))
    assert changes(flow) == [(at, 0, 2, ("T5", "T6")), (at + 20 * HOUR, 2, 0, ())]
    flow = flow_of(point("T1", at), held("T5", at, at + 10 * HOUR))
    assert changes(flow) == [(at, 0, 2, ("T1", "T5")), (at + 1, 2, 1, ("T5",)), (at + 10 * HOUR, 1, 0, ())]
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
    assert changes(flow) == [(at, 0, 3, ("T11",))]
    assert level_after(flow, HORIZON - 1) == 3
    # the machine and the ladder take no approval, revocation or recovery input of any kind
    assert list(inspect.signature(governed_paper_kill_switch_transitions).parameters) == [
        "readings",
        "start_ns",
        "horizon_ns",
    ]
    assert list(inspect.signature(build_governed_paper_kill_switch_ladder).parameters) == [
        "policy",
        "dataset",
        "economics",
        "portfolio",
        "outcome",
        "single_instrument_portfolio",
    ]


@pytest.mark.parametrize(
    ("readings", "start", "horizon", "reason"),
    [
        ([], G0, HORIZON, "readings_malformed"),
        ((object(),), G0, HORIZON, "reading_malformed"),
        ((point("KS4", G0 + 1),), G0, HORIZON, "reading_malformed"),  # no §1.19 ladder semantics
        ((point("DTL", G0 + 1),), G0, HORIZON, "reading_malformed"),
        ((point("T1", G0 - 1),), G0, HORIZON, "reading_outside_the_evaluation"),
        ((point("T1", HORIZON),), G0, HORIZON, "reading_outside_the_evaluation"),
        ((held("T1", G0 + 5, G0 + 5),), G0, HORIZON, "reading_interval_malformed"),
        ((), HORIZON, HORIZON, "evaluation_window_malformed"),
        ((), True, HORIZON, "evaluation_window_malformed"),
    ],
)
def test_a_malformed_reading_or_window_is_refused(readings: object, start: object, horizon: int, reason: str) -> None:
    with pytest.raises(GovernedPaperKillSwitchError, match=f"^{code(reason)}$"):
        governed_paper_kill_switch_transitions(readings, start_ns=start, horizon_ns=horizon)  # type: ignore[arg-type]


U = 30 * MINUTE  # the grid of the exhaustive check
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
GRID = tuple(G0 + k * U for k in range(40))


def oracle_levels(readings: tuple, grid: tuple[int, ...], *, from_entry: bool) -> list[int]:
    """INDEPENDENT ORACLE: the true level under one reading of §1.19's de-escalation clause, at the grid instants.

    Both readings escalate at once to the level of the simultaneous triggers and keep KS-3 (no approval exists). A level
    falls one step at a time once every trigger has cleared and its cool-down has elapsed, counted from the clearing
    (``from_entry=False``) or from the level's entry (``from_entry=True``); the next step's from that step. Clearing is
    observed at the grid only, which never makes either reading fall earlier.
    """

    level, since, levels = 0, None, []
    for at in grid:
        active = [
            item.trigger_id for item in readings if item.start_ns <= at and (item.end_ns is None or at < item.end_ns)
        ]
        critical = sum(1 for name in active if name in ("T9", "T10", "T11", "T12"))
        standard = len(active) - critical
        target = 3 if critical or standard >= 3 else standard
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


def bound_levels(readings: tuple) -> list[int]:
    flow = flow_of(*readings, horizon=G0 + 40 * U)
    return [level_after(flow, at) for at in GRID]


def test_the_bound_never_exceeds_the_true_level_under_either_reading_and_never_falls_when_a_reading_is_added() -> None:
    """Exhaustive over ten SYNTHETIC readings: for every proven history of at most two and every true history that adds
    at most two more, the bound of the proven one never exceeds the true level under either de-escalation reading, nor
    the bound of the true one (monotonicity), at any grid instant."""

    pairs = 0
    for size in range(3):
        for chosen in itertools.combinations(TEMPLATES, size):
            bound = bound_levels(chosen)
            rest = [item for item in TEMPLATES if item not in chosen]
            for extra in itertools.chain.from_iterable(itertools.combinations(rest, count) for count in range(3)):
                true = (*chosen, *extra)
                for upper in (
                    oracle_levels(true, GRID, from_entry=False),
                    oracle_levels(true, GRID, from_entry=True),
                    bound_levels(true),
                ):
                    assert all(low <= high for low, high in zip(bound, upper, strict=True)), (chosen, extra)
                pairs += 1
    assert pairs == 1 * (1 + 10 + 45) + 10 * (1 + 9 + 36) + 45 * (1 + 8 + 28)


# --- B. the native readers on engine-derived SYNTHETIC worlds ---------------------------------------------------------------

SPIKE = "0.002000000000000000"  # SYNTHETIC: strictly beyond 0.1% per 8 h (§1.19 trigger 6)
POSITIVE = lifet.POSITIVE
ANCHOR, END_2D = lifet.ANCHOR, lifet.END_2D
END_3D = ANCHOR + 3 * lifet.DAY


def stairs(j: int) -> Fraction:
    """SYNTHETIC marks: +4 one hour after each of the first nine opening fills, so every SHORT stops out (distance 3)."""

    return Fraction(100 + 4 * sum(1 for k in range(9) if j >= 32 * (k + 1) + 4))


CRASH = lifet.Path(rates=(POSITIVE,) * 6, mark=lifet.jump(64, 1700))  # the D_0 SHORT valued ~16% of NAV down at D_1
DROP = lifet.Path(rates=(POSITIVE,) * 6, mark=lifet.jump(64, 1200))  # ~11% down at D_1
SPIKES = lifet.Path(rates=(SPIKE,) * 4 + (POSITIVE,) * 2)
STAIRS_SPIKE = lifet.Path(rates=(SPIKE,) * 9, mark=stairs)


def decided(k: int) -> int:
    return lifet.decision_instant(k)


@functools.cache
def governed_world(path: lifet.Path, end: int = END_2D, published: tuple = (), refused: tuple = ()):  # noqa: ANN201
    """One world's managed economics and its ONE re-run under the SYNTHETIC two-sided schedule refusing ``refused``."""

    world = lifet.variant_world(path, end=end, published=published) if published else lifet.world(path, end=end)
    result = lifet.computed(lifet.managed(world))
    portfolio, outcome = simulate_historical_execution_governed_paper_decision_portfolio_and_outcome(
        result, expected_result_digest=result.result_digest, schedule=lifet.both_sides(end=end, refused=refused)
    )
    assert outcome.simulated is True, outcome.reason_codes
    return world, result, portfolio, outcome


@functools.cache
def ladder_of(path: lifet.Path, end: int = END_2D, published: tuple = (), refused: tuple = ()):  # noqa: ANN201
    world, result, portfolio, outcome = governed_world(path, end, published, refused)
    return build_governed_paper_kill_switch_ladder(
        policy=lifet.economics_policy(),
        dataset=world.dataset,
        economics=result,
        portfolio=portfolio,
        outcome=outcome,
        single_instrument_portfolio=True,
    )


def readings_of(ladder: object, trigger: str) -> list[tuple[int, int | None, str]]:
    return [(item.start_ns, item.end_ns, item.observed) for item in ladder.readings if item.trigger_id == trigger]  # type: ignore[attr-defined]


def ratio(value: Fraction) -> str:
    return lifet.d(value)  # type: ignore[no-any-return]


def test_a_crash_at_a_decision_proves_t1_t2_t11_ks3_absorbs_and_the_protective_stop_still_closes() -> None:
    _, _, portfolio, outcome = governed_world(CRASH)
    ladder = ladder_of(CRASH)
    policy = lifet.economics_policy()
    at = decided(1)
    snapshot = lifet.snapshot_at(portfolio, at)
    drop = (Fraction(snapshot.nav) - 10_000) / 10_000  # type: ignore[arg-type]
    assert Fraction(-17, 100) < drop < Fraction(-15, 100) and snapshot.day_start_nav == lifet.d(10_000)
    for name in ("T1", "T2", "T11"):
        assert readings_of(ladder, name)[0] == (at, at + 1, ratio(drop))
    by_name = {item.trigger_id: item for item in ladder.readings if item.start_ns == at}
    assert by_name["T1"].evidence_digests == (snapshot.snapshot_digest,)
    assert by_name["T2"].evidence_digests == (snapshot.snapshot_digest, policy.policy_digest)  # the peak: G's equity
    assert changes(ladder.transitions) == [(at, 0, 3, ("T1", "T2", "T11"))]
    assert governed_paper_kill_switch_level_at(ladder, at - 1) == (0, None)
    assert governed_paper_kill_switch_level_at(ladder, END_2D - 1) == (3, ladder.transitions[0])
    # the drawdown persists after the stop realized it: T2 and T11 again at D_2 (a new UTC day: no intraday T1)
    assert [entry[0] for entry in readings_of(ladder, "T11")] == [decided(k) for k in (1, 2, 3, 4)]
    assert [entry[0] for entry in readings_of(ladder, "T1")] == [at]
    # the open SHORT's protective close-only stop fills 21 s after the proven KS-3: the ladder never touches an exit
    (close,) = lifet.protective_fills(outcome)
    assert close.outcome is HistoricalExecutionFillOutcome.FILLED and close.execution_time_ns > at
    assert governed_paper_kill_switch_proven_at(ladder, at) == ("T1", "T2", "T11")
    assert governed_paper_kill_switch_unproven_at(ladder, at) == (
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
    assert [entry[0] for entry in readings_of(ladder, "T1")] == [at]
    assert [entry[0] for entry in readings_of(ladder, "T2")] == [decided(k) for k in (1, 2, 3, 4)]
    assert changes(ladder.transitions)[:5] == [
        (at, 0, 2, ("T1", "T2")),
        (at + 1, 2, 0, ()),
        (decided(2), 0, 1, ("T2",)),
        (decided(2) + 1, 1, 0, ()),
        (decided(3), 0, 1, ("T2",)),
    ]
    # at the next decision the realized drawdown still proves T2, so the bound is KS-1 there; KS-2 is never carried over
    level, setting = governed_paper_kill_switch_level_at(ladder, decided(2))
    assert (level, setting.proven_trigger_ids) == (1, ("T2",))  # type: ignore[union-attr]
    assert governed_paper_entry_safety_kill_switch_facts(ladder, decided(2)).proving_trigger_ids == ("T2",)
    assert governed_paper_entry_safety_kill_switch_facts(ladder, at).proving_trigger_ids == ("T1", "T2")


def test_five_stopped_out_shorts_prove_t5_until_the_next_close_and_with_t6_ks2() -> None:
    _, _, _, outcome = governed_world(STAIRS_SPIKE, END_3D)
    ladder = ladder_of(STAIRS_SPIKE, END_3D)
    closes = [item.end_time_ns for item in outcome.trades]
    assert len(closes) == 8 and all(
        Fraction(item.realized_gross_pnl) < 0 and Fraction(item.realized_net_pnl) < 0 for item in outcome.trades
    )
    assert closes[4] == lifet.book_visible(32 * 5 + 4)  # the fifth stop-out close
    assert readings_of(ladder, "T5") == [
        (closes[4], closes[5], "5"),
        (closes[5], closes[6], "5"),
        (closes[6], closes[7], "5"),
        (closes[7], None, "5"),
    ]
    (first,) = [item for item in ladder.readings if item.trigger_id == "T5" and item.start_ns == closes[4]]
    trades = {item.trade_digest for item in outcome.trades[:5]}
    assert set(first.evidence_digests) == trades  # no funding settled inside any of these one-hour SHORTs
    assert changes(ladder.transitions) == [(decided(3), 0, 1, ("T6",)), (closes[4], 1, 2, ("T5", "T6"))]
    assert governed_paper_kill_switch_level_at(ladder, decided(5))[0] == 2
    # only four closes before the horizon prove nothing
    assert readings_of(ladder_of(STAIRS_SPIKE, ANCHOR + 40 * HOUR), "T5") == []


def loss_readings(outcome: object, **trade_changes: dict[str, str]) -> list[tuple[int, int | None]]:
    """T5 over ``outcome`` with the given trades (by index) changed; every funding record visible at its liability."""

    trades = list(outcome.trades)  # type: ignore[attr-defined]
    for index, values in trade_changes.items():
        trades[int(index[1:])] = replace(trades[int(index[1:])], **values)
    found = kill_switch._loss_streak_readings(  # noqa: SLF001 - the reader at its exact boundaries
        replace(outcome, trades=tuple(trades)), {}, start_ns=ANCHOR, horizon_ns=END_3D
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


def funding_readings(rates: list[tuple[int, str | None, int | None]], interval: int = lifet.FUNDING):  # noqa: ANN201
    """T6 over SYNTHETIC final rates ``(event, rate, visibility)`` at their exact boundaries."""

    found = kill_switch._funding_spike_readings(  # noqa: SLF001
        [
            kill_switch._Rate(event, None if rate is None else Fraction(rate), visible, f"{index:064x}")  # noqa: SLF001
            for index, (event, rate, visible) in enumerate(rates)
        ],
        interval_ns=interval,
        start_ns=ANCHOR,
        horizon_ns=END_3D,
    )
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
    assert readings_of(ladder, "T6") == [(decided(3), decided(4), SPIKE)]
    (reading,) = [item for item in ladder.readings if item.trigger_id == "T6"]
    assert reading.evidence_digests == tuple(item.record_digest for item in records[:4])
    assert changes(ladder.transitions) == [(decided(3), 0, 1, ("T6",)), (decided(4), 1, 0, ())]
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
    assert readings_of(ladder_of(SPIKES, published=((3, 2 * HOUR),)), "T6") == [(late, decided(4), SPIKE)]
    assert readings_of(ladder_of(SPIKES, published=((3, lifet.DAY),)), "T6") == []  # visible only at 56 h
    # out-of-order publication: the latest visible rate needs every one of the three before it visible too
    # (record 2 of the 16 h window is published at 33 h, after record 3 at 32 h 10 s: nothing is proven before 33 h)
    assert funding_readings(grid((SPIKE,) * 5, {2: 9 * HOUR})) == [
        (ANCHOR + 33 * HOUR, decided(4), SPIKE),
        (decided(4), None, SPIKE),
    ]


@functools.cache
def latency_ladder(latency_ns: int):  # noqa: ANN201
    """FLAT_PATH under a SYNTHETIC economics policy whose only change is the governed latency."""

    world = lifet.world(lifet.FLAT_PATH, end=END_2D)
    policy = lifet.polt.cited_policy(
        latency_ns=latency_ns,
        max_execution_delay_ns=5 * MINUTE,
        max_mark_staleness_ns=HOUR,
        funding_interval_ns=lifet.FUNDING,
    )
    result = lifet.computed(
        build_historical_execution_economics(
            world.run,
            expected_run_digest=world.run.run_digest,
            economics_policy=policy,
            expected_economics_policy_digest=policy.policy_digest,
            economics_approval=lifet.econ.approval(world, policy),
            result_id="result-latency",
            correlation_id="corr-1",
            position_management=lifet.pm_inputs(world),
        )
    )
    portfolio, outcome = simulate_historical_execution_governed_paper_decision_portfolio_and_outcome(
        result, expected_result_digest=result.result_digest, schedule=lifet.both_sides()
    )
    return build_governed_paper_kill_switch_ladder(
        policy=policy,
        dataset=world.dataset,
        economics=result,
        portfolio=portfolio,
        outcome=outcome,
        single_instrument_portfolio=True,
    )


def test_a_governed_latency_strictly_above_10x_the_t1_budget_proves_t7_strictly_after_60s() -> None:
    assert readings_of(latency_ladder(1_000_000_000), "T7") == []  # exactly 10 x 100 ms is not beyond
    beyond = latency_ladder(1_000_000_001)
    assert readings_of(beyond, "T7") == [(ANCHOR + 60 * SECOND + 1, None, "1000000001")]
    assert changes(beyond.transitions) == [(ANCHOR + 60 * SECOND + 1, 0, 1, ("T7",))]


def drawdown_readings(*rows: tuple[int, str | None, str | None]) -> list[tuple[str, int, str]]:
    """T1, T2 and T11 over SYNTHETIC snapshots ``(instant, nav, day_start_nav)`` from an initial equity of 10 000."""

    template = governed_world(CRASH)[2].snapshots[0]
    snapshots = tuple(
        replace(
            template,
            decision_sequence=index,
            decision_time_ns=at,
            nav=nav,
            day_start_nav=start,
            snapshot_digest=f"{index:064x}",
        )
        for index, (at, nav, start) in enumerate(rows)
    )
    found = kill_switch._drawdown_readings(  # noqa: SLF001
        replace(governed_world(CRASH)[2], snapshots=snapshots),
        initial_equity=Fraction(10_000),
        initial_digest="f" * 64,
        start_ns=ANCHOR,
        horizon_ns=END_2D,
    )
    return [(item.trigger_id, item.start_ns, item.observed) for item in found]


def test_each_drawdown_threshold_is_strict_at_its_exact_boundary_and_needs_its_inputs() -> None:
    d, unit = lifet.d, Fraction(1, 10**18)
    at = ANCHOR + HOUR
    assert drawdown_readings((at, d(9_500), d(10_000))) == []  # intraday exactly -5%
    assert [name for name, *_ in drawdown_readings((at, d(9_500 - unit), d(10_000)))] == ["T1"]
    assert [name for name, *_ in drawdown_readings((at, d(9_000), None))] == []  # exactly -10% from the peak
    assert [name for name, *_ in drawdown_readings((at, d(9_000 - unit), None))] == ["T2"]
    assert [name for name, *_ in drawdown_readings((at, d(8_500), None))] == ["T2"]  # exactly -15%: T2 only
    assert [name for name, *_ in drawdown_readings((at, d(8_500 - unit), None))] == ["T2", "T11"]
    # the peak rises with the NAV observed; an unavailable NAV, a partial day or a non-positive day start proves nothing
    assert drawdown_readings((at, d(11_000), None), (at + HOUR, d(9_899), None)) == [
        ("T2", at + HOUR, d(Fraction(9_899 - 11_000, 11_000)))
    ]
    assert drawdown_readings((at, None, d(10_000)), (at + HOUR, d(8_000), d(0))) == [
        ("T2", at + HOUR, d(Fraction(-1, 5))),
        ("T11", at + HOUR, d(Fraction(-1, 5))),
    ]


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
    # the ladder rule names every §1.19 trigger once, PRDV4's thresholds and the unmeasured ones with their reasons
    rule = GOVERNED_PAPER_KILL_SWITCH_RULE
    assert [item["trigger_id"] for item in rule["triggers"]] == list(GOVERNED_PAPER_KILL_SWITCH_TRIGGER_IDS)  # type: ignore[union-attr, index]
    assert rule["thresholds"]["T11"] == lifet.d(Fraction(-15, 100))  # type: ignore[index]
    assert rule["cooldown"] == "never_claimed_nor_denied" and rule["persistence"].startswith("none_below_ks3")  # type: ignore[union-attr]
    assert sorted(rule["unmeasured"]) == sorted(ALWAYS_UNMEASURED)  # type: ignore[arg-type]


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


# --- F. the engine API and the ladder's inputs ---------------------------------------------------------------------------


def test_one_re_run_yields_the_portfolio_and_outcome_of_their_own_functions_byte_identically() -> None:
    _, result, portfolio, outcome = governed_world(CRASH)
    schedule = lifet.both_sides()
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


def test_the_ladder_is_deterministic_binds_its_inputs_and_refuses_a_foreign_forged_or_mismatched_one() -> None:
    world, result, portfolio, outcome = governed_world(CRASH)
    other_world, _, other_portfolio, other_outcome = governed_world(DROP)
    entries = governed_paper_entry_safety_entry_sequences(world.run)
    refused_portfolio = governed_world(CRASH, END_2D, (), entries[:1])[2]
    policy = lifet.economics_policy()
    base = {
        "policy": policy,
        "dataset": world.dataset,
        "economics": result,
        "portfolio": portfolio,
        "outcome": outcome,
        "single_instrument_portfolio": True,
    }
    ladder = build_governed_paper_kill_switch_ladder(**base)  # type: ignore[arg-type]
    assert ladder == ladder_of(CRASH) and ladder.ladder_digest == governed_paper_kill_switch_ladder_digest(ladder)
    assert (ladder.economics_result_digest, ladder.decision_portfolio_digest, ladder.governed_outcome_digest) == (
        result.result_digest,
        portfolio.portfolio_digest,
        outcome.outcome_digest,
    )
    payload = governed_paper_kill_switch_ladder_to_dict(ladder)
    assert [(name, payload[name]) for name, _ in GOVERNED_PAPER_KILL_SWITCH_NON_CLAIM_FLAGS] == list(
        GOVERNED_PAPER_KILL_SWITCH_NON_CLAIM_FLAGS
    )
    for changed, reason in (
        ({"policy": object()}, "input_malformed"),
        ({"single_instrument_portfolio": 1}, "input_malformed"),
        ({"outcome": replace(outcome, outcome_digest="0" * 64)}, "input_digest_mismatch"),
        ({"economics": replace(result, result_digest="0" * 64)}, "input_digest_mismatch"),
        ({"portfolio": replace(portfolio, portfolio_digest="0" * 64)}, "input_digest_mismatch"),
        ({"portfolio": refused_portfolio}, "inputs_not_of_one_governed_re_run"),
        ({"portfolio": other_portfolio, "outcome": other_outcome}, "inputs_not_of_one_governed_re_run"),
        ({"dataset": other_world.dataset}, "inputs_not_of_one_governed_re_run"),
    ):
        with pytest.raises(GovernedPaperKillSwitchError, match=f"^{code(reason)}$"):
            build_governed_paper_kill_switch_ladder(**{**base, **changed})  # type: ignore[arg-type]
    single = {state.trigger_id: state.measurement for state in ladder.triggers}
    multi = build_governed_paper_kill_switch_ladder(**{**base, "single_instrument_portfolio": False})  # type: ignore[arg-type]
    assert single["T4"] is GovernedPaperKillSwitchMeasurement.NOT_APPLICABLE
    assert {state.trigger_id: state.measurement for state in multi.triggers}[
        "T4"
    ] is GovernedPaperKillSwitchMeasurement.UNMEASURED
    for query in (governed_paper_kill_switch_level_at, governed_paper_kill_switch_proven_at):
        with pytest.raises(GovernedPaperKillSwitchError, match=f"^{code('ladder_malformed')}$"):
            query(object(), ANCHOR)  # type: ignore[arg-type]
    with pytest.raises(GovernedPaperKillSwitchError, match=f"^{code('instant_malformed')}$"):
        governed_paper_kill_switch_level_at(ladder, -1)
