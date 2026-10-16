"""Governed paper execution authority tests (GOVERNED_PAPER_TYPED_PROVENANCE_V2): genesis and per-cycle authority.

SYNTHETIC TEST VALUES ONLY: every approval here is a synthetic PASS-branch fixture, never a real human decision. The
authentic worlds (world P's EF-7 v2 admission, world G's cycles and the named scenarios) are the execution test
module's own, imported by basename so they are built once per session.
"""

from __future__ import annotations

import json
import re
from dataclasses import fields, replace
from fractions import Fraction

import pytest

from crypto_core.validation.edge_artifact_core import EdgeAuthorityBinding, edge_canonical_json, edge_sha256_text
from crypto_core.validation.edge_paper_admission_decision import edge_paper_admission_decision_digest
from crypto_core.validation.governed_paper_execution_authority import (
    GOVERNED_PAPER_AUTHORITY_NON_CLAIM_FLAGS,
    GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET,
    GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET_DIGEST,
    GovernedPaperCycleAuthority,
    GovernedPaperCyclePhase,
    GovernedPaperCycleStatus,
    GovernedPaperExecutionAuthorityError,
    GovernedPaperGenesis,
    GovernedPaperGenesisInputs,
    GovernedPaperGenesisStatus,
    build_governed_paper_cycle_authority,
    build_governed_paper_genesis,
    governed_paper_cycle_admission_window,
    governed_paper_cycle_authority_digest,
    governed_paper_cycle_reservation,
    governed_paper_genesis_authority,
    governed_paper_genesis_digest,
    governed_paper_genesis_to_dict,
    governed_paper_reservation_plan,
    verify_governed_paper_cycle_authority,
    verify_governed_paper_genesis,
)
from crypto_core.validation.governed_paper_typed_identity import governed_paper_typed_image
from crypto_core.validation.historical_execution_economics import historical_execution_latest_visible_mark
from crypto_core.validation.historical_execution_economics_policy import (
    HistoricalExecutionApprovalKind,
    historical_execution_quantize_price,
)
from crypto_core.validation.paper_sleeve_risk_budget_decision import (
    PaperSleeveRiskBudgetPolicy,
    paper_sleeve_risk_budget_policy_digest,
)
from crypto_core.validation.strategy_executable_profiles import (
    canonical_profile_parameter_assignment,
    get_strategy_executable_profile,
)

try:  # the module objects pytest collects (basename import): one shared world per session
    import test_edge_paper_admission_decision as ef7t
    import test_governed_admitted_variant_paper_execution as gpe
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_edge_paper_admission_decision as ef7t
    from tests.crypto_core.validation import test_governed_admitted_variant_paper_execution as gpe

_PREFIX = "governed_paper_execution_authority"
AUTHORIZED = GovernedPaperGenesisStatus.AUTHORIZED
BLOCKED = GovernedPaperGenesisStatus.BLOCKED
NEEDS_GOVERNANCE = GovernedPaperGenesisStatus.NEEDS_GOVERNANCE_APPROVAL
pret, ef8t, rg7t, rg4t, rg6t, rg3t = gpe.pret, gpe.ef8t, gpe.rg7t, gpe.rg4t, gpe.rg6t, gpe.rg3t
d, instant, CARRY, INS, G, DAY = gpe.d, gpe.instant, gpe.CARRY, gpe.INS, gpe.G, gpe.DAY


@pytest.fixture(autouse=True, scope="module")
def _memoized_verification():
    with pytest.MonkeyPatch.context() as patch:
        gpe.apply_memos(patch)
        yield


def code(text: str) -> str:
    return f"{_PREFIX}:{text}"


def refused(text: str):  # noqa: ANN201
    return pytest.raises(GovernedPaperExecutionAuthorityError, match=f"^{re.escape(code(text))}$")


def reseal_genesis(genesis: GovernedPaperGenesis, **changes: object) -> GovernedPaperGenesis:
    changed = replace(genesis, **changes)
    return replace(changed, genesis_digest=governed_paper_genesis_digest(changed))


def reseal_cycle(cycle: GovernedPaperCycleAuthority, **changes: object) -> GovernedPaperCycleAuthority:
    changed = replace(cycle, **changes)
    return replace(changed, cycle_digest=governed_paper_cycle_authority_digest(changed))


def genesis_of(**overrides: object) -> GovernedPaperGenesis:
    """A genesis over world G's inputs with ``overrides`` and an exact synthetic approval of the result."""

    return build_governed_paper_genesis(gpe.governed_genesis_inputs(**overrides))


def unapproved(**overrides: object) -> GovernedPaperGenesisInputs:
    return GovernedPaperGenesisInputs(**gpe.genesis_arguments(**overrides))  # type: ignore[arg-type]


def assert_flags(artifact: object) -> None:
    flags = dict(GOVERNED_PAPER_AUTHORITY_NON_CLAIM_FLAGS)
    assert {name: getattr(artifact, name) for name in flags} == flags
    assert all(type(getattr(artifact, name)) is bool for name in flags)


# --- A. the genesis derives every authority the upstream already binds ---------------------------------------------------


def test_the_world_genesis_is_authorized_and_every_fact_is_derived_from_its_upstream() -> None:
    inputs, genesis = gpe.world_genesis()
    admission, lifecycle = ef7t.admitted(), ef8t.genesis()
    walk_forward = pret.ef6_p()
    assert (genesis.status, genesis.authorized, genesis.reason_codes) == (AUTHORIZED, True, ())
    assert (genesis.sleeve_id, genesis.instrument, genesis.market_type) == (CARRY, INS, "usdt_perp")
    assert genesis.paper_admission_digest == admission.paper_admission_decision_digest
    assert (
        genesis.walk_forward_evidence_digest
        == admission.predecessor_digest
        == walk_forward.walk_forward_oos_evidence_digest
    )
    assert genesis.lifecycle_genesis_digest == lifecycle.kill_quarantine_decision_digest
    assert genesis.lifecycle_effective_at_ns == lifecycle.effective_at_ns <= genesis.genesis_start_ns == G
    assert (
        genesis.economics_policy_digest
        == walk_forward.economics_policy_digest
        == pret.economics_policy_p().policy_digest
    )
    assert genesis.executable_binding_digest == admission.executable_binding_digest
    assert genesis.strategy_spec_digest == admission.strategy_spec_digest
    assert genesis.admitted_variant_id == pret.BASE_VARIANT
    assert genesis.parameter_assignment_digest == admission.admitted_variants[0].parameter_assignment_digest
    assert genesis.unit_size == d(1)
    assert (
        genesis.risk_budget_policy_digest == admission.risk_budget_policy_digest == ef7t.budget_policy().policy_digest
    )
    assert (genesis.capacity_assumption_id, genesis.capacity_max_value) == (
        "capacity-notional",
        ef7t.CAPACITY.max_value,
    )
    assert genesis.admission_cap_fraction == admission.admission_cap_fraction
    assert (genesis.bootstrap_horizon_days, genesis.bootstrap_end_ns, genesis.reservation_band) == (
        30,
        instant(30),
        gpe.BAND,
    )
    assert (genesis.rule_set_id, genesis.rule_set_digest) == (
        GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET["rule_set_id"],
        GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET_DIGEST,
    )
    assert genesis.synthetic_test_approval_used is False
    assert_flags(genesis)
    verification = verify_governed_paper_genesis(genesis, inputs)
    assert (verification.intact, verification.recomputed_digest) == (True, genesis.genesis_digest)
    assert json.loads(verification.canonical_json) == governed_paper_genesis_to_dict(genesis)


def test_the_risk_budget_policy_is_never_an_input_and_is_rebuilt_from_the_ef7_binding() -> None:
    assert "risk_budget_policy" not in {item.name for item in fields(GovernedPaperGenesisInputs)}
    inputs, genesis = gpe.world_genesis()
    policy = governed_paper_genesis_authority(genesis, inputs).risk_budget_policy
    assert type(policy) is PaperSleeveRiskBudgetPolicy
    assert paper_sleeve_risk_budget_policy_digest(policy) == ef7t.admitted().risk_budget_policy_digest
    image = dict(governed_paper_typed_image(policy, gpe.authority._RECORD_DOMAIN)[2])  # type: ignore[index]  # noqa: SLF001
    for name, value in (("paper_only", True), ("real_orders_enabled", False), ("real_money_enabled", False)):
        assert image[name] == ["bool", value]
    assert image["require_journal_bound"] == ["bool", True]


def forged_admission(**snapshot_changes: object):  # noqa: ANN201
    """World P's EF-7 with its BOUND policy snapshot altered, the stored policy digest retained, then resealed."""

    admission = ef7t.admitted()
    snapshot = json.loads(admission.risk_budget_policy_binding.snapshot_json)
    snapshot.update(snapshot_changes)
    binding = EdgeAuthorityBinding(
        snapshot_json=edge_canonical_json(snapshot),
        expected_digest=admission.risk_budget_policy_binding.expected_digest,
    )
    forged = replace(admission, risk_budget_policy_binding=binding)
    return replace(forged, paper_admission_decision_digest=edge_paper_admission_decision_digest(forged))


@pytest.mark.parametrize(
    "changes",
    [
        {"paper_only": 1},
        {"real_orders_enabled": 0},
        {"real_money_enabled": 0},
        {"require_journal_bound": 1},
        {"total_budget": "900"},
    ],
    ids=["paper_only=1", "real_orders_enabled=0", "real_money_enabled=0", "require_journal_bound=1", "total_budget"],
)
def test_a_forged_bound_policy_never_reaches_a_genesis(changes: dict[str, object]) -> None:
    forged = forged_admission(**changes)
    with refused("paper_admission_not_authentic"):
        build_governed_paper_genesis(
            unapproved(paper_admission=forged, expected_paper_admission_digest=forged.paper_admission_decision_digest)
        )


def test_the_genesis_inputs_identity_binds_every_typed_input() -> None:
    inputs, genesis = gpe.world_genesis()
    assert genesis_of().genesis_inputs_identity_digest == genesis.genesis_inputs_identity_digest
    renamed = replace(inputs.parameter_approval, approval_reference="governance-parameters-2")
    assert (
        genesis_of(parameter_approval=renamed).genesis_inputs_identity_digest != genesis.genesis_inputs_identity_digest
    )
    other_band = genesis_of(reservation_band=d("0.2"))
    assert other_band.genesis_inputs_identity_digest != genesis.genesis_inputs_identity_digest
    assert other_band.genesis_policy_digest != genesis.genesis_policy_digest


# --- governance of the genesis itself (C1, C2) ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("approval", "reason"),
    [
        (lambda inputs: None, "genesis_approval_missing"),
        (lambda inputs: gpe.genesis_approval_for(inputs, kind=gpe.SYNTHETIC), "genesis_approval_not_human_governance"),
        (
            lambda inputs: gpe.genesis_approval_for(inputs, approved_genesis_id="gpe-other"),
            "genesis_approval_mismatch:approved_genesis_id",
        ),
        (
            lambda inputs: gpe.genesis_approval_for(inputs, approved_genesis_version="v0"),
            "genesis_approval_mismatch:approved_genesis_version",
        ),
        (
            lambda inputs: gpe.genesis_approval_for(inputs, approved_genesis_policy_digest="0" * 64),
            "genesis_approval_mismatch:approved_genesis_policy_digest",
        ),
        (
            lambda inputs: gpe.genesis_approval_for(inputs, approved_rule_set_digest="0" * 64),
            "genesis_approval_mismatch:approved_rule_set_digest",
        ),
    ],
    ids=["missing", "synthetic", "id", "version", "policy", "rule_set"],
)
def test_only_an_exact_human_approval_authorizes_a_genesis(approval, reason: str) -> None:  # noqa: ANN001
    inputs = unapproved()
    genesis = build_governed_paper_genesis(replace(inputs, approval=approval(inputs)))
    assert (genesis.status, genesis.authorized, genesis.reason_codes) == (NEEDS_GOVERNANCE, False, (code(reason),))
    assert genesis.synthetic_test_approval_used is (reason == "genesis_approval_not_human_governance")
    with refused("genesis_not_authorized"):
        governed_paper_genesis_authority(genesis, replace(inputs, approval=approval(inputs)))


def test_an_approval_that_is_not_exactly_typed_is_refused() -> None:
    inputs = gpe.governed_genesis_inputs()
    with refused("genesis_approval_kind_malformed"):
        build_governed_paper_genesis(
            replace(inputs, approval=replace(inputs.approval, approval_kind="HUMAN_GOVERNANCE"))
        )
    with refused("genesis_approval_digest_invalid"):
        build_governed_paper_genesis(replace(inputs, approval=replace(inputs.approval, approval_digest="x")))


def test_the_parameter_assignment_and_its_approval_are_exact() -> None:
    params = gpe.assignment()
    with refused("parameter_assignment_not_canonical"):
        build_governed_paper_genesis(unapproved(parameter_assignment=list(params)))
    with refused("parameter_assignment_not_canonical"):
        build_governed_paper_genesis(unapproved(parameter_assignment=tuple(reversed(params))))
    _, _, _, _, binding = gpe.ef6t.world()
    profile = get_strategy_executable_profile(binding.profile_id)
    other = tuple(canonical_profile_parameter_assignment(profile, pret.params_p(pret.UNITS[0])))
    with refused("parameter_assignment_not_the_admitted_variant"):
        build_governed_paper_genesis(unapproved(parameter_assignment=other))
    with refused("admitted_variant_unknown"):
        build_governed_paper_genesis(unapproved(admitted_variant_id=pret.VARIANT_IDS[0]))
    missing = build_governed_paper_genesis(unapproved(parameter_approval=None))
    assert missing.status is NEEDS_GOVERNANCE and code("parameter_approval_missing") in missing.reason_codes
    inputs = unapproved()
    wrong = replace(inputs.parameter_approval, approved_parameter_assignment_digest="0" * 64)
    mismatched = build_governed_paper_genesis(replace(inputs, parameter_approval=wrong))
    assert code("parameter_approval_mismatch:approved_parameter_assignment_digest") in mismatched.reason_codes


def test_the_economics_policy_is_the_walk_forward_policy_under_exact_human_approval() -> None:
    with refused("economics_policy_not_the_walk_forward_policy"):
        build_governed_paper_genesis(unapproved(economics_policy=gpe.delay_policy()))
    inputs = unapproved()
    synthetic = replace(inputs.economics_approval, approval_kind=HistoricalExecutionApprovalKind.TEST_ONLY_SYNTHETIC)
    genesis = build_governed_paper_genesis(replace(inputs, economics_approval=synthetic))
    assert code("economics_approval_not_human_governance") in genesis.reason_codes
    other = replace(inputs.economics_approval, approved_market_type="inverse_perp")
    assert (
        code("economics_approval_mismatch:approved_market_type")
        in build_governed_paper_genesis(replace(inputs, economics_approval=other)).reason_codes
    )
    aliased = replace(
        inputs.economics_approval, approval_kind="HUMAN_GOVERNANCE"
    )  # the accepted canonicalizer converts it
    with refused("economics_approval_not_canonical"):
        build_governed_paper_genesis(replace(inputs, economics_approval=aliased))
    missing = build_governed_paper_genesis(replace(inputs, economics_approval=None))
    assert code("economics_approval_missing") in missing.reason_codes


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"bootstrap_horizon_days": 29}, "bootstrap_horizon_below_minimum"),
        ({"genesis_start_ns": G - DAY}, "genesis_before_lifecycle_activation"),
        (
            {
                "equity_basis_policy": rg3t.world.basis_policy(
                    sleeve_id=CARRY, market_symbol=INS, reference_notional="5000"
                )
            },
            "equity_basis_reference_not_initial_equity",
        ),
    ],
    ids=["horizon", "before_activation", "reference_notional"],
)
def test_a_structural_shortfall_blocks_the_genesis(overrides: dict[str, object], reason: str) -> None:
    genesis = genesis_of(**overrides)
    assert genesis.status is BLOCKED and code(reason) in genesis.reason_codes and genesis.authorized is False


def test_an_envelope_that_does_not_declare_the_sleeve_blocks_the_genesis() -> None:
    env = rg7t.envelope(((rg4t.ALPHA, "400"),))
    genesis = genesis_of(
        portfolio_risk_envelope=env,
        ladder_seed=rg6t.human_seed(env, G, rg4t.ALPHA),
        performance_path_policy=rg4t.policy_for(env, ((rg4t.ALPHA, "1"),)),
    )
    assert genesis.status is BLOCKED
    assert {code("envelope_sleeve_undeclared"), code("ladder_seed_subject_mismatch")} <= set(genesis.reason_codes)


def test_an_unsupported_capacity_measure_blocks_the_genesis() -> None:
    arguments = {"capacity_assumptions": (ef7t.CAPACITY, ef7t.CAPACITY_OI), "decision_id": "ef7-gpe-oi"}
    draft = ef7t.decide(ef7t.passing_chain(), **arguments)
    admission = ef7t.decide(ef7t.passing_chain(), **arguments, governance=ef7t.approval_for(draft))
    receipt = ef8t.activate(admission, decision_id="ef8-activate-gpe-oi")
    genesis = genesis_of(
        paper_admission=admission,
        expected_paper_admission_digest=admission.paper_admission_decision_digest,
        lifecycle_genesis=receipt,
        expected_lifecycle_genesis_digest=receipt.kill_quarantine_decision_digest,
    )
    assert genesis.status is BLOCKED
    assert genesis.reason_codes == (code("capacity_measure_unsupported:capacity-open-interest"),)


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"bootstrap_horizon_days": True}, "bootstrap_horizon_days_invalid"),
        ({"bootstrap_horizon_days": "30"}, "bootstrap_horizon_days_invalid"),
        ({"reservation_band": "0.1"}, "reservation_band_invalid"),
        ({"reservation_band": d("-0.1")}, "reservation_band_invalid"),
        ({"genesis_start_ns": G + 1}, "genesis_start_ns_invalid"),
        ({"genesis_id": ""}, "genesis_id_invalid"),
        ({"expected_paper_admission_digest": "0" * 64}, "paper_admission_digest_mismatch"),
        ({"expected_lifecycle_genesis_digest": "0" * 64}, "lifecycle_genesis_digest_mismatch"),
    ],
)
def test_malformed_genesis_input_is_refused_never_represented(overrides: dict[str, object], reason: str) -> None:
    with refused(reason):
        build_governed_paper_genesis(unapproved(**overrides))


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("authorized", 1),
        ("paper_only", 1),
        ("real_orders_enabled", 0),
        ("real_money_enabled", 0),
        ("status", "AUTHORIZED"),
        ("bootstrap_horizon_days", True),
    ],
)
def test_a_forged_genesis_never_verifies_even_resealed(name: str, value: object) -> None:
    inputs, genesis = gpe.world_genesis()
    for forged in (replace(genesis, **{name: value}), reseal_genesis(genesis, **{name: value})):
        verification = verify_governed_paper_genesis(forged, inputs)
        assert verification.intact is False and verification.reason_codes
        with refused("genesis_not_authentic"):
            governed_paper_genesis_authority(forged, inputs)
    assert (
        code(f"genesis_field_mismatch:{name}")
        in verify_governed_paper_genesis(reseal_genesis(genesis, **{name: value}), inputs).reason_codes
    )


def test_the_genesis_verifier_is_total() -> None:
    inputs, genesis = gpe.world_genesis()
    for artifact, source in ((None, None), (object(), inputs), (genesis, None), (genesis, object())):
        verification = verify_governed_paper_genesis(artifact, source)
        assert verification.intact is False and verification.reason_codes


# --- B. the cycle ------------------------------------------------------------------------------------------------------------


def test_each_phase_opens_on_its_exact_upstream_state() -> None:
    days = gpe.world_days()
    expected = {0: "BOOTSTRAP_B0", 1: "BOOTSTRAP_B0", 4: "BOOTSTRAP_B1", 29: "BOOTSTRAP_B1", 30: "ORDINARY"}
    for day, phase in expected.items():
        cycle, inputs = days[day].cycle, days[day].cycle_inputs
        assert (cycle.status, cycle.phase.value, cycle.reason_codes) == (GovernedPaperCycleStatus.AUTHORIZED, phase, ())
        assert (cycle.window_start_ns, cycle.window_end_ns) == (instant(day), instant(day + 1))
        assert cycle.allocation_decision_digest == inputs.allocation_decision.allocation_decision_digest
        assert cycle.allocation_status == "READY" and cycle.sealed_day_count == day
        assert_flags(cycle)
    assert days[0].cycle.drawdown_status == "" and days[1].cycle.drawdown_status == "NOT_COMPUTABLE"
    assert (days[4].cycle.governance_status, days[4].cycle.performance_status) == ("NOT_COMPUTABLE", "NOT_COMPUTABLE")
    assert Fraction(days[4].cycle.bootstrap_max_peak_distance) <= Fraction("0.05")
    assert (days[30].cycle.governance_status, days[30].cycle.performance_status) == ("READY", "READY")
    assert days[30].cycle.bootstrap_max_peak_distance == ""


def test_the_reservation_is_derived_and_priced_on_the_engines_own_quote() -> None:
    days = gpe.world_days(6)
    world = gpe.scenario("G")
    authority_view = governed_paper_genesis_authority(world.genesis, world.genesis_inputs)
    for day in range(6):
        cycle = days[day].cycle
        mark = historical_execution_latest_visible_mark(
            gpe.archive(day - 1), policy=authority_view.economics_policy, instrument=INS, at_ns=instant(day)
        )
        assert (cycle.reservation_mark_record_digest, cycle.reservation_mark_price) == mark
        price = historical_execution_quantize_price(Fraction(mark[1]) * (1 + Fraction(gpe.BAND)))
        assert cycle.reservation_price == price[1]  # type: ignore[index]
        assert Fraction(cycle.reservation_notional) == Fraction(cycle.unit_size) * price[0]  # type: ignore[index]
        plan = gpe.reservation_plan(day, world)
        subject = days[day].cycle_inputs.allocation_inputs.sleeves[0]
        assert subject.risk_budget_state == plan.state and subject.risk_budget_decision == plan.risk_budget_decision
        assert [(tick.action, tick.intent_type, tick.quantity, tick.limit_price) for tick in plan.ticks] == [
            ("BUY", "MARKETABLE_LIMIT", cycle.unit_size, cycle.reservation_price),
            ("SELL", "MARKETABLE_LIMIT", cycle.unit_size, cycle.reservation_price),
        ]
    empty = gpe.archive_of("paper-archive-no-quote", tuple(r for r in gpe.archive(2).records if r.series_id != "mark"))
    assert gpe.reservation_plan(3, world, empty) is None


def test_a_reservation_that_is_not_the_derivation_is_refused() -> None:
    world = gpe.scenario("G")
    day = gpe.world_days(4)[3]
    foreign = governed_paper_reservation_plan(
        world.genesis,
        world.genesis_inputs,
        cycle_id="gpe-cycle-foreign",
        correlation_id="corr-gpe-cycle",
        day_index=3,
        reservation_dataset=gpe.archive(2),
    )
    governance = gpe.governance_at(3, foreign, gpe.world_days(3)[2].seal, world=world)
    with refused("allocation_reservation_not_derived"):
        build_governed_paper_cycle_authority(
            replace(
                day.cycle_inputs,
                allocation_inputs=governance.allocation_inputs,
                allocation_decision=governance.allocation,
            )
        )


def test_governance_of_another_instant_or_phase_is_refused() -> None:
    days = gpe.world_days(6)
    with refused("allocation_not_at_cycle_open"):
        build_governed_paper_cycle_authority(
            replace(
                days[5].cycle_inputs,
                allocation_inputs=days[4].cycle_inputs.allocation_inputs,
                allocation_decision=days[4].cycle_inputs.allocation_decision,
            )
        )
    with refused("drawdown_not_at_cycle_open"):
        build_governed_paper_cycle_authority(
            replace(
                days[5].cycle_inputs,
                drawdown_inputs=days[4].cycle_inputs.drawdown_inputs,
                drawdown_evidence=days[4].cycle_inputs.drawdown_evidence,
            )
        )
    with refused("drawdown_supplied_for_an_empty_window"):
        build_governed_paper_cycle_authority(
            replace(
                days[0].cycle_inputs,
                drawdown_inputs=days[1].cycle_inputs.drawdown_inputs,
                drawdown_evidence=days[1].cycle_inputs.drawdown_evidence,
            )
        )
    with refused("governance_supplied_before_any_episode"):
        build_governed_paper_cycle_authority(
            replace(
                days[2].cycle_inputs,
                governance_inputs=days[5].cycle_inputs.governance_inputs,
                governance_decision=days[5].cycle_inputs.governance_decision,
            )
        )
    with refused("portfolio_governance_not_this_cycle"):
        build_governed_paper_cycle_authority(
            replace(
                days[5].cycle_inputs,
                governance_inputs=days[4].cycle_inputs.governance_inputs,
                governance_decision=days[4].cycle_inputs.governance_decision,
            )
        )
    missing = build_governed_paper_cycle_authority(
        replace(days[5].cycle_inputs, governance_inputs=None, governance_decision=None, approval=None)
    )
    assert (
        missing.status is GovernedPaperCycleStatus.BLOCKED
        and code("portfolio_governance_missing") in missing.reason_codes
    )


def test_a_cycle_opens_only_on_the_rg3_history_it_is_given() -> None:
    days = gpe.world_days(6)
    closes = days[4].seal.day_closes
    shifted = (*closes[:-1], days[3].seal.day_closes[-1])  # day 3's close standing in for day 4's
    with refused("performance_history_not_the_sealed_history"):
        build_governed_paper_cycle_authority(replace(days[5].cycle_inputs, sealed_day_closes=shifted))
    with refused("sealed_history_not_through_previous_day"):
        build_governed_paper_cycle_authority(replace(days[5].cycle_inputs, sealed_day_closes=days[3].seal.day_closes))


@pytest.mark.parametrize(
    ("kind", "reason"),
    [
        (None, "cycle_approval_missing"),
        (gpe.SYNTHETIC, "cycle_approval_not_human_governance"),
        ("mismatch", "cycle_approval_mismatch:approved_cycle_policy_digest"),
    ],
)
def test_only_an_exact_human_approval_authorizes_a_cycle(kind: object, reason: str) -> None:
    inputs = replace(gpe.world_days(4)[3].cycle_inputs, approval=None)
    if kind is None:
        approval = None
    elif kind == "mismatch":
        approval = gpe.cycle_approval_for(inputs, approved_cycle_policy_digest="0" * 64)
    else:
        approval = gpe.cycle_approval_for(inputs, kind=kind)
    cycle = build_governed_paper_cycle_authority(replace(inputs, approval=approval))
    assert (cycle.status, cycle.authorized) == (GovernedPaperCycleStatus.NEEDS_GOVERNANCE_APPROVAL, False)
    assert cycle.reason_codes == (code(reason),)
    assert governed_paper_cycle_admission_window(cycle) is None
    with refused("cycle_approval_kind_malformed"):
        build_governed_paper_cycle_authority(
            replace(inputs, approval=replace(gpe.cycle_approval_for(inputs), approval_kind="HUMAN_GOVERNANCE"))
        )


@pytest.mark.parametrize(
    ("name", "day", "reason"),
    [
        ("stop", 4, "bootstrap_stop_triggered:1"),
        ("rejected", 0, "allocation_not_ready:ALLOCATION_REJECTED"),
        ("kill-300", 4, "lifecycle_head_not_active"),
    ],
)
def test_a_stop_a_rejection_or_a_kill_is_never_excepted(name: str, day: int, reason: str) -> None:
    cycle = gpe.days_of(name, day + 1)[day].cycle
    assert (cycle.status, cycle.authorized) == (GovernedPaperCycleStatus.BLOCKED, False)
    assert cycle.reason_codes == (code(reason),)
    assert (cycle.long_authorized, cycle.short_authorized, cycle.max_long_quantity, cycle.max_short_quantity) == (
        False,
        False,
        d(0),
        d(0),
    )
    assert governed_paper_cycle_admission_window(cycle) is None


def test_a_bootstrap_that_outlives_its_horizon_expires() -> None:
    days = gpe.days_of("b50-short", 31)
    assert days[29].cycle.phase is GovernedPaperCyclePhase.BOOTSTRAP_B0 and days[29].cycle.authorized is True
    expired = days[30].cycle
    assert (expired.status, expired.phase, expired.reason_codes) == (
        GovernedPaperCycleStatus.BLOCKED,
        GovernedPaperCyclePhase.BOOTSTRAP_B0,
        (code("bootstrap_expired"),),
    )


def test_each_direction_is_authorized_only_by_its_own_record_and_allocation() -> None:
    cycle, inputs = gpe.days_of("b50-short", 4)[3].cycle, gpe.days_of("b50-short", 4)[3].cycle_inputs
    records = {item.action: item for item in inputs.allocation_inputs.sleeves[0].risk_budget_decision.record_decisions}
    assert records["BUY"].status.value == "ELIGIBLE" and records["SELL"].status.value == "BLOCKED"
    assert records["SELL"].blockers == ("total_budget_exceeded",)
    assert (cycle.long_record_status, cycle.short_record_status) == ("ELIGIBLE", "BLOCKED")
    assert (
        Fraction(cycle.long_reserved_budget)
        == Fraction(cycle.long_final_allocated_budget)
        == Fraction(cycle.reservation_notional)
    )
    assert Fraction(cycle.short_reserved_budget) == Fraction(cycle.short_final_allocated_budget) == 0
    assert (cycle.long_authorized, cycle.short_authorized, cycle.eligible_direction_count) == (True, False, 1)
    window = governed_paper_cycle_admission_window(cycle)
    assert (window.max_long_quantity, window.max_short_quantity, window.reservation_price) == (  # type: ignore[union-attr]
        d(1),
        d(0),
        cycle.reservation_price,
    )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("authorized", 1),
        ("long_authorized", 1),
        ("short_authorized", 0),
        ("paper_only", 1),
        ("real_orders_enabled", 0),
        ("real_money_enabled", 0),
        ("status", "AUTHORIZED"),
        ("phase", "BOOTSTRAP_B0"),
        ("day_index", True),
    ],
)
def test_a_forged_cycle_never_verifies_even_resealed(name: str, value: object) -> None:
    item = gpe.world_days(4)[3]
    for forged in (replace(item.cycle, **{name: value}), reseal_cycle(item.cycle, **{name: value})):
        assert verify_governed_paper_cycle_authority(forged, item.cycle_inputs).intact is False
        with refused("cycle_not_authentic"):
            governed_paper_cycle_reservation(forged, item.cycle_inputs)
    assert (
        code(f"cycle_field_mismatch:{name}")
        in verify_governed_paper_cycle_authority(
            reseal_cycle(item.cycle, **{name: value}), item.cycle_inputs
        ).reason_codes
    )


def test_the_cycle_verifier_and_reservation_are_total_or_fail_closed() -> None:
    item = gpe.world_days(4)[3]
    for artifact, inputs in ((None, None), (object(), item.cycle_inputs), (item.cycle, None), (item.cycle, object())):
        verification = verify_governed_paper_cycle_authority(artifact, inputs)
        assert verification.intact is False and verification.reason_codes
    blocked = gpe.days_of("rejected", 1)[0]
    with refused("cycle_not_authorized"):
        governed_paper_cycle_reservation(blocked.cycle, blocked.cycle_inputs)
    reservation = governed_paper_cycle_reservation(item.cycle, item.cycle_inputs)
    assert (
        reservation.cycle == item.cycle
        and reservation.allocator_draft.draft_digest == item.cycle.reservation_draft_digest
    )


def test_the_rule_set_pins_every_bootstrap_reason_set() -> None:
    rule_set = GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET
    assert GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET_DIGEST == edge_sha256_text(edge_canonical_json(rule_set))
    assert rule_set["minimum_bootstrap_horizon_days"] == 30
    assert rule_set["supported_capacity_measure"] == [
        "max_open_position_notional",
        "quote_currency_notional",
        "per_instrument_open_position",
    ]
    for name in (
        "bootstrap_b0_drawdown_reasons",
        "bootstrap_b1_performance_reasons",
        "bootstrap_b1_drawdown_reasons",
        "bootstrap_b1_ladder_reasons",
        "bootstrap_b1_governance_reasons",
    ):
        assert rule_set[name] and all(type(item) is str for item in rule_set[name])  # type: ignore[union-attr]
