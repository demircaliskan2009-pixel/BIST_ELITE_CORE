"""Governed protective lineage tests (PROTECTIVE_POSITION_LIFECYCLE_V1: day seal v3 and lineage evidence v3).

SYNTHETIC TEST VALUES ONLY. Every bar, policy value, instant, revocation and approval here is a synthetic fixture over
the synthetic worlds of ``test_governed_admitted_variant_paper_execution.py``; no ``HUMAN_GOVERNANCE`` record built here
is a real human decision, and nothing here approves DEC-9, grants C1-C9 or proves a venue fact.

ENTRY GATE SUBSTITUTION (SYNTHETIC, TEST-ONLY), as in the lineage tests: the production entry gate refuses every S1
entry of these worlds, so this module exercises the protective mechanics an admitted entry reaches with the rule table
explicitly replaced by the test-only permissive table. ``test_governed_paper_entry_safety.py`` proves rule set v2 under
the production table. Section F (S1_NO_TRADE_NATIVE_MEASUREMENT_CLOSURE_V1: day seal v4 and lineage evidence v4) runs
the permissive table followed by the PRODUCTION NT-R02 and NT-R04 checks, so the measured governed portfolio alone
decides an entry there. The production NT-R03 blocks every prospective entry for want of an approved position-risk
measure, so with it no entry of these worlds could be admitted; the same test module proves rule set v3, NT-R03
included, under the production table.

In world G the carry profile enters SHORT on day 3 (fill at E_3 + 502 ns) and its own exit would come on day 7. Under a
protective authority the 24 h deadline at E_4 + 502 ns issues a close-only attempt; world G's next book is visible at
E_5 + 502 ns, so the attempt is still in flight when day 4 is sealed and fills on day 5, projected through the day-3
cycle that decided the excursion.
"""

from __future__ import annotations

import functools
from dataclasses import replace
from fractions import Fraction

import pytest

from crypto_core.validation.governed_admitted_variant_paper_execution import (
    GovernedPaperDayProtectionInputs,
    GovernedPaperDaySealStatus,
    GovernedPaperExecutionStatus,
    build_governed_paper_day_seal,
    build_governed_paper_execution_evidence,
    governed_paper_day_seal_digest,
    governed_paper_day_seal_to_dict,
    governed_paper_execution_evidence_digest,
    verify_governed_paper_day_seal,
    verify_governed_paper_execution_evidence,
)
from crypto_core.validation.governed_paper_execution_authority import build_governed_paper_cycle_authority
from crypto_core.validation.governed_paper_protective_authority import (
    build_governed_paper_protective_authority,
    governed_paper_protective_context,
)
from crypto_core.validation.historical_execution_economics import (
    HISTORICAL_EXECUTION_INFORMATION_TIME_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    HISTORICAL_EXECUTION_PROTECTIVE_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    HistoricalExecutionFillOutcome,
    HistoricalExecutionPositionManagementInputs,
    HistoricalExecutionProtectiveObligationStatus,
    HistoricalExecutionProtectiveTriggerKind,
    HistoricalExecutionTransitionKind,
    simulate_historical_execution_governed_paper,
)
from crypto_core.validation.historical_ohlc_bar_archive import (
    build_historical_ohlc_bar,
    build_historical_ohlc_bar_archive,
)
from crypto_core.validation.historical_position_management_policy import STOP_ATR_MULTIPLE

try:  # the module objects pytest collects (basename import): the shared synthetic worlds and their exact memos
    import test_governed_admitted_variant_paper_execution as gpe
    import test_governed_paper_protective_authority as prot
    import test_historical_ohlc_bar_archive as ohlct
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_governed_admitted_variant_paper_execution as gpe
    from tests.crypto_core.validation import test_governed_paper_protective_authority as prot
    from tests.crypto_core.validation import test_historical_ohlc_bar_archive as ohlct

SEALED = GovernedPaperDaySealStatus.SEALED
V3 = "governed-paper-day-seal.v3"
DEADLINE = gpe.instant(4) + 502  # the day-3 opening fill (E_3 + 502) plus 24 h
CLOSE = gpe.instant(5) + 502  # world G's next book after the deadline
REVOKED_AT = gpe.instant(4) + 100  # SYNTHETIC: a human revocation before the deadline

# The accepted-main identities of world G (no protection), pinned on main 8a5b7560 under the test-only permissive table:
# this contract leaves every legacy seal, evidence, lineage, economics, outcome and schedule byte-identical.
ACCEPTED_MAIN_WORLD_G = {
    "evidence": "01fea1eb3a6a2c75f8dd58f936e18562c8fd4c87103ecaca36fd28181cddcaae",
    "lineage": "5f66fc9ebf0e9f853d0a81919089e6d7c8725eb65cb43936fe97b0fd0691d184",
    "seals": {
        0: "fc3a75283919ffe7e88977f774d885f4b6b2a812f5224d148466d36d75ceb301",
        3: "d6c7d3f0d9e7e38c390eae1085b7dcc1ba69cd05e99067bb3214c93c1546b7e2",
        4: "79d9a2809d778f42d2221078400aa421c08e264f995ce6404cbc735158a9510d",
        9: "7dd6938ab28b35ee00ae95080103d07a158d0a853b332a6cdb1532b7790312d6",
        31: "997b6a605a6d99adc830c85e8342e43a9ec0657f8aaf0986b8c31ebdd25a4ac7",
    },
    "day9_economics": "9748967de6d4c6b361ce01afd7f295e0d65222a004af0315328c7a70187e52a6",
    "day9_outcome": "68c8c67696168282c9fdc45b79786a1c30e28eec80fd862fe38a19ec185a90ba",
    "day9_schedule": "6a271770260712b156438727c671d63e6d0c9c3cccc5ac5e34e6aaf9cef58e09",
}


@pytest.fixture(autouse=True, scope="module")
def _memoized_permissive_gate():
    with pytest.MonkeyPatch.context() as patch:
        gpe.apply_memos(patch)
        gpe.install_test_only_permissive_entry_gate(patch)
        yield


# --- the protective lineages ---------------------------------------------------------------------------------------------


def protection_for(
    day: int,
    days: tuple,
    *,
    name: str = "G",
    authority: tuple | None = None,
    revocations: tuple = (),
    archive: object | None = None,
    portfolio_no_trade: bool = False,
    market_data_integrity: bool = False,
) -> GovernedPaperDayProtectionInputs:
    """The protective inputs of ``day``: the world's authority, the day's OHLC archive and the open excursion's cycle."""

    prior = days[-1].seal if days else None
    excursion = None
    if prior is not None and prior.open_excursion_deciding_day_index is not None:
        source = days[prior.open_excursion_deciding_day_index]
        excursion = (source.cycle_inputs, source.cycle)
    inputs, record = prot.world_authority(name) if authority is None else authority
    return GovernedPaperDayProtectionInputs(
        authority_inputs=inputs,
        authority=record,
        revocations=revocations,
        ohlc_archive=prot.world_ohlc(day) if archive is None else archive,
        excursion_cycle_inputs=None if excursion is None else excursion[0],
        excursion_cycle=None if excursion is None else excursion[1],
        portfolio_no_trade=portfolio_no_trade,
        market_data_integrity=market_data_integrity,
    )


def protective_day(days: tuple, name: str = "G", **protection: object):  # noqa: ANN201
    """Open, run and seal the day after ``days`` of scenario ``name`` under its protective authority."""

    world = gpe.scenario(name)
    day = len(days)
    prior = days[-1].seal if days else None
    cycle_inputs = gpe.cycle_inputs_for(day, prior, world=world)
    cycle = build_governed_paper_cycle_authority(cycle_inputs)
    seal_inputs = gpe.seal_inputs_for(
        day,
        cycle_inputs,
        cycle,
        prior,
        gpe.pending_of(days),
        world=world,
        protection=protection_for(day, days, name=name, **protection),  # type: ignore[arg-type]
    )
    return gpe.Day(cycle_inputs, cycle, seal_inputs, build_governed_paper_day_seal(seal_inputs))


@functools.cache
def lineage(name: str, count: int, revoked: bool = False) -> tuple:
    """The first ``count`` protective days of ``name``; ``revoked`` adds the day-4 revocation (shared earlier days)."""

    if count == 0:
        return ()
    day = count - 1
    days = lineage(name, day, revoked and day > 4)
    revocations = ()
    if revoked and day == 4:
        revocations = (prot.revocation(prot.world_authority(name)[1], REVOKED_AT),)
    return (*days, protective_day(days, name, revocations=revocations))


def evidence_of(days: tuple, name: str = "G"):  # noqa: ANN201
    return build_governed_paper_execution_evidence(gpe.evidence_inputs(days, gpe.scenario(name)))


def rebuilt(item: object, **changes: object):  # noqa: ANN201
    """The day's seal rebuilt with its protective inputs changed."""

    inputs = item.seal_inputs  # type: ignore[attr-defined]
    return build_governed_paper_day_seal(replace(inputs, protection=replace(inputs.protection, **changes)))


def protective_records(item: object) -> tuple:
    """The day's replay as the seal saw it: its governed outcome's protective ledgers and fills."""

    outcome = protected_replay(item)[1]
    attempts = {entry.attempt_id for entry in outcome.protective_attempts}
    return outcome, [entry for entry in outcome.fills if entry.intent_id in attempts]


def protected_replay(item: object):  # noqa: ANN201
    """The day's replay rebuilt independently through the public engine functions, with its protection."""

    inputs = item.seal_inputs  # type: ignore[attr-defined]
    # through the module attribute: the exact identity memo of ``gpe.apply_memos`` (a pure re-proof of the same objects)
    view = gpe.authority.governed_paper_genesis_authority(inputs.genesis, inputs.genesis_inputs)
    genesis = view.genesis
    context = governed_paper_protective_context(inputs.protection.authority, inputs.protection.authority_inputs)
    run = gpe.execution.build_historical_decision_run(
        inputs.dataset,
        view.executable_binding,
        expected_dataset_digest=inputs.dataset.dataset_digest,
        expected_executable_binding_digest=genesis.executable_binding_digest,
        run_id=f"{inputs.seal_id}-run",
        correlation_id=inputs.correlation_id,
        parameter_assignment=view.parameter_assignment,
        instrument=genesis.instrument,
        evaluation_start_ns=genesis.genesis_start_ns,
        evaluation_end_ns=item.seal.window_end_ns,  # type: ignore[attr-defined]
        parameter_approval=view.parameter_approval,
    )
    archive = inputs.protection.ohlc_archive
    economics = gpe.execution.build_historical_execution_economics(
        run,
        expected_run_digest=run.run_digest,
        economics_policy=view.economics_policy,
        expected_economics_policy_digest=genesis.economics_policy_digest,
        economics_approval=view.economics_approval,
        result_id=f"{inputs.seal_id}-economics",
        correlation_id=inputs.correlation_id,
        position_management=HistoricalExecutionPositionManagementInputs(
            context.position_management_policy,
            context.authority.position_management_policy_digest,
            context.position_management_approval,
            archive,
            archive.archive_digest,
        ),
    )
    return economics, simulate_historical_execution_governed_paper(
        economics,
        expected_result_digest=economics.result_digest,
        schedule=item.seal.schedule,  # type: ignore[attr-defined]
    )


def reseal(seal: object, **changes: object):  # noqa: ANN201
    changed = replace(seal, **changes)  # type: ignore[type-var]
    return replace(changed, seal_digest=governed_paper_day_seal_digest(changed))


# --- A. the protective lineage of world G -----------------------------------------------------------------------------------


def test_the_24h_deadline_closes_the_short_through_a_pending_attempt_projected_on_its_deciding_cycle() -> None:
    days = lineage("G", 7)
    seals = [item.seal for item in days]
    assert all(seal.schema_version == V3 and seal.status is SEALED for seal in seals)
    authority = prot.world_authority()[1]
    assert {seal.protective_authority_digest for seal in seals} == {authority.authority_digest}
    assert [seal.close_position_quantity for seal in seals] == [gpe.d(0)] * 3 + [gpe.d(-1), gpe.d(-1)] + [gpe.d(0)] * 2
    day3, day4, day5 = seals[3], seals[4], seals[5]
    cycle3 = days[3].cycle
    # day 3 opens the excursion; it is still open at E_4 and E_5, named by its deciding cycle
    assert (day3.open_excursion_deciding_day_index, day3.open_excursion_deciding_cycle_digest) == (
        3,
        cycle3.cycle_digest,
    )
    assert (day4.open_excursion_deciding_day_index, day4.open_excursion_deciding_cycle_digest) == (
        3,
        cycle3.cycle_digest,
    )
    # day 4: the deadline obligation and its attempt, in flight at E_5 (the next book is visible at E_5 + 502)
    assert (day4.day_protective_obligation_count, day4.outstanding_protective_obligation_count) == (1, 1)
    assert day4.pending_protective_attempt_time_ns == DEADLINE
    assert day4.day_episode_count == 0
    # day 5: the close-only fill, projected through the day-3 cycle's reservation (DEC-1: no cycle direction needed)
    assert (day5.day_episode_count, day5.outstanding_protective_obligation_count) == (1, 0)
    assert day5.pending_protective_attempt_time_ns is None and day5.open_excursion_deciding_cycle_digest is None
    assert day5.episode_deciding_cycle_digests[-1] == cycle3.cycle_digest
    close = day5.episodes[-1]
    assert close.order_intent.side == "BUY" and Fraction(close.new_position_state.signed_units) == 0
    assert days[5].seal_inputs.protection.excursion_cycle is cycle3
    outcome, fills = protective_records(days[5])
    (obligation,) = outcome.protective_obligations
    assert obligation.status is HistoricalExecutionProtectiveObligationStatus.DISCHARGED
    assert [item.trigger_kind for item in obligation.triggers] == [HistoricalExecutionProtectiveTriggerKind.MAX_HOLD]
    assert [(item.outcome, item.execution_time_ns) for item in fills] == [
        (HistoricalExecutionFillOutcome.FILLED, CLOSE)
    ]
    assert obligation.breach_duration_ns == CLOSE - DEADLINE
    assert outcome.governance_rejected_fill_digests == ()


def test_the_protective_lineage_is_ready_and_every_seal_reverifies() -> None:
    days = lineage("G", 7)
    evidence = evidence_of(days)
    assert (evidence.schema_version, evidence.status, evidence.ready) == (
        "governed-paper-execution-evidence.v3",
        GovernedPaperExecutionStatus.READY,
        True,
    )
    assert evidence.protective_authority_digest == prot.world_authority()[1].authority_digest
    assert (
        evidence.terminal_protective_revoked_from_ns,
        evidence.terminal_outstanding_protective_obligation_count,
    ) == (
        None,
        0,
    )
    assert verify_governed_paper_execution_evidence(evidence, gpe.evidence_inputs(days, gpe.scenario("G"))).intact
    for item in days:
        assert verify_governed_paper_day_seal(item.seal, item.seal_inputs).intact
    # one protective semantics: the seal's schedule carries the authority window, its outcome the v3 ledgers
    for item in days:
        (window,) = item.seal.schedule.protective_windows
        assert (window.window_start_ns, window.window_end_ns) == (gpe.G, gpe.instant(prot.VALID_UNTIL_DAY))
    # every replay preserves the sealed prefix, the pending attempt excluded by its instant (X1)
    for earlier, later in zip(days, days[1:], strict=False):
        assert later.seal.prefix_digest_open == earlier.seal.prefix_digest_close


def test_the_entry_gate_evaluates_rule_set_v2_on_the_same_protective_context() -> None:
    entry_safety = gpe.entry_safety
    seal = lineage("G", 4)[3].seal
    assert seal.entry_safety_rule_set_digest == entry_safety.governed_paper_entry_safety_rule_set_digest(
        protective=True
    )
    assert seal.entry_safety_rule_set_digest != entry_safety.governed_paper_entry_safety_rule_set_digest()
    assert [item.entry_permitted for item in seal.entry_safety_decisions] == [True]


def test_the_seal_carries_the_day_archive_and_the_engine_reads_only_bars_known_then() -> None:
    days = lineage("G", 5)
    for index, item in enumerate(days):
        archive = prot.world_ohlc(index)
        assert (item.seal.ohlc_archive_digest, item.seal.ohlc_bar_count) == (archive.archive_digest, len(archive.bars))
        assert all(max(bar.available_at_ns, bar.finalized_at_ns) <= item.seal.window_end_ns for bar in archive.bars)
    economics = protected_replay(days[3])[0]
    (protection,) = economics.excursion_protections
    assert (protection.direction, protection.atr_value, protection.opened_at_ns) == (
        "SHORT",
        gpe.d("0.4"),
        gpe.instant(3) + 502,
    )
    assert protection.max_hold_deadline_ns == DEADLINE


LONG_FIRST_BAR = -300  # SYNTHETIC: 50 days of bars before G


@functools.cache
def long_world_bar(k: int):  # noqa: ANN201
    """SYNTHETIC: world G's bar ``k``, except the first true range of the long history, which is 8 (high 44, low 36)."""

    if k != LONG_FIRST_BAR + 1:
        return prot.world_bar(k)
    opened = gpe.G + k * prot.H4
    return build_historical_ohlc_bar(
        interval_ns=prot.H4,
        open_time_ns=opened,
        open_price=gpe.d(40),
        high_price=gpe.d(44),
        low_price=gpe.d(36),
        close_price=gpe.d(40),
        available_at_ns=opened + prot.H4 + prot.SECOND,
        finalized_at_ns=opened + prot.H4 + prot.SECOND,
    )


@functools.cache
def long_world_ohlc(day: int):  # noqa: ANN201
    """The long history sealed at E_(day + 1): exactly the bars visible then, growing without backfill."""

    end = gpe.instant(day + 1)
    bars = tuple(
        long_world_bar(k)
        for k in range(LONG_FIRST_BAR, 6 * (day + 1))
        if max(long_world_bar(k).available_at_ns, long_world_bar(k).finalized_at_ns) <= end
    )
    return build_historical_ohlc_bar_archive(archive_id=f"ohlc-g-long-{day}", source=prot.ohlc_source(), bars=bars)


def test_the_day_seal_binds_the_exact_full_history_atr_and_its_stop() -> None:
    """P2-DEC7-280-TR-RESEED on governed day seals: the first true range 8, every later one 0.4, over 300+ bars."""

    days: tuple = ()
    for day in range(4):
        days = (*days, protective_day(days, archive=long_world_ohlc(day)))
    assert all(item.seal.status is SEALED for item in days)
    economics, outcome = protected_replay(days[3])
    # the seal bound exactly this independently rebuilt economics and governed outcome
    assert (days[3].seal.economics_result_digest, days[3].seal.governed_outcome_digest) == (
        economics.result_digest,
        outcome.outcome_digest,
    )
    decided = gpe.instant(3) + 10  # the day-3 entry decision reads the ATR
    run = tuple(bar for bar in long_world_ohlc(3).bars if max(bar.available_at_ns, bar.finalized_at_ns) <= decided)
    atr = ohlct.wilder_oracle(run)  # the independent oracle
    assert len(run) > 281 and atr != Fraction("0.4")  # a 280-true-range re-seed read exactly 0.4 here
    (protection,) = economics.excursion_protections
    assert (protection.atr_at_ns, protection.atr_value, protection.atr_run_bar_count) == (decided, gpe.d(atr), len(run))
    assert protection.atr_window_digest == ohlct.window_of(run)
    assert [item.stop_price for item in protection.stop_levels] == [
        gpe.d(Fraction(protection.basis_price) + STOP_ATR_MULTIPLE * atr)
    ]
    assert outcome.excursion_protections == economics.excursion_protections


# --- B. DEC-1: the protective close bypasses invalidation and a zero direction ceiling ------------------------------------------


def test_a_kill_after_the_fill_never_strands_the_position_the_deadline_closes_it() -> None:
    days = lineage("kill-503", 6)
    assert days[3].seal.invalidated_from_ns == gpe.instant(3) + 503
    assert all(item.cycle.status.value == "BLOCKED" for item in days[4:])
    day5 = days[5].seal
    assert (day5.status, day5.close_position_quantity, day5.day_episode_count) == (SEALED, gpe.d(0), 1)
    assert day5.episode_deciding_cycle_digests[-1] == days[3].cycle.cycle_digest
    outcome, fills = protective_records(days[5])
    assert [item.outcome for item in fills] == [HistoricalExecutionFillOutcome.FILLED]
    assert outcome.governance_rejected_fill_digests == ()
    assert evidence_of(days, "kill-503").ready is True


def test_a_long_held_under_a_zero_short_ceiling_is_closed_by_its_protective_sell() -> None:
    days = lineage("b50-long", 6)
    day3, day5 = days[3].seal, days[5].seal
    assert day3.episodes[0].order_intent.side == "BUY" and day3.close_position_quantity == gpe.d(1)
    assert days[5].cycle.short_authorized is False  # the cycle never authorizes a SELL
    assert (day5.close_position_quantity, day5.episodes[-1].order_intent.side) == (gpe.d(0), "SELL")
    assert day5.episode_deciding_cycle_digests[-1] == days[3].cycle.cycle_digest
    transitions = protected_replay(days[5])[1].position_transitions
    assert transitions[-1].transition_kind is HistoricalExecutionTransitionKind.CLOSE
    assert evidence_of(days, "b50-long").ready is True


# --- C. revocation: a revoked authority fails closed with explicit breach evidence ---------------------------------------------


def test_a_revoked_authority_refuses_the_attempt_and_the_breach_lasts_until_the_position_is_flat() -> None:
    days = lineage("G", 8, revoked=True)
    seals = [item.seal for item in days]
    revocation = prot.revocation(prot.world_authority()[1], REVOKED_AT)
    assert seals[4].protective_revocation_digests == (revocation.revocation_digest,)
    assert all(seal.protective_revocation_digests == () for seal in seals[5:])
    assert [seal.protective_revoked_from_ns for seal in seals] == [None] * 4 + [REVOKED_AT] * 4
    assert all(seal.schedule.protective_windows[0].window_end_ns == REVOKED_AT for seal in seals[4:])
    assert [seal.outstanding_protective_obligation_count for seal in seals] == [0] * 4 + [1, 1, 1, 0]
    assert all(seal.pending_protective_attempt_time_ns is None for seal in seals)
    outcome, fills = protective_records(days[7])
    assert [(item.outcome, item.reason) for item in fills] == [
        (HistoricalExecutionFillOutcome.REJECTED, "governed_paper_protective_authority_missing")
    ]
    (obligation,) = outcome.protective_obligations
    # world G's own day-7 exit discharges it: the breach is the exact three days the position stayed open
    assert obligation.status is HistoricalExecutionProtectiveObligationStatus.DISCHARGED
    assert obligation.breach_duration_ns == (gpe.instant(7) + 502) - DEADLINE
    evidence = evidence_of(days)
    assert evidence.ready and evidence.terminal_protective_revoked_from_ns == REVOKED_AT


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"approval_kind": prot.SYNTHETIC}, "protective_revocation_not_human_governance"),
        ({"effective_at_ns": gpe.instant(5) + 1}, "protective_revocation_outside_the_sealed_day"),
        ({"authority_digest": "c" * 64}, "protective_revocation_foreign"),
    ],
)
def test_a_revocation_must_be_human_of_the_authority_and_inside_its_day(change: dict, reason: str) -> None:
    authority = prot.world_authority()[1]
    arguments = {"effective_at_ns": REVOKED_AT, **change}
    record = prot.revocation(authority, arguments.pop("effective_at_ns"), **arguments)
    with gpe.refused(reason):
        rebuilt(lineage("G", 5)[4], revocations=(record,))


def test_a_tampered_or_unordered_revocation_is_refused() -> None:
    authority = prot.world_authority()[1]
    first, second = prot.revocation(authority, REVOKED_AT), prot.revocation(authority, REVOKED_AT + 1)
    with gpe.refused("protective_revocations_not_ordered"):
        rebuilt(lineage("G", 5)[4], revocations=(second, first))
    with gpe.refused("protective_revocation_not_authentic"):
        rebuilt(lineage("G", 5)[4], revocations=(replace(first, effective_at_ns=REVOKED_AT + 2),))


# --- D. lineage, authority and archive provenance -----------------------------------------------------------------------------


def test_a_protective_fill_needs_exactly_the_cycle_that_decided_its_excursion() -> None:
    days = lineage("G", 6)
    with gpe.refused("excursion_deciding_cycle_not_authentic"):
        rebuilt(days[5], excursion_cycle_inputs=None, excursion_cycle=None)
    with gpe.refused("excursion_deciding_cycle_not_authentic"):
        rebuilt(days[5], excursion_cycle_inputs=days[4].cycle_inputs, excursion_cycle=days[4].cycle)
    with gpe.refused("excursion_cycle_without_an_open_excursion"):
        rebuilt(days[1], excursion_cycle_inputs=days[0].cycle_inputs, excursion_cycle=days[0].cycle)


def test_a_divergent_archive_rewrites_the_sealed_protective_prefix() -> None:
    days = lineage("G", 5)
    original = gpe.archive(4)
    event = gpe.S0 + 319 * gpe.FUNDING + 500  # the book that priced the day-3 opening fill
    values = {**gpe.book_values(event), "best_bid_price": gpe.d(Fraction("39.95"))}
    divergent = gpe._record("book", "order_book", 319, event, event + 2, values)  # noqa: SLF001
    records = tuple(
        divergent if (item.series_id, item.sequence_id) == ("book", 319) else item for item in original.records
    )
    with gpe.refused("sealed_prefix_rewritten"):
        build_governed_paper_day_seal(
            replace(days[4].seal_inputs, dataset=gpe.archive_of("paper-archive-G-4-divergent", records))
        )


def test_a_lineage_is_protective_from_day_0_or_never() -> None:
    protective, legacy = lineage("G", 2), gpe.days_of("G", 2)
    with gpe.refused("protective_lineage_switched"):
        build_governed_paper_day_seal(replace(protective[1].seal_inputs, protection=None))
    with gpe.refused("protective_lineage_switched"):
        build_governed_paper_day_seal(replace(legacy[1].seal_inputs, protection=protective[1].seal_inputs.protection))


def test_the_authority_is_authentic_of_the_genesis_and_constant_across_the_lineage() -> None:
    days = lineage("G", 2)
    inputs, record = prot.world_authority()
    forged = prot.reseal(record, valid_until_ns=gpe.instant(90))
    with gpe.refused("protective_authority_not_authentic"):
        rebuilt(days[1], authority=forged)
    other = prot.authority_inputs(authority_id="gpe-protective-other")
    with gpe.refused("protective_authority_changed_inside_the_lineage"):
        rebuilt(days[1], authority_inputs=other, authority=build_governed_paper_protective_authority(other))
    foreign_inputs, foreign = prot.world_authority("b50-long")
    with gpe.refused("protective_authority_foreign"):
        rebuilt(days[0], authority_inputs=foreign_inputs, authority=foreign)
    assert inputs is prot.world_authority()[0]


def test_an_authority_that_is_not_authorized_blocks_the_day_with_explicit_evidence() -> None:
    pending_inputs = prot.authority_inputs(approval=None)
    seal = rebuilt(
        lineage("G", 1)[0],
        authority_inputs=pending_inputs,
        authority=build_governed_paper_protective_authority(pending_inputs),
    )
    assert (seal.schema_version, seal.status, seal.reason_codes) == (
        V3,
        GovernedPaperDaySealStatus.BLOCKED,
        (gpe.code("protective_authority_not_authorized"),),
    )
    assert seal.schedule.protective_windows == () and seal.economics_result_digest == ""


def test_the_ohlc_archive_is_authentic_of_the_adopted_source_and_known_at_the_seal() -> None:
    day1 = lineage("G", 2)[1]
    with gpe.refused("ohlc_archive_holds_a_bar_unknown_at_the_seal"):
        rebuilt(day1, ohlc_archive=prot.world_ohlc(2))
    other = prot.world_ohlc(1, source=prot.ohlc_source(source_id="synthetic-ohlc-other"))
    with gpe.refused("ohlc_archive_not_of_the_adopted_source"):
        rebuilt(day1, ohlc_archive=other)
    with gpe.refused("ohlc_archive_not_authentic"):
        rebuilt(day1, ohlc_archive=replace(prot.world_ohlc(1), archive_id="ohlc-forged"))


def test_the_evidence_refuses_a_rewritten_or_backfilled_ohlc_archive() -> None:
    days = lineage("G", 3)
    full = prot.world_ohlc(2)
    trimmed = build_historical_ohlc_bar_archive(archive_id="ohlc-g-2", source=prot.ohlc_source(), bars=full.bars[1:])
    rewritten = protective_day(days[:2], archive=trimmed)
    with gpe.refused("ohlc_archive_rewritten:2"):
        evidence_of((*days[:2], rewritten))
    early = prot.world_ohlc(1)
    late = gpe.G + 24 * prot.HOUR  # the bar first visible during day 1 (at G + 28 h + 1 s), withheld from its archive
    missing = build_historical_ohlc_bar_archive(
        archive_id="ohlc-g-1",
        source=prot.ohlc_source(),
        bars=tuple(bar for bar in early.bars if bar.open_time_ns != late),
    )
    assert len(missing.bars) == len(early.bars) - 1
    day1 = protective_day(days[:1], archive=missing)
    day2 = protective_day((days[0], day1))
    with gpe.refused("ohlc_archive_backfilled_before_the_day:2"):
        evidence_of((days[0], day1, day2))


# --- E. identity and legacy -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("outstanding_protective_obligation_count", 0),
        ("pending_protective_attempt_time_ns", None),
        ("open_excursion_deciding_cycle_digest", None),
        ("protective_revoked_from_ns", gpe.instant(6)),
        ("ohlc_bar_count", 1),
    ],
)
def test_a_resealed_protective_fact_never_verifies(name: str, value: object) -> None:
    item = lineage("G", 5)[4]
    forged = reseal(item.seal, **{name: value})
    assert not verify_governed_paper_day_seal(forged, item.seal_inputs).intact


def test_a_v2_seal_never_carries_a_protective_fact() -> None:
    legacy = gpe.days_of("G", 1)[0]
    payload = governed_paper_day_seal_to_dict(legacy.seal)
    assert "protective_authority_digest" not in payload and "ohlc_archive_digest" not in payload
    forged = replace(legacy.seal, ohlc_bar_count=3)
    with pytest.raises(ValueError, match="legacy_schema_carries_an_extension_field:ohlc_bar_count"):
        governed_paper_day_seal_to_dict(forged)
    assert not verify_governed_paper_day_seal(forged, legacy.seal_inputs).intact


def test_a_resealed_protective_evidence_fact_never_verifies() -> None:
    days = lineage("G", 5)
    evidence = evidence_of(days)
    for name, value in (
        ("terminal_outstanding_protective_obligation_count", 0),
        ("protective_authority_digest", "0" * 64),
    ):
        forged = replace(evidence, **{name: value})
        forged = replace(forged, evidence_digest=governed_paper_execution_evidence_digest(forged))
        assert not verify_governed_paper_execution_evidence(forged, gpe.evidence_inputs(days, gpe.scenario("G"))).intact
    assert evidence.terminal_outstanding_protective_obligation_count == 1  # never reclassified as a success


def test_world_g_without_protection_is_byte_identical_to_accepted_main() -> None:
    days = gpe.world_days()
    evidence = gpe.world_evidence()
    assert (evidence.evidence_digest, evidence.lineage_digest) == (
        ACCEPTED_MAIN_WORLD_G["evidence"],
        ACCEPTED_MAIN_WORLD_G["lineage"],
    )
    assert {index: days[index].seal.seal_digest for index in ACCEPTED_MAIN_WORLD_G["seals"]} == ACCEPTED_MAIN_WORLD_G[
        "seals"
    ]
    economics, outcome = gpe.replay_of(days[9])
    assert (economics.result_digest, outcome.outcome_digest, outcome.schedule_digest) == (
        ACCEPTED_MAIN_WORLD_G["day9_economics"],
        ACCEPTED_MAIN_WORLD_G["day9_outcome"],
        ACCEPTED_MAIN_WORLD_G["day9_schedule"],
    )
    assert all(item.seal.schema_version == "governed-paper-day-seal.v2" for item in days)


# --- F. rule set v3: the native portfolio NO-TRADE lineage (seal v4, evidence v4) ------------------------------------------

V4 = "governed-paper-day-seal.v4"
PASS = gpe.entry_safety.GovernedPaperEntrySafetyStatus.PASS
MEASURED_IDS = ("NT-R02", "NT-R04")
# Captured at import, before the module fixture installs the permissive table: the PRODUCTION NT-R02 and NT-R04 checks.
NATIVE_PORTFOLIO_CHECKS = tuple(item for item in gpe.entry_safety._CHECKS if item.check_id in MEASURED_IDS)  # noqa: SLF001
# SYNTHETIC, TEST-ONLY: the permissive table followed by those native portfolio checks, so that the measured portfolio
# alone decides an entry of these worlds (the production NT-R03 would block every prospective entry; see the docstring).
PERMISSIVE_WITH_NATIVE_PORTFOLIO = (*gpe.TEST_ONLY_PERMISSIVE_ENTRY_CHECKS, *NATIVE_PORTFOLIO_CHECKS)
# The accepted-main identities (main 99518b37) of world G's protective lineage under the permissive table: the native
# portfolio contract leaves every v3 seal and the v3 evidence byte-identical.
ACCEPTED_MAIN_PROTECTIVE_G = {
    "seals": {
        0: "c8dcc99cc1510fd796d27faea3d4b83660761e3c628e76edf45a3ee0d108ca52",
        1: "c7f159dbb95b8f21936a029cc3e0b589fa095cd004926a5b457a1ad9b161ff31",
        2: "361a3259010813a9279d1c9e37bfa2f676014205a065969e1564c68ae0f89edb",
        3: "bb504d20f62af04e8cd2f0296811b817bc5b34231b52aff21d3fa5236c0ab1c6",
        4: "18479b7f194571c84b37826d2ac7501c9bd63b8f20d9e361b251ee7f9bb03bef",
        5: "cdf9d34815d6af8345628db6416bac971825c21bd5d2efd8dbb289d6d602e3d4",
        6: "6920afa5b014e5d3da6ca20334a3db840df51b0e1029c226e5abfee29b5b58df",
    },
    "evidence": "ba727c6b2da841dae6bdb0e30777e229b9fe232d996b03e384eb368d358ef495",
}


@pytest.fixture
def native_portfolio_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC, TEST-ONLY: the permissive table plus the native portfolio checks, for this test only."""

    lineage("G", 7)  # the v3 lineage is built (or reused) under the module's permissive table, never under this one
    monkeypatch.setattr(gpe.entry_safety, "_CHECKS", PERMISSIVE_WITH_NATIVE_PORTFOLIO)


@functools.cache
def portfolio_lineage(count: int) -> tuple:
    """World G's first ``count`` protective days with the native portfolio checks (seal v4), under that table only."""

    assert gpe.entry_safety._CHECKS is PERMISSIVE_WITH_NATIVE_PORTFOLIO  # noqa: SLF001
    if count == 0:
        return ()
    days = portfolio_lineage(count - 1)
    return (*days, protective_day(days, portfolio_no_trade=True))


def check_of(decision: object, check_id: str):  # noqa: ANN201
    return next(item for item in decision.checks if item.check_id == check_id)  # type: ignore[attr-defined]


def test_the_protective_lineage_keeps_its_accepted_main_identity() -> None:
    days = lineage("G", 7)
    assert {index: item.seal.seal_digest for index, item in enumerate(days)} == ACCEPTED_MAIN_PROTECTIVE_G["seals"]
    assert evidence_of(days).evidence_digest == ACCEPTED_MAIN_PROTECTIVE_G["evidence"]


def test_the_native_portfolio_lineage_admits_its_low_concentration_entry_and_changes_no_fill(
    native_portfolio_gate: None,
) -> None:
    legacy, days = lineage("G", 7), portfolio_lineage(7)
    digest = gpe.entry_safety.governed_paper_entry_safety_rule_set_digest(protective=True, portfolio=True)
    for item in days:
        seal = item.seal
        assert (seal.schema_version, seal.status, seal.reason_codes) == (V4, SEALED, ())
        assert seal.entry_safety_rule_set_digest == digest
        assert seal.schedule.schema_version == HISTORICAL_EXECUTION_INFORMATION_TIME_ADMISSION_SCHEDULE_SCHEMA_VERSION
        verification = verify_governed_paper_day_seal(seal, item.seal_inputs)
        assert (verification.intact, verification.reason_codes) == (True, ())
    assert all(
        item.seal.schedule.schema_version == HISTORICAL_EXECUTION_PROTECTIVE_ADMISSION_SCHEDULE_SCHEMA_VERSION
        for item in legacy
    )
    entry, held = (decision for item in days for decision in item.seal.entry_safety_decisions)
    # day 3: flat, no intraday PnL, and its one-unit SHORT candidate holds ~0.4% of NAV at the mark: admitted
    assert (entry.entry_permitted, entry.first_failure_check_id) == (True, "")
    loss, concentration = check_of(entry, "NT-R02"), check_of(entry, "NT-R04")
    assert (loss.status, loss.observed) == (PASS, gpe.d(0))
    assert (concentration.status, concentration.reason) == (
        PASS,
        "governed_paper_entry_safety:NT-R04:candidate_position_within_25pct_of_nav_and_bounded_at_its_fill",
    )
    assert 0 < Fraction(concentration.observed) < Fraction(1, 100)
    # day 5: the day-3 SHORT is still open at the decision (its protective close fills after it): a hold, no entry
    assert (held.entry_permitted, held.first_failure_check_id) == (True, "")
    assert check_of(held, "NT-R04").reason == "governed_paper_entry_safety:NT-R04:single_position_within_25pct_of_nav"
    assert Fraction(check_of(held, "NT-R04").observed) > 0  # the open SHORT's share of NAV, on the fresh visible mark
    # information time admits exactly what the v3 lineage admits here (no settlement is unpublished at the entry's fill
    # and the bound holds): every fill, episode and funding event is unchanged, and nothing is refused
    for earlier, later in zip(legacy, days, strict=True):
        assert protected_replay(later)[1].fills == protected_replay(earlier)[1].fills
        assert (later.seal.episodes, later.seal.funding_events) == (earlier.seal.episodes, earlier.seal.funding_events)
    assert all(item.seal.schedule.entry_refused_decision_sequences == () for item in (*legacy, *days))
    evidence = evidence_of(days)
    assert (evidence.schema_version, evidence.status) == (
        "governed-paper-execution-evidence.v4",
        GovernedPaperExecutionStatus.READY,
    )
    verification = verify_governed_paper_execution_evidence(evidence, gpe.evidence_inputs(days, gpe.scenario("G")))
    assert (verification.intact, verification.reason_codes) == (True, ())


def test_a_forged_native_portfolio_fact_never_verifies_even_resealed(native_portfolio_gate: None) -> None:
    item = portfolio_lineage(4)[3]
    seal, inputs = item.seal, item.seal_inputs
    (entry,) = seal.entry_safety_decisions
    reason = "governed_paper_entry_safety:NT-R04:candidate_position_above_25pct_of_nav"
    refused = replace(entry, entry_permitted=False, first_failure_check_id="NT-R04", first_failure_reason=reason)
    for changes in (
        {"entry_safety_decisions": (refused,)},
        {"schedule": replace(seal.schedule, entry_refused_decision_sequences=(entry.decision_sequence,))},
        # the booked-equity v3 re-run never seals a native portfolio day
        {
            "schedule": replace(
                seal.schedule, schema_version=HISTORICAL_EXECUTION_PROTECTIVE_ADMISSION_SCHEDULE_SCHEMA_VERSION
            )
        },
        {"entry_safety_rule_set_digest": gpe.entry_safety.governed_paper_entry_safety_rule_set_digest(protective=True)},
        {"schema_version": V3},
    ):
        for forged in (replace(seal, **changes), reseal(seal, **changes)):
            assert not verify_governed_paper_day_seal(forged, inputs).intact
    assert verify_governed_paper_day_seal(seal, inputs).intact


def test_a_native_portfolio_lineage_is_one_from_day_0_or_never(native_portfolio_gate: None) -> None:
    native, legacy = portfolio_lineage(2), lineage("G", 2)

    def switched(item: object, value: object):  # noqa: ANN202
        inputs = item.seal_inputs  # type: ignore[attr-defined]
        return replace(inputs, protection=replace(inputs.protection, portfolio_no_trade=value))

    with gpe.refused("portfolio_no_trade_lineage_switched"):
        build_governed_paper_day_seal(switched(native[1], False))
    with gpe.refused("portfolio_no_trade_lineage_switched"):
        build_governed_paper_day_seal(switched(legacy[1], True))
    with gpe.refused("protection_inputs_malformed:portfolio_no_trade"):
        build_governed_paper_day_seal(switched(native[1], 1))
    with gpe.refused("protective_lineage_switched"):
        build_governed_paper_day_seal(replace(native[1].seal_inputs, protection=None))


# --- G. rule set v4: the native market-data integrity lineage (seal v5, evidence v5) -------------------------------------

V5 = "governed-paper-day-seal.v5"
# The accepted-main identity (main cde35d4f) of the protective authority and the day-3 OHLC archive of world G: the
# declared bar origin of archive schema v2 leaves every source and archive of undeclared origin exactly as it was.
ACCEPTED_MAIN_AUTHORITY_G = "a584f0501d0226838ca4753aa95584f13284714f8b6a3ad175c75b88a01e9e72"
ACCEPTED_MAIN_OHLC_G_DAY3 = "a14730907df0a33ef41a3fcc811e1726a252d9d6c4e9db98bfaa63196c34428b"


@functools.cache
def market_data_lineage(count: int) -> tuple:
    """World G's first ``count`` protective days of the market-data integrity lineage (seal v5), under that table only."""

    assert gpe.entry_safety._CHECKS is PERMISSIVE_WITH_NATIVE_PORTFOLIO  # noqa: SLF001
    if count == 0:
        return ()
    days = market_data_lineage(count - 1)
    return (*days, protective_day(days, portfolio_no_trade=True, market_data_integrity=True))


def test_the_protective_authority_and_its_ohlc_archive_keep_their_accepted_main_identity() -> None:
    assert prot.world_authority()[1].authority_digest == ACCEPTED_MAIN_AUTHORITY_G
    archive = prot.world_ohlc(3)
    assert (archive.archive_digest, archive.schema_version, archive.source.bar_origin) == (
        ACCEPTED_MAIN_OHLC_G_DAY3,
        "historical-ohlc-bar-archive.v1",
        None,
    )


def test_the_market_data_lineage_changes_only_its_version_and_rule_set_and_reverifies(
    native_portfolio_gate: None,
) -> None:
    days, native = market_data_lineage(4), portfolio_lineage(4)
    digest = gpe.entry_safety.governed_paper_entry_safety_rule_set_digest(
        protective=True, portfolio=True, market_data=True
    )
    for item, old in zip(days, native, strict=True):
        seal = item.seal
        assert (seal.schema_version, seal.status, seal.reason_codes) == (V5, SEALED, ())
        assert seal.entry_safety_rule_set_digest == digest != old.seal.entry_safety_rule_set_digest
        # the same admissions, schedule, outcome and history as the v4 lineage under this table
        for name in ("schedule", "governed_outcome_digest", "episodes", "funding_events", "sealed_history_digest"):
            assert getattr(seal, name) == getattr(old.seal, name), name
        assert [decision.entry_permitted for decision in seal.entry_safety_decisions] == [
            decision.entry_permitted for decision in old.seal.entry_safety_decisions
        ]
        verification = verify_governed_paper_day_seal(seal, item.seal_inputs)
        assert (verification.intact, verification.reason_codes) == (True, ())
    evidence = evidence_of(days)
    assert (evidence.schema_version, evidence.status) == (
        "governed-paper-execution-evidence.v5",
        GovernedPaperExecutionStatus.READY,
    )
    verification = verify_governed_paper_execution_evidence(evidence, gpe.evidence_inputs(days, gpe.scenario("G")))
    assert (verification.intact, verification.reason_codes) == (True, ())
    payload = governed_paper_day_seal_to_dict(days[3].seal)
    assert payload["schema_version"] == V5 and "protective_authority_digest" in payload


def test_a_market_data_lineage_is_one_from_day_0_or_never_and_only_on_a_portfolio_lineage(
    native_portfolio_gate: None,
) -> None:
    market, native = market_data_lineage(2), portfolio_lineage(2)

    def switched(item: object, **changes: object):  # noqa: ANN202
        inputs = item.seal_inputs  # type: ignore[attr-defined]
        return replace(inputs, protection=replace(inputs.protection, **changes))

    with gpe.refused("market_data_integrity_lineage_switched"):
        build_governed_paper_day_seal(switched(market[1], market_data_integrity=False))
    with gpe.refused("market_data_integrity_lineage_switched"):
        build_governed_paper_day_seal(switched(native[1], market_data_integrity=True))
    with gpe.refused("market_data_integrity_needs_the_portfolio_lineage"):
        build_governed_paper_day_seal(switched(market[0], portfolio_no_trade=False))
    with gpe.refused("protection_inputs_malformed:market_data_integrity"):
        build_governed_paper_day_seal(switched(market[1], market_data_integrity=1))
    with gpe.refused("portfolio_no_trade_lineage_switched"):
        build_governed_paper_day_seal(switched(market[1], portfolio_no_trade=False, market_data_integrity=False))
    # a v5 seal re-labelled v4 (or a v4 seal re-labelled v5) never verifies, even resealed
    for item, label in ((market[1], "governed-paper-day-seal.v4"), (native[1], V5)):
        for forged in (replace(item.seal, schema_version=label), reseal(item.seal, schema_version=label)):
            assert not verify_governed_paper_day_seal(forged, item.seal_inputs).intact
