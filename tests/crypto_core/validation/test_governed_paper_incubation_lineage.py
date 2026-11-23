"""Incubation lineage tests on world G (seal v13, evidence v13, rule set v12, schedule v9) and the legacy pins.

SYNTHETIC TEST VALUES ONLY. Every policy approval, registry row and basis is a TEST_ONLY_SYNTHETIC fixture; the production
registry and policy table are empty and production ACTIVE is unreachable (HD-INC-AUTH-1 r2). World G's one entry decision
is refused first by NT-D01 under every registry: incubation never relaxes a data, risk or protective gate.

What is proven: the lineage seals v13 from day 0 or never and never switches, binds the policy, the registry projection and
the incubation evidence with X1 chains (opening prefix = previous closing prefix), refuses a backdated registry row and a
change of registry, verifies through the public lineage verifier, never verifies a TEST-ONLY lineage against the
production registry, and leaves every accepted-main v12 identity byte-identical (pinned on main 523c140e before any change).
"""

from __future__ import annotations

import contextlib
import functools
from collections.abc import Iterator
from dataclasses import replace

import pytest

import crypto_core.validation.governed_paper_incubation as incubation_module
from crypto_core.validation.governed_admitted_variant_paper_execution import (
    GovernedPaperDaySealStatus,
    GovernedPaperExecutionError,
    GovernedPaperExecutionStatus,
    build_governed_paper_day_seal,
    governed_paper_day_seal_to_dict,
)
from crypto_core.validation.governed_paper_entry_safety import (
    GOVERNED_PAPER_ENTRY_SAFETY_INCUBATION_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_KELLY_RULE_SET_DIGEST,
)
from crypto_core.validation.governed_paper_incubation import (
    GOVERNED_PAPER_INCUBATION_PRODUCTION_POLICY_TABLE,
    GOVERNED_PAPER_INCUBATION_PRODUCTION_REGISTRY,
    GovernedPaperIncubationApprovalKind,
    GovernedPaperIncubationBasisKind,
    GovernedPaperIncubationContext,
    GovernedPaperIncubationPolicyTable,
    GovernedPaperIncubationRegistry,
    build_governed_paper_incubation_approval_row,
    build_governed_paper_incubation_basis,
    build_governed_paper_incubation_policy,
    build_governed_paper_incubation_policy_approval,
    governed_paper_incubation_record_for_lineage,
)
from crypto_core.validation.historical_execution_economics import (
    HISTORICAL_EXECUTION_INCUBATION_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    historical_execution_admission_schedule_digest,
)

try:  # the module objects pytest collects (basename import), so cached worlds are shared
    import test_governed_admitted_variant_paper_execution as gpe
    import test_governed_paper_entry_safety as est
    import test_governed_paper_kelly_reading as kr
    import test_governed_paper_risk_lineage as rlt
    import test_governed_paper_risk_measurement as rmt
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_governed_admitted_variant_paper_execution as gpe
    from tests.crypto_core.validation import test_governed_paper_entry_safety as est
    from tests.crypto_core.validation import test_governed_paper_kelly_reading as kr
    from tests.crypto_core.validation import test_governed_paper_risk_lineage as rlt
    from tests.crypto_core.validation import test_governed_paper_risk_measurement as rmt

DAY = 86_400 * 1_000_000_000
SYNTHETIC = GovernedPaperIncubationApprovalKind.TEST_ONLY_SYNTHETIC
TEST_POLICY_TABLE = GovernedPaperIncubationPolicyTable("test_only", SYNTHETIC, ())
POLICY = build_governed_paper_incubation_policy(policy_id="synthetic-incubation-policy", policy_version="1")
CONTEXT = GovernedPaperIncubationContext(
    POLICY,
    build_governed_paper_incubation_policy_approval(
        approval_kind=SYNTHETIC, approver_reference="test-only", approved_policy_digest=POLICY.policy_digest
    ),
)
EMPTY = GovernedPaperIncubationRegistry("test_only", SYNTHETIC, (), ())
V13_SEAL, V13_EVIDENCE = "governed-paper-day-seal.v13", "governed-paper-execution-evidence.v13"
V13_FIELDS = (
    "incubation_policy_digest",
    "incubation_policy_approval_digest",
    "incubation_registry_id",
    "incubation_projection_digest_open",
    "incubation_projection_digest_close",
    "incubation_record_digest",
    "incubation_evidence_digest",
    "incubation_prefix_digest_open",
    "incubation_prefix_digest_close",
    "incubation_attempts_at_close",
    "incubation_final_state",
)
# The accepted-main identities this contract keeps, computed on main 523c140e's source before any change of this contract:
# rule set v11, world G's Kelly lineage seals v12 (seal, Kelly evidence and schedule v8 digests) and its evidence v12.
ACCEPTED_MAIN_RULE_SET_V11_DIGEST = "4c5d6e8612b8957ac97f5064a8dbba39f8b3571421a0154b27d73b5a2780cb21"
ACCEPTED_MAIN_KELLY_SEALS_V12 = (
    (
        "549fc5fd6bf00f022bf19b5f49df86653991d36c443f71a50ed9462332b8bb3d",
        "0d5d99231b93571bbba93de272ddbfc9462d3d4ee40d27edf1edf323b9dcf6cc",
        "97d86a0b439074ca56f0970b871c3c63630bfa3c2a40a62aea7cdd63cc7244f1",
    ),
    (
        "8fd7209bef30892426ff75b7f5e592c8cc623c4af192076ddad4eea1f805ea7c",
        "a8dd315564d8e447a76a620844fd854251d6f6cdfaa09b148319a2b78a374b14",
        "e8ceea2c89c01c2748f1f6b5ed6dd258ec6909d7d268aedf8c95f9535a98131f",
    ),
    (
        "eecd3afe1f892b93795ca10fb0931cf58dee90bbf95b41788327f80741ae45af",
        "c3e75e054301a6037021df73305a563539bb6e326bd75a164e994ce274d1a859",
        "36c7a49d1d1939fa5faf224a78d530b65349a6d7cccc5b7fcf845dc09af0b397",
    ),
    (
        "6bcdd62850b74c6e3873a1923a30f1f022e6cfc04ba6a801bf7189c20b4c8016",
        "5126822ea7a100ee9f58ed375eea34728d61d79a2f82d2cfe77bbbe9d996c684",
        "edff6b95f7e1fd6c5ee1f4de8492332eb97a71e63e59160c01208842d8d49feb",
    ),
)
ACCEPTED_MAIN_KELLY_EVIDENCE_V12_DIGEST = "d6b2cca1526422e526b883af02fe2b0e7744af1187b29fc0131d3f4ab869a605"

_autouse = kr._production_tables_with_exact_memos  # noqa: SLF001 - the shared exact memos of the world G helpers


@contextlib.contextmanager
def installed(registry: object, table: object = TEST_POLICY_TABLE) -> Iterator[None]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(incubation_module, "_REGISTRY", registry)
        patch.setattr(incubation_module, "_POLICY_TABLE", table)
        yield
    assert incubation_module._REGISTRY is GOVERNED_PAPER_INCUBATION_PRODUCTION_REGISTRY  # noqa: SLF001
    assert incubation_module._POLICY_TABLE is GOVERNED_PAPER_INCUBATION_PRODUCTION_POLICY_TABLE  # noqa: SLF001


def incubation_inputs(days: tuple, context: object = CONTEXT):  # noqa: ANN201
    cycle_inputs, cycle, seal_inputs = rlt.risk_inputs(days, rlt.risk_context(len(days)))
    protection = replace(seal_inputs.protection, kelly=True, incubation=context)
    return cycle_inputs, cycle, replace(seal_inputs, protection=protection)


def incubation_day(days: tuple, registry: object = EMPTY, table: object = TEST_POLICY_TABLE):  # noqa: ANN201
    cycle_inputs, cycle, seal_inputs = incubation_inputs(days)
    with rlt.tables(rmt.TEST_ONLY_TABLE), installed(registry, table):
        seal = build_governed_paper_day_seal(seal_inputs)
    return gpe.Day(cycle_inputs, cycle, seal_inputs, seal)


@functools.cache
def incubation_days(count: int, key: str = "empty") -> tuple:
    if count == 0:
        return ()
    days = incubation_days(count - 1, key)
    registry, table = REGISTRIES[key]()
    return (*days, incubation_day(days, registry, table))


@functools.cache
def active_registry() -> GovernedPaperIncubationRegistry:
    """A TEST-ONLY approval of world G's record from day 0, with every r2 basis (SYNTHETIC)."""

    authority = est.run_and_evidence(kr.kelly_days(1)[0])[0]
    g0 = authority.genesis.genesis_start_ns
    record = governed_paper_incubation_record_for_lineage(authority, covered=("U3", "U4", "U5"), start_ns=g0)
    row = build_governed_paper_incubation_approval_row(
        record=record,
        approval_kind=SYNTHETIC,
        approver_reference="test-only",
        approval_time_ns=g0,
        decision_record_digest="a" * 64,
        published_at_ns=g0,
    )
    bases = tuple(
        build_governed_paper_incubation_basis(
            basis_kind=kind,
            record_digest=record.record_digest,
            valid_from_ns=g0,
            valid_until_ns=g0 + 400 * DAY,
            basis_reference=f"test-only-{kind.value.lower()}",
        )
        for kind in GovernedPaperIncubationBasisKind
    )
    return GovernedPaperIncubationRegistry("test_only", SYNTHETIC, (row,), bases)


REGISTRIES = {
    "empty": lambda: (EMPTY, TEST_POLICY_TABLE),
    "active": lambda: (active_registry(), TEST_POLICY_TABLE),
    "production": lambda: (
        GOVERNED_PAPER_INCUBATION_PRODUCTION_REGISTRY,
        GOVERNED_PAPER_INCUBATION_PRODUCTION_POLICY_TABLE,
    ),
}


def lineage_evidence(days: tuple, registry: object, table: object = TEST_POLICY_TABLE) -> tuple:
    with installed(registry, table):
        return rlt.lineage_evidence(days)


def test_the_accepted_v12_kelly_lineage_and_rule_set_v11_stay_byte_identical() -> None:  # F6, I18
    assert ACCEPTED_MAIN_RULE_SET_V11_DIGEST == GOVERNED_PAPER_ENTRY_SAFETY_KELLY_RULE_SET_DIGEST
    days = kr.kelly_days(4)
    observed = tuple(
        (
            item.seal.seal_digest,
            item.seal.kelly_evidence_digest,
            historical_execution_admission_schedule_digest(item.seal.schedule),
        )
        for item in days
    )
    assert observed == ACCEPTED_MAIN_KELLY_SEALS_V12
    for item in days:
        assert not set(V13_FIELDS) & set(governed_paper_day_seal_to_dict(item.seal))
    evidence, verification = rlt.lineage_evidence(days)
    assert (evidence.evidence_digest, verification.intact) == (ACCEPTED_MAIN_KELLY_EVIDENCE_V12_DIGEST, True)


def test_world_g_incubation_lineage_seals_v13_binds_its_chains_and_refuses_every_entry() -> None:  # F4
    days, legacy = incubation_days(4), kr.kelly_days(4)
    for day, (item, old) in enumerate(zip(days, legacy, strict=True)):
        seal = item.seal
        assert (seal.schema_version, seal.status, seal.reason_codes) == (
            V13_SEAL,
            GovernedPaperDaySealStatus.SEALED,
            (),
        )
        assert seal.entry_safety_rule_set_digest == GOVERNED_PAPER_ENTRY_SAFETY_INCUBATION_RULE_SET_DIGEST
        assert seal.schedule.schema_version == HISTORICAL_EXECUTION_INCUBATION_ADMISSION_SCHEDULE_SCHEMA_VERSION
        assert seal.schedule == replace(
            old.seal.schedule, schema_version=HISTORICAL_EXECUTION_INCUBATION_ADMISSION_SCHEDULE_SCHEMA_VERSION
        )  # no record: no incubation entry, window or cover
        assert (seal.incubation_registry_id, seal.incubation_record_digest, seal.incubation_attempts_at_close) == (
            "test_only",
            "",
            0,
        )
        assert seal.incubation_policy_digest == POLICY.policy_digest
        if day:
            prior = days[day - 1].seal
            assert seal.incubation_prefix_digest_open == prior.incubation_prefix_digest_close
            assert seal.incubation_projection_digest_open == prior.incubation_projection_digest_close
        assert all(not entry.entry_permitted for entry in seal.entry_safety_decisions)
    (entry,) = days[3].seal.entry_safety_decisions
    assert (entry.entry_permitted, entry.first_failure_check_id, entry.basis) == (False, "NT-D01", "REFUSED")
    evidence, verification = lineage_evidence(days, EMPTY)
    assert (evidence.schema_version, evidence.status) == (V13_EVIDENCE, GovernedPaperExecutionStatus.READY)
    assert (verification.intact, verification.reason_codes) == (True, ())


def test_an_active_record_never_relaxes_world_gs_data_gate() -> None:  # I19
    days = incubation_days(4, "active")
    seal = days[3].seal
    assert seal.incubation_record_digest == active_registry().rows[0].record_digest
    assert seal.incubation_projection_digest_open != incubation_days(4)[3].seal.incubation_projection_digest_open
    (entry,) = seal.entry_safety_decisions
    assert (entry.entry_permitted, entry.first_failure_check_id) == (False, "NT-D01")
    assert seal.incubation_attempts_at_close == 0
    evidence, verification = lineage_evidence(days, active_registry())
    assert (evidence.status, verification.intact) == (GovernedPaperExecutionStatus.READY, True)


def test_the_production_registry_and_policy_table_admit_no_incubation() -> None:  # I5, I9
    days = incubation_days(2, "production")
    for item in days:
        assert item.seal.schema_version == V13_SEAL and item.seal.incubation_registry_id == "production"
        assert item.seal.incubation_record_digest == ""


def test_a_test_only_lineage_never_verifies_against_the_production_registry() -> None:
    days = incubation_days(2)
    # the public seal verifier (unmemoized) re-derives the seal over the active registry: a TEST-ONLY seal fails there
    with installed(GOVERNED_PAPER_INCUBATION_PRODUCTION_REGISTRY):
        production = rlt.verified(days[1])
    assert production.intact is False
    with installed(EMPTY):
        assert rlt.verified(days[1]).intact is True


def test_a_backdated_or_removed_row_rewrites_a_sealed_day_and_is_refused() -> None:  # I10, I12
    days = incubation_days(3)
    with pytest.raises(GovernedPaperExecutionError, match="incubation_registry_rewritten"):
        incubation_day(days, active_registry())  # world G's row is published at G, inside the sealed days
    active = incubation_days(3, "active")
    with pytest.raises(GovernedPaperExecutionError, match="incubation_registry_rewritten"):
        incubation_day(active, EMPTY)  # the sealed row removed


def test_the_incubation_lineage_starts_at_day_0_or_never_and_never_switches() -> None:
    v12 = kr.kelly_days(1)
    with pytest.raises(GovernedPaperExecutionError, match="incubation_lineage_switched"):
        incubation_day(v12)
    v13 = incubation_days(1)
    _, _, seal_inputs = incubation_inputs(v13)
    plain = replace(seal_inputs, protection=replace(seal_inputs.protection, incubation=None))
    with rlt.tables(rmt.TEST_ONLY_TABLE), installed(EMPTY):  # noqa: SIM117
        with pytest.raises(GovernedPaperExecutionError, match="incubation_lineage_switched"):
            build_governed_paper_day_seal(plain)
    other = build_governed_paper_incubation_policy(policy_id="another-policy", policy_version="1")
    changed = GovernedPaperIncubationContext(
        other,
        build_governed_paper_incubation_policy_approval(
            approval_kind=SYNTHETIC, approver_reference="test-only", approved_policy_digest=other.policy_digest
        ),
    )
    _, _, seal_inputs = incubation_inputs(v13, changed)
    with rlt.tables(rmt.TEST_ONLY_TABLE), installed(EMPTY):  # noqa: SIM117
        with pytest.raises(GovernedPaperExecutionError, match="incubation_context_changed"):
            build_governed_paper_day_seal(seal_inputs)
