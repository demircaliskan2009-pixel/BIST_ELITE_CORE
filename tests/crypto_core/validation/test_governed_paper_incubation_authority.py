"""S1_TEMPORAL_AUTHORITY_UNIFIED_CONSTRUCTION_V1: the one point-in-time incubation authority, schedule v9 and rule set v12.

The authority tests run on a SYNTHETIC lineage-edge key with a 200-day bootstrap horizon (H = 200, the public builder's
own input type) under a TEST-ONLY table installed per test; the production table admits nothing. The three inherited
blocker identities are regression-tested by name:

* B1 ``INCUBATION_FUTURE_APPROVAL_REWRITES_PAST``;
* B2 ``INCUBATION_KNOWN_SIGNAL_BLOCK_DELAYED_UNTIL_EFFECTIVE_TIME``;
* B3 ``INCUBATION_ACTIVE_WITH_EMPTY_FILL_WINDOW``.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from dataclasses import replace
from fractions import Fraction

import pytest

import crypto_core.validation.governed_paper_entry_safety as gate
import crypto_core.validation.governed_paper_incubation_authority as inc
import crypto_core.validation.historical_execution_economics as economics
from crypto_core.validation.governed_paper_entry_safety import (
    GOVERNED_PAPER_ENTRY_SAFETY_INCUBATION_RULE_SET,
    GOVERNED_PAPER_ENTRY_SAFETY_INCUBATION_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_INCUBATION_RULE_SET_ID,
    GOVERNED_PAPER_ENTRY_SAFETY_KELLY_RULE_SET,
    GOVERNED_PAPER_ENTRY_SAFETY_KELLY_RULE_SET_DIGEST,
    GovernedPaperEntrySafetyError,
    GovernedPaperEntrySafetyIncubation,
    GovernedPaperEntrySafetyKelly,
    GovernedPaperEntrySafetyStatus,
    evaluate_governed_paper_entry_safety,
    governed_paper_entry_safety_a9_multipliers,
    governed_paper_entry_safety_incubation_basis,
    governed_paper_entry_safety_rule_set,
)
from crypto_core.validation.governed_paper_incubation_authority import (
    GOVERNED_PAPER_INCUBATION_PRODUCTION_TABLE,
    GovernedPaperIncubationBasis,
    GovernedPaperIncubationBasisKind,
    GovernedPaperIncubationContext,
    GovernedPaperIncubationCoverage,
    GovernedPaperIncubationEndKind,
    GovernedPaperIncubationError,
    GovernedPaperIncubationInterval,
    GovernedPaperIncubationLineage,
    GovernedPaperIncubationPolicy,
    GovernedPaperIncubationRecord,
    GovernedPaperIncubationRow,
    GovernedPaperIncubationRowKind,
    GovernedPaperIncubationState,
    GovernedPaperIncubationTable,
    build_governed_paper_incubation_evidence,
    build_governed_paper_incubation_reading,
    derive_governed_paper_incubation_authority,
    governed_paper_incubation_basis_digest,
    governed_paper_incubation_fill_permitted,
    governed_paper_incubation_policy_digest,
    governed_paper_incubation_prefix_digest,
    governed_paper_incubation_record_digest,
    governed_paper_incubation_row_digest,
    governed_paper_incubation_schedule_bounds,
    governed_paper_incubation_state_at,
)
from crypto_core.validation.governed_paper_kelly_reading import (
    GovernedPaperKellyKnownTrade,
    build_governed_paper_kelly_reading,
)
from crypto_core.validation.historical_execution_economics import (
    HISTORICAL_EXECUTION_INCUBATION_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    HISTORICAL_EXECUTION_KELLY_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    HistoricalExecutionEconomicsError,
    HistoricalExecutionFillOutcome,
    HistoricalExecutionIncubationWindow,
    canonical_historical_execution_admission_schedule,
    historical_execution_admission_schedule_to_dict,
)

try:  # the module objects pytest collects (basename import), so cached worlds are shared
    import test_governed_paper_kelly_reading as kt
    import test_governed_paper_risk_measurement as rmt
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_governed_paper_kelly_reading as kt
    from tests.crypto_core.validation import test_governed_paper_risk_measurement as rmt

F = Fraction
DAY = 86_400 * 10**9
G = 19_675 * DAY  # a UTC midnight
H_DAYS = 200
S = G + 10 * DAY
X = S + 91 * DAY
St = GovernedPaperIncubationState
Cov = GovernedPaperIncubationCoverage
K = GovernedPaperIncubationBasisKind
TEST_TABLE = GovernedPaperIncubationTable("test_only", "TEST_ONLY_SYNTHETIC", (), (), (), ())
B1 = "INCUBATION_FUTURE_APPROVAL_REWRITES_PAST"
B2 = "INCUBATION_KNOWN_SIGNAL_BLOCK_DELAYED_UNTIL_EFFECTIVE_TIME"
B3 = "INCUBATION_ACTIVE_WITH_EMPTY_FILL_WINDOW"


@contextlib.contextmanager
def table(value: object) -> Iterator[None]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(inc, "_TABLE", value)
        yield


@pytest.fixture(autouse=True)
def _test_only_table() -> Iterator[None]:
    assert inc._TABLE is GOVERNED_PAPER_INCUBATION_PRODUCTION_TABLE  # noqa: SLF001
    with table(TEST_TABLE):
        yield
    assert inc._TABLE is GOVERNED_PAPER_INCUBATION_PRODUCTION_TABLE  # noqa: SLF001


# --- SYNTHETIC builders ------------------------------------------------------------------------------------------------


def lineage(**changes: object) -> GovernedPaperIncubationLineage:
    values: dict[str, object] = {
        "genesis_id": "genesis-incubation",
        "genesis_digest": "a" * 64,
        "genesis_start_ns": G,
        "bootstrap_horizon_days": H_DAYS,
        "bootstrap_end_ns": G + H_DAYS * DAY,
        "edge_id": "variant-1",
        "strategy_spec_digest": "b" * 64,
        "parameter_assignment_digest": "c" * 64,
        "paper_admission_digest": "d" * 64,
        "walk_forward_evidence_digest": "e" * 64,
    }
    values.update(changes)
    return GovernedPaperIncubationLineage(**values)  # type: ignore[arg-type]


def policy(**changes: object) -> GovernedPaperIncubationPolicy:
    values: dict[str, object] = {
        "schema": "governed-paper-incubation-policy.v1",
        "policy_id": "incubation-policy-r1",
        "attempt_bound": 21,
        "duration_bound_days": 91,
        "exposure_fraction": "0.08",
        "channel": "TEST_ONLY_SYNTHETIC",
        "policy_digest": "",
    }
    values.update(changes)
    seed = GovernedPaperIncubationPolicy(**values)  # type: ignore[arg-type]
    return replace(seed, policy_digest=governed_paper_incubation_policy_digest(seed))


POLICY = policy()


def record(start: int = S, covered: tuple = ("U5",), **changes: object) -> GovernedPaperIncubationRecord:
    key = lineage()
    values: dict[str, object] = {
        "schema": "PAPER_INCUBATION_RECORD_V1",
        "genesis_id": key.genesis_id,
        "genesis_digest": key.genesis_digest,
        "genesis_start_ns": G,
        "bootstrap_horizon_days": H_DAYS,
        "admission_scope": "LIMITED_S1_PAPER_V1",
        "edge_id": key.edge_id,
        "strategy_spec_digest": key.strategy_spec_digest,
        "parameter_assignment_digest": key.parameter_assignment_digest,
        "paper_admission_digest": key.paper_admission_digest,
        "walk_forward_evidence_digest": key.walk_forward_evidence_digest,
        "ef5_preregistration_digest": "1" * 64,
        "ef7_decision_digest": "2" * 64,
        "trial_chain_head_digest": "3" * 64,
        "covered": covered,
        "attempt_bound": 21,
        "duration_bound_days": 91,
        "start_ns": start,
        "policy_digest": POLICY.policy_digest,
    }
    values.update(changes)
    return GovernedPaperIncubationRecord(**values)  # type: ignore[arg-type]


RECORD = record()
RECORD_DIGEST = governed_paper_incubation_record_digest(RECORD)


def sealed_row(seed: GovernedPaperIncubationRow) -> GovernedPaperIncubationRow:
    return replace(seed, row_digest=governed_paper_incubation_row_digest(seed))


def approval(
    sequence: int, rec: GovernedPaperIncubationRecord = RECORD, published: int = S - DAY, **changes: object
) -> GovernedPaperIncubationRow:
    values: dict[str, object] = {
        "schema": "governed-paper-incubation-registry-row.v1",
        "sequence": sequence,
        "kind": GovernedPaperIncubationRowKind.RECORD_APPROVAL,
        "genesis_digest": rec.genesis_digest,
        "edge_id": rec.edge_id,
        "record_digest": governed_paper_incubation_record_digest(rec),
        "record": rec,
        "approver_id": "synthetic-approver",
        "channel": "TEST_ONLY_SYNTHETIC",
        "decision_record_digest": "4" * 64,
        "end_kind": None,
        "published_at_ns": published,
        "effective_at_ns": published - DAY,
        "row_digest": "",
    }
    values.update(changes)
    return sealed_row(GovernedPaperIncubationRow(**values))  # type: ignore[arg-type]


def end_row(  # noqa: PLR0913
    sequence: int,
    kind: GovernedPaperIncubationEndKind,
    published: int,
    effective: int,
    digest: str = RECORD_DIGEST,
    channel: str = "TEST_ONLY_SYNTHETIC",
) -> GovernedPaperIncubationRow:
    return sealed_row(
        GovernedPaperIncubationRow(
            schema="governed-paper-incubation-registry-row.v1",
            sequence=sequence,
            kind=GovernedPaperIncubationRowKind.RECORD_END,
            genesis_digest=lineage().genesis_digest,
            edge_id=lineage().edge_id,
            record_digest=digest,
            record=None,
            approver_id="",
            channel=channel,
            decision_record_digest="5" * 64,
            end_kind=kind,
            published_at_ns=published,
            effective_at_ns=effective,
            row_digest="",
        )
    )


def basis(
    kind: GovernedPaperIncubationBasisKind,
    segments: tuple[tuple[int, int], ...],
    published: int = S - DAY,
    source: str = "synthetic-source",
    digest: str = RECORD_DIGEST,
) -> GovernedPaperIncubationBasis:
    seed = GovernedPaperIncubationBasis(
        schema="governed-paper-incubation-basis.v1",
        kind=kind,
        record_digest=digest,
        source_id=source,
        channel="TEST_ONLY_SYNTHETIC",
        published_at_ns=published,
        segments=tuple(GovernedPaperIncubationInterval(a, b) for a, b in segments),
        basis_digest="",
    )
    return replace(seed, basis_digest=governed_paper_incubation_basis_digest(seed))


def all_bases(
    start: int = S, end: int = X, published: int = S - DAY, digest: str = RECORD_DIGEST
) -> tuple[GovernedPaperIncubationBasis, ...]:
    return tuple(basis(kind, ((start, end),), published, digest=digest) for kind in K)


def context(rows: tuple = (), bases: tuple = ()) -> GovernedPaperIncubationContext:
    ordered = tuple(sorted(bases, key=lambda item: item.published_at_ns))
    return GovernedPaperIncubationContext(POLICY, rows, ordered)


def derive(ctx: GovernedPaperIncubationContext, horizon: int = G + H_DAYS * DAY, **options: object):  # noqa: ANN201
    return derive_governed_paper_incubation_authority(ctx, lineage=lineage(), horizon_ns=horizon, **options)  # type: ignore[arg-type]


ACTIVE_CONTEXT = context((approval(0),), all_bases())


def state(authority: object, instant: int, attempts: tuple = ()) -> St:
    return governed_paper_incubation_state_at(authority, instant, attempts_before=attempts)[0]  # type: ignore[arg-type]


def fill(authority: object, instant: int) -> bool:
    return governed_paper_incubation_fill_permitted(authority, instant)  # type: ignore[arg-type]


def kelly_at(instant: int, sequence: int = 1, trades: tuple = (), rho: object = F(1, 100)):  # noqa: ANN201
    return build_governed_paper_kelly_reading(
        decision_sequence=sequence,
        decision_time_ns=instant,
        target_direction="LONG",
        trades=trades,
        rho=rho,
        rho_reason="" if rho is not None else "synthetic_rho_unproven",
    )


def trade(knowledge: int, net: int) -> GovernedPaperKellyKnownTrade:
    return GovernedPaperKellyKnownTrade(f"t{knowledge}", knowledge, knowledge, F(net), F(1))


def segments(authority: object, name: str) -> tuple:
    return tuple((item.start_ns, item.end_ns) for item in getattr(authority, name))


# --- the production table ----------------------------------------------------------------------------------------------


def test_the_production_table_admits_no_row_basis_policy_or_horizon() -> None:
    assert GOVERNED_PAPER_INCUBATION_PRODUCTION_TABLE == GovernedPaperIncubationTable(
        "production", "HUMAN_GOVERNANCE", (), (), (), ()
    )
    with table(GOVERNED_PAPER_INCUBATION_PRODUCTION_TABLE):
        authority = derive(ACTIVE_CONTEXT)
        assert authority.refusal_reason == "incubation_record_approval_not_admitted"
        assert authority.base_segments == authority.fill_segments == ()
        for instant in (S, S + 3 * DAY + 10, X - 1):
            assert state(authority, instant) is St.NOT_ESTABLISHED
            assert fill(authority, instant) is False
        human = context((approval(0, channel="HUMAN_GOVERNANCE"),), all_bases())
        assert derive(human).refusal_reason == "incubation_record_approval_not_admitted"  # listed digests only
    # a production-channel row is never admitted by the test-only table either: tables never cross channels
    assert derive(context((approval(0, channel="HUMAN_GOVERNANCE"),), all_bases())).refusal_reason == (
        "incubation_record_approval_not_admitted"
    )
    for value, reason in (
        (replace(TEST_TABLE, admitted_row_digests=("0" * 64,)), "table_malformed:test_only_lists_nothing"),
        (replace(TEST_TABLE, admitted_channel="HUMAN_GOVERNANCE"), "table_malformed:channel"),
        (replace(TEST_TABLE, table_id="staging"), "table_malformed"),
    ):
        with table(value), pytest.raises(GovernedPaperIncubationError, match=f"{reason}$"):
            derive(ACTIVE_CONTEXT)


def test_every_positive_source_must_be_admitted_and_r1_values_are_fixed() -> None:
    other = policy(channel="HUMAN_GOVERNANCE")
    rec = record(policy_digest=other.policy_digest)
    ctx = GovernedPaperIncubationContext(other, (approval(0, rec),), all_bases())
    authority = derive(ctx)
    assert authority.refusal_reason == "incubation_policy_not_admitted"
    for changes, reason in (
        ({"attempt_bound": 20}, "policy_values_not_the_approved_r1_values"),
        ({"duration_bound_days": 90}, "policy_values_not_the_approved_r1_values"),
        ({"exposure_fraction": "0.40"}, "policy_values_not_the_approved_r1_values"),
        ({"exposure_fraction": "0.080"}, "policy_values_not_the_approved_r1_values"),  # one canonical text
    ):
        with pytest.raises(GovernedPaperIncubationError, match=f"{reason}$"):
            derive(GovernedPaperIncubationContext(policy(**changes), (), ()))
    with pytest.raises(GovernedPaperIncubationError, match="policy_digest_mismatch$"):
        derive(GovernedPaperIncubationContext(replace(POLICY, policy_id="other"), (), ()))
    # an unadmitted basis confers nothing
    unadmitted = tuple(replace(item, channel="HUMAN_GOVERNANCE") for item in all_bases())
    unadmitted = tuple(replace(item, basis_digest=governed_paper_incubation_basis_digest(item)) for item in unadmitted)
    authority = derive(context((approval(0),), unadmitted))
    assert authority.base_segments == () and state(authority, S + DAY) is St.HOLD


# --- B3: one interval model for decisions and fills ---------------------------------------------------------------------


def test_b3_a_delayed_basis_never_yields_active_with_an_empty_fill_window() -> None:  # B3
    case_a = derive(context((approval(0),), all_bases(start=S)))
    case_b = derive(context((approval(0),), all_bases(start=S + 1)))
    decision = S + 3 * DAY + 10
    for authority in (case_a, case_b):
        assert state(authority, decision) is St.ACTIVE, B3
        assert fill(authority, decision) is True, B3
        assert authority.fill_segments != (), B3
    assert segments(case_a, "fill_segments") == ((S, X),)
    assert segments(case_b, "fill_segments") == ((S + 1, X),)
    # the only difference is the one nanosecond the delayed bases do not cover, for decisions and fills alike
    assert (state(case_a, S), fill(case_a, S)) == (St.ACTIVE, True)
    assert (state(case_b, S), fill(case_b, S)) == (St.HOLD, False)
    assert governed_paper_incubation_state_at(case_b, S, context=context((approval(0),), all_bases(S + 1)))[1] == (
        "incubation_authority_unproven:a3_a4_a5_a6"
    )


def test_staggered_starts_gaps_and_renewals_intersect_and_never_reach_back() -> None:
    staggered = (
        basis(K.A3_APPROVAL_PROVENANCE, ((S, X),)),
        basis(K.A4_TEMPORAL_PROVENANCE, ((S + DAY, X),)),
        basis(K.A5_REVOCATION_VIEW, ((S + 2 * DAY, X),)),
        basis(K.A6_DECISION_CURRENTNESS, ((S + 3 * DAY, S + 5 * DAY), (S + 7 * DAY, S + 10 * DAY))),
        basis(K.A6_DECISION_CURRENTNESS, ((S + 9 * DAY, S + 12 * DAY),), source="renewal"),  # overlapping renewal
    )
    ctx = context((approval(0),), staggered)
    authority = derive(ctx)
    assert segments(authority, "base_segments") == ((S + 3 * DAY, S + 5 * DAY), (S + 7 * DAY, S + 12 * DAY))
    assert authority.fill_segments == authority.base_segments
    for instant, expected in (
        (S + 3 * DAY - 1, St.HOLD),  # A6 not yet valid
        (S + 3 * DAY, St.ACTIVE),  # boundary equality: a segment includes its start
        (S + 5 * DAY - 1, St.ACTIVE),
        (S + 5 * DAY, St.HOLD),  # ... and excludes its end: the gap grants nothing
        (S + 6 * DAY, St.HOLD),
        (S + 7 * DAY, St.ACTIVE),
        (S + 10 * DAY, St.ACTIVE),  # the overlapping renewal bridges the first basis's end
        (S + 12 * DAY, St.HOLD),
    ):
        assert state(authority, instant) is expected, instant
        assert fill(authority, instant) is (expected is St.ACTIVE), instant  # decision and fill agree
    assert governed_paper_incubation_state_at(authority, S + 6 * DAY, context=ctx)[1] == (
        "incubation_authority_unproven:a6"
    )


def test_a_basis_is_knowledge_only_from_its_publication() -> None:
    late = (*all_bases()[:3], basis(K.A6_DECISION_CURRENTNESS, ((S, X),), published=S + 2 * DAY))
    authority = derive(context((approval(0),), late))
    assert segments(authority, "base_segments") == ((S + 2 * DAY, X),)  # never reaches back before its publication
    assert state(authority, S + DAY) is St.HOLD and fill(authority, S + DAY) is False


def test_the_duration_and_horizon_bounds_are_half_open_and_refuse_without_shortening() -> None:
    authority = derive(ACTIVE_CONTEXT)
    assert (authority.start_ns, authority.end_ns) == (S, X)
    assert (state(authority, X - 1), fill(authority, X - 1)) == (St.ACTIVE, True)
    assert (state(authority, X), fill(authority, X)) == (St.EXPIRED_HOLD, False)
    assert state(authority, S - 1) is St.NOT_ESTABLISHED
    # S + 91 days exactly at G + H is allowed; one nanosecond past it refuses the record, with no shortened substitute
    edge = G + H_DAYS * DAY - 91 * DAY
    for start, refusal in ((edge, ""), (edge + 1, "incubation_horizon_exceeds_lineage")):
        rec = record(start=start)
        found = derive(context((approval(0, rec, published=start - DAY),), all_bases(start, G + H_DAYS * DAY)))
        assert found.refusal_reason == refusal
    found = derive(context((approval(0, record(start=edge + 1), published=edge),), ()))
    assert (found.end_ns, found.base_segments, state(found, edge + 2)) == (None, (), St.NOT_ESTABLISHED)


# --- B1: knowledge is publication-visible only --------------------------------------------------------------------------


def evidence_of(ctx: GovernedPaperIncubationContext, instants: tuple[int, ...], horizon: int, attempts: tuple = ()):  # noqa: ANN201
    authority = derive(ctx, horizon)
    readings = [
        build_governed_paper_incubation_reading(
            authority,
            kelly=kelly_at(instant, sequence),
            attempts_before=tuple(t for s, t in attempts if s < sequence),
        )
        for sequence, instant in enumerate(instants)
    ]
    return build_governed_paper_incubation_evidence(
        ctx, lineage=lineage(), horizon_ns=horizon, known_trades=(), readings=readings, attempts=attempts
    )


def test_b1_a_prospective_first_approval_never_rewrites_earlier_knowledge() -> None:  # B1
    before = context((), ())
    instants = tuple(G + k * DAY + 5 for k in range(6))
    publication = G + 6 * DAY
    old = evidence_of(before, instants, publication)
    assert all(item.state is St.NOT_ESTABLISHED for item in old.readings)
    rec = record(start=G + 8 * DAY)
    after = context(
        (approval(0, rec, published=publication),),
        all_bases(G + 8 * DAY, G + 99 * DAY, publication, governed_paper_incubation_record_digest(rec)),
    )
    later_instants = (*instants, G + 7 * DAY, G + 9 * DAY)
    new = evidence_of(after, later_instants, G + 10 * DAY)
    assert new.readings[: len(instants)] == old.readings, B1  # the earlier decisions' readings are byte-identical
    for boundary in (G + DAY, G + 3 * DAY, publication):
        assert governed_paper_incubation_prefix_digest(new, before_ns=boundary) == (
            governed_paper_incubation_prefix_digest(old, before_ns=boundary)
        ), B1
    assert governed_paper_incubation_prefix_digest(new, before_ns=publication + 1) != (
        governed_paper_incubation_prefix_digest(old, before_ns=publication + 1)
    )
    assert [item.state for item in new.readings[len(instants) :]] == [St.NOT_ESTABLISHED, St.ACTIVE]
    with pytest.raises(GovernedPaperIncubationError, match="context_carries_an_artifact_published_after_the_horizon$"):
        derive(after, publication - 1)  # no evaluation ever reads a fact its horizon does not know


def test_a_retroactive_or_duplicate_approval_terminates_and_never_resurrects() -> None:
    late = derive(context((approval(0, published=S + 1, effective_at_ns=S - DAY),), all_bases()))
    assert (late.final_state, late.final_ns, late.final_reason) == (
        St.TERMINATED,
        S + 1,
        "incubation_record_approval_retroactive",
    )
    assert late.base_segments == () and state(late, S) is St.NOT_ESTABLISHED and state(late, S + 1) is St.TERMINATED
    after_start = derive(context((approval(0, published=S - DAY, effective_at_ns=S + 1),), all_bases()))
    assert after_start.final_reason == "incubation_record_approval_retroactive"
    second = approval(1, record(start=S + DAY), published=S + 5 * DAY)
    duplicate = derive(context((approval(0), second), all_bases()))
    assert (duplicate.final_state, duplicate.final_ns) == (St.TERMINATED, S + 5 * DAY)
    assert segments(duplicate, "base_segments") == ((S, S + 5 * DAY),)
    assert state(duplicate, S + 5 * DAY - 1) is St.ACTIVE and state(duplicate, S + 50 * DAY) is St.TERMINATED
    for changes, reason in (
        ({"genesis_start_ns": G + 1}, "incubation_record_wrong_lineage"),
        ({"strategy_spec_digest": "9" * 64}, "incubation_record_not_the_executed_edge"),
        ({"attempt_bound": 20}, "incubation_record_policy_mismatch"),
    ):
        authority = derive(context((approval(0, record(**changes)),), all_bases()))
        assert (authority.final_state, authority.final_reason) == (St.TERMINATED, reason)
        assert authority.base_segments == ()
    forged = sealed_row(
        replace(approval(0), record=record(ef7_decision_digest="8" * 64))
    )  # re-digested row, old record id
    authority = derive(context((forged,), all_bases()))
    assert authority.final_reason == "incubation_record_digest_mismatch"


# --- B2: a known signal blocks at its publication; finality waits for its effect ----------------------------------------------


@pytest.mark.parametrize(
    ("kind", "final"),
    [
        (GovernedPaperIncubationEndKind.ADVERSE_SIGNAL, St.TERMINATED),
        (GovernedPaperIncubationEndKind.REVOKED, St.REVOKED),
        (GovernedPaperIncubationEndKind.VALIDATION_NOT_CURRENT, St.TERMINATED),
    ],
)
def test_b2_a_known_end_signal_blocks_at_publication_and_is_final_at_its_effect(kind: object, final: St) -> None:  # B2
    publication, effective = S + 20 * DAY, S + 25 * DAY
    without = derive(ACTIVE_CONTEXT)
    ctx = context((approval(0), end_row(1, kind, publication, effective)), all_bases())  # type: ignore[arg-type]
    authority = derive(ctx)
    for instant, expected, permitted in (
        (publication - 1, St.ACTIVE, True),
        (publication, St.HOLD, False),  # immediate: not delayed until the effective instant
        (effective - 1, St.HOLD, False),
        (effective, final, False),
        (effective + 1, final, False),
        (X + DAY, final, False),  # final, never left
    ):
        assert state(authority, instant) is expected, (B2, instant)
        assert fill(authority, instant) is permitted, (B2, instant)  # a pending intent cannot fill from P on
    assert (authority.final_state, authority.final_ns, authority.final_effective_ns) == (final, effective, effective)
    assert segments(authority, "fill_segments") == ((S, publication),)
    # no historical rewrite: before P the authority is the one without the row
    old = evidence_of(ACTIVE_CONTEXT, (S + DAY, S + 10 * DAY), S + 30 * DAY)
    new = evidence_of(ctx, (S + DAY, S + 10 * DAY), S + 30 * DAY)
    assert old.readings == new.readings
    assert governed_paper_incubation_prefix_digest(old, before_ns=publication) == (
        governed_paper_incubation_prefix_digest(new, before_ns=publication)
    )
    assert segments(without, "base_segments") == ((S, X),)


def test_finality_is_never_dated_before_publication_and_an_unqualified_signal_only_blocks() -> None:
    retro = derive(
        context(
            (approval(0), end_row(1, GovernedPaperIncubationEndKind.REVOKED, S + 9 * DAY, S + 2 * DAY)), all_bases()
        )
    )
    assert (retro.final_state, retro.final_ns, retro.final_effective_ns) == (St.REVOKED, S + 9 * DAY, S + 2 * DAY)
    assert state(retro, S + 5 * DAY) is St.ACTIVE  # decisions before P keep the authority they had
    unqualified = end_row(
        1, GovernedPaperIncubationEndKind.REVOKED, S + 9 * DAY, S + 9 * DAY, channel="HUMAN_GOVERNANCE"
    )
    authority = derive(context((approval(0), unqualified), all_bases()))
    assert state(authority, S + 9 * DAY) is St.HOLD and state(authority, S + 50 * DAY) is St.HOLD  # A5: it blocks
    assert (authority.final_state, state(authority, X)) == (St.EXPIRED_HOLD, St.EXPIRED_HOLD)  # never REVOKED
    foreign = end_row(1, GovernedPaperIncubationEndKind.REVOKED, S + 9 * DAY, S + 9 * DAY, digest="7" * 64)
    authority = derive(context((approval(0), foreign), all_bases()))
    assert state(authority, S + 9 * DAY) is St.HOLD and authority.final_state is St.EXPIRED_HOLD
    early = derive(
        context((end_row(0, GovernedPaperIncubationEndKind.ADVERSE_SIGNAL, S - 3 * DAY, S), approval(1)), all_bases())
    )
    assert early.base_segments == () and state(early, S + DAY) is St.TERMINATED  # final at max(P, E) = S
    quiet = end_row(0, GovernedPaperIncubationEndKind.ADVERSE_SIGNAL, S - 3 * DAY, S, channel="HUMAN_GOVERNANCE")
    unqualified_early = derive(context((quiet, approval(1)), all_bases()))
    assert unqualified_early.base_segments == () and state(unqualified_early, S + DAY) is St.HOLD  # it still binds


def test_a_final_state_is_never_left_by_a_later_publication() -> None:
    revoked = (approval(0), end_row(1, GovernedPaperIncubationEndKind.REVOKED, S + 4 * DAY, S + 4 * DAY))
    renewed = (*all_bases(), *(basis(kind, ((S + 5 * DAY, X),), S + 5 * DAY, "renewal") for kind in K))
    second = approval(2, record(start=S + 6 * DAY), published=S + 5 * DAY)
    authority = derive(context((*revoked, second), renewed))
    assert segments(authority, "base_segments") == ((S, S + 4 * DAY),)
    assert {state(authority, S + k * DAY) for k in range(4, 90)} == {St.REVOKED}  # no resurrection


# --- attempts and graduation ----------------------------------------------------------------------------------------------


def test_attempt_21_is_admissible_and_ends_the_record_with_no_fill_at_or_after_it() -> None:
    attempts = tuple(S + k * DAY for k in range(1, 22))
    authority = derive(ACTIVE_CONTEXT, attempt_instants=attempts)
    t21 = attempts[20]
    assert state(authority, t21, attempts[:20]) is St.ACTIVE  # the decision consuming attempt 21 reads 20 before it
    assert state(authority, t21 + 1, attempts) is St.EXPIRED_HOLD
    assert (authority.final_state, authority.final_ns, authority.exhaustion_ns) == (St.EXPIRED_HOLD, t21, t21)
    assert segments(authority, "fill_segments") == ((S, t21),)
    assert segments(authority, "base_segments") == ((S, X),)  # the base model is the decisions'; fills are cut (O4)
    assert fill(authority, t21 - 1) is True and fill(authority, t21) is False  # attempt 21's own fill is refused
    static = derive(ACTIVE_CONTEXT)
    for instant in (S + DAY // 2, S + 30 * DAY, X - 1):  # with fewer than 21 earlier attempts, decision == fill
        before = tuple(item for item in attempts if item < instant)
        assert (state(authority, instant, before) is St.ACTIVE) is fill(authority, instant)
        assert state(static, instant, before) is state(authority, instant, before)


def test_u5_graduation_and_a_multi_reading_record_that_never_graduates() -> None:
    trades = ((S + 3 * DAY, "WIN"), (S + 5 * DAY, "ZERO"), (S + 8 * DAY, "LOSS"))
    authority = derive(ACTIVE_CONTEXT, known_trades=trades)
    assert (authority.u5_completion_ns, authority.graduation_ns) == (S + 8 * DAY, S + 8 * DAY)
    assert (authority.final_state, segments(authority, "fill_segments")) == (St.GRADUATED, ((S, S + 8 * DAY),))
    assert state(authority, S + 8 * DAY) is St.GRADUATED and fill(authority, S + 8 * DAY) is False
    rec = record(covered=("U1", "U5"))
    digest = governed_paper_incubation_record_digest(rec)
    ctx = context((approval(0, rec),), tuple(basis(kind, ((S, X),), digest=digest) for kind in K))
    multi = derive(ctx, known_trades=trades)
    assert (multi.graduation_ns, multi.final_state) == (None, St.EXPIRED_HOLD)  # U1 has no producer: never complete
    assert state(multi, S + 9 * DAY) is St.ACTIVE
    with pytest.raises(GovernedPaperIncubationError, match="known_trades_malformed$"):
        derive(ACTIVE_CONTEXT, known_trades=((S, "DRAW"),))


def test_the_u5_reading_is_excepted_only_when_active_selected_and_undefined_for_missing_history() -> None:
    authority = derive(ACTIVE_CONTEXT, known_trades=((S + 8 * DAY, "WIN"), (S + 9 * DAY, "LOSS")))
    t = S + 2 * DAY
    for kelly, attempts, expected in (
        (kelly_at(t), (), Cov.COLD_START_EXCEPTED),
        (kelly_at(t, rho=None), (), Cov.ORDINARY),  # an unproven rho also blocks: never missing history alone
        (kelly_at(t, trades=(trade(S + DAY, -200),)), (), Cov.ORDINARY),  # proven domain ruin FAILs: FAIL dominates
        (kelly_at(S - 1), (), Cov.NOT_COVERED),  # before S
        (kelly_at(S + 10 * DAY), (), Cov.NOT_COVERED),  # graduated at S + 9 days: final
    ):
        reading = build_governed_paper_incubation_reading(authority, kelly=kelly, attempts_before=attempts)
        assert reading.u5 is expected, (kelly.reason, kelly.decision_time_ns)
    ruin = build_governed_paper_incubation_reading(
        authority, kelly=kelly_at(t, trades=(trade(S + DAY, -200),)), attempts_before=()
    )
    assert ruin.u5_reason == "u5_ordinary:kelly_log_domain_ruin"
    not_selected = derive(context((approval(0, record(covered=("U3",))),), ()))
    reading = build_governed_paper_incubation_reading(not_selected, kelly=kelly_at(t), attempts_before=())
    assert reading.u5 is Cov.NOT_COVERED
    multi_rec = record(covered=("U1", "U5"))
    multi = derive(
        context(
            (approval(0, multi_rec),),
            tuple(basis(kind, ((S, X),), digest=governed_paper_incubation_record_digest(multi_rec)) for kind in K),
        ),
        known_trades=((S + DAY, "WIN"), (S + DAY + 1, "LOSS")),
    )
    ended = build_governed_paper_incubation_reading(multi, kelly=kelly_at(t), attempts_before=())
    assert (ended.state, ended.u5) == (St.ACTIVE, Cov.COVERAGE_ENDED)  # per reading, irreversible
    with pytest.raises(GovernedPaperIncubationError, match="kelly_reading_not_authentic$"):
        build_governed_paper_incubation_reading(authority, kelly=replace(kelly_at(t), rho="1"), attempts_before=())


def test_the_evidence_binds_only_the_authoritys_own_readings_and_attempts() -> None:
    instants = (S + DAY, S + 2 * DAY, S + 3 * DAY)
    good = evidence_of(ACTIVE_CONTEXT, instants, S + 4 * DAY, attempts=((0, S + DAY),))
    assert [item.attempts_before for item in good.readings] == [0, 1, 1]
    assert governed_paper_incubation_schedule_bounds(good) == ((0,), ((S, X),), True)
    authority = derive(ACTIVE_CONTEXT, S + 4 * DAY)
    wrong = build_governed_paper_incubation_reading(authority, kelly=kelly_at(S + 2 * DAY, 1), attempts_before=())
    with pytest.raises(GovernedPaperIncubationError, match="reading_not_the_authoritys$"):
        build_governed_paper_incubation_evidence(
            ACTIVE_CONTEXT,
            lineage=lineage(),
            horizon_ns=S + 4 * DAY,
            known_trades=(),
            readings=(good.readings[0], wrong),
            attempts=((0, S + DAY),),
        )
    early = build_governed_paper_incubation_reading(authority, kelly=kelly_at(S - DAY, 0), attempts_before=())
    with pytest.raises(GovernedPaperIncubationError, match="attempt_not_an_active_decision$"):
        build_governed_paper_incubation_evidence(
            ACTIVE_CONTEXT,
            lineage=lineage(),
            horizon_ns=S + 4 * DAY,
            known_trades=(),
            readings=(early,),
            attempts=((0, S - DAY),),
        )


def test_malformed_inputs_are_refused_before_any_authority() -> None:
    rows = (approval(0),)
    for ctx, reason in (
        (context((approval(1),), ()), "row_malformed:sequence_not_append_only"),
        (context((replace(approval(0), approver_id="x"),), ()), "row_digest_mismatch"),
        (context((approval(0, published=S), approval(1, published=S - 2 * DAY)), ()), "rows_not_in_publication_order"),
        (context(rows, (all_bases()[0], all_bases()[0])), "context_malformed:basis_repeated"),
        (context(rows, (basis(K.A3_APPROVAL_PROVENANCE, ((S, S + 2), (S + 2, X))),)), "segments_not_ordered_disjoint"),
        (context(rows, (basis(K.A3_APPROVAL_PROVENANCE, ((S, S),)),)), "basis_malformed:segment"),
        (context((approval(0, record(covered=("U5", "U1"))),), ()), "record_malformed:covered"),
        (context((approval(0, record(covered=())),), ()), "record_malformed:covered"),
        (context((approval(0, record(covered=("U6",))),), ()), "record_malformed:covered"),
    ):
        with pytest.raises(GovernedPaperIncubationError, match=f"{reason}"):
            derive(ctx)
    with pytest.raises(GovernedPaperIncubationError, match="attempt_instants_malformed$"):
        derive(ACTIVE_CONTEXT, attempt_instants=(S + 2, S + 1))


# --- schedule v9 ---------------------------------------------------------------------------------------------------------

V8 = HISTORICAL_EXECUTION_KELLY_ADMISSION_SCHEDULE_SCHEMA_VERSION
V9 = HISTORICAL_EXECUTION_INCUBATION_ADMISSION_SCHEDULE_SCHEMA_VERSION
V9_FIELDS = {"incubation_decision_sequences", "incubation_fill_windows", "incubation_kelly_covered"}


def test_schedule_v9_carries_its_fields_alone_and_v8_keeps_its_payload() -> None:
    _, world = rmt.hold_v2()
    v8 = kt.hold_schedule(world, "SHORT")
    v9 = replace(v8, schema_version=V9)
    assert set(historical_execution_admission_schedule_to_dict(v9)) == (
        set(historical_execution_admission_schedule_to_dict(v8)) | V9_FIELDS
    )
    assert canonical_historical_execution_admission_schedule(v9) == v9
    window = HistoricalExecutionIncubationWindow(1, 2)
    for schedule, reason in (
        (replace(v8, incubation_kelly_covered=True), "incubation_fields_need_schema_v9"),
        (replace(v8, incubation_fill_windows=(window,)), "incubation_fields_need_schema_v9"),
        (replace(v9, incubation_decision_sequences=(3, 3)), "incubation_decisions_not_strictly_increasing"),
        (
            replace(v9, incubation_decision_sequences=(3,), entry_refused_decision_sequences=(3,)),
            "incubation_decision_refused",
        ),
        (
            replace(v9, incubation_fill_windows=(window, HistoricalExecutionIncubationWindow(2, 3))),
            "not_ordered_disjoint",
        ),
        (replace(v9, incubation_fill_windows=(HistoricalExecutionIncubationWindow(2, 2),)), "fill_window_empty"),
        (replace(v9, incubation_kelly_covered=1), "incubation_fields"),
    ):
        with pytest.raises(HistoricalExecutionEconomicsError, match=reason):
            canonical_historical_execution_admission_schedule(schedule)


def seeded_v9(history: tuple, **fields: object):  # noqa: ANN201
    """The SHORT HOLD world under a schedule v9 with ``fields``, its simulation seeded with ``history`` closed trades and
    the ordinary exposure envelope lifted. WHITE-BOX: no evaluation admits an incubation entry while the production table
    admits nothing and SCALE-1's other terms are never proven, so the fill-time authority is reachable only this way."""

    original = economics._GovernedPaperSimulation.__init__  # noqa: SLF001

    def init(self: object, *args: object, **kwargs: object) -> None:
        original(self, *args, **kwargs)  # type: ignore[arg-type]
        self.trade_exact_values.extend(  # type: ignore[attr-defined]
            economics.HistoricalExecutionTradeExactValues(
                f"seed-{k}", F(net), None if value is None else F(value), instant
            )
            for k, (net, value, instant) in enumerate(history)
        )

    result, world = rmt.hold_v2()
    schedule = replace(kt.hold_schedule(world, "SHORT"), schema_version=V9, **fields)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(economics._GovernedPaperSimulation, "__init__", init)  # noqa: SLF001
        return kt.governed(result, schedule)


def fill_instant(sequence: int) -> int:
    """The instant the engine admits the HOLD entry fill at (its book visibility), recorded through the hook itself."""

    seen: list[int] = []
    original = economics._GovernedPaperSimulation._incubation_fill_admission  # noqa: SLF001

    def recording(self: object, order: object, *args: object) -> object:
        seen.append(args[-1])  # type: ignore[arg-type]
        return original(self, order, *args)  # type: ignore[arg-type]

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(economics._GovernedPaperSimulation, "_incubation_fill_admission", recording)  # noqa: SLF001
        seeded_v9((), incubation_decision_sequences=(sequence,))
    return seen[0]  # type: ignore[return-value]


def test_the_engine_fill_hook_reads_the_same_fill_segments_and_w_inc_and_takes_kd13_once() -> None:
    result, world = rmt.hold_v2()
    v7 = kt.governed(result, kt.hold_schedule(world, "SHORT", kt.V7))
    entry = rmt.entry_fill(v7)
    sequence = next(item.decision_sequence for item in v7.intents if item.intent_id == entry.intent_id)
    instant = fill_instant(sequence)
    window = HistoricalExecutionIncubationWindow(instant - 1, instant + 1)
    # KD-13: no known trade, U5 covered, the fill inside the window -> the ratio-undefined reading is excepted
    excepted = seeded_v9(
        (), incubation_decision_sequences=(sequence,), incubation_fill_windows=(window,), incubation_kelly_covered=True
    )
    assert rmt.entry_fill(excepted).outcome is HistoricalExecutionFillOutcome.FILLED
    for fields, history, reason in (
        (
            {"incubation_fill_windows": (HistoricalExecutionIncubationWindow(instant + 1, instant + 2),)},
            (),
            "governed_paper_incubation_fill_not_permitted",
        ),
        (
            {"incubation_fill_windows": (HistoricalExecutionIncubationWindow(0, instant),)},
            (),
            "governed_paper_incubation_fill_not_permitted",
        ),  # end excluded
        ({"incubation_kelly_covered": False}, (), "governed_paper_kelly_unproven_at_fill"),  # U5 not selected
        ({}, ((-1, None, 0), (3, 1, 0)), "governed_paper_kelly_unproven_at_fill"),  # another undefined component
        ({}, ((-(10**9), 1, 0),), "governed_paper_kelly_log_domain_ruin_at_fill"),  # a proven FAIL dominates
    ):
        values = {
            "incubation_decision_sequences": (sequence,),
            "incubation_fill_windows": (window,),
            "incubation_kelly_covered": True,
        }
        values.update(fields)
        refused = seeded_v9(history, **values)
        fill_outcome = rmt.entry_fill(refused)
        assert (fill_outcome.outcome, fill_outcome.reason) == (HistoricalExecutionFillOutcome.REJECTED, reason), reason
        assert refused.position_transitions == ()  # whole: never a resize
    # W_INC at the fill: lower the cap below the fill's own exposure fraction and the same fill is refused
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(economics, "HISTORICAL_EXECUTION_INCUBATION_EXPOSURE_CAP", F(0))
        capped = seeded_v9(
            (),
            incubation_decision_sequences=(sequence,),
            incubation_fill_windows=(window,),
            incubation_kelly_covered=True,
        )
    assert rmt.entry_fill(capped).reason == "governed_paper_incubation_envelope_exceeded_at_fill"
    # an intent not decided on the incubation basis never reads the incubation authority
    ordinary = seeded_v9((), incubation_fill_windows=(window,), incubation_kelly_covered=True)
    assert rmt.entry_fill(ordinary).reason == "governed_paper_kelly_unproven_at_fill"


# --- rule set v12 ------------------------------------------------------------------------------------------------------

STATUS = GovernedPaperEntrySafetyStatus


def test_rule_set_v12_is_rule_set_v11_with_the_incubation_rule_and_v11_keeps_its_identity() -> None:
    assert (
        GOVERNED_PAPER_ENTRY_SAFETY_INCUBATION_RULE_SET["checks"]
        == GOVERNED_PAPER_ENTRY_SAFETY_KELLY_RULE_SET["checks"]
    )
    assert (
        GOVERNED_PAPER_ENTRY_SAFETY_INCUBATION_RULE_SET["rule_set_id"]
        == GOVERNED_PAPER_ENTRY_SAFETY_INCUBATION_RULE_SET_ID
    )
    assert GOVERNED_PAPER_ENTRY_SAFETY_INCUBATION_RULE_SET["incubation_rule"]["values"] == {  # type: ignore[index]
        "A_max": 21,
        "T_max_utc_days": 91,
        "W_INC": "0.08",
    }
    assert "incubation_rule" not in GOVERNED_PAPER_ENTRY_SAFETY_KELLY_RULE_SET
    assert GOVERNED_PAPER_ENTRY_SAFETY_KELLY_RULE_SET_DIGEST == ACCEPTED_MAIN_RULE_SET_V11_DIGEST
    assert GOVERNED_PAPER_ENTRY_SAFETY_INCUBATION_RULE_SET_DIGEST != ACCEPTED_MAIN_RULE_SET_V11_DIGEST
    with pytest.raises(GovernedPaperEntrySafetyError, match="incubation_rule_set_needs_the_kelly_rule_set$"):
        governed_paper_entry_safety_rule_set(incubation=True)


ACCEPTED_MAIN_RULE_SET_V11_DIGEST = "4c5d6e8612b8957ac97f5064a8dbba39f8b3571421a0154b27d73b5a2780cb21"


def v12(active: bool, kelly_status: str = "BLOCKED"):  # noqa: ANN201, FBT001
    """A SYNTHETIC rule set v12 observation of decision 7 at ``est.T`` whose incubation reading is ACTIVE or HOLD."""

    observation = kt.v11(kelly_status)
    kelly = observation.kelly.reading  # type: ignore[union-attr]
    instant = kelly.decision_time_ns
    start, genesis = instant - DAY, instant - 10 * DAY
    rec = record(start=start, genesis_start_ns=genesis)
    digest = governed_paper_incubation_record_digest(rec)
    bases = tuple(basis(kind, ((start, start + 5 * DAY),), start - DAY, digest=digest) for kind in K)
    ctx = context((approval(0, rec, published=start - DAY),), bases if active else ())
    lin = lineage(genesis_start_ns=genesis, bootstrap_end_ns=genesis + H_DAYS * DAY)
    with table(TEST_TABLE):
        authority = derive_governed_paper_incubation_authority(ctx, lineage=lin, horizon_ns=instant + DAY)
        reading = build_governed_paper_incubation_reading(authority, kelly=kelly, attempts_before=())
    assert reading.state is (St.ACTIVE if active else St.HOLD)
    return replace(observation, incubation=GovernedPaperEntrySafetyIncubation(reading, authority.authority_digest))


def test_scale_1_excepts_the_kelly_term_only_under_an_active_record_and_keeps_every_other_term_binding() -> None:
    active, hold = v12(True), v12(False)
    terms = governed_paper_entry_safety_a9_multipliers(active)
    assert terms[-1] == ("kelly_fit_1_28", "COLD_START_EXCEPTED", "u5_kelly_ratio_undefined_missing_own_history")
    assert terms[:-1] == governed_paper_entry_safety_a9_multipliers(kt.v11("BLOCKED"))[:-1]
    assert governed_paper_entry_safety_a9_multipliers(hold)[-1] == (
        "kelly_fit_1_28",
        "UNPROVEN",
        "kelly_ratio_undefined",
    )
    decision = evaluate_governed_paper_entry_safety(active)
    scale = kt.scale(decision)
    assert (
        scale[0] is STATUS.BLOCKED_ON_MISSING_INPUT and "kelly_fit_1_28" not in scale[2]
    )  # the other terms stay unproven
    assert scale[3][-1] == active.incubation.reading.reading_digest  # type: ignore[union-attr]
    assert decision.entry_permitted is False and governed_paper_entry_safety_incubation_basis(decision) is False
    failing = v12(True, "FAIL")
    assert kt.scale(evaluate_governed_paper_entry_safety(failing))[0] is STATUS.FAIL  # a proven reduction still refuses


def test_a_cold_start_exception_admits_only_under_an_active_record_white_box() -> None:
    """WHITE-BOX: every check replaced by a stub, so the admission rule itself is observable."""

    def stub(status: GovernedPaperEntrySafetyStatus):  # noqa: ANN202
        return gate._Check("STUB", gate._Family.DATA, "stub", "stub", lambda _: gate._Outcome(status, "", "stub"))  # noqa: SLF001

    for active, statuses, permitted, basis_flag in (
        (True, (STATUS.PASS, STATUS.COLD_START_EXCEPTED), True, True),
        (True, (STATUS.PASS, STATUS.PROVEN_NOT_APPLICABLE), True, False),  # ordinary basis
        (False, (STATUS.PASS, STATUS.COLD_START_EXCEPTED), False, False),  # never outside ACTIVE
        (True, (STATUS.COLD_START_EXCEPTED, STATUS.FAIL), False, False),
        (True, (STATUS.COLD_START_EXCEPTED, STATUS.BLOCKED_ON_MISSING_INPUT), False, False),
    ):
        observation = v12(active)
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(gate, "_CHECKS", tuple(stub(item) for item in statuses))
            patch.setattr(gate, "_REGIME_CHECKS", ())
            patch.setattr(gate, "_RISK_MEASUREMENT_CHECKS", ())
            decision = evaluate_governed_paper_entry_safety(observation)
        assert (decision.entry_permitted, governed_paper_entry_safety_incubation_basis(decision)) == (
            permitted,
            basis_flag,
        )


def test_the_incubation_facts_are_canonical_and_only_on_top_of_the_kelly_facts() -> None:
    observation = v12(True)
    facts = observation.incubation
    for changed, reason in (
        (replace(observation, kelly=None), "observation_malformed:incubation_without_the_kelly_facts"),
        (
            replace(observation, incubation=replace(facts, authority_digest="x")),
            "observation_malformed:incubation_authority_digest",
        ),  # type: ignore[arg-type]
        (
            replace(observation, incubation=replace(facts, reading=replace(facts.reading, decision_sequence=8))),  # type: ignore[arg-type,union-attr]
            "observation_malformed:incubation_reading",
        ),
        (
            replace(
                observation,
                incubation=replace(facts, reading=replace(facts.reading, state=St.ACTIVE, state_reason="forged")),
            ),  # type: ignore[arg-type,union-attr]
            "observation_malformed:incubation_reading_digest",
        ),
        (
            replace(observation, kelly=GovernedPaperEntrySafetyKelly(kt.kelly_facts("PASS").reading, "d" * 64)),
            "observation_malformed:incubation_reading",
        ),
        (replace(observation, incubation=object()), "observation_malformed:incubation"),
    ):
        with pytest.raises(GovernedPaperEntrySafetyError, match=f"{reason}$"):
            evaluate_governed_paper_entry_safety(changed)  # type: ignore[arg-type]


def test_a_record_that_was_never_established_never_graduates() -> None:
    late = G + H_DAYS * DAY - 90 * DAY  # S + 91 days exceeds G + H: refused
    rec = record(start=late)
    ctx = context((approval(0, rec, published=late - DAY),), all_bases(late, late + 91 * DAY, late - DAY))
    refused = derive(ctx, known_trades=((late + DAY, "WIN"), (late + 2 * DAY, "LOSS")))
    assert (refused.refusal_reason, refused.graduation_ns, refused.final_state) == (
        "incubation_horizon_exceeds_lineage",
        None,
        None,
    )
    assert state(refused, late + 3 * DAY) is St.NOT_ESTABLISHED
    after_end = derive(ACTIVE_CONTEXT, known_trades=((X, "WIN"), (X + 1, "LOSS")))
    assert (after_end.graduation_ns, after_end.final_state) == (
        None,
        St.EXPIRED_HOLD,
    )  # coverage after X: no retroactive graduation


def test_a_record_without_fill_permission_leaves_the_schedule_unchanged() -> None:  # B1 at the schedule level
    late = G + H_DAYS * DAY - 90 * DAY
    rec = record(start=late)
    refused_ctx = context((approval(0, rec, published=late - DAY),), all_bases(late, late + 91 * DAY, late - DAY))
    for ctx in (context(), refused_ctx, context((approval(0),), ())):  # no record, refused, never authorized
        evidence = evidence_of(ctx, (late,), late + DAY)
        assert governed_paper_incubation_schedule_bounds(evidence) == ((), (), False), B1
