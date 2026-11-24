"""S1_TEMPORAL_AUTHORITY_UNIFIED_CONSTRUCTION_V1 on world G: seal v13, evidence v13, X1 and the public verifier.

World G's genesis has a 30-day bootstrap horizon, so a 91-day record can never be established in it
(``incubation_horizon_exceeds_lineage``): these tests prove the lineage binding, the cross-day knowledge rule (B1), the
public reconstruction, the production refusal and the byte identity of the accepted v12 artifacts. The ACTIVE semantics
are proven on the 200-day synthetic key of ``test_governed_paper_incubation_authority``.
"""

from __future__ import annotations

import contextlib
import functools
from collections.abc import Iterator
from dataclasses import replace

import pytest

import crypto_core.validation.governed_paper_incubation_authority as inc
from crypto_core.validation.governed_admitted_variant_paper_execution import (
    GovernedPaperExecutionStatus,
    build_governed_paper_day_seal,
    governed_paper_day_seal_to_dict,
)
from crypto_core.validation.governed_paper_entry_safety import (
    GOVERNED_PAPER_ENTRY_SAFETY_INCUBATION_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_INCUBATION_RULE_SET_ID,
    GovernedPaperEntrySafetyPortfolio,
    build_governed_paper_entry_safety_evidence,
)
from crypto_core.validation.governed_paper_incubation_authority import (
    GOVERNED_PAPER_INCUBATION_PRODUCTION_TABLE,
    GovernedPaperIncubationBasis,
    GovernedPaperIncubationBasisKind,
    GovernedPaperIncubationContext,
    GovernedPaperIncubationInterval,
    GovernedPaperIncubationPolicy,
    GovernedPaperIncubationRecord,
    GovernedPaperIncubationRow,
    GovernedPaperIncubationRowKind,
    GovernedPaperIncubationState,
    GovernedPaperIncubationTable,
    governed_paper_incubation_basis_digest,
    governed_paper_incubation_lineage,
    governed_paper_incubation_policy_digest,
    governed_paper_incubation_prefix_digest,
    governed_paper_incubation_record_digest,
    governed_paper_incubation_row_digest,
)
from crypto_core.validation.historical_execution_economics import (
    HISTORICAL_EXECUTION_INCUBATION_ADMISSION_SCHEDULE_SCHEMA_VERSION,
)

try:  # the module objects pytest collects (basename import), so cached worlds are shared
    import test_governed_admitted_variant_paper_execution as gpe
    import test_governed_paper_entry_safety as est
    import test_governed_paper_kelly_reading as kt
    import test_governed_paper_kill_switch as kst
    import test_governed_paper_protective_ledger as plt
    import test_governed_paper_protective_lineage as lineage_tests
    import test_governed_paper_regime_state as rst
    import test_governed_paper_risk_lineage as rlt
    import test_governed_paper_risk_measurement as rmt
    import test_governed_paper_sizing_chain as sct
    from test_governed_paper_kelly_reading import _production_tables_with_exact_memos  # noqa: F401 - autouse memos
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_governed_admitted_variant_paper_execution as gpe
    from tests.crypto_core.validation import test_governed_paper_entry_safety as est
    from tests.crypto_core.validation import test_governed_paper_kelly_reading as kt
    from tests.crypto_core.validation import test_governed_paper_kill_switch as kst
    from tests.crypto_core.validation import test_governed_paper_protective_ledger as plt
    from tests.crypto_core.validation import test_governed_paper_protective_lineage as lineage_tests
    from tests.crypto_core.validation import test_governed_paper_regime_state as rst
    from tests.crypto_core.validation import test_governed_paper_risk_lineage as rlt
    from tests.crypto_core.validation import test_governed_paper_risk_measurement as rmt
    from tests.crypto_core.validation import test_governed_paper_sizing_chain as sct
    from tests.crypto_core.validation.test_governed_paper_kelly_reading import (  # noqa: F401 - autouse memos
        _production_tables_with_exact_memos,
    )

DAY = gpe.DAY
V9 = HISTORICAL_EXECUTION_INCUBATION_ADMISSION_SCHEDULE_SCHEMA_VERSION
V12_SEAL, V13_SEAL = "governed-paper-day-seal.v12", "governed-paper-day-seal.v13"
V13_EVIDENCE = "governed-paper-execution-evidence.v13"
V13_FIELDS = (
    "incubation_policy_digest",
    "incubation_row_digests",
    "incubation_basis_digests",
    "incubation_evidence_digest",
    "incubation_prefix_digest_open",
    "incubation_prefix_digest_close",
    "incubation_attempt_count",
)
TEST_TABLE = GovernedPaperIncubationTable("test_only", "TEST_ONLY_SYNTHETIC", (), (), (), ())
St = GovernedPaperIncubationState
B1 = "INCUBATION_FUTURE_APPROVAL_REWRITES_PAST"
# The accepted-main v12 identities this contract keeps, computed on main 523c140e's own source (a detached worktree of
# that commit) before any change of this contract: world G's first two Kelly days and their lineage evidence.
ACCEPTED_MAIN_KELLY_SEAL_V12_DIGESTS = (
    "549fc5fd6bf00f022bf19b5f49df86653991d36c443f71a50ed9462332b8bb3d",
    "8fd7209bef30892426ff75b7f5e592c8cc623c4af192076ddad4eea1f805ea7c",
)
ACCEPTED_MAIN_KELLY_SCHEDULE_V8_DIGESTS = (
    "97d86a0b439074ca56f0970b871c3c63630bfa3c2a40a62aea7cdd63cc7244f1",
    "e8ceea2c89c01c2748f1f6b5ed6dd258ec6909d7d268aedf8c95f9535a98131f",
)
ACCEPTED_MAIN_KELLY_EVIDENCE_DIGESTS = (
    "0d5d99231b93571bbba93de272ddbfc9462d3d4ee40d27edf1edf323b9dcf6cc",
    "a8dd315564d8e447a76a620844fd854251d6f6cdfaa09b148319a2b78a374b14",
)
ACCEPTED_MAIN_KELLY_ENTRY_EVIDENCE_DIGESTS = (
    "53aaf9a7572159f47152ff1fe372c45a6b8bb36f03e6b4de24e836f7a33df520",
    "ecdd850243a702fb127145b81920395f6b2c427598fd4528c9afd5eb0b2099e8",
)
ACCEPTED_MAIN_KELLY_LINEAGE_EVIDENCE_V12_DIGEST = "3dc5fb5586342c23549edc0c156431ec1c1ed901fae25b2b8656b22cd6758cde"


@contextlib.contextmanager
def incubation_table(value: GovernedPaperIncubationTable = TEST_TABLE) -> Iterator[None]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(inc, "_TABLE", value)
        yield


# --- SYNTHETIC registry artifacts of world G's lineage-edge key ---------------------------------------------------------


def _policy() -> GovernedPaperIncubationPolicy:
    seed = GovernedPaperIncubationPolicy(
        "governed-paper-incubation-policy.v1", "incubation-policy-r1", 21, 91, "0.08", "TEST_ONLY_SYNTHETIC", ""
    )
    return replace(seed, policy_digest=governed_paper_incubation_policy_digest(seed))


POLICY = _policy()


def world_record(start: int) -> GovernedPaperIncubationRecord:
    key = governed_paper_incubation_lineage(gpe.scenario("G").genesis)
    return GovernedPaperIncubationRecord(
        schema="PAPER_INCUBATION_RECORD_V1",
        genesis_id=key.genesis_id,
        genesis_digest=key.genesis_digest,
        genesis_start_ns=key.genesis_start_ns,
        bootstrap_horizon_days=key.bootstrap_horizon_days,
        admission_scope="LIMITED_S1_PAPER_V1",
        edge_id=key.edge_id,
        strategy_spec_digest=key.strategy_spec_digest,
        parameter_assignment_digest=key.parameter_assignment_digest,
        paper_admission_digest=key.paper_admission_digest,
        walk_forward_evidence_digest=key.walk_forward_evidence_digest,
        ef5_preregistration_digest="1" * 64,
        ef7_decision_digest="2" * 64,
        trial_chain_head_digest="3" * 64,
        covered=("U5",),
        attempt_bound=21,
        duration_bound_days=91,
        start_ns=start,
        policy_digest=POLICY.policy_digest,
    )


def world_approval(published: int, start: int) -> GovernedPaperIncubationRow:
    rec = world_record(start)
    seed = GovernedPaperIncubationRow(
        schema="governed-paper-incubation-registry-row.v1",
        sequence=0,
        kind=GovernedPaperIncubationRowKind.RECORD_APPROVAL,
        genesis_digest=rec.genesis_digest,
        edge_id=rec.edge_id,
        record_digest=governed_paper_incubation_record_digest(rec),
        record=rec,
        approver_id="synthetic-approver",
        channel="TEST_ONLY_SYNTHETIC",
        decision_record_digest="4" * 64,
        end_kind=None,
        published_at_ns=published,
        effective_at_ns=published,
        row_digest="",
    )
    return replace(seed, row_digest=governed_paper_incubation_row_digest(seed))


def world_basis(kind: GovernedPaperIncubationBasisKind, published: int, start: int) -> GovernedPaperIncubationBasis:
    seed = GovernedPaperIncubationBasis(
        schema="governed-paper-incubation-basis.v1",
        kind=kind,
        record_digest=governed_paper_incubation_record_digest(world_record(start)),
        source_id="synthetic-source",
        channel="TEST_ONLY_SYNTHETIC",
        published_at_ns=published,
        segments=(GovernedPaperIncubationInterval(start, start + 91 * DAY),),
        basis_digest="",
    )
    return replace(seed, basis_digest=governed_paper_incubation_basis_digest(seed))


EMPTY = GovernedPaperIncubationContext(POLICY, (), ())


@functools.cache
def entry_instant() -> int:
    (entry,) = kt.kelly_days(4)[3].seal.entry_safety_decisions  # world G's one entry decision (day 3)
    return entry.decision_time_ns


@functools.cache
def published_context(offset: int) -> GovernedPaperIncubationContext:
    """The day-3 context adding the first approval and its four bases, published ``offset`` ns after day 3's entry
    decision, for a record starting at E_4 (prospective)."""

    published, start = entry_instant() + offset, gpe.instant(4)
    bases = tuple(world_basis(kind, published, start) for kind in GovernedPaperIncubationBasisKind)
    return GovernedPaperIncubationContext(POLICY, (world_approval(published, start),), bases)


def incubation_day(days: tuple, context: object, table: object = TEST_TABLE):  # noqa: ANN201
    cycle_inputs, cycle, seal_inputs = rlt.risk_inputs(days, rlt.risk_context(len(days)))
    seal_inputs = replace(seal_inputs, protection=replace(seal_inputs.protection, kelly=True, incubation=context))
    with rlt.tables(rmt.TEST_ONLY_TABLE), incubation_table(table):  # type: ignore[arg-type]
        seal = build_governed_paper_day_seal(seal_inputs)
    return gpe.Day(cycle_inputs, cycle, seal_inputs, seal)


@functools.cache
def incubation_days(count: int, scenario: str = "empty") -> tuple:
    """World G's first ``count`` days of the incubation lineage (seal v13). ``empty``: no registry row ever. ``b1``: day 3
    publishes the first approval one nanosecond after its entry decision. ``production``: ``b1`` under the PRODUCTION
    incubation table."""

    if count == 0:
        return ()
    days = incubation_days(count - 1, scenario)
    day = len(days)
    context = published_context(1) if scenario != "empty" and day >= 3 else EMPTY  # noqa: PLR2004
    table = GOVERNED_PAPER_INCUBATION_PRODUCTION_TABLE if scenario == "production" else TEST_TABLE
    return (*days, incubation_day(days, context, table))


def verified(item: object, table: object = TEST_TABLE):  # noqa: ANN201
    with incubation_table(table):  # type: ignore[arg-type]
        return rlt.verified(item)


def lineage_evidence(days: tuple, table: object = TEST_TABLE) -> tuple:
    with incubation_table(table):  # type: ignore[arg-type]
        return rlt.lineage_evidence(days)


def incubation_gate(item: object, day: int, context: object, table: object = TEST_TABLE):  # noqa: ANN201
    """Day ``day``'s rule set v12 evaluation of ``item``, rebuilt independently through the public builders."""

    authority, run, _ = est.run_and_evidence(item)
    economics_result = lineage_tests.protected_replay(item)[0]
    with rlt.tables(rmt.TEST_ONLY_TABLE), incubation_table(table):  # type: ignore[arg-type]
        return build_governed_paper_entry_safety_evidence(
            authority=authority,
            run=run,
            dataset=item.seal_inputs.dataset,  # type: ignore[attr-defined]
            invalidated_from_ns=None,
            protection=est.seal_protection(item),
            portfolio=GovernedPaperEntrySafetyPortfolio(economics_result, item.seal.schedule),  # type: ignore[attr-defined]
            market_data=True,
            kill_switch=True,
            regime=rst.regime_context(day),
            system_safety=True,
            sizing=sct.NO_SOURCE,
            protective_ledger=plt.NO_PROOFS,
            risk=rlt.risk_context(day),
            kelly=True,
            incubation=context,  # type: ignore[arg-type]
        )


# --- the lineage ------------------------------------------------------------------------------------------------------


def test_world_g_incubation_lineage_seals_v13_binds_the_evidence_and_refuses_every_entry() -> None:
    days, legacy = incubation_days(4), kt.kelly_days(4)
    moved = set(kt.MOVED) | {"kelly_evidence_digest"}  # the schedule v9 binds the outcome the Kelly evidence names
    for day, (item, old) in enumerate(zip(days, legacy, strict=True)):
        seal = item.seal
        assert (seal.schema_version, seal.status, seal.reason_codes) == (V13_SEAL, gpe.SEALED, ())
        assert seal.entry_safety_rule_set_digest == GOVERNED_PAPER_ENTRY_SAFETY_INCUBATION_RULE_SET_DIGEST
        assert seal.schedule == replace(old.seal.schedule, schema_version=V9)  # no record: no decision, no window
        for name in governed_paper_day_seal_to_dict(old.seal):
            if name not in moved:
                assert getattr(seal, name) == getattr(old.seal, name), name
        assert (seal.incubation_policy_digest, seal.incubation_row_digests, seal.incubation_attempt_count) == (
            POLICY.policy_digest,
            (),
            0,
        )
        if day:
            assert seal.incubation_prefix_digest_open == days[day - 1].seal.incubation_prefix_digest_close
        verification = verified(item)
        assert (verification.intact, verification.reason_codes) == (True, ())
        assert all(not entry.entry_permitted for entry in seal.entry_safety_decisions)
    (entry,) = days[3].seal.entry_safety_decisions
    assert (entry.entry_permitted, entry.first_failure_check_id) == (False, "NT-D01")
    payload = governed_paper_day_seal_to_dict(days[1].seal)
    assert set(payload) - set(V13_FIELDS) == set(governed_paper_day_seal_to_dict(legacy[1].seal))
    evidence, verification = lineage_evidence(days)
    assert (evidence.schema_version, evidence.status) == (V13_EVIDENCE, GovernedPaperExecutionStatus.READY)
    assert (verification.intact, verification.reason_codes) == (True, ())


def test_b1_seals_a_prospective_first_approval_without_rewriting_any_sealed_fact() -> None:  # B1
    empty, published = incubation_days(4), incubation_days(4, "b1")
    assert tuple(item.seal for item in published[:3]) == tuple(item.seal for item in empty[:3]), B1
    day3, old3 = published[3].seal, empty[3].seal
    assert day3.incubation_row_digests == (published_context(1).rows[0].row_digest,)
    assert day3.incubation_prefix_digest_open == published[2].seal.incubation_prefix_digest_close, B1  # X1
    assert day3.incubation_prefix_digest_open == old3.incubation_prefix_digest_open, B1
    assert day3.incubation_prefix_digest_close != old3.incubation_prefix_digest_close  # the row is new knowledge
    assert day3.entry_safety_decisions == old3.entry_safety_decisions, B1  # the decision before P is unchanged
    gate = incubation_gate(published[3], 3, published_context(1))
    assert gate.evidence_digest == day3.entry_safety_evidence_digest  # the public builders reconstruct the seal
    found = gate.incubation_evidence
    assert found is not None and found.evidence_digest == day3.incubation_evidence_digest
    (reading,) = found.readings
    assert (reading.state, reading.state_reason, reading.record_digest) == (
        St.NOT_ESTABLISHED,
        "incubation_no_record_known",
        "",
    )
    assert found.authority.refusal_reason == "incubation_horizon_exceeds_lineage"  # world G: H = 30 days < 91
    for before, sealed in (
        (gpe.instant(3), day3.incubation_prefix_digest_open),
        (gpe.instant(4), day3.incubation_prefix_digest_close),
    ):
        assert governed_paper_incubation_prefix_digest(found, before_ns=before) == sealed
    old_gate = incubation_gate(empty[3], 3, EMPTY)
    assert old_gate.incubation_evidence.readings == found.readings, B1  # type: ignore[union-attr]
    assert verified(published[3]).intact is True
    evidence, verification = lineage_evidence(published)
    assert (evidence.schema_version, verification.intact) == (V13_EVIDENCE, True)
    # had the approval been published before the decision, the same decision would read the refused record at once
    earlier = incubation_gate(empty[3], 3, published_context(-1)).incubation_evidence
    (early,) = earlier.readings  # type: ignore[union-attr]
    assert (early.state, early.state_reason) == (St.NOT_ESTABLISHED, "incubation_horizon_exceeds_lineage")


def test_a_registry_is_append_only_inside_its_day_and_the_lineage_never_switches() -> None:
    days = incubation_days(4, "b1")
    backdated = replace(published_context(1), rows=(world_approval(gpe.instant(3) - 1, gpe.instant(4)),))
    future = replace(published_context(1), rows=(world_approval(gpe.instant(5), gpe.instant(6)),))
    other_policy = replace(POLICY, policy_id="other")
    other_policy = replace(other_policy, policy_digest=governed_paper_incubation_policy_digest(other_policy))
    for item, changes, reason in (
        (days[3], {"incubation": backdated}, "incubation_artifact_backdated_before_the_day"),
        (days[3], {"incubation": future}, "incubation_artifact_published_after_the_seal"),
        (days[2], {"incubation": replace(EMPTY, policy=other_policy)}, "incubation_policy_changed_inside_the_lineage"),
        (days[3], {"incubation": None}, "incubation_authority_lineage_switched"),
        (kt.kelly_days(2)[1], {"incubation": EMPTY}, "incubation_authority_lineage_switched"),
        (days[0], {"kelly": False}, "incubation_authority_needs_the_kelly_lineage"),
        (days[1], {"incubation": object()}, "protection_inputs_malformed:incubation"),
    ):
        with rlt.tables(rmt.TEST_ONLY_TABLE), incubation_table(), gpe.refused(reason):
            build_governed_paper_day_seal(kst.switched(item, **changes))
    with pytest.raises(ValueError, match="legacy_schema_carries_an_extension_field:incubation_policy_digest$"):
        gpe.reseal_seal(days[1].seal, schema_version=V12_SEAL)


def test_a_seal_never_promotes_a_forged_incubation_fact() -> None:
    item = incubation_days(4, "b1")[3]
    for changes in (
        {"incubation_evidence_digest": "0" * 64},
        {"incubation_prefix_digest_open": "0" * 64},
        {"incubation_prefix_digest_close": "0" * 64},
        {"incubation_attempt_count": 1},
        {"incubation_row_digests": ()},
        {"schedule": replace(item.seal.schedule, incubation_kelly_covered=True, schema_version=V9)},
    ):
        assert verified(replace(item, seal=gpe.reseal_seal(item.seal, **changes))).intact is False, changes
    assert verified(item).intact is True


def test_on_the_production_table_no_approval_is_admitted_and_seals_never_cross_tables() -> None:
    days = incubation_days(4, "production")
    for item in days:
        assert (item.seal.schema_version, item.seal.status) == (V13_SEAL, gpe.SEALED)
        assert verified(item, GOVERNED_PAPER_INCUBATION_PRODUCTION_TABLE).intact is True
        assert all(not entry.entry_permitted for entry in item.seal.entry_safety_decisions)
    gate = incubation_gate(days[3], 3, published_context(1), GOVERNED_PAPER_INCUBATION_PRODUCTION_TABLE)
    assert gate.rule_set_id == GOVERNED_PAPER_ENTRY_SAFETY_INCUBATION_RULE_SET_ID
    assert gate.incubation_evidence.authority.table_id == "production"  # type: ignore[union-attr]
    assert gate.incubation_evidence.authority.refusal_reason == "incubation_record_approval_not_admitted"  # type: ignore[union-attr]
    assert gate.incubation_evidence.authority.base_segments == ()  # type: ignore[union-attr]
    assert verified(days[3], TEST_TABLE).intact is False  # a production seal is never re-proven under the test table


# --- the accepted identities ---------------------------------------------------------------------------------------------


def test_the_accepted_v12_seals_v8_schedules_and_lineage_evidence_are_byte_identical() -> None:
    days = kt.kelly_days(2)
    assert tuple(item.seal.seal_digest for item in days) == ACCEPTED_MAIN_KELLY_SEAL_V12_DIGESTS
    assert tuple(item.seal.schedule_digest for item in days) == ACCEPTED_MAIN_KELLY_SCHEDULE_V8_DIGESTS
    assert tuple(item.seal.kelly_evidence_digest for item in days) == ACCEPTED_MAIN_KELLY_EVIDENCE_DIGESTS
    assert tuple(item.seal.entry_safety_evidence_digest for item in days) == ACCEPTED_MAIN_KELLY_ENTRY_EVIDENCE_DIGESTS
    assert all(set(V13_FIELDS).isdisjoint(governed_paper_day_seal_to_dict(item.seal)) for item in days)
    evidence, verification = rlt.lineage_evidence(days)
    assert (evidence.evidence_digest, verification.intact) == (ACCEPTED_MAIN_KELLY_LINEAGE_EVIDENCE_V12_DIGEST, True)
