"""Tests for the governed paper execution authority (GOVERNED_PAPER_EXECUTION_AUTHORITY_V1).

Fixtures are world G of the execution test module (imported under the basename pytest collects it with, so the world
and its memos are one object) and its variants. Every approval, attestation, band, horizon, cap and stop level below is
a SYNTHETIC TEST VALUE; none is a production value, and real paper execution stays BLOCKED.
"""

from __future__ import annotations

import ast
import functools
import re
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

import crypto_core.validation.governed_paper_execution_authority as authority_module
import crypto_core.validation.paper_sharpe_evidence as sharpe_module
from crypto_core.strategy.spec import strategy_spec_digest
from crypto_core.validation.edge_artifact_core import edge_canonical_json, edge_sha256_text
from crypto_core.validation.governed_paper_execution_authority import (
    GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET_DIGEST,
    GOVERNED_PAPER_NON_CLAIM_FLAGS,
    GovernedPaperCycleAuthority,
    GovernedPaperCyclePhase,
    GovernedPaperCycleStatus,
    GovernedPaperExecutionAuthorityError,
    GovernedPaperGenesisStatus,
    build_governed_paper_cycle_authority,
    build_governed_paper_genesis,
    governed_paper_cycle_admission_window,
    governed_paper_cycle_authority_digest,
    governed_paper_cycle_capacity,
    governed_paper_cycle_chain,
    governed_paper_execution_authority_rule_set,
    governed_paper_genesis_digest,
    verify_governed_paper_cycle_authority,
    verify_governed_paper_genesis,
)
from crypto_core.validation.historical_execution_economics_policy import (
    HistoricalExecutionApprovalKind,
    historical_execution_quantize_price,
)
from crypto_core.validation.paper_capacity_gate import evaluate_paper_capacity_gate
from crypto_core.validation.paper_end_to_end_episode import build_paper_end_to_end_episode
from crypto_core.validation.paper_episode_runner import run_paper_episode
from crypto_core.validation.paper_fill_simulator import (
    build_paper_fill_market_snapshot,
    build_paper_fill_policy,
    simulate_paper_fill,
)
from crypto_core.validation.paper_order_intent import build_paper_order_intent
from crypto_core.validation.paper_order_intent_admission import (
    PaperOrderIntentType,
    PaperOrderSide,
    build_paper_order_intent_request,
    evaluate_paper_order_intent_admission,
)
from crypto_core.validation.paper_pnl_report import build_paper_mark_snapshot, compute_paper_pnl_report
from crypto_core.validation.paper_position_state import apply_paper_fill_to_position
from crypto_core.validation.paper_realized_pnl import compute_paper_realized_pnl_event
from crypto_core.validation.paper_sleeve_daily_valuation_evidence import (
    PaperSleeveDayCloseValuation,
    PaperSleeveEpisodeEvidence,
)
from crypto_core.validation.strategy_signal_to_paper_intent import build_strategy_signal_to_paper_intent

try:  # the module objects pytest collects (basename import), so world G and its memos are built once
    import test_edge_kill_quarantine_decision as ef8t
    import test_edge_paper_admission_decision as ef7t
    import test_edge_pre_paper_validation_evidence as pret
    import test_governed_admitted_variant_paper_execution as gw
    import test_historical_execution_economics_policy as polt
    import test_paper_portfolio_allocation_decision as rg7t
    import test_strategy_executable_binding as bindt
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_edge_kill_quarantine_decision as ef8t
    from tests.crypto_core.validation import test_edge_paper_admission_decision as ef7t
    from tests.crypto_core.validation import test_edge_pre_paper_validation_evidence as pret
    from tests.crypto_core.validation import test_governed_admitted_variant_paper_execution as gw
    from tests.crypto_core.validation import test_historical_execution_economics_policy as polt
    from tests.crypto_core.validation import test_paper_portfolio_allocation_decision as rg7t
    from tests.crypto_core.validation import test_strategy_executable_binding as bindt

_PREFIX = "governed_paper_execution_authority"
G, DAY, INS, SLEEVE, E = gw.G, gw.DAY, gw.INS, gw.SLEEVE, gw.E
d = gw.d
UNIT = Fraction(1, 10**18)
AUTHORIZED = GovernedPaperCycleStatus.AUTHORIZED
BLOCKED = GovernedPaperCycleStatus.BLOCKED
NEEDS_GOVERNANCE = GovernedPaperCycleStatus.NEEDS_GOVERNANCE_APPROVAL


@pytest.fixture(autouse=True, scope="module")
def _memoized_verification():
    with pytest.MonkeyPatch.context() as patch:
        gw.apply_memos(patch)
        yield


def code(text: str) -> str:
    return f"{_PREFIX}:{text}"


def refused(text: str):
    return pytest.raises(GovernedPaperExecutionAuthorityError, match=f"^{re.escape(code(text))}$")


def genesis_of(**overrides: object):
    return build_governed_paper_genesis(gw.genesis_inputs(**overrides))


def cycle_of(k: int, *, genesis=None, approve: bool = True, **overrides: object):
    """World G's cycle-``k`` inputs, optionally over another genesis or with other inputs, and their authority."""

    base, _ = gw.world_g().cycles[k]
    gi, gen = (base.genesis_inputs, base.genesis) if genesis is None else genesis
    inputs = replace(base, genesis_inputs=gi, genesis=gen, approval=None, **overrides)
    return gw.approve_cycle(inputs) if approve else (inputs, build_governed_paper_cycle_authority(inputs))


# --- A. the genesis -----------------------------------------------------------------------------------------------------


def test_world_g_genesis_is_ready_and_binds_every_reproven_identity() -> None:
    gi, genesis = gw.world_genesis()
    assert (genesis.status, genesis.ready, genesis.blocked_reason_codes, genesis.governance_reason_codes) == (
        GovernedPaperGenesisStatus.READY,
        True,
        (),
        (),
    )
    ef7, ef8 = ef7t.admitted(), ef8t.genesis()
    snapshot = authority_module.edge_authority_binding_snapshot(ef7.predecessor_binding)
    assert genesis.paper_admission_decision_digest == ef7.paper_admission_decision_digest
    assert genesis.lifecycle_genesis_digest == ef8.kill_quarantine_decision_digest
    assert genesis.economics_policy_digest == snapshot["economics_policy_digest"] == gi.economics_policy.policy_digest
    assert genesis.executable_binding_digest == ef7.executable_binding_digest
    assert (genesis.admitted_variant_id, genesis.unit_size) == (pret.BASE_VARIANT, d(1))
    assert genesis.admission_cap_fraction == ef7.admission_cap_fraction
    assert (genesis.capacity_assumption_id, genesis.capacity_max_value) == (
        ef7t.CAPACITY.assumption_id,
        ef7t.CAPACITY.max_value,
    )
    assert (genesis.reservation_beta, genesis.bootstrap_horizon_days, genesis.bootstrap_end_ns) == (gw.BETA, 30, E(30))
    assert genesis.initial_equity == gi.equity_basis_policy.paper_performance_reference_notional
    assert genesis.rule_set_digest == GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET_DIGEST
    flags = dict(GOVERNED_PAPER_NON_CLAIM_FLAGS)
    assert {name: getattr(genesis, name) for name in flags} == flags
    verification = verify_governed_paper_genesis(genesis, gi)
    assert (verification.intact, verification.recomputed_digest) == (True, genesis.genesis_digest)
    assert governed_paper_genesis_digest(genesis) == genesis.genesis_digest


@pytest.mark.parametrize("kind", ["paper_adoption", "bootstrap", "reservation_band"])
def test_each_human_commitment_must_be_exact(kind: str) -> None:
    def variant(mode: str):
        if kind == "paper_adoption":
            if mode == "missing":
                return genesis_of(adopt=False)
            draft = genesis_of(adopt=False)
            value = (
                gw.approval(kind, draft.genesis_id, draft.genesis_policy_digest, kind=gw.SYNTHETIC)
                if mode == "synthetic"
                else gw.approval(kind, draft.genesis_id, "0" * 64)
            )
            return genesis_of(adoption_approval=value)
        builder = gw.bootstrap_authority if kind == "bootstrap" else gw.reservation_band
        field = "bootstrap" if kind == "bootstrap" else "reservation_band"
        record = builder()
        value = {
            "missing": None,
            "synthetic": replace(record.approval, approval_kind=gw.SYNTHETIC),  # type: ignore[arg-type]
            "mismatch": replace(record.approval, approved_subject_digest="0" * 64),  # type: ignore[arg-type]
        }[mode]
        return genesis_of(**{field: replace(record, approval=value)})

    for mode, reason in (
        ("missing", f"{kind}_approval_missing"),
        ("synthetic", f"{kind}_approval_not_human_governance"),
        ("mismatch", f"{kind}_approval_approved_subject_digest_mismatch"),
    ):
        genesis = variant(mode)
        assert genesis.status is GovernedPaperGenesisStatus.NEEDS_GOVERNANCE_APPROVAL, (mode, genesis)
        assert code(reason) in genesis.governance_reason_codes


def test_a_synthetic_economics_approval_never_adopts_the_economics() -> None:
    synthetic = replace(gw.economics_approval(), approval_kind=HistoricalExecutionApprovalKind.TEST_ONLY_SYNTHETIC)
    genesis = genesis_of(economics_approval=synthetic, adopt=False)
    assert code("economics_approval_not_human_governance") in genesis.governance_reason_codes
    assert genesis.synthetic_test_approval_used is True


@pytest.mark.parametrize(
    "tamper",
    [
        {"real_orders_enabled": True},
        {"real_money_enabled": True},
        {"paper_only": False},
        {"require_journal_bound": False},
        {"total_budget": "999999"},
        {"per_intent_budget_cap": "1000"},
        {"per_instrument_budget_cap": "1"},
        {"metadata": (("review", "rewritten"),)},
        {"schema_version": "paper-sleeve-risk-budget-policy.v0"},
    ],
)
def test_the_risk_budget_policy_must_be_exactly_what_its_public_builder_rebuilds(tamper: dict[str, object]) -> None:
    gi, genesis = gw.world_genesis()
    forged = replace(gi.risk_budget_policy, **tamper)  # the admitted digest and sleeve are kept
    assert (forged.policy_digest, forged.sleeve_id) == (gi.risk_budget_policy.policy_digest, SLEEVE)
    inputs = replace(gi, risk_budget_policy=forged)
    with refused("risk_budget_policy_not_authentic"):
        build_governed_paper_genesis(inputs)
    assert verify_governed_paper_genesis(genesis, inputs).intact is False
    assert verify_governed_paper_genesis(genesis, gi).intact  # the unchanged policy still proves the genesis


@functools.cache
def foreign_assignment():
    return pret.params_p(pret.UNITS[0])


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"admitted_variant_id": pret.VARIANT_IDS[0]}, "admitted_variant_not_admitted"),
        ({"parameter_assignment": "foreign"}, "parameter_assignment_not_the_admitted_variant"),
        ({"parameter_approval": "foreign"}, "parameter_approval_not_the_admitted_variant"),
        ({"economics_policy": "default"}, "economics_policy_not_the_admission_evaluation_policy"),
        ({"economics_approval": "other_instrument"}, "economics_approval_not_the_policy_approval"),
        ({"risk_budget_policy": "other_total"}, "risk_budget_policy_not_the_admission_policy"),
        ({"lifecycle_genesis": "disabled"}, "lifecycle_genesis_not_an_active_initial_activation"),
        ({"instrument": "ETH-USDT-PERP"}, "paper_admission_universe_not_the_instrument"),
        ({"sleeve_id": "other-sleeve"}, "paper_admission_sleeve_mismatch"),
        ({"genesis_ns": G + 1}, "genesis_not_utc_day_aligned"),
        ({"genesis_ns": G - DAY}, "lifecycle_genesis_after_paper_genesis"),
    ],
)
def test_a_foreign_variant_parameter_approval_or_head_is_refused(overrides: dict[str, object], reason: str) -> None:
    _, _, _, _, binding = gw.ef6t.world()
    resolved = {
        "parameter_assignment": {"foreign": foreign_assignment()},
        "parameter_approval": {"foreign": bindt.parameter_approval_for(binding, foreign_assignment())},
        "economics_policy": {"default": polt.cited_policy()},
        "economics_approval": {
            "other_instrument": replace(gw.economics_approval(), approved_instrument="ETH-USDT-PERP")
        },
        "risk_budget_policy": {"other_total": ef7t.budget_policy(SLEEVE, total_budget="999")},
        "lifecycle_genesis": {"disabled": ef8t.disabled()},
    }
    values = {name: resolved.get(name, {}).get(value, value) for name, value in overrides.items()}  # type: ignore[union-attr]
    with refused(reason):
        genesis_of(adopt=False, **values)


def test_scope_is_exactly_one_bootstrap_sleeve() -> None:
    two = rg7t.envelope(((SLEEVE, "400"), ("other-sleeve", "300")))
    with refused("single_sleeve_envelope_required"):
        genesis_of(adopt=False, portfolio_risk_envelope=two)
    with refused("bootstrap_not_of_the_genesis"):
        genesis_of(adopt=False, bootstrap=gw.bootstrap_authority(sleeve="other-sleeve"))
    with refused("bootstrap_not_of_the_genesis"):
        genesis_of(adopt=False, bootstrap=gw.bootstrap_authority(genesis_ns=G + DAY))


def test_the_basis_must_be_the_economics_initial_equity_and_the_horizon_the_minimum_sample() -> None:
    other_basis = gw.world.basis_policy(sleeve_id=SLEEVE, market_symbol=INS, reference_notional="1000")
    basis = genesis_of(equity_basis_policy=other_basis)
    assert basis.status is GovernedPaperGenesisStatus.BLOCKED
    assert basis.blocked_reason_codes == (code("equity_basis_reference_notional_not_initial_equity"),)
    short = genesis_of(bootstrap=gw.bootstrap_authority(horizon=29))
    assert short.blocked_reason_codes == (code("bootstrap_horizon_below_the_minimum_sample"),)
    assert authority_module._MIN_BOOTSTRAP_HORIZON_DAYS == sharpe_module._REQUIRED_CONSECUTIVE_BUCKET_COUNT


def test_the_seed_must_enter_at_the_genesis_under_human_governance() -> None:
    env = gw.solo_envelope()
    with refused("ladder_seed_not_entered_at_genesis"):
        genesis_of(adopt=False, ladder_seed=gw.rg6t.human_seed(env, G + DAY, SLEEVE))
    synthetic = gw.rg6t.make_seed(portfolio_risk_envelope=env, tier_entered_at_ns=G, sleeve_id=SLEEVE)
    assert code("ladder_seed_not_governed") in genesis_of(ladder_seed=synthetic).governance_reason_codes


@functools.cache
def open_interest_admission():
    """A governed EF-7 v2 PASS of world P whose only capacity assumption uses an unsupported measure (C6)."""

    arguments = {"capacity_assumptions": (ef7t.CAPACITY_OI,), "decision_id": "ef7-oi"}
    draft = ef7t.decide(ef7t.passing_chain(), **arguments)
    admission = ef7t.decide(ef7t.passing_chain(), **arguments, governance=ef7t.approval_for(draft))
    return admission, ef8t.activate(admission, decision_id="ef8-activate-oi")


def test_an_unsupported_capacity_measure_is_never_equated_and_blocks() -> None:
    admission, head = open_interest_admission()
    genesis = genesis_of(paper_admission=admission, lifecycle_genesis=head)
    assert genesis.status is GovernedPaperGenesisStatus.BLOCKED
    assert genesis.blocked_reason_codes == (code("capacity_measure_unsupported"),)
    assert authority_module._SUPPORTED_CAPACITY == (
        ef7t.CAPACITY.capacity_measure_id,
        ef7t.CAPACITY.unit_id,
        ef7t.CAPACITY.scope_id,
    )


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"genesis_id": ""}, "genesis_id_invalid"),
        ({"genesis_id": "x" * 65}, "genesis_id_invalid"),
        ({"methodology_id": "bad id"}, "methodology_id_invalid"),
        ({"reservation_band": "zero_beta"}, "reservation_band_beta_invalid"),
        ({"reservation_band": "other_instrument"}, "reservation_band_not_of_the_instrument"),
        ({"paper_admission": object()}, "paper_admission_malformed"),
        ({"parameter_assignment": list}, "parameter_assignment_malformed"),
    ],
)
def test_malformed_genesis_inputs_are_refused(overrides: dict[str, object], reason: str) -> None:
    band = gw.reservation_band()
    resolved = {
        "zero_beta": replace(band, beta=d(0)),
        "other_instrument": replace(band, instrument="ETH-USDT-PERP"),
    }
    values = {
        name: (
            list(pret.params_p()) if value is list else resolved.get(value, value) if isinstance(value, str) else value
        )  # type: ignore[arg-type]
        for name, value in overrides.items()
    }
    with refused(reason):
        genesis_of(adopt=False, **values)


def test_the_genesis_verifier_is_exact_and_total() -> None:
    gi, genesis = gw.world_genesis()
    forged = replace(genesis, reservation_beta=d("0.2"))
    resealed = replace(forged, genesis_digest=governed_paper_genesis_digest(forged))
    for candidate, reason in (
        (forged, "genesis_self_digest_mismatch"),
        (resealed, "genesis_field_mismatch:reservation_beta"),
        (replace(genesis, real_paper_execution_authorized=True), "genesis_self_digest_mismatch"),
    ):
        verification = verify_governed_paper_genesis(candidate, gi)
        assert verification.intact is False and code(reason) in verification.reason_codes
    for garbage in (None, object(), gi):
        assert verify_governed_paper_genesis(garbage, gi).intact is False
    assert verify_governed_paper_genesis(genesis, object()).reason_codes == (code("genesis_rebuild_failed"),)


# --- B. the cycle authority -------------------------------------------------------------------------------------------


def test_cycle_zero_reserves_one_unit_each_way_at_the_banded_opening_mark() -> None:
    inputs, cycle = gw.world_g().cycles[0]
    mark = gw.mark_price(635)
    expected = historical_execution_quantize_price(mark * (1 + Fraction(gw.BETA)))
    assert expected is not None and cycle.reservation_price == expected[1]
    assert (cycle.status, cycle.phase, cycle.authorized) == (AUTHORIZED, GovernedPaperCyclePhase.BOOTSTRAP_B0, True)
    assert Fraction(cycle.opening_mark_price) == mark
    assert (cycle.max_long_quantity, cycle.max_short_quantity) == (d(1), d(1))
    assert (cycle.window_start_ns, cycle.window_end_ns, cycle.opening_ns, cycle.closing_ns) == (G, E(1), G, E(1))
    window = governed_paper_cycle_admission_window(cycle)
    assert window is not None and (window.reservation_price, window.max_short_quantity) == (
        cycle.reservation_price,
        d(1),
    )
    chain = governed_paper_cycle_chain(inputs)
    assert chain is not None
    records = chain.risk_budget_state.records
    assert [(getattr(r.action, "value", r.action), r.quantity, r.limit_price) for r in records] == [
        ("BUY", d(1), cycle.reservation_price),
        ("SELL", d(1), cycle.reservation_price),
    ]
    assert all(r.journal_bound and r.instrument_id == INS for r in records)
    assert Fraction(chain.risk_budget_decision.total_reserved_budget) == 2 * Fraction(cycle.reservation_price)
    assert chain.allocator_draft.status.value == "DRAFT_READY" and chain.allocator_draft.eligible_count == 2
    _, gen = gw.world_genesis()
    draft, policy = governed_paper_cycle_capacity(inputs.genesis_inputs, gen, cycle)
    assert (draft, policy) == (chain.allocator_draft, chain.capacity_policy)
    admitted = evaluate_paper_capacity_gate(
        draft, policy, requested_notional=cycle.reservation_notional, requested_units=d(1), correlation_id="probe"
    )
    assert admitted.status.value == "ADMITTED"
    flags = dict(GOVERNED_PAPER_NON_CLAIM_FLAGS)
    assert {name: getattr(cycle, name) for name in flags} == flags


def test_the_cycle_approval_must_commit_to_the_exact_draft() -> None:
    inputs, draft = cycle_of(1, approve=False)
    assert (draft.status, draft.authorized, draft.window_start_ns) == (NEEDS_GOVERNANCE, False, None)
    assert draft.governance_reason_codes == (code("cycle_approval_missing"),)
    assert governed_paper_cycle_admission_window(draft) is None
    for value, reason in (
        (
            gw.approval("cycle", draft.cycle_id, draft.cycle_policy_digest, kind=gw.SYNTHETIC),
            "cycle_approval_not_human_governance",
        ),
        (gw.approval("cycle", draft.cycle_id, "0" * 64), "cycle_approval_approved_subject_digest_mismatch"),
        (gw.approval("cycle", "gp-c9", draft.cycle_policy_digest), "cycle_approval_approved_subject_id_mismatch"),
    ):
        authority = build_governed_paper_cycle_authority(replace(inputs, approval=value))
        assert authority.status is NEEDS_GOVERNANCE and code(reason) in authority.governance_reason_codes
    approved = build_governed_paper_cycle_authority(
        replace(inputs, approval=gw.approval("cycle", draft.cycle_id, draft.cycle_policy_digest))
    )
    assert approved.status is AUTHORIZED and approved.cycle_policy_digest == draft.cycle_policy_digest


def test_the_opening_archive_must_be_the_genesis_manifest_as_of_the_opening() -> None:
    inputs, _ = gw.world_g().cycles[2]
    future = gw._raw_archive((*inputs.opening_dataset.records, gw.mark_record(700)))
    with refused("opening_dataset_record_visible_after_opening"):
        build_governed_paper_cycle_authority(replace(inputs, opening_dataset=future))
    foreign = gw.foreign_manifest_archive(E(2))
    assert foreign.source_manifest_digest != inputs.opening_dataset.source_manifest_digest and foreign.advances
    with refused("opening_dataset_not_of_the_genesis_manifest"):
        build_governed_paper_cycle_authority(replace(inputs, opening_dataset=foreign))


def test_capacity_and_the_rg7_admission_cap_bound_the_reservation() -> None:
    _, capped = cycle_of(1, genesis=gw.variant_genesis(beta="10000.000000000000000000"))
    assert capped.status is BLOCKED and code("capacity_assumption_exceeded") in capped.blocked_reason_codes
    _, over = cycle_of(1, genesis=gw.variant_genesis(cap="300"))
    assert over.status is BLOCKED and code("rg7_allocation_rejected") in over.blocked_reason_codes
    assert over.allocation_status == "ALLOCATION_REJECTED" and over.window_start_ns is None


def test_the_attested_head_must_be_the_paper_genesis_receipt() -> None:
    _, killed = cycle_of(1, head_authority_inputs=gw.head_at(E(1), ef8t.disabled()))
    assert killed.status is BLOCKED
    assert {code("lifecycle_head_not_the_paper_genesis"), code("lifecycle_head_not_active")} <= set(
        killed.blocked_reason_codes
    )
    _, unattested = cycle_of(1, head_authority_inputs=gw.head_at(E(1), approval_kind=None))
    assert unattested.status is NEEDS_GOVERNANCE
    assert unattested.governance_reason_codes == (code("rg7_needs_governance_approval"),)
    assert unattested.head_attested is False


def test_a_stale_head_attestation_never_attests_the_next_cycle() -> None:
    earlier = gw.head_at(E(1))
    stale = replace(earlier, evaluation_end_ns=E(2))
    _, cycle = cycle_of(2, head_authority_inputs=stale)
    assert (cycle.status, cycle.head_attested, cycle.window_start_ns) == (NEEDS_GOVERNANCE, False, None)
    assert cycle.governance_reason_codes == (code("rg7_needs_governance_approval"),)


def test_the_time_window_source_must_be_of_the_instrument() -> None:
    with refused("metrics_summary_not_of_the_instrument"):
        genesis_of(adopt=False, metrics_summary=gw.rg3t.world_summary())


def test_b1_needs_exactly_the_insufficient_sample_and_a_strict_bootstrap_stop() -> None:
    _, b1 = gw.world_g().cycles[10]
    numerator, denominator = map(int, b1.bootstrap_max_peak_distance.split("/"))
    peak = Fraction(numerator, denominator)
    assert b1.phase is GovernedPaperCyclePhase.BOOTSTRAP_B1 and peak > 0
    floor = Fraction(peak.numerator * 10**18 // peak.denominator, 10**18)
    below, at_or_above = gw.rg8t.scale18(floor), gw.rg8t.scale18(floor if floor == peak else floor + UNIT)
    _, stopped = cycle_of(10, genesis=gw.variant_genesis(stops=(below,)))
    if floor == peak:
        assert stopped.status is AUTHORIZED  # equality never breaches
    else:
        assert stopped.status is BLOCKED and stopped.blocked_reason_codes == (code("bootstrap_stop_triggered"),)
        assert stopped.bootstrap_status == "STOP_TRIGGERED"
    _, kept = cycle_of(10, genesis=gw.variant_genesis(stops=(at_or_above,)))
    assert kept.status is AUTHORIZED and kept.phase is GovernedPaperCyclePhase.BOOTSTRAP_B1


def test_an_rg8_stop_or_missing_governance_is_never_excepted() -> None:
    w = gw.world_g()
    _, ordinary = w.cycles[30]
    assert ordinary.phase is GovernedPaperCyclePhase.ORDINARY and ordinary.governance_status == "READY"
    _, stopped = cycle_of(30, genesis=gw.variant_genesis(stops=("0.000000000000000001",)))
    assert stopped.status is BLOCKED and stopped.governance_status == "PORTFOLIO_STOP_TRIGGERED"
    assert code("rg8_portfolio_stop_triggered_never_excepted") in stopped.blocked_reason_codes
    _, unattested = cycle_of(30, head_authority_inputs=gw.head_at(E(30), approval_kind=None))
    assert unattested.governance_status == "NEEDS_GOVERNANCE_APPROVAL"
    assert code("rg8_needs_governance_approval_never_excepted") in unattested.blocked_reason_codes
    assert unattested.window_start_ns is None


def flat_closes(days: int, state) -> tuple[PaperSleeveDayCloseValuation, ...]:
    """SYNTHETIC day closes of a FLAT ``state``: the world's mark at each bucket end and the report over that state."""

    closes = []
    for day in range(days):
        mark = build_paper_mark_snapshot(
            mark_snapshot_id=f"flat-close-{day}",
            market_symbol=INS,
            mark_price=d(gw.mark_price(636 + day)),
            observed_at_ns=E(day + 1),
            correlation_id="flat-close",
        )
        report = compute_paper_pnl_report(
            state, mark, pnl_report_id=f"flat-close-pnl-{day}", correlation_id="flat-close"
        )
        closes.append(PaperSleeveDayCloseValuation(close_mark_snapshot=mark, close_pnl_report=report))
    return tuple(closes)


def test_the_bootstrap_is_bounded_by_its_horizon() -> None:
    _, genesis = gw.world_genesis()
    state = gw.execution._genesis_position(genesis)
    _, expired = cycle_of(
        30, sealed_episodes=(), sealed_day_closes=flat_closes(30, state), sealed_funding_events=(), prior_ladder=None
    )
    assert expired.status is BLOCKED and expired.blocked_reason_codes == (code("bootstrap_expired"),)
    assert expired.bootstrap_status == "EXPIRED"
    longer = gw.variant_genesis(horizon=40)
    _, within = cycle_of(
        30,
        genesis=longer,
        sealed_episodes=(),
        sealed_day_closes=flat_closes(30, gw.execution._genesis_position(longer[1])),
        sealed_funding_events=(),
        prior_ladder=None,
    )
    assert (within.status, within.phase) == (AUTHORIZED, GovernedPaperCyclePhase.BOOTSTRAP_B0)


def zero_return_history(genesis_inputs, genesis, capacity):
    """A SYNTHETIC zero-fee round trip at one price on day 0 and 30 flat closes: every daily return is exactly zero."""

    draft, policy = capacity
    spec = authority_module.governed_paper_strategy_spec(genesis_inputs)
    prior = gw.execution._genesis_position(genesis)
    episodes = []
    for seq, (side, at) in enumerate(((PaperOrderSide.BUY, G + 100), (PaperOrderSide.SELL, G + 200))):
        decision = evaluate_paper_capacity_gate(
            draft, policy, requested_notional="40", requested_units="1", correlation_id=f"zero-cap-{seq}"
        )
        request = build_paper_order_intent_request(
            request_id=f"zero-req-{seq}",
            capacity_decision_digest=decision.decision_digest,
            market_symbol=INS,
            side=side,
            intent_type=PaperOrderIntentType.MARKET,
            requested_notional="40",
            requested_units="1",
            limit_price=None,
            correlation_id=f"zero-corr-req-{seq}",
        )
        bridge = build_strategy_signal_to_paper_intent(
            spec,
            expected_spec_digest=strategy_spec_digest(spec),
            signal_id=request.request_id,
            run_id=f"zero-run-{seq}",
            correlation_id=f"zero-corr-req-{seq}",
            market_symbol=INS,
            side=side,
            intent_type=PaperOrderIntentType.MARKET,
            requested_units="1",
            requested_notional="40",
            capacity_decision_digest=decision.decision_digest,
            limit_price=None,
        )
        admission = evaluate_paper_order_intent_admission(decision, request, correlation_id=f"zero-admit-{seq}")
        intent = build_paper_order_intent(
            admission, intent_id=f"zero-intent-{seq}", correlation_id=f"zero-intent-{seq}"
        )
        snapshot = build_paper_fill_market_snapshot(
            snapshot_id=f"zero-snap-{seq}", market_symbol=INS, reference_price="40", observed_at_ns=at
        )
        fill_policy = build_paper_fill_policy(
            policy_id="zero-fee", slippage_bps="0", fee_rate_bps="0", allow_partial_fill=False
        )
        mark = build_paper_mark_snapshot(
            mark_snapshot_id=f"zero-mark-{seq}",
            market_symbol=INS,
            mark_price="40",
            observed_at_ns=at,
            correlation_id="zero",
        )
        ids = {
            "fill_simulation_id": f"zero-fill-{seq}",
            "position_transition_id": f"zero-trans-{seq}",
            "new_position_state_id": f"zero-pos-{seq}",
            "pnl_report_id": f"zero-pnl-{seq}",
        }
        run = run_paper_episode(
            intent, prior, snapshot, fill_policy, mark, **ids, episode_run_id=f"zero-ep-{seq}", correlation_id="zero"
        )
        fill = simulate_paper_fill(
            intent, snapshot, fill_policy, fill_simulation_id=ids["fill_simulation_id"], correlation_id="zero"
        )
        transition, state = apply_paper_fill_to_position(
            prior,
            fill,
            transition_id=ids["position_transition_id"],
            new_position_state_id=ids["new_position_state_id"],
            correlation_id="zero",
        )
        report = compute_paper_pnl_report(state, mark, pnl_report_id=ids["pnl_report_id"], correlation_id="zero")  # type: ignore[arg-type]
        event = compute_paper_realized_pnl_event(
            prior, fill, transition, state, realized_pnl_event_id=f"zero-rpnl-{seq}", correlation_id="zero"
        )  # type: ignore[arg-type]
        episode = build_paper_end_to_end_episode(
            bridge,
            intent,
            run,
            event,
            expected_bridge_digest=bridge.bridge_digest,
            expected_order_intent_digest=intent.intent_digest,
            expected_episode_run_digest=run.episode_run_digest,
            expected_realized_pnl_event_digest=event.realized_pnl_event_digest,
            episode_id=f"zero-episode-{seq}",
            run_id=f"zero-run-{seq}",
            correlation_id="zero",
        )
        episodes.append(
            PaperSleeveEpisodeEvidence(
                policy,
                draft,
                decision,
                request,
                admission,
                intent,
                spec,
                bridge,
                prior,
                snapshot,
                fill_policy,
                mark,  # type: ignore[arg-type]
                fill,
                transition,
                state,
                report,
                run,
                event,
                episode,  # type: ignore[arg-type]
            )
        )
        prior = state  # type: ignore[assignment]
    return tuple(episodes), flat_closes(30, prior)


def test_zero_variance_is_never_a_bootstrap_reason() -> None:
    longer = gw.variant_genesis(horizon=40)
    _, source = cycle_of(0, genesis=longer)
    capacity = governed_paper_cycle_capacity(longer[0], longer[1], source)
    episodes, closes = zero_return_history(longer[0], longer[1], capacity)
    inputs, authority = cycle_of(
        30,
        genesis=longer,
        sealed_episodes=episodes,
        sealed_day_closes=closes,
        sealed_funding_events=(),
        prior_ladder=None,
    )
    chain = governed_paper_cycle_chain(inputs)
    assert chain is not None and chain.performance is not None
    assert chain.performance.status.value == "NOT_COMPUTABLE"
    assert chain.performance.reason_codes != authority_module._BOOTSTRAP_RG3_REASONS
    assert authority.status is BLOCKED and authority.blocked_reason_codes == (code("bootstrap_b1_not_eligible"),)


def test_a_cycle_reads_only_the_history_sealed_before_its_opening() -> None:
    inputs, _ = gw.world_g().cycles[8]
    with refused("sealed_day_closes_not_one_per_sealed_day"):
        build_governed_paper_cycle_authority(replace(inputs, sealed_day_closes=inputs.sealed_day_closes[:-1]))
    with refused("prior_ladder_without_sealed_history"):
        build_governed_paper_cycle_authority(
            replace(gw.world_g().cycles[1][0], prior_ladder=gw.world_g().cycles[31][0].prior_ladder)
        )


def test_the_cycle_verifier_is_exact_and_total() -> None:
    inputs, cycle = gw.world_g().cycles[4]
    verification = verify_governed_paper_cycle_authority(cycle, inputs)
    assert (verification.intact, verification.recomputed_digest) == (True, cycle.authority_digest)
    forged = replace(cycle, reservation_price=d(50))
    resealed = replace(forged, authority_digest=governed_paper_cycle_authority_digest(forged))
    for candidate, reason in (
        (forged, "cycle_authority_self_digest_mismatch"),
        (resealed, "cycle_authority_field_mismatch:reservation_price"),
        (replace(cycle, execution_authorized=True), "cycle_authority_self_digest_mismatch"),
    ):
        result = verify_governed_paper_cycle_authority(candidate, inputs)
        assert result.intact is False and code(reason) in result.reason_codes
    for garbage in (None, object(), inputs):
        assert verify_governed_paper_cycle_authority(garbage, inputs).intact is False
    assert verify_governed_paper_cycle_authority(cycle, object()).reason_codes == (
        code("cycle_authority_rebuild_failed"),
    )
    with pytest.raises(GovernedPaperExecutionAuthorityError):
        governed_paper_cycle_admission_window(object())  # type: ignore[arg-type]
    assert isinstance(cycle, GovernedPaperCycleAuthority)


def test_the_rule_set_commits_every_rule() -> None:
    rules = governed_paper_execution_authority_rule_set()
    assert GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET_DIGEST == edge_sha256_text(edge_canonical_json(rules))
    assert rules["bootstrap_rg3_reasons"] == list(authority_module._BOOTSTRAP_RG3_REASONS)
    assert rules["capacity_measure"] == list(authority_module._SUPPORTED_CAPACITY)
    assert rules["bootstrap_minimum_horizon_days"] == 30
    assert {"risk_budget_policy_rule_id", "direction_rule_id"} <= set(rules)
    for key, reasons in (
        ("bootstrap_b0_rg4_reasons", authority_module._B0_DRAWDOWN_REASONS),
        ("bootstrap_b1_rg4_reasons", authority_module._B1_DRAWDOWN_REASONS),
        ("bootstrap_b1_rg6_reasons", authority_module._B1_LADDER_REASONS),
        ("bootstrap_b1_rg8_reasons", authority_module._B1_GOVERNANCE_REASONS),
    ):
        assert rules[key] == list(reasons)


def test_the_authority_module_is_pure() -> None:
    source = Path(authority_module.__file__).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            assert all(alias.name in ("json",) for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert node.module.split(".")[0] in (
                "__future__",
                "collections",
                "dataclasses",
                "enum",
                "fractions",
                "typing",
                "crypto_core",
            )
            assert not node.module.startswith(
                ("crypto_core.execution", "crypto_core.service", "crypto_core.data.ingest")
            )
        if isinstance(node, ast.Constant):
            assert type(node.value) is not float
    lowered = source.lower()
    assert not [
        token
        for token in ("bist", "borsa", "place_order", "submit_order", "wall_clock", "time.time")
        if token in lowered
    ]
