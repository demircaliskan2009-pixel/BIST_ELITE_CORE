"""PAPER_INCUBATION_RECORD_V1 construction tests (S1_PAPER_INCUBATION_RECORD_V1_CONSTRUCTION): record, policy, registry,
lifecycle, coverage, KD-13, the schedule v9 fill, the incubation envelope and the rule set v12 decision basis.

SYNTHETIC TEST VALUES ONLY. Every record, row, basis, approval and table here is a TEST_ONLY_SYNTHETIC fixture that
exercises structure. No human approval, qualified temporal source, complete revocation view or currentness basis exists:
the production registry and policy table are empty, and production ACTIVE is unreachable (HD-INC-AUTH-1 r2 A3-A6). The
values 21, 91 and 0.08 are the human-approved r1 values the policy builder fixes, never values chosen here.
"""

from __future__ import annotations

import contextlib
import functools
from collections.abc import Iterator
from dataclasses import replace
from fractions import Fraction

import pytest

import crypto_core.validation.governed_paper_entry_safety as entry_safety
import crypto_core.validation.governed_paper_incubation as incubation_module
from crypto_core.validation.governed_paper_allocation_envelope import (
    GovernedPaperAllocationEligibility,
    GovernedPaperEnvelopeFitStatus,
    evaluate_governed_paper_envelope_fit,
    governed_paper_allocation_incubation_eligibility,
)
from crypto_core.validation.governed_paper_entry_safety import (
    GOVERNED_PAPER_ENTRY_SAFETY_INCUBATION_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_KELLY_RULE_SET_DIGEST,
    GovernedPaperEntrySafetyIncubation,
    GovernedPaperEntrySafetyKelly,
    GovernedPaperEntrySafetyStatus,
    evaluate_governed_paper_entry_safety,
    governed_paper_entry_safety_sequential_admissions,
)
from crypto_core.validation.governed_paper_incubation import (
    GOVERNED_PAPER_INCUBATION_PRODUCTION_POLICY_TABLE,
    GOVERNED_PAPER_INCUBATION_PRODUCTION_REGISTRY,
    GovernedPaperIncubationApprovalKind,
    GovernedPaperIncubationBasisKind,
    GovernedPaperIncubationContext,
    GovernedPaperIncubationDecision,
    GovernedPaperIncubationEndCause,
    GovernedPaperIncubationError,
    GovernedPaperIncubationPolicyTable,
    GovernedPaperIncubationReading,
    GovernedPaperIncubationReadingStatus,
    GovernedPaperIncubationRegistry,
    GovernedPaperIncubationState,
    build_governed_paper_incubation_approval_row,
    build_governed_paper_incubation_basis,
    build_governed_paper_incubation_end_row,
    build_governed_paper_incubation_policy,
    build_governed_paper_incubation_policy_approval,
    derive_governed_paper_incubation_evidence,
    governed_paper_incubation_prefix_digest,
    governed_paper_incubation_projection_digest,
    governed_paper_incubation_record_digest,
    governed_paper_incubation_record_for_lineage,
)
from crypto_core.validation.governed_paper_kelly_reading import (
    build_governed_paper_kelly_reading,
    governed_paper_kelly_reading_digest,
)
from crypto_core.validation.historical_execution_economics import (
    HISTORICAL_EXECUTION_INCUBATION_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    HISTORICAL_EXECUTION_KELLY_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    HistoricalExecutionEconomicsError,
    HistoricalExecutionFillOutcome,
    HistoricalExecutionIncubationWindow,
    canonical_historical_execution_admission_schedule,
    historical_execution_admission_schedule_digest,
    historical_execution_admission_schedule_to_dict,
    historical_execution_kelly_cold_start,
    historical_execution_kelly_fit,
)

try:  # the module objects pytest collects (basename import), so cached worlds are shared
    import test_governed_paper_entry_safety as est
    import test_governed_paper_kelly_reading as kr
    import test_governed_paper_risk_measurement as rmt
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_governed_paper_entry_safety as est
    from tests.crypto_core.validation import test_governed_paper_kelly_reading as kr
    from tests.crypto_core.validation import test_governed_paper_risk_measurement as rmt

F = Fraction
DAY = 86_400 * 1_000_000_000
S = GovernedPaperEntrySafetyStatus
SYNTHETIC = GovernedPaperIncubationApprovalKind.TEST_ONLY_SYNTHETIC
HUMAN = GovernedPaperIncubationApprovalKind.HUMAN_GOVERNANCE
V9 = HISTORICAL_EXECUTION_INCUBATION_ADMISSION_SCHEDULE_SCHEMA_VERSION
TEST_POLICY_TABLE = GovernedPaperIncubationPolicyTable("test_only", SYNTHETIC, ())
POLICY = build_governed_paper_incubation_policy(policy_id="synthetic-incubation-policy", policy_version="1")
APPROVAL = build_governed_paper_incubation_policy_approval(
    approval_kind=SYNTHETIC, approver_reference="test-only", approved_policy_digest=POLICY.policy_digest
)
CONTEXT = GovernedPaperIncubationContext(POLICY, APPROVAL)
DECISION_RECORD = "a" * 64

_autouse = kr._production_tables_with_exact_memos  # noqa: SLF001 - the shared exact memos of the world G helpers


@contextlib.contextmanager
def installed(registry: object, table: object = TEST_POLICY_TABLE) -> Iterator[None]:
    """A TEST-ONLY registry and policy table, installed for the block only."""

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(incubation_module, "_REGISTRY", registry)
        patch.setattr(incubation_module, "_POLICY_TABLE", table)
        yield
    assert incubation_module._REGISTRY is GOVERNED_PAPER_INCUBATION_PRODUCTION_REGISTRY  # noqa: SLF001
    assert incubation_module._POLICY_TABLE is GOVERNED_PAPER_INCUBATION_PRODUCTION_POLICY_TABLE  # noqa: SLF001


@functools.cache
def authority():  # noqa: ANN201
    """World G's genesis authority with a SYNTHETIC 200-day bootstrap horizon, so a 91-day record fits it."""

    real = est.run_and_evidence(kr.kelly_days(1)[0])[0]
    return replace(real, genesis=replace(real.genesis, bootstrap_horizon_days=200))


@functools.cache
def flat_outcome():  # noqa: ANN201
    """A governed outcome with no order of any kind (the zero-order case of U3/U4)."""

    result, world = rmt.hold_v2()
    outcome = kr.governed(result, kr.hold_schedule(world, "SHORT", kr.V7))
    return replace(outcome, intents=(), protective_attempts=(), protective_children=())


def g0() -> int:
    return authority().genesis.genesis_start_ns


def record(covered: tuple[str, ...] = ("U3", "U4", "U5"), start: int | None = None, **changes: object):  # noqa: ANN201
    base = governed_paper_incubation_record_for_lineage(
        authority(), covered=covered, start_ns=g0() + DAY if start is None else start
    )
    if not changes:
        return base
    changed = replace(base, **changes)
    return replace(changed, record_digest=governed_paper_incubation_record_digest(changed))


def approval_row(item: object, published: int | None = None, approved: int | None = None):  # noqa: ANN201
    return build_governed_paper_incubation_approval_row(
        record=item,  # type: ignore[arg-type]
        approval_kind=SYNTHETIC,
        approver_reference="test-only",
        approval_time_ns=g0() if approved is None else approved,
        decision_record_digest=DECISION_RECORD,
        published_at_ns=g0() if published is None else published,
    )


def end_row(item: object, cause: GovernedPaperIncubationEndCause, at: int):  # noqa: ANN201
    return build_governed_paper_incubation_end_row(
        lineage_genesis_digest=item.genesis_digest,  # type: ignore[attr-defined]
        edge_id=item.edge_id,  # type: ignore[attr-defined]
        record_digest=item.record_digest,  # type: ignore[attr-defined]
        end_cause=cause,
        effective_at_ns=at,
        approval_kind=SYNTHETIC,
        approver_reference="test-only",
        approval_time_ns=at,
        decision_record_digest=DECISION_RECORD,
        published_at_ns=at,
    )


def bases(item: object, kinds: tuple = tuple(GovernedPaperIncubationBasisKind), until: int | None = None) -> tuple:
    return tuple(
        build_governed_paper_incubation_basis(
            basis_kind=kind,
            record_digest=item.record_digest,  # type: ignore[attr-defined]
            valid_from_ns=g0(),
            valid_until_ns=g0() + 400 * DAY if until is None else until,
            basis_reference=f"test-only-{kind.value.lower()}",
        )
        for kind in kinds
    )


def registry(rows: tuple = (), basis: tuple = ()) -> GovernedPaperIncubationRegistry:
    return GovernedPaperIncubationRegistry("test_only", SYNTHETIC, rows, basis)


def derive(decisions: tuple, admissions: tuple = (), kelly: object = None, outcome: object = None):  # noqa: ANN201
    return derive_governed_paper_incubation_evidence(
        context=CONTEXT,
        authority=authority(),
        decisions=decisions,
        incubation_admissions=admissions,
        outcome=flat_outcome() if outcome is None else outcome,
        kelly=kelly,
        horizon_ns=g0() + 300 * DAY,
    )


def states(evidence: object) -> list[tuple[str, str]]:
    return [(item.state.value, item.state_reason) for item in evidence.decisions]  # type: ignore[attr-defined]


def active_registry(item: object | None = None, extra: tuple = ()) -> GovernedPaperIncubationRegistry:
    item = record() if item is None else item
    return registry((approval_row(item), *extra), bases(item))


# --- the policy and the record ----------------------------------------------------------------------------------------


def test_the_policy_fixes_the_approved_r1_values_and_refuses_any_other() -> None:
    assert (POLICY.attempt_bound, POLICY.duration_bound_days, POLICY.envelope_fraction) == (21, 91, "2/25")
    assert POLICY.readings == ("U1", "U2", "U3", "U4", "U5")
    forged = replace(POLICY, attempt_bound=22)
    with pytest.raises(GovernedPaperIncubationError, match="policy_not_canonical"):
        incubation_module.governed_paper_incubation_canonical_context(GovernedPaperIncubationContext(forged, APPROVAL))


def test_the_production_tables_admit_nothing_and_a_synthetic_approval_is_refused_there() -> None:
    assert GOVERNED_PAPER_INCUBATION_PRODUCTION_REGISTRY.rows == ()
    assert GOVERNED_PAPER_INCUBATION_PRODUCTION_REGISTRY.bases == ()
    assert incubation_module.governed_paper_incubation_policy_admission(POLICY, APPROVAL) == (
        "synthetic_policy_approval_refused_on_the_production_table"
    )
    human = build_governed_paper_incubation_policy_approval(
        approval_kind=HUMAN, approver_reference="unlisted", approved_policy_digest=POLICY.policy_digest
    )
    assert incubation_module.governed_paper_incubation_policy_admission(POLICY, human) == (
        "policy_approval_not_authorized_for_production_use"
    )
    with installed(registry()):
        assert incubation_module.governed_paper_incubation_policy_admission(POLICY, human) == (
            "only_test_only_synthetic_policy_approvals_on_the_test_only_table"
        )
        assert incubation_module.governed_paper_incubation_policy_admission(POLICY, APPROVAL) == ""


def test_the_production_registry_admits_no_unqualified_basis_and_no_synthetic_row() -> None:
    item = record()
    with pytest.raises(GovernedPaperIncubationError, match="production_registry_admits_no_unqualified_basis"):
        incubation_module._canonical_registry(  # noqa: SLF001
            GovernedPaperIncubationRegistry("production", HUMAN, (), bases(item))
        )
    with pytest.raises(GovernedPaperIncubationError, match="approval_kind_not_admitted_by_the_registry"):
        incubation_module._canonical_registry(  # noqa: SLF001
            GovernedPaperIncubationRegistry("production", HUMAN, (approval_row(item),), ())
        )


def test_the_record_digest_covers_every_supplied_field_and_excludes_the_end() -> None:
    item = record()
    assert governed_paper_incubation_record_digest(item) == item.record_digest
    assert not hasattr(item, "end_ns")
    for name, value in (("start_ns", item.start_ns + 1), ("covered", ("U5",)), ("trial_chain_digest", "b" * 64)):
        moved = replace(item, **{name: value})
        assert governed_paper_incubation_record_digest(moved) != item.record_digest, name


# --- the registry --------------------------------------------------------------------------------------------------------


def test_rows_are_append_ordered_digest_bound_and_never_retroactive() -> None:
    item = record()
    row = approval_row(item)
    with pytest.raises(GovernedPaperIncubationError, match="registry_row_digest_mismatch"):
        incubation_module._canonical_registry(registry((replace(row, published_at_ns=row.published_at_ns + 1),)))  # noqa: SLF001
    later = approval_row(item, published=g0() + 5)
    with pytest.raises(GovernedPaperIncubationError, match="not_append_ordered"):
        incubation_module._canonical_registry(registry((later, row)))  # noqa: SLF001
    with pytest.raises(GovernedPaperIncubationError, match="published_before_its_approval"):
        incubation_module._canonical_registry(registry((approval_row(item, published=g0(), approved=g0() + 1),)))  # noqa: SLF001
    retro = end_row(item, GovernedPaperIncubationEndCause.REVOKED, g0() + 10)
    retro = replace(retro, effective_at_ns=g0() + 5)
    retro = replace(retro, row_digest=incubation_module.governed_paper_incubation_row_digest(retro))
    with pytest.raises(GovernedPaperIncubationError, match="malformed_or_retroactive"):
        incubation_module._canonical_registry(registry((row, retro)))  # noqa: SLF001


def test_the_projection_moves_with_the_keys_rows_only_and_never_with_a_later_row() -> None:
    item = record()
    early = registry((approval_row(item),), bases(item))
    later = registry((approval_row(item), end_row(item, GovernedPaperIncubationEndCause.REVOKED, g0() + 10 * DAY)))
    key = {"lineage_genesis_digest": item.genesis_digest, "edge_id": item.edge_id}
    assert governed_paper_incubation_projection_digest(early, before_ns=g0() + DAY, **key) != (
        governed_paper_incubation_projection_digest(registry(), before_ns=g0() + DAY, **key)
    )
    # a row published after the instant never enters the projection before it
    assert governed_paper_incubation_projection_digest(
        later, before_ns=g0() + DAY, **key
    ) == governed_paper_incubation_projection_digest(registry((approval_row(item),)), before_ns=g0() + DAY, **key)
    foreign = {"lineage_genesis_digest": "c" * 64, "edge_id": item.edge_id}
    assert governed_paper_incubation_projection_digest(
        early, before_ns=g0() + DAY, **foreign
    ) == governed_paper_incubation_projection_digest(registry(), before_ns=g0() + DAY, **foreign)


# --- the lifecycle -------------------------------------------------------------------------------------------------------


def test_no_record_no_policy_approval_and_the_production_registry_never_give_a_basis() -> None:
    decisions = ((1, g0() + 2 * DAY, True),)
    with installed(registry()):
        assert states(derive(decisions)) == [("NOT_ESTABLISHED", "incubation_record_absent")]
    with installed(active_registry(), GOVERNED_PAPER_INCUBATION_PRODUCTION_POLICY_TABLE):
        (state,) = states(derive(decisions))
        assert state[0] == "NOT_ESTABLISHED" and state[1].startswith("incubation_policy_not_admitted")
    evidence = derive(decisions)  # the production registry and table
    assert states(evidence)[0][0] == "NOT_ESTABLISHED" and evidence.fill_windows == ()
    assert (evidence.registry_id, evidence.policy_admitted) == ("production", False)


def test_active_needs_every_r2_basis_covering_the_instant_unknown_is_never_final() -> None:  # O1
    item = record()
    decisions = ((1, g0() + 2 * DAY, True), (2, g0() + 3 * DAY, True))
    for missing in GovernedPaperIncubationBasisKind:
        kinds = tuple(kind for kind in GovernedPaperIncubationBasisKind if kind is not missing)
        with installed(registry((approval_row(item),), bases(item, kinds))):
            evidence = derive(decisions)
        assert [state for state, _ in states(evidence)] == ["NOT_ESTABLISHED"] * 2
        assert missing.value in evidence.decisions[0].state_reason
        # UNKNOWN currentness is never terminal by itself: the only final transition is the record's own end X
        assert (evidence.final_state, evidence.final_at_ns) == (
            GovernedPaperIncubationState.EXPIRED_HOLD,
            evidence.end_ns,
        )
        assert evidence.final_reason == "incubation_expired" and evidence.fill_windows == ()
    with installed(registry((approval_row(item),), bases(item, until=g0() + 3 * DAY))):
        assert [state for state, _ in states(derive(decisions))] == ["ACTIVE", "NOT_ESTABLISHED"]


def test_the_start_the_end_and_the_horizon_bound_the_record_exactly() -> None:  # T-INC-04, T-INC-17, T-INC-20
    item = record()
    start, end = item.start_ns, item.start_ns + 91 * DAY
    decisions = ((1, start - 1, True), (2, start, True), (3, end - 1, True), (4, end, True))
    with installed(active_registry(item)):
        evidence = derive(decisions)
    assert [state for state, _ in states(evidence)] == ["NOT_ESTABLISHED", "ACTIVE", "ACTIVE", "EXPIRED_HOLD"]
    assert evidence.end_ns == end and evidence.fill_windows == (HistoricalExecutionIncubationWindow(start, end),)
    long = replace(authority(), genesis=replace(authority().genesis, bootstrap_horizon_days=91))
    short = governed_paper_incubation_record_for_lineage(long, covered=("U5",), start_ns=g0() + DAY)
    with installed(registry((approval_row(short),), bases(short))):
        evidence = derive_governed_paper_incubation_evidence(
            context=CONTEXT,
            authority=long,
            decisions=((1, g0() + 2 * DAY, True),),
            incubation_admissions=(),
            outcome=flat_outcome(),
            kelly=None,
            horizon_ns=g0() + 300 * DAY,
        )
    assert states(evidence) == [("TERMINATED", "incubation_horizon_exceeds_lineage")]


def test_a_record_that_does_not_bind_the_lineage_or_was_approved_late_terminates() -> None:  # T-INC-03
    cases = {
        "incubation_record_trial_chain_digest_mismatch": record(trial_chain_digest="b" * 64),
        "incubation_record_attempt_bound_mismatch": record(attempt_bound=20),
        "incubation_record_edge_id_mismatch": record(edge_id="another-edge"),
        "incubation_class_not_covered": record(covered=("U6",)),
    }
    for reason, item in cases.items():
        key_item = replace(item, edge_id=record().edge_id) if reason == "incubation_record_edge_id_mismatch" else item
        row = approval_row(item)
        row = replace(row, edge_id=key_item.edge_id)
        row = replace(row, row_digest=incubation_module.governed_paper_incubation_row_digest(row))
        with installed(registry((row,), bases(item))):
            assert states(derive(((1, g0() + 2 * DAY, True),))) == [("TERMINATED", reason)], reason
    late = record()
    with installed(
        registry((approval_row(late, published=late.start_ns + 1, approved=late.start_ns + 1),), bases(late))
    ):
        assert states(derive(((1, late.start_ns + 2, True),))) == [
            ("TERMINATED", "incubation_record_approved_after_its_start")
        ]


def test_revocation_proven_loss_duplicates_and_adverse_signals_follow_o1_and_finals_never_resurrect() -> None:
    item = record()
    t = item.start_ns
    decisions = tuple((index, t + index * DAY, True) for index in range(1, 6))
    cases = (
        (GovernedPaperIncubationEndCause.REVOKED, ["ACTIVE", "ACTIVE", "REVOKED", "REVOKED", "REVOKED"]),
        (
            GovernedPaperIncubationEndCause.VALIDATION_NOT_CURRENT,
            ["ACTIVE", "ACTIVE", "TERMINATED", "TERMINATED", "TERMINATED"],
        ),
        (
            GovernedPaperIncubationEndCause.ADVERSE_SIGNAL,
            ["ACTIVE", "ACTIVE", "NOT_ESTABLISHED", "NOT_ESTABLISHED", "NOT_ESTABLISHED"],
        ),
    )
    for cause, expected in cases:
        with installed(active_registry(item, (end_row(item, cause, t + 3 * DAY),))):
            evidence = derive(decisions)
        assert [state for state, _ in states(evidence)] == expected, cause
        assert evidence.fill_windows == (HistoricalExecutionIncubationWindow(t, t + 3 * DAY),)
    # REVOKED first, then a duplicate approval: the earlier final state is never relabelled
    duplicate = approval_row(record(covered=("U5",)), published=t + 4 * DAY, approved=t)
    with installed(
        active_registry(item, (end_row(item, GovernedPaperIncubationEndCause.REVOKED, t + 3 * DAY), duplicate))
    ):
        assert [state for state, _ in states(derive(decisions))][-1] == "REVOKED"
    with installed(active_registry(item, (duplicate,))):  # T-INC-15: a second approval terminates the live record
        assert states(derive(decisions))[-1] == ("TERMINATED", "incubation_duplicate_record")


def test_attempts_count_at_admission_and_the_21st_exhausts_the_record_and_its_fill_window() -> None:  # T-INC-05, I14
    item = record()
    t = item.start_ns
    decisions = tuple((index, t + index, True) for index in range(1, 24))
    admitted = tuple(range(1, 22))
    with installed(active_registry(item)):
        evidence = derive(decisions, admitted)
    assert [item.attempts_before for item in evidence.decisions][:22] == list(range(22))
    assert [state for state, _ in states(evidence)][20:] == ["ACTIVE", "EXPIRED_HOLD", "EXPIRED_HOLD"]
    assert evidence.final_state is GovernedPaperIncubationState.EXPIRED_HOLD
    # no permission survives the end: the window closes right after the 21st admission, before its own fill
    assert evidence.fill_windows == (HistoricalExecutionIncubationWindow(t, t + 21 + 1),)
    assert evidence.incubation_entry_decision_sequences == admitted


def test_coverage_u1_u2_are_blocked_u3_u4_only_at_zero_orders_and_u5_until_class_completion() -> None:
    item = record(covered=("U1", "U2", "U3", "U4", "U5"))
    t = item.start_ns
    with installed(active_registry(item)):
        decision = derive(((1, t + 1, True),)).decisions[0]
        result, world = rmt.hold_v2()
        ordered = kr.governed(result, kr.hold_schedule(world, "SHORT", kr.V7))
        with_orders = derive(((1, ordered.intents[0].decision_time_ns + 1, True),), outcome=ordered).decisions[0]
    status = {reading.reading_id: (reading.status.value, reading.reason) for reading in decision.readings}
    assert status["U1"] == ("BLOCKED", "own_history_method_unapproved:FCD-13")
    assert status["U2"] == ("BLOCKED", "own_history_method_unapproved:FCD-13")
    assert status["U3"] == status["U4"] == ("COVERED", "no_order_sent")
    assert status["U5"] == ("COVERED", "kelly_class_incomplete")
    if with_orders.state is GovernedPaperIncubationState.ACTIVE:
        after = {reading.reading_id: reading.status for reading in with_orders.readings}
        assert after["U3"] is after["U4"] is GovernedPaperIncubationReadingStatus.BLOCKED


def test_the_prefix_is_run_independent_and_excludes_later_decisions_and_finals() -> None:
    item = record()
    t = item.start_ns
    with installed(active_registry(item, (end_row(item, GovernedPaperIncubationEndCause.REVOKED, t + 3 * DAY),))):
        short = derive(((1, t + DAY, True),))
        long = derive(((1, t + DAY, True), (2, t + 4 * DAY, True)))
    assert governed_paper_incubation_prefix_digest(short, before_ns=t + 2 * DAY) == (
        governed_paper_incubation_prefix_digest(long, before_ns=t + 2 * DAY)
    )
    assert governed_paper_incubation_prefix_digest(long, before_ns=t + 5 * DAY) != (
        governed_paper_incubation_prefix_digest(long, before_ns=t + 2 * DAY)
    )


def test_duplicate_or_unordered_observations_are_refused() -> None:  # T-INC-16
    with installed(registry()):
        with pytest.raises(GovernedPaperIncubationError, match="decisions_duplicated"):
            derive(((1, g0() + DAY, True), (1, g0() + 2 * DAY, True)))
        with pytest.raises(GovernedPaperIncubationError, match="decisions_not_in_time_order"):
            derive(((1, g0() + 2 * DAY, True), (2, g0() + DAY, True)))


# --- KD-13 and the schedule v9 fill --------------------------------------------------------------------------------------


def test_kd13_covers_only_class_incomplete_history_and_fail_dominates() -> None:  # T-KCW-01..12 at the arithmetic
    def kd13(trades: list, rho: object) -> tuple[str, str]:
        return historical_execution_kelly_cold_start(
            historical_execution_kelly_fit(trades, unknown_count=0, rho=rho), rho
        )

    assert kd13([], F(1, 25)) == ("COLD_START_EXCEPTED", "")  # equality at 0.04 admits
    assert kd13([], F(1, 25) + F(1, 10**30)) == ("FAIL", "KELLY_COLD_START_CAP_EXCEEDED")
    assert kd13([(F(1), F(1))], F(1, 50)) == ("COLD_START_EXCEPTED", "")  # a first win: still covered
    assert kd13([(F(0), F(1))], F(1, 50)) == ("COLD_START_EXCEPTED", "")  # a zero completes no class
    assert kd13([(F(-1), F(1)), (F(-1), F(1))], F(1, 50)) == ("FAIL", "KELLY_LOG_UTILITY_NON_POSITIVE")
    assert kd13([(F(-60), F(1))], F(1, 50)) == ("FAIL", "KELLY_LOG_DOMAIN_RUIN")
    assert kd13([(F(1), None)], F(1, 50)) == ("BLOCKED", "KELLY_OUTCOME_UNPROVEN")
    assert kd13([], None) == ("BLOCKED", "KELLY_RISK_FRACTION_UNPROVEN")
    assert kd13([(F(1), F(1)), (F(-1), F(1))], F(1, 50)) == ("NOT_COVERED", "KELLY_CLASS_COMPLETE")
    unknown = historical_execution_kelly_fit([], unknown_count=1, rho=F(1, 50))
    assert historical_execution_kelly_cold_start(unknown, F(1, 50)) == ("BLOCKED", "KELLY_TRADE_COUNT_UNPROVEN")


def v9_schedule(world: object, direction: str, **changes: object):  # noqa: ANN201
    return replace(kr.hold_schedule(world, direction, V9), **changes)


def test_schedule_v9_admits_a_covered_first_fill_only_for_a_declared_entry_inside_a_window() -> None:  # F5, I13, I14
    for (result, world), direction in ((rmt.hold_v2(), "SHORT"), (kr.long_v2(), "LONG")):
        v7 = kr.governed(result, kr.hold_schedule(world, direction, kr.V7))
        fill = rmt.entry_fill(v7)
        sequence = next(item.decision_sequence for item in v7.intents if item.intent_id == fill.intent_id)
        decided = next(item.decision_time_ns for item in v7.intents if item.intent_id == fill.intent_id)
        window = (HistoricalExecutionIncubationWindow(0, 2**62),)
        admitted = kr.governed(
            result,
            v9_schedule(
                world,
                direction,
                incubation_entry_decision_sequences=(sequence,),
                kelly_cold_start_cover=True,
                incubation_fill_windows=window,
            ),
        )
        assert rmt.entry_fill(admitted).outcome is HistoricalExecutionFillOutcome.FILLED, direction
        refusals = {
            "undeclared": {"incubation_fill_windows": window, "kelly_cold_start_cover": True},
            "uncovered": {"incubation_entry_decision_sequences": (sequence,), "incubation_fill_windows": window},
            "window_ended": {
                "incubation_entry_decision_sequences": (sequence,),
                "kelly_cold_start_cover": True,
                "incubation_fill_windows": (HistoricalExecutionIncubationWindow(0, decided + 1),),
            },
        }
        for name, changes in refusals.items():
            refused = rmt.entry_fill(kr.governed(result, v9_schedule(world, direction, **changes)))
            assert (refused.outcome, refused.reason) == (
                HistoricalExecutionFillOutcome.REJECTED,
                "governed_paper_kelly_unproven_at_fill",
            ), (direction, name)


def test_schedule_v9_fields_are_v9_only_and_never_in_a_legacy_payload() -> None:  # F6
    _, world = rmt.hold_v2()
    v8 = kr.hold_schedule(world, "SHORT")
    assert v8.schema_version == HISTORICAL_EXECUTION_KELLY_ADMISSION_SCHEDULE_SCHEMA_VERSION
    assert not {"incubation_entry_decision_sequences", "kelly_cold_start_cover", "incubation_fill_windows"} & set(
        historical_execution_admission_schedule_to_dict(v8)
    )
    with pytest.raises(HistoricalExecutionEconomicsError, match="incubation_bounds_need_schema_v9"):
        canonical_historical_execution_admission_schedule(replace(v8, kelly_cold_start_cover=True))
    v9 = v9_schedule(world, "SHORT", incubation_entry_decision_sequences=(3, 1))
    with pytest.raises(HistoricalExecutionEconomicsError, match="not_strictly_increasing"):
        canonical_historical_execution_admission_schedule(v9)
    clash = v9_schedule(world, "SHORT", entry_refused_decision_sequences=(1,), incubation_entry_decision_sequences=(1,))
    with pytest.raises(HistoricalExecutionEconomicsError, match="incubation_entry_also_refused"):
        canonical_historical_execution_admission_schedule(clash)
    assert historical_execution_admission_schedule_digest(v9_schedule(world, "SHORT")) != (
        historical_execution_admission_schedule_digest(v8)
    )


# --- the incubation envelope ----------------------------------------------------------------------------------------------


def test_incubation_member_needs_every_section_4_1_condition() -> None:
    names = (
        "record_active",
        "activation_only_non_pass_leg_is_u4",
        "ehs_only_undefined_input_is_u1",
        "u4_cold_start_excepted",
        "u1_cold_start_excepted",
    )
    full = dict.fromkeys(names, True)
    assert governed_paper_allocation_incubation_eligibility(candidate_count=1, **full) is (
        GovernedPaperAllocationEligibility.INCUBATION_MEMBER
    )
    assert governed_paper_allocation_incubation_eligibility(candidate_count=2, **full) is (
        GovernedPaperAllocationEligibility.UNKNOWN
    )
    for name in names:
        assert governed_paper_allocation_incubation_eligibility(candidate_count=1, **(full | {name: False})) is (
            GovernedPaperAllocationEligibility.UNKNOWN
        ), name


def test_the_incubation_envelope_admits_equality_fails_above_and_keeps_the_hard_cap() -> None:
    def fit(usage: object, exact: bool = True, nav: object = F(1000)):  # noqa: ANN202, FBT001, FBT002
        return evaluate_governed_paper_envelope_fit(
            eligibility=GovernedPaperAllocationEligibility.INCUBATION_MEMBER,
            weight=None,
            nav=nav,
            usage_lower=usage,
            usage_exact=exact,
            incubation_fraction=F(2, 25),
        )

    assert fit(F(80)).status is GovernedPaperEnvelopeFitStatus.COLD_START_EXCEPTED
    assert fit(F(80) + F(1, 10**20)).status is GovernedPaperEnvelopeFitStatus.FAIL
    assert fit(F(10), exact=False).status is GovernedPaperEnvelopeFitStatus.BLOCKED
    assert fit(F(10), nav=None).status is GovernedPaperEnvelopeFitStatus.BLOCKED
    assert fit(F(500)).reason == "usage_above_0_40_of_nav_for_any_eligibility"
    with pytest.raises(Exception, match="incubation_member_needs_w_inc_and_no_weight"):
        evaluate_governed_paper_envelope_fit(
            eligibility=GovernedPaperAllocationEligibility.INCUBATION_MEMBER,
            weight=F(1, 10),
            nav=F(1000),
            usage_lower=F(1),
            usage_exact=True,
            incubation_fraction=F(2, 25),
        )


# --- the rule set v12 decision -----------------------------------------------------------------------------------------


def facts(state: str = "ACTIVE", increasing: bool = True, u3: str = "COVERED", attempts: int = 0):  # noqa: ANN201, FBT001, FBT002
    readings = tuple(
        GovernedPaperIncubationReading(
            reading,
            GovernedPaperIncubationReadingStatus(u3 if reading == "U3" else "NOT_SELECTED"),
            "",
        )
        for reading in ("U1", "U2", "U3", "U4", "U5")
    )
    decision = GovernedPaperIncubationDecision(
        decision_sequence=7,
        decision_time_ns=est.T,
        exposure_increasing=increasing,
        state=GovernedPaperIncubationState(state),
        state_reason="",
        attempts_before=attempts,
        readings=readings,
        kelly_cold_start_status="",
        kelly_cold_start_reason="",
    )
    return GovernedPaperEntrySafetyIncubation(decision, "e" * 64, "f" * 64)


def observation(**incubation: object):  # noqa: ANN201
    reading = build_governed_paper_kelly_reading(
        decision_sequence=7,
        decision_time_ns=est.T,
        target_direction="SHORT",
        trades=(),
        rho=F(1, 30),
        rho_reason="",
        cold_start=True,
    )
    assert reading.cold_start_status == "COLD_START_EXCEPTED"
    assert governed_paper_kelly_reading_digest(reading) == reading.reading_digest
    return replace(rmt.v10(), kelly=GovernedPaperEntrySafetyKelly(reading, "d" * 64), incubation=facts(**incubation))


def _pass(_: object) -> object:
    return entry_safety._Outcome(S.PASS, "", "test_only_pass")  # noqa: SLF001


def _fail(_: object) -> object:
    return entry_safety._Outcome(S.FAIL, "", "test_only_fail")  # noqa: SLF001


@contextlib.contextmanager
def checks(*extra: object) -> Iterator[None]:
    """A TEST-ONLY check table: one permissive check, the real NT-X02 and any ``extra`` checks (SYNTHETIC)."""

    real = next(item for item in entry_safety._CHECKS if item.check_id == "NT-X02")  # noqa: SLF001
    permissive = entry_safety._Check("TEST-PASS", entry_safety._Family.DATA, "test", "test", _pass)  # noqa: SLF001
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(entry_safety, "_CHECKS", (permissive, real, *extra))
        patch.setattr(entry_safety, "_REGIME_CHECKS", ())
        patch.setattr(entry_safety, "_RISK_MEASUREMENT_CHECKS", ())
        yield


def test_nt_x02_is_cold_start_excepted_only_while_u3_is_covered() -> None:
    covered = evaluate_governed_paper_entry_safety(observation())
    assert est.check_of(covered, "NT-X02").status is S.COLD_START_EXCEPTED
    blocked = evaluate_governed_paper_entry_safety(observation(u3="BLOCKED"))
    assert est.check_of(blocked, "NT-X02").status is S.BLOCKED_ON_MISSING_INPUT
    legacy = evaluate_governed_paper_entry_safety(replace(observation(), incubation=None))
    assert est.check_of(legacy, "NT-X02").status is S.BLOCKED_ON_MISSING_INPUT
    assert legacy.basis == "" and "basis" not in entry_safety._to_payload(legacy)  # noqa: SLF001


def test_scale_1_reads_kd13_under_u5_coverage_and_stays_blocked_on_every_other_unproven_term() -> None:
    covered = replace(
        observation(),
        incubation=replace(
            facts(),
            decision=replace(
                facts().decision,
                readings=tuple(
                    replace(item, status=GovernedPaperIncubationReadingStatus.COVERED)
                    if item.reading_id == "U5"
                    else item
                    for item in facts().decision.readings
                ),
            ),
        ),
    )
    terms = dict((name, status) for name, status, _ in entry_safety.governed_paper_entry_safety_a9_multipliers(covered))
    assert terms["kelly_fit_1_28"] == "COLD_START_EXCEPTED"
    assert terms["edge_health_alpha_1_6"] == "UNPROVEN"  # U1 never covered while FCD-13 is pending
    scale = est.check_of(evaluate_governed_paper_entry_safety(covered), "SCALE-1")
    assert scale.status not in (S.PASS, S.COLD_START_EXCEPTED)  # an unproven or reduced term always binds


def test_the_basis_is_ordinary_incubation_or_refused_and_fail_dominates() -> None:  # T-INC-08, T-INC-14
    failing = entry_safety._Check("TEST-FAIL", entry_safety._Family.RISK, "test", "test", _fail)  # noqa: SLF001
    with checks():
        incubated = evaluate_governed_paper_entry_safety(observation(attempts=20))
        ordinary = evaluate_governed_paper_entry_safety(observation(u3="BLOCKED"))
        inactive = evaluate_governed_paper_entry_safety(observation(state="NOT_ESTABLISHED", u3="BLOCKED"))
        reduction = evaluate_governed_paper_entry_safety(observation(increasing=False))
    assert (incubated.entry_permitted, incubated.basis, incubated.incubation_attempt_index) == (True, "INCUBATION", 21)
    assert incubated.incubation_record_digest == "f" * 64  # the record, never the evidence digest
    assert (ordinary.entry_permitted, ordinary.basis) == (False, "REFUSED")  # NT-X02 ordinary BLOCKED refuses
    assert (inactive.entry_permitted, inactive.first_failure_check_id) == (False, "NT-X02")
    assert (reduction.entry_permitted, reduction.basis) == (False, "REFUSED")
    assert "cold_start_exception_without_an_active_incubation_entry" in reduction.first_failure_reason
    with checks(failing):
        failed = evaluate_governed_paper_entry_safety(observation())
    assert (failed.entry_permitted, failed.basis, failed.first_failure_check_id) == (False, "REFUSED", "TEST-FAIL")
    payload = entry_safety._to_payload(incubated)  # noqa: SLF001
    assert (payload["basis"], payload["incubation_attempt_index"]) == ("INCUBATION", 21)
    permissive = entry_safety._Check("TEST-PASS-2", entry_safety._Family.DATA, "t", "t", _pass)  # noqa: SLF001
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(entry_safety, "_CHECKS", (permissive,))
        patch.setattr(entry_safety, "_REGIME_CHECKS", ())
        patch.setattr(entry_safety, "_RISK_MEASUREMENT_CHECKS", ())
        plain = evaluate_governed_paper_entry_safety(observation())
    assert (plain.entry_permitted, plain.basis) == (True, "ORDINARY")


def test_rule_set_v12_is_a_new_identity_and_v11_keeps_its_accepted_one() -> None:
    assert GOVERNED_PAPER_ENTRY_SAFETY_KELLY_RULE_SET_DIGEST == (
        "4c5d6e8612b8957ac97f5064a8dbba39f8b3571421a0154b27d73b5a2780cb21"  # accepted main 523c140e, pinned first
    )
    assert GOVERNED_PAPER_ENTRY_SAFETY_INCUBATION_RULE_SET_DIGEST != GOVERNED_PAPER_ENTRY_SAFETY_KELLY_RULE_SET_DIGEST
    rule_set = entry_safety.governed_paper_entry_safety_rule_set(
        protective=True,
        portfolio=True,
        market_data=True,
        kill_switch=True,
        regime=True,
        system_safety=True,
        sizing_chain=True,
        protective_ledger=True,
        risk_measurement=True,
        kelly=True,
        incubation=True,
    )
    assert rule_set["rule_set_id"] == "governed-paper-entry-safety.v12"
    with pytest.raises(entry_safety.GovernedPaperEntrySafetyError, match="needs_the_kelly_rule_set"):
        entry_safety.governed_paper_entry_safety_rule_set(incubation=True)


# --- the causal fixed point ------------------------------------------------------------------------------------------------


def test_the_sequential_admission_settles_on_the_unique_causal_fixed_point() -> None:  # INV-CAUSAL
    entries = (1, 2, 3, 4, 5)
    calls: list[tuple] = []

    def causal(state: tuple) -> tuple:
        """SYNTHETIC: entry k is admitted on the incubation basis iff fewer than 2 earlier entries were, else refused."""

        calls.append(state)
        refused, admitted, _, _ = state
        out_refused, out_admitted = [], []
        for entry in entries:
            earlier = [item for item in admitted if item < entry]
            (out_admitted if len(earlier) < 2 else out_refused).append(entry)  # noqa: PLR2004
        return tuple(out_refused), tuple(out_admitted), (), True

    state = governed_paper_entry_safety_sequential_admissions(entries, causal)
    assert state == ((3, 4, 5), (1, 2), (), True)
    assert len(calls) <= len(entries) + 2

    def oscillating(state: tuple) -> tuple:
        return (state[1], state[0], (), False)

    with pytest.raises(entry_safety.GovernedPaperEntrySafetyError, match="sequential_admission_not_converged"):
        governed_paper_entry_safety_sequential_admissions((1, 2), oscillating)
