"""Governed paper allocation envelope tests (ALLOCATION_ENVELOPE_V1 and ENVELOPE_FIT of
S1_APPROVED_SIZING_CHAIN_CONSTRUCTION_V1).

SYNTHETIC TEST VALUES ONLY. Every EHS, Sharpe_30d, activation and DECAY_ALERT reading, NAV and usage here is a synthetic
fixture that exercises structure; none is the output of an approved EHS or Sharpe method (FCD-13 is pending), a venue
fact or a real human decision. The approved companion's worked examples (§4.4) and acceptance criteria (§10.2,
T-ALLOC-01..20) are reproduced exactly, and the projection is compared against an independent exact oracle.
"""

from __future__ import annotations

import ast
import inspect
import itertools
import random
from dataclasses import replace
from fractions import Fraction

import pytest

import crypto_core.validation.governed_paper_allocation_envelope as allocation
from crypto_core.validation.governed_paper_allocation_envelope import (
    GOVERNED_PAPER_ALLOCATION_CAP,
    GOVERNED_PAPER_ALLOCATION_EDGE_STATE_REASON,
    GOVERNED_PAPER_ALLOCATION_FLOOR,
    GOVERNED_PAPER_ALLOCATION_GOVERNED_READING_REASON,
    GovernedPaperAllocationActivation,
    GovernedPaperAllocationCandidate,
    GovernedPaperAllocationDecayAlert,
    GovernedPaperAllocationEligibility,
    GovernedPaperAllocationError,
    GovernedPaperAllocationStatus,
    GovernedPaperEnvelopeFitStatus,
    derive_governed_paper_allocation,
    derive_governed_paper_allocation_timeline,
    evaluate_governed_paper_envelope_fit,
    governed_paper_allocation_reading_at,
    governed_paper_allocation_timeline_digest,
    governed_paper_bounded_projection,
)
from crypto_core.validation.historical_execution_economics_policy import historical_execution_render_amount

F = Fraction
FLOOR, CAP = GOVERNED_PAPER_ALLOCATION_FLOOR, GOVERNED_PAPER_ALLOCATION_CAP
PASS_, FAIL_ = GovernedPaperAllocationActivation.PASS, GovernedPaperAllocationActivation.FAIL
UNKNOWN_ACT = GovernedPaperAllocationActivation.UNKNOWN
ACTIVE, INACTIVE = GovernedPaperAllocationDecayAlert.ACTIVE, GovernedPaperAllocationDecayAlert.INACTIVE
UNKNOWN_DECAY = GovernedPaperAllocationDecayAlert.UNKNOWN
MEMBER = GovernedPaperAllocationEligibility.MEMBER
NON_MEMBER = GovernedPaperAllocationEligibility.NON_MEMBER
UNKNOWN = GovernedPaperAllocationEligibility.UNKNOWN
ALLOCATED, NO_ALLOCATION, BLOCKED = (
    GovernedPaperAllocationStatus.ALLOCATED,
    GovernedPaperAllocationStatus.NO_ALLOCATION,
    GovernedPaperAllocationStatus.BLOCKED,
)
EF_PASS, EF_FAIL, EF_BLOCKED = (
    GovernedPaperEnvelopeFitStatus.PASS,
    GovernedPaperEnvelopeFitStatus.FAIL,
    GovernedPaperEnvelopeFitStatus.BLOCKED,
)
DAY = 86_400 * 1_000_000_000
G = 19_000 * DAY  # SYNTHETIC genesis on a UTC midnight
GENESIS = "a" * 64
UNIT = F(1, 10**18)


def d(value: object) -> str:
    rendered = historical_execution_render_amount(F(value))  # type: ignore[arg-type]
    assert rendered is not None
    return rendered


def candidate(  # noqa: PLR0913
    edge_id: str,
    ehs: object = "0.6",
    sharpe: object = "1",
    *,
    activation: GovernedPaperAllocationActivation = PASS_,
    decay: GovernedPaperAllocationDecayAlert = INACTIVE,
    defined: bool = True,
) -> GovernedPaperAllocationCandidate:
    return GovernedPaperAllocationCandidate(
        edge_id=edge_id,
        activation=activation,
        ehs=d(ehs) if defined and ehs is not None else None,
        sharpe_30d=d(sharpe) if defined and sharpe is not None else None,
        decay_alert=decay,
        reading_reason="synthetic_test_reading",
    )


def weights(result: object) -> list[Fraction | None]:
    return [None if item.weight is None else F(item.weight) for item in result.weights]  # type: ignore[attr-defined]


# --- A. the bounded projection (§4.3, §4.4) --------------------------------------------------------------------------------


# §4.4 exactly: (t, D9 weights, one-pass result when that result breaks a bound, else None)
WORKED = [
    ((F(1),), (F(2, 5),), (F(1),)),
    ((F(7, 10), F(3, 10)), (F(2, 5), F(3, 10)), (F(4, 7), F(3, 7))),
    ((F(1, 2), F(1, 2)), (F(2, 5), F(2, 5)), (F(1, 2), F(1, 2))),
    ((F(97, 100), F(3, 100)), (F(2, 5), F(1, 20)), (F(8, 9), F(1, 9))),
    ((F(1, 2), F(3, 10), F(1, 5)), (F(2, 5), F(7, 20), F(1, 4)), (F(4, 9), F(1, 3), F(2, 9))),
    ((F(9, 20), F(9, 20), F(1, 10)), (F(2, 5), F(2, 5), F(1, 5)), (F(4, 9), F(4, 9), F(1, 9))),
    ((F(1), F(0), F(0)), (F(2, 5), F(3, 10), F(3, 10)), (F(4, 5), F(1, 10), F(1, 10))),
    ((F(1, 3),) * 3, (F(1, 3),) * 3, None),
    (
        (F(11, 20), F(1, 4), F(3, 20), F(1, 20)),
        (F(2, 5), F(3, 10), F(1, 5), F(1, 10)),
        (F(8, 17), F(5, 17), F(3, 17), F(1, 17)),
    ),
    (
        (F(2, 5), F(2, 5), F(19, 100), F(1, 100)),
        (F(29, 75), F(29, 75), F(53, 300), F(1, 20)),
        (F(40, 104), F(40, 104), F(19, 104), F(5, 104)),
    ),
    (
        (F(2, 5), F(2, 5), F(3, 20), F(1, 25), F(1, 100)),
        (F(23, 60), F(23, 60), F(2, 15), F(1, 20), F(1, 20)),
        (F(40, 105), F(40, 105), F(15, 105), F(5, 105), F(5, 105)),
    ),
    ((F(9, 10), *(F(1, 40),) * 4), (F(2, 5), *(F(3, 20),) * 4), (F(2, 3), *(F(1, 12),) * 4)),
    ((F(1, 5),) * 5, (F(1, 5),) * 5, None),
    # BOOST at the cap: the superseded value 4/9 is the old pipeline's BOOST after renormalization (asserted below)
    ((F(4, 9), F(5, 18), F(5, 18)), (F(2, 5), F(3, 10), F(3, 10)), None),
    ((F(18, 53), F(35, 106), F(35, 106)), (F(18, 53), F(35, 106), F(35, 106)), None),
]


def test_boost_at_the_cap_is_absorbed_where_the_old_pipeline_broke_the_cap() -> None:
    r = (F(2, 5), F(3, 10), F(3, 10))
    old = one_pass(r)  # the old pipeline: clip and renormalize, then BOOST and renormalize again
    boosted = (old[0] * F(6, 5), old[1], old[2])
    assert tuple(item / sum(boosted) for item in boosted)[0] == F(4, 9) > CAP
    assert governed_paper_bounded_projection((F(4, 9), F(5, 18), F(5, 18))) == (CAP, F(3, 10), F(3, 10))


def one_pass(shares: tuple[Fraction, ...]) -> tuple[Fraction, ...]:
    """The superseded rule: clip, then divide by the sum."""

    clipped = [min(CAP, max(FLOOR, item)) for item in shares]
    return tuple(item / sum(clipped) for item in clipped)


@pytest.mark.parametrize(("shares", "expected", "superseded"), WORKED)
def test_every_worked_example_is_exact_and_no_bound_breaking_one_pass_output_is_produced(
    shares: tuple, expected: tuple, superseded: tuple | None
) -> None:
    result = governed_paper_bounded_projection(shares)
    assert result == expected
    assert all(FLOOR <= item <= CAP for item in result)  # P1
    if len(shares) >= 3:
        assert sum(result) == 1  # P2
    if superseded is not None:  # T-ALLOC-18: the one-pass output broke a bound and is never produced
        assert one_pass(shares) == superseded
        assert any(not FLOOR <= item <= CAP for item in superseded)
        assert result != superseded


def test_n_0_1_2_follow_the_clip_with_an_unallocated_residual() -> None:
    assert governed_paper_bounded_projection(()) == ()
    assert governed_paper_bounded_projection((F(1),)) == (CAP,)  # T-ALLOC-02: residual 0.60
    for shares, expected, total in (
        ((F(7, 10), F(3, 10)), (CAP, F(3, 10)), F(7, 10)),
        ((F(1, 2), F(1, 2)), (CAP, CAP), F(4, 5)),
        ((F(97, 100), F(3, 100)), (CAP, FLOOR), F(9, 20)),
    ):  # T-ALLOC-03
        result = governed_paper_bounded_projection(shares)
        assert (result, sum(result)) == (expected, total)
        assert F(9, 20) <= sum(result) <= F(4, 5)  # P2 for n = 2


def oracle(shares: tuple[Fraction, ...]) -> tuple[Fraction, ...]:
    """INDEPENDENT ORACLE: enumerate every LOW / FREE / HIGH assignment of the KKT form, keep the feasible ones and
    require them to agree (strict convexity: the minimizer is unique)."""

    found: set[tuple[Fraction, ...]] = set()
    for pattern in itertools.product("LFH", repeat=len(shares)):
        free = [item for item, kind in zip(shares, pattern, strict=True) if kind == "F"]
        low, high = pattern.count("L"), pattern.count("H")
        if free:
            shift = (1 - low * FLOOR - high * CAP - sum(free, F(0))) / len(free)
            candidate_ = []
            consistent = True
            for item, kind in zip(shares, pattern, strict=True):
                value = item + shift
                if kind == "F":
                    consistent &= FLOOR <= value <= CAP
                    candidate_.append(value)
                elif kind == "L":
                    consistent &= value <= FLOOR
                    candidate_.append(FLOOR)
                else:
                    consistent &= value >= CAP
                    candidate_.append(CAP)
            if consistent:
                found.add(tuple(candidate_))
        elif low * FLOOR + high * CAP == 1:
            lows = [FLOOR - item for item, kind in zip(shares, pattern, strict=True) if kind == "L"]
            highs = [CAP - item for item, kind in zip(shares, pattern, strict=True) if kind == "H"]
            if max(highs, default=F(-10)) <= min(lows, default=F(10)):
                found.add(tuple(FLOOR if kind == "L" else CAP for kind in pattern))
    assert len(found) == 1, found
    return found.pop()


def compositions(total: int, parts: int):  # noqa: ANN201
    if parts == 1:
        yield (total,)
        return
    for first in range(total + 1):
        for rest in compositions(total - first, parts - 1):
            yield (first, *rest)


def test_the_projection_equals_an_independent_exact_oracle_exhaustively_and_on_random_vectors() -> None:
    vectors = [
        *(tuple(F(part, 20) for part in item) for item in compositions(20, 3)),
        *(tuple(F(part, 12) for part in item) for item in compositions(12, 4)),
        *(tuple(F(part, 8) for part in item) for item in compositions(8, 5)),
    ]
    generator = random.Random(20261107)  # noqa: S311 - seeded test fixture generator, not a security primitive
    for _ in range(400):
        count = generator.choice((3, 4, 5))
        raw = [F(generator.randint(0, 997), generator.randint(1, 97)) for _ in range(count)]
        total = sum(raw)
        if total:
            vectors.append(tuple(item / total for item in raw))
    for shares in vectors:
        result = governed_paper_bounded_projection(shares)
        assert result == oracle(shares), shares
        assert sum(result) == 1 and all(FLOOR <= item <= CAP for item in result)  # P1, P2
        if all(FLOOR <= item <= CAP for item in shares):  # P3
            assert result == shares
        for i, j in itertools.permutations(range(len(shares)), 2):  # P4
            if shares[i] <= shares[j]:
                assert result[i] <= result[j]
        assert governed_paper_bounded_projection(shares) == result  # P5


@pytest.mark.parametrize(
    "shares",
    [
        [F(1, 2), F(1, 2)],
        (0.5, 0.5),
        (F(1, 2), F(1, 3)),
        (F(-1, 10), F(11, 10)),
        (F(1, 30),) * 30,
    ],
)
def test_a_malformed_or_infeasible_share_vector_is_refused(shares: object) -> None:
    with pytest.raises(GovernedPaperAllocationError):
        governed_paper_bounded_projection(shares)  # type: ignore[arg-type]


# --- B. eligibility, selection, shares and BOOST (§4.1, §4.2) ----------------------------------------------------------------


def test_n_1_is_capped_at_0_40_with_a_0_60_residual_and_n_0_allocates_nothing() -> None:
    single = derive_governed_paper_allocation((candidate("s1"),))
    assert (single.status, single.member_count, weights(single), single.residual) == (ALLOCATED, 1, [CAP], "3/5")
    assert single.weights[0].rendered == "0.400000000000000000"
    none_ = derive_governed_paper_allocation((candidate("s1", activation=FAIL_), candidate("s2", ehs="0.29")))
    assert (none_.status, none_.member_count, weights(none_)) == (NO_ALLOCATION, 0, [None, None])
    assert [(item.eligibility, item.reason) for item in none_.weights] == [
        (NON_MEMBER, "activation_proven_fail"),
        (NON_MEMBER, "edge_health_score_below_0_30_disabled"),
    ]


@pytest.mark.parametrize(
    ("unknown", "reason"),
    [
        (candidate("u", activation=UNKNOWN_ACT), "activation_unproven"),
        (candidate("u", ehs=None), "edge_health_score_undefined"),
        (candidate("u", sharpe=None), "sharpe_30d_undefined"),
    ],
)
def test_one_unknown_candidate_blocks_every_weight_and_is_never_excluded(unknown: object, reason: str) -> None:
    result = derive_governed_paper_allocation((candidate("a"), candidate("b"), candidate("c"), unknown))  # type: ignore[arg-type]
    assert (result.status, result.member_count, weights(result)) == (BLOCKED, None, [None] * 4)
    assert result.reason == "eligibility_unknown:u"
    assert [item.eligibility for item in result.weights] == [UNKNOWN] * 4  # T-ALLOC-07, T-ALLOC-08
    assert result.weights[3].reason == reason
    # an edge proven outside E_active stays NON_MEMBER even beside an unknown one
    mixed = derive_governed_paper_allocation((candidate("x", activation=FAIL_), unknown))  # type: ignore[arg-type]
    assert [item.eligibility for item in mixed.weights] == [NON_MEMBER, UNKNOWN]


def test_the_top_five_are_selected_by_score_then_higher_ehs_then_ascending_utf8_edge_id() -> None:
    # seven proven E_active edges; the fifth place ties on EHS x Sharpe between three edges
    edges = (
        candidate("e1", "0.9", "3"),
        candidate("e2", "0.8", "3"),
        candidate("e3", "0.7", "3"),
        candidate("e4", "0.6", "3"),
        candidate("b", "0.5", "3"),  # score 1.5, EHS 0.5
        candidate("a", "0.75", "2"),  # score 1.5, EHS 0.75: wins the tie on the higher EHS
        candidate("Z", "0.5", "3"),  # score 1.5, EHS 0.5: "Z" (0x5A) sorts before "b" (0x62)
    )
    result = derive_governed_paper_allocation(edges)
    eligible = {item.edge_id: (item.eligibility, item.reason) for item in result.weights}
    assert [name for name, (state, _) in eligible.items() if state is MEMBER] == ["e1", "e2", "e3", "e4", "a"]
    assert eligible["b"] == eligible["Z"] == (NON_MEMBER, "proven_outside_the_top_five")  # T-ALLOC-19
    assert result.member_count == 5 and sum(item for item in weights(result) if item is not None) == 1
    without_a = derive_governed_paper_allocation(tuple(item for item in edges if item.edge_id != "a"))
    chosen = [item.edge_id for item in without_a.weights if item.eligibility is MEMBER]
    assert chosen == ["e1", "e2", "e3", "e4", "Z"]


def test_numerators_are_clipped_at_zero_and_all_zero_numerators_share_equally() -> None:
    # numerators 1, 0, -2 (T-ALLOC-09): t = (1, 0, 0) -> 0.40, 0.30, 0.30
    result = derive_governed_paper_allocation(
        (candidate("a", "0.5", "2"), candidate("b", "0.5", "0"), candidate("c", "0.5", "-4"))
    )
    assert weights(result) == [CAP, F(3, 10), F(3, 10)]
    equal = derive_governed_paper_allocation(
        (candidate("a", "0.5", "0"), candidate("b", "0.5", "-1"), candidate("c", "0.5", "-2"))
    )
    assert weights(equal) == [F(1, 3)] * 3


def test_the_n_3_4_5_and_collision_rows_hold_through_the_share_vector() -> None:
    def shares_of(*numerators: str) -> list[GovernedPaperAllocationCandidate]:
        return [candidate(f"e{index}", "0.5", value) for index, value in enumerate(numerators)]

    cases = (
        (("1", "0.6", "0.4"), [CAP, F(7, 20), F(1, 4)]),  # T-ALLOC-04
        (("0.9", "0.9", "0.2"), [CAP, CAP, F(1, 5)]),  # T-ALLOC-11: two caps
        (("1.1", "0.5", "0.3", "0.1"), [CAP, F(3, 10), F(1, 5), F(1, 10)]),  # T-ALLOC-05
        (("0.8", "0.8", "0.38", "0.02"), [F(29, 75), F(29, 75), F(53, 300), FLOOR]),  # T-ALLOC-10
        (("1.8", "0.05", "0.05", "0.05", "0.05"), [CAP, *[F(3, 20)] * 4]),  # T-ALLOC-06
        (("1", "1", "1", "1", "1"), [F(1, 5)] * 5),
    )
    for numerators, expected in cases:
        assert weights(derive_governed_paper_allocation(tuple(shares_of(*numerators)))) == expected


def boost_world(decay: GovernedPaperAllocationDecayAlert, *, at_cap: bool) -> tuple:
    if at_cap:  # r = 0.40, 0.30, 0.30 with a proven BOOST on the first: t = 4/9, 5/18, 5/18
        return (candidate("a", "0.96", "2.5", decay=decay), candidate("b", "0.6", "3"), candidate("c", "0.6", "3"))
    # r = 0.30, 0.35, 0.35 with a proven BOOST on the first: t = 18/53, 35/106, 35/106 inside the box
    return (candidate("a", "0.9", "2", decay=decay), candidate("b", "0.7", "3"), candidate("c", "0.7", "3"))


def test_boost_keeps_its_place_before_the_projection_and_never_rises_above_the_cap() -> None:
    inside = derive_governed_paper_allocation(boost_world(INACTIVE, at_cap=False))
    assert (inside.boost, weights(inside)) == ("PROVEN", [F(18, 53), F(35, 106), F(35, 106)])
    capped = derive_governed_paper_allocation(boost_world(INACTIVE, at_cap=True))
    assert (capped.boost, weights(capped)) == ("PROVEN", [CAP, F(3, 10), F(3, 10)])  # T-ALLOC-12
    # a proven DECAY_ALERT proves the BOOST false; the weight is the pre-reduction weight (DE-WEIGHT is a SCALE-1 term)
    decayed = derive_governed_paper_allocation(boost_world(ACTIVE, at_cap=False))
    assert weights(decayed) == [F(3, 10), F(7, 20), F(7, 20)]


def test_an_unknown_boost_stands_only_when_every_value_gives_identical_weights() -> None:
    identical = derive_governed_paper_allocation(boost_world(UNKNOWN_DECAY, at_cap=True))
    assert (identical.status, identical.boost, weights(identical)) == (
        ALLOCATED,
        "IDENTICAL_UNDER_EVERY_VALUE",
        [CAP, F(3, 10), F(3, 10)],
    )
    differs = derive_governed_paper_allocation(boost_world(UNKNOWN_DECAY, at_cap=False))  # T-ALLOC-13
    assert (differs.status, differs.boost, differs.reason) == (
        BLOCKED,
        "UNRESOLVED",
        "boost_condition_unknown_and_the_weights_differ_under_its_values",
    )
    assert [item.eligibility for item in differs.weights] == [MEMBER] * 3 and weights(differs) == [None] * 3


def test_a_disabled_edge_is_removed_and_the_rest_re_projected() -> None:
    full = (candidate("a", "0.5", "1"), candidate("b", "0.5", "0.6"), candidate("c", "0.5", "0.4"))
    disabled = derive_governed_paper_allocation((*full, candidate("d", "0.29", "9")))  # T-ALLOC-15
    assert weights(disabled) == [CAP, F(7, 20), F(1, 4), None]
    assert disabled.weights[3].reason == "edge_health_score_below_0_30_disabled"


def test_the_rendering_truncates_and_never_crosses_a_bound() -> None:
    result = derive_governed_paper_allocation(
        (
            candidate("a", "0.5", "0.8"),
            candidate("b", "0.5", "0.8"),
            candidate("c", "0.5", "0.38"),
            candidate("d", "0.5", "0.02"),
        )
    )
    rendered = [item.rendered for item in result.weights]
    assert rendered == ["0.386666666666666666", "0.386666666666666666", "0.176666666666666666", "0.050000000000000000"]
    for item in result.weights:  # T-ALLOC-20
        assert FLOOR <= F(item.rendered) <= F(item.weight) <= CAP  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "candidates",
    [
        (candidate("a"), candidate("a")),
        (replace(candidate("a"), ehs="0.5"),),
        (replace(candidate("a"), ehs="1.100000000000000000"),),
        (replace(candidate("a"), activation="PASS"),),
        (replace(candidate("a"), edge_id=""),),
        [candidate("a")],
    ],
)
def test_malformed_candidates_are_refused(candidates: object) -> None:
    with pytest.raises(GovernedPaperAllocationError):
        derive_governed_paper_allocation(candidates)  # type: ignore[arg-type]


# --- C. the governed timeline ------------------------------------------------------------------------------------------------


def test_the_governed_timeline_reads_every_candidate_unknown_at_every_utc_midnight() -> None:
    timeline = derive_governed_paper_allocation_timeline(
        genesis_digest=GENESIS, candidate_edge_ids=("s1",), start_ns=G, horizon_ns=G + 3 * DAY
    )
    assert [item.instant_ns for item in timeline.rebalances] == [G, G + DAY, G + 2 * DAY]
    assert all(item.trigger == "UTC_MIDNIGHT" for item in timeline.rebalances)
    for rebalance in timeline.rebalances:
        (reading,) = rebalance.candidates
        assert (reading.activation, reading.ehs, reading.sharpe_30d, reading.decay_alert) == (
            UNKNOWN_ACT,
            None,
            None,
            UNKNOWN_DECAY,
        )
        assert reading.reading_reason == GOVERNED_PAPER_ALLOCATION_GOVERNED_READING_REASON
        assert (rebalance.result.status, rebalance.result.reason) == (BLOCKED, "eligibility_unknown:s1")
    assert (timeline.edge_state_transitions_proven, timeline.edge_state_reason) == (
        False,
        GOVERNED_PAPER_ALLOCATION_EDGE_STATE_REASON,
    )
    assert timeline.timeline_digest == governed_paper_allocation_timeline_digest(timeline)
    assert (timeline.capital_allocated, timeline.incubation_basis_available, timeline.production_use_authorized) == (
        False,
        False,
        False,
    )
    # a start off a midnight has no rebalance before the next midnight
    late = derive_governed_paper_allocation_timeline(
        genesis_digest=GENESIS, candidate_edge_ids=("s1",), start_ns=G + 1, horizon_ns=G + DAY + 1
    )
    assert [item.instant_ns for item in late.rebalances] == [G + DAY]
    before = governed_paper_allocation_reading_at(late, edge_id="s1", time_ns=G + 5)
    assert (before.eligibility, before.rebalance_ns, before.reason) == (
        UNKNOWN,
        None,
        "no_rebalance_at_or_before_the_instant",
    )
    blocked = governed_paper_allocation_reading_at(timeline, edge_id="s1", time_ns=G + DAY + 7)
    assert (blocked.eligibility, blocked.weight, blocked.rebalance_ns, blocked.reason) == (
        UNKNOWN,
        None,
        G + DAY,
        "allocation_blocked_at_the_rebalance:eligibility_unknown:s1",
    )


def test_a_proven_allocation_is_read_only_at_its_own_instant_without_an_edge_state_record() -> None:
    base = derive_governed_paper_allocation_timeline(
        genesis_digest=GENESIS, candidate_edge_ids=("s1",), start_ns=G, horizon_ns=G + 2 * DAY
    )
    member = derive_governed_paper_allocation((candidate("s1"),))
    proven = replace(base, rebalances=tuple(replace(item, result=member) for item in base.rebalances))
    at = governed_paper_allocation_reading_at(proven, edge_id="s1", time_ns=G + DAY)
    assert (at.eligibility, at.weight, at.reason) == (MEMBER, "2/5", "proven_member")
    after = governed_paper_allocation_reading_at(proven, edge_id="s1", time_ns=G + DAY + 1)
    assert (after.eligibility, after.weight, after.reason) == (
        UNKNOWN,
        None,
        "edge_state_transitions_since_the_rebalance_unproven",
    )
    recorded = replace(proven, edge_state_transitions_proven=True)
    held = governed_paper_allocation_reading_at(recorded, edge_id="s1", time_ns=G + DAY + 1)
    assert (held.eligibility, held.weight) == (MEMBER, "2/5")


@pytest.mark.parametrize(
    "changes",
    [
        {"genesis_digest": "x"},
        {"candidate_edge_ids": ()},
        {"candidate_edge_ids": ["s1"]},
        {"start_ns": -1},
        {"horizon_ns": G},
    ],
)
def test_a_malformed_timeline_input_is_refused(changes: dict[str, object]) -> None:
    arguments: dict[str, object] = {
        "genesis_digest": GENESIS,
        "candidate_edge_ids": ("s1",),
        "start_ns": G,
        "horizon_ns": G + DAY,
    }
    arguments.update(changes)
    with pytest.raises(GovernedPaperAllocationError):
        derive_governed_paper_allocation_timeline(**arguments)  # type: ignore[arg-type]


# --- D. ENVELOPE_FIT (§4.6) ------------------------------------------------------------------------------------------------


def fit(
    eligibility: GovernedPaperAllocationEligibility, weight: object, nav: object, usage: object, exact: bool = True
):  # noqa: ANN201, FBT001, FBT002
    return evaluate_governed_paper_envelope_fit(
        eligibility=eligibility,
        weight=None if weight is None else F(weight),  # type: ignore[arg-type]
        nav=None if nav is None else F(nav),  # type: ignore[arg-type]
        usage_lower=None if usage is None else F(usage),  # type: ignore[arg-type]
        usage_exact=exact,
    )


def test_a_member_passes_at_its_exact_weight_boundary_and_fails_one_unit_above() -> None:
    at = fit(MEMBER, F(2, 5), 10_000, 4_000)
    assert (at.status, at.observed, at.reason) == (
        EF_PASS,
        "0.400000000000000000",
        "member_usage_within_its_weight_times_nav",
    )
    above = fit(MEMBER, F(1, 5), 10_000, F(2_000) + UNIT)
    assert (above.status, above.reason) == (EF_FAIL, "member_usage_above_its_weight_times_nav")
    assert fit(MEMBER, F(1, 5), 10_000, 2_000).status is EF_PASS
    # an inexact usage within the weight never passes; a proven lower bound above it fails
    assert (fit(MEMBER, F(1, 5), 10_000, 1_000, exact=False).status) is EF_BLOCKED
    assert fit(MEMBER, F(1, 5), 10_000, 2_500, exact=False).status is EF_FAIL


def test_the_fixed_unit_excess_example_fails_and_is_never_resized() -> None:
    # B = 100,000, a floored weight 0.05: the envelope is 5,000 and the reservation u x L_k = 8,000 (T-ALLOC-16)
    result = fit(MEMBER, FLOOR, 100_000, 8_000)
    assert (result.status, result.observed, result.reason) == (
        EF_FAIL,
        "0.080000000000000000",
        "member_usage_above_its_weight_times_nav",
    )


def test_non_members_fail_any_positive_usage_and_any_usage_above_0_40_fails_for_every_eligibility() -> None:
    assert fit(NON_MEMBER, None, 10_000, UNIT).reason == "non_member_with_a_positive_usage"
    assert fit(NON_MEMBER, None, None, 1).status is EF_FAIL  # no NAV is needed to prove it
    unknown_within = fit(UNKNOWN, None, 10_000, 4_000)
    assert (unknown_within.status, unknown_within.reason) == (
        EF_BLOCKED,
        "eligibility_unknown_and_usage_within_0_40_of_nav",
    )
    unknown_above = fit(UNKNOWN, None, 10_000, F(4_000) + UNIT)
    assert (unknown_above.status, unknown_above.reason) == (EF_FAIL, "usage_above_0_40_of_nav_for_any_eligibility")
    assert fit(MEMBER, None, 10_000, F(4_000) + UNIT).status is EF_FAIL
    assert fit(MEMBER, None, 10_000, 4_000).reason == "member_weight_unproven"


def test_an_unproven_nav_or_usage_is_blocked() -> None:
    for nav, reason in ((None, "publication_visible_nav_unavailable"), (0, "publication_visible_nav_not_positive")):
        result = fit(MEMBER, F(2, 5), nav, 1)
        assert (result.status, result.reason) == (EF_BLOCKED, reason)
    assert fit(UNKNOWN, None, 10_000, None, exact=False).reason == "usage_unavailable"


@pytest.mark.parametrize(
    "arguments",
    [
        {"eligibility": "MEMBER"},
        {"weight": 0.4},
        {"weight": F(1, 2)},
        {"usage_lower": F(-1)},
        {"usage_exact": 1},
        {"usage_lower": None, "usage_exact": True},
    ],
)
def test_malformed_envelope_inputs_are_refused(arguments: dict[str, object]) -> None:
    base: dict[str, object] = {
        "eligibility": MEMBER,
        "weight": F(2, 5),
        "nav": F(10_000),
        "usage_lower": F(1),
        "usage_exact": True,
    }
    base.update(arguments)
    with pytest.raises(GovernedPaperAllocationError):
        evaluate_governed_paper_envelope_fit(**base)  # type: ignore[arg-type]


def test_the_module_is_pure_exact_and_offline() -> None:
    source = inspect.getsource(allocation)
    tree = ast.parse(source)
    modules = {
        alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
    }
    modules |= {
        node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    assert modules <= {
        "__future__",
        "bisect",
        "itertools",
        "collections",
        "dataclasses",
        "enum",
        "fractions",
        "crypto_core",
    }
    for forbidden in ("float(", "Decimal", "import random", "import time", "open(", "import os", "socket"):
        assert forbidden not in source
