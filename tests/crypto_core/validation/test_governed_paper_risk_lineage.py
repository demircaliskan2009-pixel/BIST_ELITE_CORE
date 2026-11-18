"""World G's native risk measurement lineage (S1_NATIVE_RISK_MEASUREMENT_CONSTRUCTION_V1): seal v11, evidence v11,
schedule v7 and rule set v10 on the protective ledger lineage.

SYNTHETIC TEST VALUES ONLY. The risk policy, its TEST-ONLY approval, the daily MARK archive and every reading here are
synthetic fixtures that exercise structure: none is a calibrated threshold, a qualified (M1) source or a real human
decision. The TEST-ONLY risk approval table is installed only where a test says so; the PRODUCTION table admits no
policy and stays in force everywhere else, where every risk reading is BLOCKED and the schedule carries no CVaR bound.

It proves that, with a risk context on every day from day 0:

* every day seals as seal v11 and changes, against the accepted protective ledger lineage (seal v10), only its version,
  the schedule (v7 with the CVaR bounds the context implies), the governed outcome and the evidence that binds it, the
  rule set (v10) and the ladder v2 and system state v2 evidence, and binds its risk policy, approval, archive, evidence
  and X1 prefix chain; no fill and no economics changes, and every entry is still refused (NT-D01 first);
* the public gate replays the sealed risk evidence, and refuses a schedule whose version or bounds are not the risk
  context's;
* a risk lineage is one from day 0 or never, only on a protective ledger lineage, with one policy and approval, an
  archive of the policy source known at the seal, never rewritten and never backfilled before its day;
* on the PRODUCTION table the same lineage seals with every risk reading BLOCKED, no CVaR bound (an entry fill could never
  be admitted) and a constant risk prefix, and neither table's seal verifies under the other.
* a signed CVaR99* (the rising audit counterexample: LONG negative, SHORT positive) keeps both sides from the public
  market to the sealed schedule v7, replays and re-verifies, and stays fail-closed on the PRODUCTION table.
"""

from __future__ import annotations

import contextlib
import functools
from collections.abc import Iterator
from dataclasses import replace
from fractions import Fraction

import pytest

import crypto_core.validation.governed_paper_ctr_qualification as ctr
import crypto_core.validation.governed_paper_regime_state as regime
import crypto_core.validation.governed_paper_risk_measurement as risk
from crypto_core.validation.governed_admitted_variant_paper_execution import (
    GovernedPaperDaySealStatus,
    GovernedPaperExecutionStatus,
    build_governed_paper_day_seal,
    build_governed_paper_execution_evidence,
    governed_paper_day_seal_to_dict,
    verify_governed_paper_execution_evidence,
)
from crypto_core.validation.governed_paper_entry_safety import (
    GOVERNED_PAPER_ENTRY_SAFETY_RISK_MEASUREMENT_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_RISK_MEASUREMENT_RULE_SET_ID,
    GovernedPaperEntrySafetyError,
    GovernedPaperEntrySafetyPortfolio,
    GovernedPaperEntrySafetyStatus,
    build_governed_paper_entry_safety_evidence,
    governed_paper_entry_safety_evidence_to_dict,
)
from crypto_core.validation.governed_paper_risk_measurement import (
    GOVERNED_PAPER_RISK_PRODUCTION_APPROVAL_TABLE,
    GovernedPaperRiskApprovalTable,
    GovernedPaperRiskContext,
    build_governed_paper_risk_approval,
    build_governed_paper_risk_policy,
    derive_governed_paper_risk_market,
    governed_paper_risk_cvar_star,
    governed_paper_risk_evidence_digest,
    governed_paper_risk_fill_bounds,
    governed_paper_risk_mc_seed,
    governed_paper_risk_prefix_digest,
)
from crypto_core.validation.historical_execution_economics import (
    HISTORICAL_EXECUTION_RISK_MEASUREMENT_ADMISSION_SCHEDULE_SCHEMA_VERSION,
)
from crypto_core.validation.historical_ohlc_bar_archive import build_historical_ohlc_bar_archive

try:  # the module objects pytest collects (basename import), so cached worlds are shared
    import test_authenticated_pit_ingress as ingt
    import test_governed_admitted_variant_paper_execution as gpe
    import test_governed_paper_entry_safety as est
    import test_governed_paper_kill_switch as kst
    import test_governed_paper_protective_ledger as plt
    import test_governed_paper_protective_lineage as lineage
    import test_governed_paper_regime_state as rst
    import test_governed_paper_risk_measurement as rmt
    import test_governed_paper_sizing_chain as sct
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_authenticated_pit_ingress as ingt
    from tests.crypto_core.validation import test_governed_admitted_variant_paper_execution as gpe
    from tests.crypto_core.validation import test_governed_paper_entry_safety as est
    from tests.crypto_core.validation import test_governed_paper_kill_switch as kst
    from tests.crypto_core.validation import test_governed_paper_protective_ledger as plt
    from tests.crypto_core.validation import test_governed_paper_protective_lineage as lineage
    from tests.crypto_core.validation import test_governed_paper_regime_state as rst
    from tests.crypto_core.validation import test_governed_paper_risk_measurement as rmt
    from tests.crypto_core.validation import test_governed_paper_sizing_chain as sct

DAY = rmt.DAY
SECOND = rmt.SECOND
V7 = HISTORICAL_EXECUTION_RISK_MEASUREMENT_ADMISSION_SCHEDULE_SCHEMA_VERSION
V10_SEAL, V11_SEAL = "governed-paper-day-seal.v10", "governed-paper-day-seal.v11"
V11_EVIDENCE = "governed-paper-execution-evidence.v11"
SEALED = GovernedPaperDaySealStatus.SEALED
S = GovernedPaperEntrySafetyStatus
PRODUCTION = GOVERNED_PAPER_RISK_PRODUCTION_APPROVAL_TABLE
RISK_ORIGIN = gpe.G - 260 * DAY  # SYNTHETIC: daily MARK bar 260 closes at G (E_0), bar 260 + k at E_k
V11_FIELDS = (
    "risk_policy_digest",
    "risk_approval_digest",
    "risk_archive_digest",
    "risk_evidence_digest",
    "risk_prefix_digest_open",
    "risk_prefix_digest_close",
)
# What a v11 day moves of the v10 day. Schedule v7 adds the CVaR bounds, so the governed outcome and every evidence that
# binds it move; rule set v10 moves the gate, and the ladder v2 (T8) and the system state v2 (S3, S6) their evidence.
MOVED = (
    "schema_version",
    "prior_seal_digest",
    "schedule",
    "schedule_digest",
    "governed_outcome_digest",
    "entry_safety_rule_set_digest",
    "entry_safety_evidence_digest",
    "entry_safety_decisions",
    "seal_digest",
    "kill_switch_ladder_digest",
    "kill_switch_prefix_digest_open",
    "kill_switch_prefix_digest_close",
    "system_state_evidence_digest",
    "protective_ledger_evidence_digest",
)
# The rule set v9 checks rule set v10 reads in place on the risk evidence, those that keep their outcome and bind a moved
# evidence digest, and the checks it appends.
READ_IN_PLACE = ("NT-R03", "NT-R05", "NT-M01", "NT-X03", "SYSTEM-STATE", "HZ-LIMITS")
REBOUND = ("NT-R01", "NT-T02", "SCALE-1", "PROTECTIVE-LEDGER")
APPENDED = ("HZ-CVAR", "EDGE-CVAR", "MARGINAL-CVAR", "STRESS-HV", "STRESS-CORR", "STRESS-LIQ", "OB-SPREAD")
NOT_ADMITTED = "risk_policy_not_admitted:synthetic_approval_refused_on_the_production_table"


@pytest.fixture(autouse=True, scope="module")
def _production_tables_with_exact_memos():
    """The protective ledger tests' exact upstream memos and identity memos of pure re-proofs; every PRODUCTION rule and
    approval table stays (a TEST-ONLY table is installed only where a test says so)."""

    with pytest.MonkeyPatch.context() as patch:
        gpe.apply_memos(patch)
        archives = gpe.SameObjects(regime.verify_historical_ohlc_bar_archive)
        for module in (regime, gpe.execution, risk):
            patch.setattr(module, "verify_historical_ohlc_bar_archive", archives)
        exact = gpe._EXACT[(gpe.execution, "verify_historical_pit_dataset")]  # noqa: SLF001
        for module in (regime, ctr, risk):
            patch.setattr(module, "verify_historical_pit_dataset", exact)
        assert risk._APPROVAL_TABLE is PRODUCTION  # noqa: SLF001
        yield
    assert risk._APPROVAL_TABLE is PRODUCTION  # noqa: SLF001


def world_g_bars(day: int, *, skip: frozenset[int] = frozenset(), path=rmt.close_path):  # noqa: ANN001, ANN201
    """The policy's SYNTHETIC MARK archive known at ``E_{day+1}``: daily bars 0..260 + day (bar 260 + j closes at E_j and
    is published one second later)."""

    return rmt.daily_archive(260 + day, origin=RISK_ORIGIN, skip=skip, path=path)


@functools.cache
def world_g_archive(day: int):  # noqa: ANN201
    return world_g_bars(day)


def context_of(archive: object, policy: object = None, approval: object = None) -> GovernedPaperRiskContext:
    return GovernedPaperRiskContext(
        rmt.risk_policy() if policy is None else policy,  # type: ignore[arg-type]
        rmt.risk_approval() if approval is None else approval,  # type: ignore[arg-type]
        archive,  # type: ignore[arg-type]
    )


@functools.cache
def risk_context(day: int) -> GovernedPaperRiskContext:
    return context_of(world_g_archive(day))


@contextlib.contextmanager
def tables(table: GovernedPaperRiskApprovalTable = rmt.TEST_ONLY_TABLE) -> Iterator[None]:
    """The TEST-ONLY regime and integrity tables, and the risk ``table``."""

    with rst.approval_table(rst.TEST_ONLY_TABLE), plt.integrity_table(plt.TEST_ONLY_TABLE), rmt.risk_table(table):
        yield


def risk_inputs(days: tuple, context: object):  # noqa: ANN201
    """The cycle and seal inputs of the day after ``days`` of world G's protective ledger lineage with the risk
    ``context``."""

    cycle_inputs, cycle, seal_inputs = plt.ledger_inputs(days, plt.NO_PROOFS)
    return cycle_inputs, cycle, replace(seal_inputs, protection=replace(seal_inputs.protection, risk=context))


def risk_day(days: tuple, context: object, table: GovernedPaperRiskApprovalTable = rmt.TEST_ONLY_TABLE):  # noqa: ANN201
    """Open, run and seal the day after ``days`` of world G with the risk ``context`` (a refusal raises)."""

    cycle_inputs, cycle, seal_inputs = risk_inputs(days, context)
    with tables(table):
        seal = build_governed_paper_day_seal(seal_inputs)
    return gpe.Day(cycle_inputs, cycle, seal_inputs, seal)


@functools.cache
def risk_days(count: int, production: bool = False) -> tuple:
    """World G's first ``count`` days of the risk measurement lineage (seal v11) under the TEST-ONLY risk table, or under
    the PRODUCTION one."""

    if count == 0:
        return ()
    days = risk_days(count - 1, production)
    return (*days, risk_day(days, risk_context(len(days)), PRODUCTION if production else rmt.TEST_ONLY_TABLE))


def verified(item: object, table: GovernedPaperRiskApprovalTable = rmt.TEST_ONLY_TABLE):  # noqa: ANN201
    """The public seal verifier without the identity memo, under the risk ``table``."""

    with plt.integrity_table(plt.TEST_ONLY_TABLE), rmt.risk_table(table):
        return rst.verify_unmemoized(item.seal, item.seal_inputs, rst.TEST_ONLY_TABLE)  # type: ignore[attr-defined]


def lineage_evidence(days: tuple, table: GovernedPaperRiskApprovalTable = rmt.TEST_ONLY_TABLE) -> tuple:
    with tables(table):
        evidence = build_governed_paper_execution_evidence(gpe.evidence_inputs(days))
        verification = verify_governed_paper_execution_evidence(evidence, gpe.evidence_inputs(days))
    return evidence, verification


def fill_bounds(day: int, context: GovernedPaperRiskContext | None = None, item: object = None) -> tuple:
    """Day ``day``'s schedule v7 bounds, derived through the public risk functions over ``[G, E_{day+1})``."""

    with rmt.risk_table(rmt.TEST_ONLY_TABLE):
        market = derive_governed_paper_risk_market(
            risk_context(day) if context is None else context,
            dataset=(risk_days(day + 1)[day] if item is None else item).seal_inputs.dataset,  # type: ignore[attr-defined]
            instrument=gpe.INS,
            start_ns=gpe.G,
            horizon_ns=gpe.instant(day + 1),
        )
    return governed_paper_risk_fill_bounds(market)


def risk_gate(item: object, day: int, context: object, schedule: object | None = None):  # noqa: ANN201
    """Day ``day``'s rule set v10 evaluation of ``item``, rebuilt independently through the public builders."""

    authority, run, _ = est.run_and_evidence(item)
    economics = lineage.protected_replay(item)[0]
    with tables():
        return build_governed_paper_entry_safety_evidence(
            authority=authority,
            run=run,
            dataset=item.seal_inputs.dataset,  # type: ignore[attr-defined]
            invalidated_from_ns=None,
            protection=est.seal_protection(item),
            portfolio=GovernedPaperEntrySafetyPortfolio(
                economics,
                item.seal.schedule if schedule is None else schedule,  # type: ignore[attr-defined]
            ),
            market_data=True,
            kill_switch=True,
            regime=rst.regime_context(day),
            system_safety=True,
            sizing=sct.NO_SOURCE,
            protective_ledger=plt.NO_PROOFS,
            risk=context,  # type: ignore[arg-type]
        )


def readings_of(decision: object) -> dict[str, tuple]:
    return {
        item.check_id: (item.status, item.observed, item.reason.removeprefix(est.code(f"{item.check_id}:")))
        for item in decision.checks  # type: ignore[attr-defined]
    }


# --- the lineage on the TEST-ONLY risk table --------------------------------------------------------------------------------


def test_world_g_risk_lineage_changes_only_its_version_schedule_rule_set_and_risk_bindings() -> None:
    days, legacy = risk_days(4), plt.ledger_days(4)
    for day, (item, old) in enumerate(zip(days, legacy, strict=True)):
        seal = item.seal
        assert (seal.schema_version, seal.status, seal.reason_codes) == (V11_SEAL, SEALED, ())
        assert seal.entry_safety_rule_set_digest == GOVERNED_PAPER_ENTRY_SAFETY_RISK_MEASUREMENT_RULE_SET_DIGEST
        for name in governed_paper_day_seal_to_dict(old.seal):
            if name not in MOVED:
                assert getattr(seal, name) == getattr(old.seal, name), name  # no fill, no economics, no prefix moves
        assert seal.schedule == replace(old.seal.schedule, schema_version=V7, cvar_bounds=fill_bounds(day))
        assert (seal.risk_policy_digest, seal.risk_approval_digest, seal.risk_archive_digest) == (
            rmt.risk_policy().policy_digest,
            rmt.risk_approval().approval_digest,
            world_g_archive(day).archive_digest,
        )
        if day:  # X1: nothing known before E_k ever changes
            assert seal.risk_prefix_digest_open == days[day - 1].seal.risk_prefix_digest_close
        verification = verified(item)
        assert (verification.intact, verification.reason_codes) == (True, ())
    # a new close is read from the second it is published (C-1): one bound per readable span, from G to E_4
    instant = gpe.instant
    assert [(item.window_start_ns, item.window_end_ns) for item in days[3].seal.schedule.cvar_bounds] == [
        (instant(0), instant(0) + SECOND),
        (instant(0) + SECOND, instant(1) + SECOND),
        (instant(1) + SECOND, instant(2) + SECOND),
        (instant(2) + SECOND, instant(3) + SECOND),
        (instant(3) + SECOND, instant(4)),
    ]
    evidence, verification = lineage_evidence(days)
    assert (evidence.schema_version, evidence.status) == (V11_EVIDENCE, GovernedPaperExecutionStatus.READY)
    assert (verification.intact, verification.reason_codes) == (True, ())
    payload = governed_paper_day_seal_to_dict(days[3].seal)
    assert set(payload) - set(V11_FIELDS) == set(governed_paper_day_seal_to_dict(legacy[3].seal))


def test_a_bound_is_the_exact_cvar99_star_of_the_253_closes_its_span_reads() -> None:
    """An oracle from the close path itself: the span [G + 1 s, E_1) reads bars 8..260 (bar 260 closes at G)."""

    (bound,) = [item for item in fill_bounds(0) if item.window_start_ns == gpe.G + SECOND]
    closes = [rmt.close_path(k) for k in range(8, 261)]  # oldest first
    returns = [closes[252 - age] / closes[251 - age] - 1 for age in range(252)]  # age 0: the latest day
    digests = {item.close_time_ns: item.bar_digest for item in world_g_archive(0).bars}
    seed = governed_paper_risk_mc_seed(
        policy_digest=rmt.risk_policy().policy_digest,
        source_digest=rmt.DAILY_SOURCE_DIGEST,
        interval_ns=DAY,
        series_end_ns=gpe.G,
        close_digests=[digests[RISK_ORIGIN + k * DAY] for k in range(8, 261)],
    )
    long = governed_paper_risk_cvar_star([-item for item in returns], seed)
    short = governed_paper_risk_cvar_star(returns, seed)
    assert (Fraction(bound.long_unit_cvar), Fraction(bound.short_unit_cvar)) == (long.cvar, short.cvar)
    assert long.monte_carlo_used and short.monte_carlo_used  # lambda 0.94 leaves fewer than 50 tail scenarios (C-6)


def test_the_entry_reads_rule_set_v10_in_place_and_appended_and_is_still_refused_at_nt_d01() -> None:
    (entry,) = risk_days(4)[3].seal.entry_safety_decisions
    (old,) = plt.ledger_days(4)[3].seal.entry_safety_decisions
    assert [item.check_id for item in entry.checks] == [*(item.check_id for item in old.checks), *APPENDED]
    for new, item in zip(entry.checks, old.checks, strict=False):
        if item.check_id in READ_IN_PLACE:
            continue
        before = (item.status, item.observed, item.threshold, item.reason)
        assert (new.status, new.observed, new.threshold, new.reason) == before, item.check_id
        assert (new.evidence_record_digests == item.evidence_record_digests) is (item.check_id not in REBOUND)
    assert (entry.entry_permitted, entry.first_failure_check_id) == (False, "NT-D01")  # no new admission
    readings = readings_of(entry)
    # SYNTHETIC readings of the TEST-ONLY approval: world G's position management policy is v1 (no R-1 stop is armed),
    # its data contract declares no LAST_TRADE series and no depth-50 tip is fresh at the decision
    assert {name: readings[name] for name in (*READ_IN_PLACE, *APPENDED)} == {
        "NT-R03": (S.BLOCKED_ON_MISSING_INPUT, "", "armed_stop_needs_the_policy_v2_r1_stop"),
        "NT-R05": (S.PASS, "0.000151337717073632", "portfolio_cvar99_below_5pct_of_nav"),
        "NT-M01": (S.BLOCKED_ON_MISSING_INPUT, "", "no_liquidity_observation_known_at_t"),
        "NT-X03": (S.BLOCKED_ON_MISSING_INPUT, "", "no_fresh_depth_50_tip_at_the_decision"),
        "SYSTEM-STATE": (
            S.BLOCKED_ON_MISSING_INPUT,
            "lower_bound=SS-0;shs_upper_bound=0.979999990000000000",
            "ss0_unprovable_signals_s6_s7_s9_have_no_reading_and_no_signal_has_an_upper_bound",  # S3 is read
        ),
        "HZ-LIMITS": (
            S.PASS,
            "share=0.003998007992017976;trades_today=0;order_in_flight=false",
            "single_position_within_the_intraday_8pct_and_intraday_turnover_the_entry_is_at_most_trade_20_of_the_utc_day",
        ),
        "HZ-CVAR": (S.PASS, "0.000151337717073632", "intraday_horizon_cvar99_below_2pct_of_nav_hzb_1"),
        "EDGE-CVAR": (
            S.BLOCKED_ON_MISSING_INPUT,
            "",
            "edge_cvar_budget_needs_fcd_17_kmax_external_adv_and_h_e_pending",
        ),
        "MARGINAL-CVAR": (S.BLOCKED_ON_MISSING_INPUT, "", "marginal_cvar_rule_needs_a_defined_edge_budget"),
        "STRESS-HV": (S.PASS, "0.000227006575610448", "high_vol_stress_cvar99_below_8pct_of_nav"),
        "STRESS-CORR": (
            S.PROVEN_NOT_APPLICABLE,
            "",
            "single_instrument_paper_portfolio_has_no_correlation_to_stress",
        ),
        "STRESS-LIQ": (S.BLOCKED_ON_MISSING_INPUT, "", "no_fresh_depth_50_tip_at_the_decision"),
        "OB-SPREAD": (S.BLOCKED_ON_MISSING_INPUT, "", "no_fresh_depth_50_tip_at_the_decision"),
    }


def test_the_public_gate_replays_the_sealed_risk_evidence_and_refuses_a_foreign_schedule() -> None:
    item = risk_days(4)[3]
    evidence = risk_gate(item, 3, risk_context(3))
    assert (evidence.rule_set_id, evidence.evidence_digest) == (
        GOVERNED_PAPER_ENTRY_SAFETY_RISK_MEASUREMENT_RULE_SET_ID,
        item.seal.entry_safety_evidence_digest,
    )
    found = evidence.risk_evidence
    assert found is not None and found.evidence_digest == item.seal.risk_evidence_digest
    assert found.evidence_digest == governed_paper_risk_evidence_digest(found)
    assert (found.policy_digest, found.approval_digest, found.archive_digest, found.dataset_digest) == (
        item.seal.risk_policy_digest,
        item.seal.risk_approval_digest,
        item.seal.risk_archive_digest,
        item.seal.dataset_digest,
    )
    assert (found.approval_table_id, found.approval_admitted, found.synthetic_risk_approval_used) == (
        "test_only",
        True,
        True,
    )
    assert (found.production_use_authorized, found.real_market_source_qualified, found.de_risk_actions_executed) == (
        False,
        False,
        False,
    )
    for before, sealed in (
        (gpe.instant(3), item.seal.risk_prefix_digest_open),
        (gpe.instant(4), item.seal.risk_prefix_digest_close),
    ):
        assert governed_paper_risk_prefix_digest(found, before_ns=before) == sealed
    legacy = plt.ledger_gate(plt.ledger_days(4)[3], 3, plt.NO_PROOFS)  # rule set v9, through the public builders
    assert "risk_evidence" not in governed_paper_entry_safety_evidence_to_dict(legacy)
    with pytest.raises(ValueError, match="legacy_rule_set_carries_a_risk_evidence$"):
        governed_paper_entry_safety_evidence_to_dict(replace(legacy, risk_evidence=found))
    schedule = item.seal.schedule
    shortened = replace(schedule, cvar_bounds=schedule.cvar_bounds[:-1])
    for foreign, context, reason in (
        (schedule, None, "risk_schedule_and_rule_set_mismatch"),
        (plt.ledger_days(4)[3].seal.schedule, risk_context(3), "risk_schedule_and_rule_set_mismatch"),
        (schedule, object(), "risk_context_malformed"),
        (shortened, risk_context(3), "risk_schedule_bounds_not_the_derived_bounds"),
        (schedule, risk_context(2), "risk_schedule_bounds_not_the_derived_bounds"),  # the archive known a day earlier
    ):
        with pytest.raises(GovernedPaperEntrySafetyError, match=f"{reason}$"):
            risk_gate(item, 3, context, foreign)


# --- one lineage, one context, known at the seal ------------------------------------------------------------------------


def test_a_risk_lineage_is_one_from_day_0_or_never_and_only_on_a_protective_ledger_lineage() -> None:
    days, legacy = risk_days(2), plt.ledger_days(2)
    for item, changes, reason in (
        (days[1], {"risk": None}, "risk_measurement_lineage_switched"),
        (legacy[1], {"risk": risk_context(1)}, "risk_measurement_lineage_switched"),
        (days[0], {"protective_ledger": None}, "risk_measurement_needs_the_protective_ledger_lineage"),
        (days[1], {"risk": object()}, "protection_inputs_malformed:risk"),
    ):
        with rst.approval_table(rst.TEST_ONLY_TABLE), rmt.risk_table(rmt.TEST_ONLY_TABLE), gpe.refused(reason):
            build_governed_paper_day_seal(kst.switched(item, **changes))
    assert verified(replace(days[1], seal=replace(days[1].seal, schema_version=V10_SEAL))).intact is False
    with pytest.raises(ValueError, match="legacy_schema_carries_an_extension_field:risk_policy_digest$"):
        gpe.reseal_seal(days[1].seal, schema_version=V10_SEAL)
    for forged in (
        replace(legacy[1].seal, schema_version=V11_SEAL),
        gpe.reseal_seal(legacy[1].seal, schema_version=V11_SEAL),
    ):
        assert verified(replace(legacy[1], seal=forged)).intact is False
    for changes in (
        {"risk_policy_digest": "0" * 64},
        {"risk_approval_digest": "0" * 64},
        {"risk_archive_digest": "0" * 64},
        {"risk_evidence_digest": "0" * 64},
        {"risk_prefix_digest_open": "0" * 64},
        {"risk_prefix_digest_close": "0" * 64},
        {"schedule": replace(days[1].seal.schedule, cvar_bounds=())},
    ):
        assert verified(replace(days[1], seal=gpe.reseal_seal(days[1].seal, **changes))).intact is False


def test_the_context_is_re_proven_one_policy_and_approval_and_an_archive_of_the_source_known_at_the_seal() -> None:
    days = risk_days(1)
    policy, archive = rmt.risk_policy(), world_g_archive(1)
    other_policy = rmt.risk_policy("synthetic-risk-policy-2")
    other_approval = rmt.risk_approval(policy_id="synthetic-risk-policy-2")
    second_approval = build_governed_paper_risk_approval(
        approval_id="synthetic-risk-approval-2",
        approval_kind=rmt.SYNTHETIC,
        policy_digest=policy.policy_digest,
        approver_reference="synthetic-test-fixture",
    )
    foreign_source = build_historical_ohlc_bar_archive(
        archive_id="synthetic-foreign-source",
        source=rmt.daily_source(source_id="synthetic-other-mark-daily"),
        bars=archive.bars,
    )
    for context, reason in (
        (context_of(archive, replace(policy, open_risk_cap="1/20")), "risk_policy_not_authentic"),
        (context_of(archive, approval=other_approval), "risk_approval_not_of_the_policy"),
        (context_of(object()), "risk_archive_malformed"),
        (context_of(foreign_source), "risk_archive_not_of_the_policy_source"),
        (context_of(world_g_archive(2)), "risk_archive_holds_a_bar_unknown_at_the_seal"),
        (context_of(archive, other_policy, other_approval), "risk_policy_changed_inside_the_lineage"),
        (context_of(archive, approval=second_approval), "risk_policy_changed_inside_the_lineage"),
    ):
        with gpe.refused(reason):
            risk_day(days, context)
    eth_policy = build_governed_paper_risk_policy(
        policy_id="synthetic-risk-policy-eth",
        instrument=ingt.ETH,
        mark_source_digest=rmt.DAILY_SOURCE_DIGEST,
        mark_interval_ns=DAY,
    )
    eth_approval = build_governed_paper_risk_approval(
        approval_id="synthetic-risk-approval-eth",
        approval_kind=rmt.SYNTHETIC,
        policy_digest=eth_policy.policy_digest,
        approver_reference="synthetic-test-fixture",
    )
    with gpe.refused("risk_policy_not_of_the_genesis_instrument"):
        risk_day((), context_of(world_g_archive(0), eth_policy, eth_approval))


def rewritten(k: int):  # noqa: ANN201
    """The SYNTHETIC close path with bar ``k``'s close one higher (bars ``k`` and ``k + 1`` change)."""

    def path(index: int) -> Fraction:
        return rmt.close_path(index) + (1 if index == k else 0)

    return path


def test_a_read_rewrite_breaks_the_risk_prefix_and_an_unread_rewrite_or_backfill_breaks_the_evidence() -> None:
    days = risk_days(1)
    # bar 100 is read by every span before E_1 (bars 7..259, then 8..260): day 0's X1 risk prefix moves
    with gpe.refused("risk_prefix_rewritten"):
        risk_day(days, context_of(world_g_bars(1, path=rewritten(100))))
    # bars 3 and 4 are never read: the day seals and re-verifies, and the lineage evidence refuses the rewrite
    quiet = risk_day(days, context_of(world_g_bars(1, path=rewritten(3))))
    assert (quiet.seal.status, verified(quiet).intact) == (SEALED, True)
    assert quiet.seal.risk_prefix_digest_open == days[0].seal.risk_prefix_digest_close
    with gpe.refused("risk_archive_rewritten:1"):
        lineage_evidence((*days, quiet))
    # an unread bar first carried by day 1 although published long before E_1: a backfill
    gap = risk_day((), context_of(world_g_bars(0, skip=frozenset({2}))))
    filled = risk_day((gap,), risk_context(1))
    assert (gap.seal.status, filled.seal.status) == (SEALED, SEALED)
    with gpe.refused("risk_archive_backfilled_before_the_day:1"):
        lineage_evidence((gap, filled))


# --- the PRODUCTION table ------------------------------------------------------------------------------------------------


def test_on_the_production_table_every_risk_reading_is_blocked_and_no_fill_bound_exists() -> None:
    days, tested = risk_days(4, production=True), risk_days(4)
    for item in days:
        seal = item.seal
        assert (seal.schema_version, seal.status, seal.reason_codes) == (V11_SEAL, SEALED, ())
        assert (seal.schedule.schema_version, seal.schedule.cvar_bounds) == (V7, ())  # C-10 refuses every entry fill
        # nothing is measured: the prefix of the production evidence never moves
        assert seal.risk_prefix_digest_open == seal.risk_prefix_digest_close == days[0].seal.risk_prefix_digest_open
        assert verified(item, PRODUCTION).intact is True
    (entry,) = days[3].seal.entry_safety_decisions
    assert (entry.entry_permitted, entry.first_failure_check_id) == (False, "NT-D01")
    readings = readings_of(entry)
    for name in ("NT-R03", "NT-R05", "NT-M01", "NT-X03", *APPENDED):
        assert readings[name] == (S.BLOCKED_ON_MISSING_INPUT, "", NOT_ADMITTED), name
    assert readings["HZ-LIMITS"] == (
        S.BLOCKED_ON_MISSING_INPUT,
        "share=0.003998007992017976",
        f"intraday_turnover_{NOT_ADMITTED}",
    )
    assert "ss0_unprovable_signals_s3_s6_s7_s9" in readings["SYSTEM-STATE"][2]  # S3 has no reading
    assert {readings[name][0] for name in (*READ_IN_PLACE, *APPENDED)} == {S.BLOCKED_ON_MISSING_INPUT}
    # neither table's seal verifies under the other
    assert verified(days[3]).intact is False
    assert verified(tested[3], PRODUCTION).intact is False
    evidence, verification = lineage_evidence(days, PRODUCTION)
    assert (evidence.schema_version, evidence.status, verification.intact) == (
        V11_EVIDENCE,
        GovernedPaperExecutionStatus.READY,
        True,
    )


# --- a signed CVaR99* lineage (P2-SIGNED-CVAR-OPPOSITE-SIDE-POISONING) ------------------------------------------------------


def rising(k: int) -> Fraction:
    """The SYNTHETIC audit counterexample path c_k = 100 + k/100: every daily return is positive, so the LONG CVaR99* is
    negative and the SHORT one positive."""

    return 100 + Fraction(k, 100)


@functools.cache
def rising_context(day: int) -> GovernedPaperRiskContext:
    return context_of(world_g_bars(day, path=rising))


@functools.cache
def rising_days(count: int, production: bool = False) -> tuple:
    """World G's first ``count`` days with the rising archive, under the TEST-ONLY risk table or the PRODUCTION one."""

    if count == 0:
        return ()
    days = rising_days(count - 1, production)
    return (*days, risk_day(days, rising_context(len(days)), PRODUCTION if production else rmt.TEST_ONLY_TABLE))


def test_a_signed_cvar_lineage_seals_and_replays_both_sides_and_stays_fail_closed_on_production() -> None:
    days = rising_days(2)
    for day, item in enumerate(days):
        seal = item.seal
        assert (seal.schema_version, seal.status, seal.reason_codes) == (V11_SEAL, SEALED, ())
        bounds = seal.schedule.cvar_bounds
        assert bounds == fill_bounds(day, rising_context(day), item)  # the public path, both signed sides kept
        assert bounds and all(Fraction(bound.long_unit_cvar) < 0 < Fraction(bound.short_unit_cvar) for bound in bounds)
        assert seal.risk_archive_digest == rising_context(day).archive.archive_digest  # type: ignore[attr-defined]
        if day:  # X1 over the signed readings
            assert seal.risk_prefix_digest_open == days[day - 1].seal.risk_prefix_digest_close
        verification = verified(item)
        assert (verification.intact, verification.reason_codes) == (True, ())
    evidence, verification = lineage_evidence(days)
    assert (evidence.schema_version, evidence.status, verification.intact) == (
        V11_EVIDENCE,
        GovernedPaperExecutionStatus.READY,
        True,
    )
    # the same signed contexts on the PRODUCTION table: no bound, a constant prefix, and only that table re-verifies
    production = rising_days(2, production=True)
    for item in production:
        assert (item.seal.status, item.seal.schedule.cvar_bounds) == (SEALED, ())
        assert item.seal.risk_prefix_digest_open == item.seal.risk_prefix_digest_close
        assert verified(item, PRODUCTION).intact is True
        assert verified(item).intact is False
    assert verified(days[1], PRODUCTION).intact is False
