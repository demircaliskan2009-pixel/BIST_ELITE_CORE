"""S1_OWN_HISTORY_UNIFIED_CONSTRUCTION_V1 on world G: seal v14, evidence v14, X1, the public verifier and FA-19.

World G's genesis has a 30-day bootstrap horizon and its one entry decision (day 3) is refused at NT-D01, so no governed
entry and no ACTIVE incubation record is reachable here, exactly as for the accepted seal v13. These tests prove the
lineage binding of the one own-history authority, the cross-day knowledge rule of its coverage claims (X1, FA-2), the
public reconstruction and verifier, the production refusal and the byte identity of the accepted v13 artifacts (FA-19).
The readings themselves are proven on the engine worlds of ``test_governed_paper_own_history``.
"""

from __future__ import annotations

import contextlib
import functools
from collections.abc import Iterator
from dataclasses import replace

import pytest

import crypto_core.validation.governed_paper_own_history as own
from crypto_core.validation.governed_admitted_variant_paper_execution import (
    GovernedPaperExecutionStatus,
    build_governed_paper_day_seal,
    governed_paper_day_seal_to_dict,
)
from crypto_core.validation.governed_paper_entry_safety import (
    GOVERNED_PAPER_ENTRY_SAFETY_OWN_HISTORY_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_OWN_HISTORY_RULE_SET_ID,
    GovernedPaperEntrySafetyPortfolio,
    build_governed_paper_entry_safety_evidence,
)
from crypto_core.validation.governed_paper_own_history import (
    GOVERNED_PAPER_OWN_HISTORY_COVERAGE_SCHEMA,
    GOVERNED_PAPER_OWN_HISTORY_PRODUCTION_TABLE,
    GOVERNED_PAPER_OWN_HISTORY_TEST_CHANNEL,
    GovernedPaperOwnHistoryContext,
    GovernedPaperOwnHistoryCoverage,
    GovernedPaperOwnHistoryTable,
    governed_paper_own_history_coverage_digest,
    governed_paper_own_history_evidence_digest,
    governed_paper_own_history_prefix_digest,
    verify_governed_paper_own_history_evidence,
)
from crypto_core.validation.historical_execution_economics import (
    HISTORICAL_EXECUTION_INCUBATION_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    HISTORICAL_EXECUTION_OWN_HISTORY_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    simulate_historical_execution_governed_paper,
)

try:  # the module objects pytest collects (basename import), so cached worlds are shared
    import test_governed_paper_incubation_authority_lineage as ilt
    from test_governed_paper_kelly_reading import _production_tables_with_exact_memos  # noqa: F401 - autouse memos
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_governed_paper_incubation_authority_lineage as ilt
    from tests.crypto_core.validation.test_governed_paper_kelly_reading import (  # noqa: F401 - autouse memos
        _production_tables_with_exact_memos,
    )

gpe, est, kst, rlt, rmt = ilt.gpe, ilt.est, ilt.kst, ilt.rlt, ilt.rmt
HOUR = 3_600 * 10**9
V9 = HISTORICAL_EXECUTION_INCUBATION_ADMISSION_SCHEDULE_SCHEMA_VERSION
V10 = HISTORICAL_EXECUTION_OWN_HISTORY_ADMISSION_SCHEDULE_SCHEMA_VERSION
V13_SEAL, V14_SEAL = "governed-paper-day-seal.v13", "governed-paper-day-seal.v14"
V14_EVIDENCE = "governed-paper-execution-evidence.v14"
V14_FIELDS = (
    "own_history_coverage_digests",
    "own_history_evidence_digest",
    "own_history_prefix_digest_open",
    "own_history_prefix_digest_close",
)
TEST_TABLE = GovernedPaperOwnHistoryTable("test_only", GOVERNED_PAPER_OWN_HISTORY_TEST_CHANNEL, ())
PRODUCTION = GOVERNED_PAPER_OWN_HISTORY_PRODUCTION_TABLE
EMPTY = GovernedPaperOwnHistoryContext(())
# The accepted-main v13 identities this contract keeps, computed on main 7ef48bd7's own source (a detached worktree of that
# commit) before any change of this contract: world G's first two incubation days and their lineage evidence.
ACCEPTED_MAIN_INCUBATION_SEAL_V13_DIGESTS = (
    "967ba19266a48f82da167c6f5322bd05e4152c85cd639ab6986e3206b78a6f77",
    "4d903b18c0d4415928334c6f2d4e948e1bc7683e50a0d28b6138b43a0fcb87c3",
)
ACCEPTED_MAIN_INCUBATION_SCHEDULE_V9_DIGESTS = (
    "32f59567aba4a83bc0af0b98bb1506260de11247e67dc63c17bcf9936c32722d",
    "1ec0a567d68e8418cd2d2ff4a4487a6f40869c9c78cd482b62ae4e28c1a04496",
)
ACCEPTED_MAIN_INCUBATION_EVIDENCE_DIGESTS = (
    "28c1c3d6d6599392bc3824a429ba5978c3e966c5f77c3e582b6ee44433ee0d1e",
    "6b516e3df6f17a722e004c98851b032f821161c44df03f9b5faed7caf88f20f1",
)
ACCEPTED_MAIN_INCUBATION_ENTRY_EVIDENCE_V12_DIGESTS = (
    "b0759a0ff6862908176cd899b18811deb9617aad4535141f7b598c245ee5dc1c",
    "0ba20d21a9abb51c3f21ac268e38c3332dbff29657af164d5d4ae1fc5d2f00e8",
)
ACCEPTED_MAIN_INCUBATION_KELLY_EVIDENCE_DIGESTS = (
    "77370e5bf0606e77d52df16a11f2e316e97965844f27a4428045cc8df715037d",
    "9fc33cc86b476684d9664a337168303cef3a65f94fba4352a31cf6ff035f26f9",
)
ACCEPTED_MAIN_INCUBATION_OUTCOME_DIGESTS = (
    "2ec6f8890b6a8e71180f8afe6f7cc25bd24bd95b0b7c157247e2d4710499ff1a",
    "93eb81ab1d7f5890010be330610850f77eabe827f427a25d2f3e2de6c5d4ae4e",
)
ACCEPTED_MAIN_INCUBATION_LINEAGE_EVIDENCE_V13_DIGEST = (
    "9cbcd1d6541b864c0e14460b6e80c131c4cc46017f621e110a99d3f8c7b988d6"
)
# What a v14 seal of the same day may change against the v13 seal: its version and identities, the schedule v10 and the
# outcome, entry evidence and rule set that bind it, and the derived evidence that names that outcome (the incubation
# evidence is v2: it graduates on the U1-U4 coverage ends). Every other v13 field is identical.
MOVED = {
    "schema_version",
    "prior_seal_digest",
    "seal_digest",
    "schedule",
    "schedule_digest",
    "governed_outcome_digest",
    "entry_safety_rule_set_digest",
    "entry_safety_evidence_digest",
    "entry_safety_decisions",
    "kill_switch_ladder_digest",
    "kill_switch_prefix_digest_open",
    "kill_switch_prefix_digest_close",
    "system_state_evidence_digest",
    "sizing_evidence_digest",
    "protective_ledger_evidence_digest",
    "risk_evidence_digest",
    "kelly_evidence_digest",
    "incubation_evidence_digest",
    "incubation_prefix_digest_open",
    "incubation_prefix_digest_close",
}


@contextlib.contextmanager
def own_table(value: GovernedPaperOwnHistoryTable = TEST_TABLE) -> Iterator[None]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(own, "_TABLE", value)
        yield


@functools.cache
def world_identity() -> tuple[str, str, tuple[str, str, str]]:
    """World G's archive identity, instrument and the three series its economics reads."""

    item = ilt.incubation_days(1)[0]
    _, run, _ = est.run_and_evidence(item)
    result = ilt.lineage_tests.protected_replay(item)[0]
    series = (run.funding_series_id, result.mark_series_id, result.order_book_series_id)
    return item.seal_inputs.dataset.source_manifest_digest, run.instrument, series


def world_context(published: int) -> GovernedPaperOwnHistoryContext:
    """SYNTHETIC test-only claims covering world G's three series from G for 31 days, published at ``published``."""

    manifest, instrument, series = world_identity()
    claims = []
    for name in series:
        seed = GovernedPaperOwnHistoryCoverage(
            schema=GOVERNED_PAPER_OWN_HISTORY_COVERAGE_SCHEMA,
            source_manifest_digest=manifest,
            instrument=instrument,
            series_id=name,
            start_ns=gpe.instant(0),
            end_ns=gpe.instant(31),
            channel=GOVERNED_PAPER_OWN_HISTORY_TEST_CHANNEL,
            published_at_ns=published,
            coverage_digest="",
        )
        claims.append(replace(seed, coverage_digest=governed_paper_own_history_coverage_digest(seed)))
    return GovernedPaperOwnHistoryContext(tuple(claims))


LATE = gpe.instant(2) + HOUR  # inside day 2


def own_day(days: tuple, context: object, table: GovernedPaperOwnHistoryTable = TEST_TABLE):  # noqa: ANN201
    cycle_inputs, cycle, seal_inputs = rlt.risk_inputs(days, rlt.risk_context(len(days)))
    protection = replace(seal_inputs.protection, kelly=True, incubation=ilt.EMPTY, own_history=context)
    seal_inputs = replace(seal_inputs, protection=protection)
    with rlt.tables(rmt.TEST_ONLY_TABLE), ilt.incubation_table(), own_table(table):
        seal = build_governed_paper_day_seal(seal_inputs)
    return gpe.Day(cycle_inputs, cycle, seal_inputs, seal)


@functools.cache
def own_days(count: int, scenario: str = "covered") -> tuple:
    """World G's first ``count`` days of the own-history lineage (seal v14). ``covered``: the claims, published at G, on
    every day. ``absent``: no claim ever. ``late``: day 2 publishes the claims one hour after it opens. ``production``:
    ``covered`` under the PRODUCTION own-history table."""

    if count == 0:
        return ()
    days = own_days(count - 1, scenario)
    day = len(days)
    if scenario == "absent" or (scenario == "late" and day < 2):  # noqa: PLR2004
        context = EMPTY
    else:
        context = world_context(LATE if scenario == "late" else gpe.instant(0))
    return (*days, own_day(days, context, PRODUCTION if scenario == "production" else TEST_TABLE))


def verified(item: object, table: GovernedPaperOwnHistoryTable = TEST_TABLE):  # noqa: ANN201
    with own_table(table):
        return ilt.verified(item)


def lineage_evidence(days: tuple, table: GovernedPaperOwnHistoryTable = TEST_TABLE) -> tuple:
    with own_table(table):
        return ilt.lineage_evidence(days)


def own_gate(item: object, day: int, context: object, table: GovernedPaperOwnHistoryTable = TEST_TABLE):  # noqa: ANN201
    """Day ``day``'s rule set v13 evaluation of ``item``, rebuilt independently through the public builders."""

    authority, run, _ = est.run_and_evidence(item)
    economics_result = ilt.lineage_tests.protected_replay(item)[0]
    with rlt.tables(rmt.TEST_ONLY_TABLE), ilt.incubation_table(), own_table(table):
        return build_governed_paper_entry_safety_evidence(
            authority=authority,
            run=run,
            dataset=item.seal_inputs.dataset,  # type: ignore[attr-defined]
            invalidated_from_ns=None,
            protection=est.seal_protection(item),
            portfolio=GovernedPaperEntrySafetyPortfolio(economics_result, item.seal.schedule),  # type: ignore[attr-defined]
            market_data=True,
            kill_switch=True,
            regime=ilt.rst.regime_context(day),
            system_safety=True,
            sizing=ilt.sct.NO_SOURCE,
            protective_ledger=ilt.plt.NO_PROOFS,
            risk=rlt.risk_context(day),
            kelly=True,
            incubation=ilt.EMPTY,
            own_history=context,  # type: ignore[arg-type]
        )


# --- the accepted identities (FA-19) -------------------------------------------------------------------------------------------


def test_the_accepted_v13_seals_v9_schedules_and_lineage_evidence_are_byte_identical() -> None:  # FA-19
    days = ilt.incubation_days(2)
    assert tuple(item.seal.seal_digest for item in days) == ACCEPTED_MAIN_INCUBATION_SEAL_V13_DIGESTS
    assert tuple(item.seal.schedule_digest for item in days) == ACCEPTED_MAIN_INCUBATION_SCHEDULE_V9_DIGESTS
    assert tuple(item.seal.incubation_evidence_digest for item in days) == ACCEPTED_MAIN_INCUBATION_EVIDENCE_DIGESTS
    assert (
        tuple(item.seal.entry_safety_evidence_digest for item in days)
        == ACCEPTED_MAIN_INCUBATION_ENTRY_EVIDENCE_V12_DIGESTS
    )
    assert tuple(item.seal.kelly_evidence_digest for item in days) == ACCEPTED_MAIN_INCUBATION_KELLY_EVIDENCE_DIGESTS
    assert tuple(item.seal.governed_outcome_digest for item in days) == ACCEPTED_MAIN_INCUBATION_OUTCOME_DIGESTS
    assert all(set(V14_FIELDS).isdisjoint(governed_paper_day_seal_to_dict(item.seal)) for item in days)
    evidence, verification = ilt.lineage_evidence(days)
    assert (evidence.evidence_digest, verification.intact) == (
        ACCEPTED_MAIN_INCUBATION_LINEAGE_EVIDENCE_V13_DIGEST,
        True,
    )


# --- the lineage ------------------------------------------------------------------------------------------------------------


def test_world_g_own_history_lineage_seals_v14_binds_the_authority_and_refuses_every_entry() -> None:
    days, legacy = own_days(4), ilt.incubation_days(4)
    claims = tuple(item.coverage_digest for item in world_context(gpe.instant(0)).coverages)
    for day, (item, old) in enumerate(zip(days, legacy, strict=True)):
        seal = item.seal
        assert (seal.schema_version, seal.status, seal.reason_codes) == (V14_SEAL, gpe.SEALED, ())
        assert seal.entry_safety_rule_set_digest == GOVERNED_PAPER_ENTRY_SAFETY_OWN_HISTORY_RULE_SET_DIGEST
        assert seal.schedule == replace(old.seal.schedule, schema_version=V10)  # no record: the same bounds
        changed = {
            name for name in governed_paper_day_seal_to_dict(old.seal) if getattr(seal, name) != getattr(old.seal, name)
        }
        assert changed <= MOVED, changed - MOVED
        assert seal.own_history_coverage_digests == claims
        if day:
            assert seal.own_history_prefix_digest_open == days[day - 1].seal.own_history_prefix_digest_close  # X1
        verification = verified(item)
        assert (verification.intact, verification.reason_codes) == (True, ())
        assert all(not entry.entry_permitted for entry in seal.entry_safety_decisions)
    (entry,) = days[3].seal.entry_safety_decisions
    assert (entry.entry_permitted, entry.first_failure_check_id) == (False, "NT-D01")
    payload = governed_paper_day_seal_to_dict(days[1].seal)
    assert set(payload) - set(V14_FIELDS) == set(governed_paper_day_seal_to_dict(legacy[1].seal))
    evidence, verification = lineage_evidence(days)
    assert (evidence.schema_version, evidence.status) == (V14_EVIDENCE, GovernedPaperExecutionStatus.READY)
    assert (verification.intact, verification.reason_codes) == (True, ())


def test_a_claim_published_inside_day_2_never_rewrites_a_sealed_fact() -> None:  # FA-2, X1
    absent, late = own_days(4, "absent"), own_days(4, "late")
    assert tuple(item.seal for item in late[:2]) == tuple(item.seal for item in absent[:2])
    day2, old2 = late[2].seal, absent[2].seal
    assert day2.own_history_coverage_digests == tuple(item.coverage_digest for item in world_context(LATE).coverages)
    assert day2.own_history_prefix_digest_open == late[1].seal.own_history_prefix_digest_close  # X1
    assert day2.own_history_prefix_digest_open == old2.own_history_prefix_digest_open  # nothing before E_2 changed
    assert day2.own_history_evidence_digest != old2.own_history_evidence_digest  # the claims are new knowledge
    # world G reads nothing before its day-3 entry, so the prefix at E_3 is unchanged; the day-3 reading is complete
    assert day2.own_history_prefix_digest_close == old2.own_history_prefix_digest_close
    day3, old3 = late[3].seal, absent[3].seal
    assert day3.own_history_prefix_digest_open == day2.own_history_prefix_digest_close  # X1
    assert day3.own_history_prefix_digest_close != old3.own_history_prefix_digest_close
    assert all(verified(item).intact for item in late)
    evidence, verification = lineage_evidence(late)
    assert (evidence.schema_version, verification.intact) == (V14_EVIDENCE, True)


def test_coverage_claims_are_append_only_inside_their_day_and_the_lineage_never_switches() -> None:
    late = own_days(4, "late")
    for item, changes, reason in (
        (late[2], {"own_history": world_context(gpe.instant(2) - 1)}, "own_history_coverage_backdated_before_the_day"),
        (late[2], {"own_history": world_context(gpe.instant(3) + 1)}, "own_history_coverage_published_after_the_seal"),
        (late[3], {"own_history": EMPTY}, "own_history_coverage_rewritten"),
        (late[3], {"own_history": None}, "own_history_authority_lineage_switched"),
        (ilt.incubation_days(2)[1], {"own_history": EMPTY}, "own_history_authority_lineage_switched"),
        (late[0], {"incubation": None}, "own_history_authority_needs_the_incubation_lineage"),
        (late[1], {"own_history": object()}, "protection_inputs_malformed:own_history"),
        (late[1], {"own_history": GovernedPaperOwnHistoryContext([])}, "own_history_context_not_canonical"),
    ):
        with rlt.tables(rmt.TEST_ONLY_TABLE), ilt.incubation_table(), own_table(), gpe.refused(reason):
            build_governed_paper_day_seal(kst.switched(item, **changes))
    with pytest.raises(ValueError, match="legacy_schema_carries_an_extension_field:own_history_coverage_digests$"):
        gpe.reseal_seal(own_days(2)[1].seal, schema_version=V13_SEAL)


def test_a_seal_never_promotes_a_forged_own_history_fact() -> None:
    item = own_days(4)[3]
    for changes in (
        {"own_history_evidence_digest": "0" * 64},
        {"own_history_prefix_digest_open": "0" * 64},
        {"own_history_prefix_digest_close": "0" * 64},
        {"own_history_coverage_digests": ()},
        {"schedule": replace(item.seal.schedule, schema_version=V9)},
    ):
        assert verified(replace(item, seal=gpe.reseal_seal(item.seal, **changes))).intact is False, changes
    assert verified(item).intact is True


# --- the public reconstruction and verifier -------------------------------------------------------------------------------


def test_the_public_builders_and_verifier_reconstruct_the_sealed_own_history_authority() -> None:
    item = own_days(4)[3]
    context = world_context(gpe.instant(0))
    gate = own_gate(item, 3, context)
    assert (gate.rule_set_id, gate.evidence_digest) == (
        GOVERNED_PAPER_ENTRY_SAFETY_OWN_HISTORY_RULE_SET_ID,
        item.seal.entry_safety_evidence_digest,
    )
    found = gate.own_history_evidence
    assert found is not None and found.evidence_digest == item.seal.own_history_evidence_digest
    for before, sealed in (
        (gpe.instant(3), item.seal.own_history_prefix_digest_open),
        (gpe.instant(4), item.seal.own_history_prefix_digest_close),
    ):
        assert governed_paper_own_history_prefix_digest(found, before_ns=before) == sealed
    (entry,) = item.seal.entry_safety_decisions
    (reading,) = found.readings  # world G's one entry decision
    assert (reading.decision_sequence, reading.decision_time_ns, reading.complete) == (
        entry.decision_sequence,
        entry.decision_time_ns,
        True,
    )
    assert [item_.decision_sequence for item_ in found.signals] == sorted(
        item_.decision_sequence for item_ in found.signals
    )
    assert gate.incubation_evidence.schema_version == "governed-paper-incubation-evidence.v2"  # type: ignore[union-attr]
    sizing = gate.sizing_evidence
    assert sizing is not None and sizing.schema_version == "governed-paper-sizing-evidence.v2"
    (row,) = sizing.readings
    assert row.allocation_reason == f"own_history:{reading.allocation_reason}"
    assert row.allocation_rebalance_ns == reading.allocation_rebalance_ns
    authority, run, _ = est.run_and_evidence(item)
    result = ilt.lineage_tests.protected_replay(item)[0]
    outcome = simulate_historical_execution_governed_paper(
        result, expected_result_digest=result.result_digest, schedule=item.seal.schedule
    )
    assert outcome.outcome_digest == item.seal.governed_outcome_digest
    replay = {
        "authority": authority,
        "run": run,
        "dataset": item.seal_inputs.dataset,
        "result": result,
        "expected_result_digest": result.result_digest,
        "outcome": outcome,
    }
    forged = replace(found, readings=(replace(reading, complete=False),))
    resealed = replace(forged, evidence_digest=governed_paper_own_history_evidence_digest(forged))
    with own_table():
        verification = verify_governed_paper_own_history_evidence(found, context=context, **replay)
        assert (verification.intact, verification.reason_codes) == (True, ())
        refused = verify_governed_paper_own_history_evidence(resealed, context=context, **replay)
        assert refused.reason_codes == ("governed_paper_own_history:evidence_not_the_derivation",)
        assert verify_governed_paper_own_history_evidence(forged, context=context, **replay).intact is False
        assert verify_governed_paper_own_history_evidence(found, context=EMPTY, **replay).intact is False
    with own_table(PRODUCTION):
        assert verify_governed_paper_own_history_evidence(found, context=context, **replay).intact is False


def test_on_the_production_table_no_claim_is_admitted_and_seals_never_cross_tables() -> None:
    days = own_days(4, "production")
    for item in days:
        assert (item.seal.schema_version, item.seal.status) == (V14_SEAL, gpe.SEALED)
        assert verified(item, PRODUCTION).intact is True
        assert all(not entry.entry_permitted for entry in item.seal.entry_safety_decisions)
    gate = own_gate(days[3], 3, world_context(gpe.instant(0)), PRODUCTION)
    found = gate.own_history_evidence
    assert found is not None and (found.table_id, found.coverage_digests) == ("production", ())
    assert all(item.endswith(":coverage_channel_not_admitted_by_the_active_table") for item in found.coverage_refusals)
    assert {item.complete for item in found.readings} == {False}
    assert verified(days[3], TEST_TABLE).intact is False  # a production seal is never re-proven under the test table
    assert verified(own_days(4)[3], PRODUCTION).intact is False
