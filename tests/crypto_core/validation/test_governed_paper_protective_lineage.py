"""Governed protective lineage tests (PROTECTIVE_POSITION_LIFECYCLE_V1: day seal v3 and lineage evidence v3).

SYNTHETIC TEST VALUES ONLY. Every bar, policy value, instant, revocation and approval here is a synthetic fixture over
the synthetic worlds of ``test_governed_admitted_variant_paper_execution.py``; no ``HUMAN_GOVERNANCE`` record built here
is a real human decision, and nothing here approves DEC-9, grants C1-C9 or proves a venue fact.

ENTRY GATE SUBSTITUTION (SYNTHETIC, TEST-ONLY), as in the lineage tests: the production entry gate refuses every S1
entry of these worlds, so this module exercises the protective mechanics an admitted entry reaches with the rule table
explicitly replaced by the test-only permissive table. ``test_governed_paper_entry_safety.py`` proves rule set v2 under
the production table.

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
from crypto_core.validation.governed_paper_execution_authority import (
    build_governed_paper_cycle_authority,
    governed_paper_genesis_authority,
)
from crypto_core.validation.governed_paper_protective_authority import (
    build_governed_paper_protective_authority,
    governed_paper_protective_context,
)
from crypto_core.validation.historical_execution_economics import (
    HistoricalExecutionFillOutcome,
    HistoricalExecutionPositionManagementInputs,
    HistoricalExecutionProtectiveObligationStatus,
    HistoricalExecutionProtectiveTriggerKind,
    HistoricalExecutionTransitionKind,
    simulate_historical_execution_governed_paper,
)
from crypto_core.validation.historical_ohlc_bar_archive import build_historical_ohlc_bar_archive

try:  # the module objects pytest collects (basename import): the shared synthetic worlds and their exact memos
    import test_governed_admitted_variant_paper_execution as gpe
    import test_governed_paper_protective_authority as prot
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_governed_admitted_variant_paper_execution as gpe
    from tests.crypto_core.validation import test_governed_paper_protective_authority as prot

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
    view = governed_paper_genesis_authority(inputs.genesis, inputs.genesis_inputs)
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
