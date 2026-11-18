"""Native risk measurement tests (S1_NATIVE_RISK_MEASUREMENT_CONSTRUCTION_V1): RECORD B constructed.

SYNTHETIC TEST VALUES ONLY. Every price, mark, book, bar, trade, policy, approval and table here is a synthetic fixture
that exercises structure: no production threshold, venue truth, qualified source or real human decision. RECORD B's own
constants (lambda 47/50, 253 closes, tau 1/100, 10,000 paths, 8,640 members, the 0.04 / 0.05 / 0.08 / 0.02 limits, the
5 bps band and V1-V4) are the human-approved methodology the module fixes, never values chosen here. A risk policy is
only ever used under the TEST-ONLY table these tests install; the production table admits none.

The T-NRM-* ids name the acceptance criteria of the adoption document (section 12) each test closes.
"""

from __future__ import annotations

import functools
import hashlib
import inspect
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from fractions import Fraction
from types import SimpleNamespace

import pytest

import crypto_core.validation.governed_paper_risk_measurement as risk
import crypto_core.validation.historical_execution_economics as economics
from crypto_core.strategy.source_packet import SourcePacketRightsStatus
from crypto_core.validation.governed_paper_entry_safety import (
    GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_MARKET_DATA_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_PORTFOLIO_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_LEDGER_RULE_SET,
    GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_LEDGER_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_REGIME_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_RISK_MEASUREMENT_RULE_SET,
    GOVERNED_PAPER_ENTRY_SAFETY_RISK_MEASUREMENT_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_RISK_MEASUREMENT_RULE_SET_ID,
    GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_SIZING_CHAIN_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_SYSTEM_SAFETY_RULE_SET_DIGEST,
    GovernedPaperEntrySafetyError,
    GovernedPaperEntrySafetyRisk,
    GovernedPaperEntrySafetyStatus,
    evaluate_governed_paper_entry_safety,
    governed_paper_entry_safety_system_state_reading,
)
from crypto_core.validation.governed_paper_kill_switch import (
    GOVERNED_PAPER_KILL_SWITCH_RISK_RULE,
    GOVERNED_PAPER_KILL_SWITCH_RULE,
    GOVERNED_PAPER_KILL_SWITCH_RULE_DIGEST,
    derive_governed_paper_kill_switch_ladder,
    derive_governed_paper_kill_switch_risk_ladder,
    governed_paper_kill_switch_transitions,
)
from crypto_core.validation.governed_paper_risk_measurement import (
    GOVERNED_PAPER_RISK_APPROVED_ITEMS,
    GOVERNED_PAPER_RISK_CHECK_IDS,
    GOVERNED_PAPER_RISK_PENDING_ITEMS,
    GOVERNED_PAPER_RISK_PRODUCTION_APPROVAL_TABLE,
    GovernedPaperRiskApprovalKind,
    GovernedPaperRiskApprovalTable,
    GovernedPaperRiskCheckReading,
    GovernedPaperRiskContext,
    GovernedPaperRiskError,
    GovernedPaperRiskLiquidityEntry,
    GovernedPaperRiskObservation,
    GovernedPaperRiskReading,
    GovernedPaperRiskStatus,
    build_governed_paper_risk_approval,
    build_governed_paper_risk_policy,
    derive_governed_paper_risk_market,
    governed_paper_risk_cvar_star,
    governed_paper_risk_fill_bounds,
    governed_paper_risk_horizon_cvar_limit,
    governed_paper_risk_liquidity_entries,
    governed_paper_risk_liquidity_severity,
    governed_paper_risk_mc_ages,
    governed_paper_risk_mc_seed,
    governed_paper_risk_nt_m01,
    governed_paper_risk_policy_digest,
    governed_paper_risk_reading_digest,
    governed_paper_risk_spread_checks,
    governed_paper_risk_stop_risk,
    governed_paper_risk_t8_intervals,
    governed_paper_risk_tip_reading,
    governed_paper_risk_turnover,
    governed_paper_risk_weighted_es,
    verify_governed_paper_risk_approval,
    verify_governed_paper_risk_policy,
)
from crypto_core.validation.governed_paper_system_state import (
    GOVERNED_PAPER_SYSTEM_STATE_RULE,
    GOVERNED_PAPER_SYSTEM_STATE_RULE_DIGEST,
    GovernedPaperSystemStateError,
    GovernedPaperSystemStateMeasurement,
    derive_governed_paper_system_state_reading,
)
from crypto_core.validation.historical_execution_economics import (
    HISTORICAL_EXECUTION_CVAR_BUDGET,
    HISTORICAL_EXECUTION_OPEN_RISK_CAP,
    HISTORICAL_EXECUTION_PROTECTIVE_LEDGER_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    HISTORICAL_EXECUTION_RISK_MEASUREMENT_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    HistoricalExecutionAdmissionSchedule,
    HistoricalExecutionAdmissionWindow,
    HistoricalExecutionCvarBound,
    HistoricalExecutionDepthCap,
    HistoricalExecutionEconomicsError,
    HistoricalExecutionExposureEnvelope,
    HistoricalExecutionFillOutcome,
    HistoricalExecutionProtectiveWindow,
    HistoricalExecutionSide,
    canonical_historical_execution_admission_schedule,
    historical_execution_admission_schedule_to_dict,
    historical_execution_close_only_exit_quote,
    historical_execution_governed_paper_outcome_digest,
    historical_execution_risk_rational_text,
    simulate_historical_execution_governed_paper,
)
from crypto_core.validation.historical_ohlc_bar_archive import (
    HistoricalOhlcBarArchive,
    HistoricalOhlcPriceSemantics,
    HistoricalOhlcSourceDeclaration,
    build_historical_ohlc_bar,
    build_historical_ohlc_bar_archive,
    historical_ohlc_source_declaration_digest,
    historical_ohlc_wilder_atr,
)
from crypto_core.validation.historical_position_management_policy import (
    historical_position_management_initial_stop_fraction,
)

try:  # the module objects pytest collects (basename import), so cached worlds are shared
    import test_authenticated_pit_ingress as ingt
    import test_governed_paper_entry_safety as est
    import test_governed_paper_kill_switch as kst
    import test_governed_paper_protective_ledger as plt
    import test_governed_paper_regime_state as rst
    import test_governed_paper_system_safety as sst
    import test_historical_execution_protective_lifecycle as lifet
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_authenticated_pit_ingress as ingt
    from tests.crypto_core.validation import test_governed_paper_entry_safety as est
    from tests.crypto_core.validation import test_governed_paper_kill_switch as kst
    from tests.crypto_core.validation import test_governed_paper_protective_ledger as plt
    from tests.crypto_core.validation import test_governed_paper_regime_state as rst
    from tests.crypto_core.validation import test_governed_paper_system_safety as sst
    from tests.crypto_core.validation import test_historical_execution_protective_lifecycle as lifet

SECOND = 1_000_000_000
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE
DAY = 24 * HOUR
GRID = 300 * SECOND  # V3
V1, V2, V4 = 172_800 * SECOND, 600 * SECOND, 300 * SECOND
BASELINE = 8_640
INS = ingt.INS
UNIT = Fraction(1, 10**18)
S = GovernedPaperEntrySafetyStatus
R = GovernedPaperRiskStatus
SYNTHETIC = GovernedPaperRiskApprovalKind.TEST_ONLY_SYNTHETIC
HUMAN = GovernedPaperRiskApprovalKind.HUMAN_GOVERNANCE
TEST_ONLY_TABLE = GovernedPaperRiskApprovalTable("test_only", SYNTHETIC, ())
PRODUCTION_TABLE = risk._APPROVAL_TABLE  # noqa: SLF001 - captured at import, before any test could patch it
d = ingt.d


def code(text: str) -> str:
    return f"governed_paper_risk_measurement:{text}"


@contextmanager
def risk_table(table: GovernedPaperRiskApprovalTable) -> Iterator[None]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(risk, "_APPROVAL_TABLE", table)
        yield


# --- the policy, its approval and the tables ---------------------------------------------------------------------------


def daily_source(**changes: object) -> HistoricalOhlcSourceDeclaration:
    base = HistoricalOhlcSourceDeclaration(
        source_id="synthetic-risk-mark-daily",
        source_reference="archive:synthetic-risk-mark-daily",
        rights_status=SourcePacketRightsStatus.OWN_RESEARCH,
        rights_reference="license-1",
        instrument=INS,
        price_semantics=HistoricalOhlcPriceSemantics.MARK_PRICE,
        bar_intervals_ns=(DAY,),
    )
    return replace(base, **changes)  # type: ignore[arg-type]


DAILY_SOURCE_DIGEST = historical_ohlc_source_declaration_digest(daily_source())


@functools.cache
def risk_policy(policy_id: str = "synthetic-risk-policy-1", source_digest: str = DAILY_SOURCE_DIGEST):  # noqa: ANN201
    return build_governed_paper_risk_policy(
        policy_id=policy_id, instrument=INS, mark_source_digest=source_digest, mark_interval_ns=DAY
    )


@functools.cache
def risk_approval(kind: GovernedPaperRiskApprovalKind = SYNTHETIC, policy_id: str = "synthetic-risk-policy-1"):  # noqa: ANN201
    return build_governed_paper_risk_approval(
        approval_id="synthetic-risk-approval-1",
        approval_kind=kind,
        policy_digest=risk_policy(policy_id).policy_digest,
        approver_reference="synthetic-test-fixture",
    )


def test_the_policy_fixes_every_record_b_constant_and_only_its_id_instrument_and_source_vary() -> None:
    policy = risk_policy()
    assert verify_governed_paper_risk_policy(policy).intact
    assert policy.policy_digest == governed_paper_risk_policy_digest(policy)
    assert (
        policy.max_daily_bar_age_ns,
        policy.liquidity_proof_age_ns,
        policy.observation_grid_ns,
        policy.t8_lapse_ns,
    ) == (
        V1,
        V2,
        GRID,
        V4,
    )  # V1-V4 as approved (BV)
    assert (policy.open_risk_cap, policy.cvar_budget, policy.horizon_cvar_limit, policy.stress_limit) == (
        "1/25",
        "1/20",
        "1/50",
        "2/25",
    )
    assert (policy.cvar_decay, policy.cvar_closes, policy.cvar_scenarios, policy.cvar_tail_probability) == (
        "47/50",
        253,
        252,
        "1/100",
    )
    assert (policy.cvar_min_tail_count, policy.cvar_mc_paths, policy.cvar_mc_top, policy.cvar_mc_selection) == (
        50,
        10_000,
        100,
        "MC-8a:max_of_es_and_cvar_mc",
    )
    assert (policy.liquidity_baseline_members, policy.liquidity_band, policy.liquidity_crisis_bound) == (
        8_640,
        "1/2000",
        "3/20",
    )
    assert (policy.stress_liq_method_id, policy.horizon_reading_id, policy.spread_multiple, policy.turnover_cap) == (
        "LS-A",
        "HZB-1",
        3,
        20,
    )
    assert (
        "D-B2:exactness_rule" in policy.approved_items and "D-B2:alternative_depth_definition" in policy.pending_items
    )
    assert "MC-8b" not in str(policy) and "LS-B" not in str(policy) and "HZB-2" not in str(policy)
    assert (policy.paper_only, policy.calibrated, policy.production_use_authorized) == (True, False, False)
    # a changed constant, even resealed, is not the approved methodology; the builder takes no constant
    tampered = replace(policy, open_risk_cap="1/20")
    resealed = replace(tampered, policy_digest=governed_paper_risk_policy_digest(tampered))
    assert not verify_governed_paper_risk_policy(resealed).intact
    assert list(inspect.signature(build_governed_paper_risk_policy).parameters) == [
        "policy_id",
        "instrument",
        "mark_source_digest",
        "mark_interval_ns",
    ]
    with pytest.raises(GovernedPaperRiskError, match=code("mark_interval_not_a_utc_day_divisor")):
        build_governed_paper_risk_policy(
            policy_id="p", instrument=INS, mark_source_digest=DAILY_SOURCE_DIGEST, mark_interval_ns=7 * HOUR
        )


def test_the_approval_is_exactly_the_construction_scope_and_only_the_test_only_table_admits_a_synthetic_one() -> None:
    approval = risk_approval()
    assert verify_governed_paper_risk_approval(approval).intact
    assert approval.approved_items == GOVERNED_PAPER_RISK_APPROVED_ITEMS
    assert not set(GOVERNED_PAPER_RISK_APPROVED_ITEMS) & set(GOVERNED_PAPER_RISK_PENDING_ITEMS)
    widened = replace(approval, approved_items=(*approval.approved_items, "D-B2:alternative_depth_definition"))
    assert not verify_governed_paper_risk_approval(widened).intact
    assert PRODUCTION_TABLE is GOVERNED_PAPER_RISK_PRODUCTION_APPROVAL_TABLE
    assert (PRODUCTION_TABLE.table_id, PRODUCTION_TABLE.admitted_policy_digests) == ("production", ())
    archive = daily_archive(260, origin=ORIGIN)
    assert risk._admission(PRODUCTION_TABLE, approval, archive) == "synthetic_approval_refused_on_the_production_table"  # noqa: SLF001
    assert (
        risk._admission(PRODUCTION_TABLE, risk_approval(HUMAN), archive)
        == "risk_policy_not_authorized_for_production_use"
    )  # noqa: SLF001
    listed = GovernedPaperRiskApprovalTable("production", HUMAN, (risk_policy().policy_digest,))
    # even a listed policy needs an M1-qualified archive, which no archive is (C-21)
    assert risk._admission(listed, risk_approval(HUMAN), archive) == "mark_archive_not_m1_qualified"  # noqa: SLF001
    assert risk._admission(TEST_ONLY_TABLE, approval, archive) == ""  # noqa: SLF001
    assert risk._admission(TEST_ONLY_TABLE, risk_approval(HUMAN), archive) == (  # noqa: SLF001
        "only_test_only_synthetic_approvals_on_the_test_only_table"
    )
    with pytest.raises(GovernedPaperRiskError, match=code("approval_table_malformed")):
        risk._canonical_table(GovernedPaperRiskApprovalTable("test_only", SYNTHETIC, (risk_policy().policy_digest,)))  # noqa: SLF001


def test_hzb_1_shares_the_5pct_daily_budget_1pct_2pct_2pct_and_s1_reads_the_intraday_2pct() -> None:
    assert [governed_paper_risk_horizon_cvar_limit(name) for name in ("MICRO", "INTRADAY", "SWING")] == [
        Fraction(1, 100),
        Fraction(2, 100),
        Fraction(2, 100),
    ]
    assert Fraction(risk_policy().horizon_cvar_limit) == governed_paper_risk_horizon_cvar_limit("INTRADAY")
    assert sum(share for _, share in risk.GOVERNED_PAPER_RISK_HORIZON_SHARES) == 1
    with pytest.raises(GovernedPaperRiskError, match=code("horizon_unknown")):
        governed_paper_risk_horizon_cvar_limit("POSITIONAL")


# --- CVaR99* (C-1..C-8, MC-1..MC-11) -------------------------------------------------------------------------------------


def regression_losses() -> list[Fraction]:
    """MC-11: r_a = ((37 a mod 41) - 20) / 1000 except r_5, r_30, r_100, r_200; LONG with |q| m / E = 1."""

    returns = {age: Fraction((37 * age) % 41 - 20, 1000) for age in range(252)}
    returns.update({5: Fraction(-12, 100), 30: Fraction(10, 100), 100: Fraction(-15, 100), 200: Fraction(-20, 100)})
    return [-returns[age] for age in range(252)]


REGRESSION_SEED = hashlib.sha256(b"CVAR99_MC_REGRESSION_V1").digest()
# The exact ES of the MC-11 vector (pinned by digest: a ~1,400-bit rational), about 0.12037190432654903.
REGRESSION_ES_SHA256 = hashlib.sha256(
    str(governed_paper_risk_weighted_es(regression_losses())[0]).encode("ascii")
).hexdigest()


def test_mc_11_the_10000_path_regression_vector_reproduces_exactly() -> None:  # T-NRM-08
    assert REGRESSION_SEED.hex() == "fc670340bfcb039f6e651ee4f7d363fe4e3f7ff9859efea7aae2f57cee628857"
    uniforms = [
        int.from_bytes(hashlib.sha256(REGRESSION_SEED + i.to_bytes(8, "big")).digest()[:8], "big") for i in range(3)
    ]
    assert uniforms == [8420428673457154365, 12947070990645480281, 6972368347563711628]
    ages = governed_paper_risk_mc_ages(REGRESSION_SEED)
    assert (len(ages), ages[:5]) == (10_000, (9, 19, 7, 18, 13))
    estimate = governed_paper_risk_cvar_star(regression_losses(), REGRESSION_SEED)
    assert (estimate.tail_count, estimate.value_at_risk, estimate.monte_carlo_used) == (3, Fraction(3, 25), True)
    assert (estimate.monte_carlo_var, estimate.monte_carlo_cvar) == (Fraction(3, 25), Fraction(3, 25))
    es = estimate.expected_shortfall
    assert abs(es - Fraction("0.12037190432654903")) < Fraction(1, 10**16)
    assert hashlib.sha256(str(es).encode("ascii")).hexdigest() == REGRESSION_ES_SHA256
    assert estimate.cvar == es == max(es, Fraction(3, 25))  # MC-8a; MC-8b's literal 0.12 is never read
    assert historical_execution_risk_rational_text(estimate.cvar) == str(es)


def test_c5_es_is_the_exact_weighted_tail_and_c6_falls_back_exactly_below_50_tail_observations() -> None:  # T-NRM-07
    weights = risk._WEIGHTS  # noqa: SLF001
    assert sum(weights) == 1 and weights[0] == Fraction(3, 50) / (1 - Fraction(47, 50) ** 252)
    # the 52 oldest scenarios lose 1, every other 0: their weights stay below tau, so 53 observations carry the tail
    old = [Fraction(1) if age >= 200 else Fraction(0) for age in range(252)]
    es, var, tail = governed_paper_risk_weighted_es(old)
    covered = sum(weights[200:])
    assert covered < Fraction(1, 100) and tail == 53 and var == 0
    assert es == covered / Fraction(1, 100)  # exact: the tail beyond the 52 losses adds 0 x weight
    estimate = governed_paper_risk_cvar_star(old, REGRESSION_SEED)
    assert (estimate.monte_carlo_used, estimate.cvar) == (False, es)  # C-8: n_tail >= 50 reads ES alone
    # C-6: the fallback applies exactly when the 49 largest losses carry at least 1% of the weight
    for losses in (old, regression_losses()):
        ordered = sorted(range(252), key=lambda age: (-losses[age], age))
        w49 = sum(weights[age] for age in ordered[:49])
        assert (governed_paper_risk_weighted_es(losses)[2] < 50) is (w49 >= Fraction(1, 100))
    with pytest.raises(GovernedPaperRiskError, match=code("losses_malformed")):
        governed_paper_risk_weighted_es([0.5] * 252)  # type: ignore[list-item]


def close_path(k: int) -> Fraction:
    """A SYNTHETIC daily MARK close path with exact, varied returns."""

    return Fraction(100) + Fraction((37 * k) % 41 - 20, 10) + Fraction(k % 7, 100)


def daily_archive(
    last: int,
    *,
    first: int = 0,
    late: dict[int, int] | None = None,
    skip: frozenset[int] = frozenset(),
    archive_id: str = "synthetic-risk-daily",
    origin: int = 0,
    path=close_path,  # noqa: ANN001
) -> HistoricalOhlcBarArchive:
    """Daily SYNTHETIC MARK bars ``first..last``: bar ``k`` closes at ``origin + k`` days at ``path(k)``, published one
    second after its close unless ``late`` gives its visibility."""

    bars = []
    for k in range(first, last + 1):
        if k in skip:
            continue
        previous, close = path(k - 1), path(k)
        visible = (late or {}).get(k, origin + k * DAY + SECOND)
        bars.append(
            build_historical_ohlc_bar(
                interval_ns=DAY,
                open_time_ns=origin + (k - 1) * DAY,
                open_price=d(previous),
                high_price=d(max(previous, close)),
                low_price=d(min(previous, close)),
                close_price=d(close),
                available_at_ns=visible,
                finalized_at_ns=visible,
            )
        )
    return build_historical_ohlc_bar_archive(archive_id=archive_id, source=daily_source(), bars=tuple(bars))


ORIGIN = 20_000 * DAY  # SYNTHETIC: a UTC midnight, the close of daily bar 0


@functools.cache
def small_books():  # noqa: ANN201
    """A SYNTHETIC dataset of one depth-50 tip (the CVaR spans read no book)."""

    return rst.book_dataset(
        [rst.book_record(ORIGIN + 300 * DAY, ORIGIN + 300 * DAY)], dataset_id="synthetic-risk-books"
    )


def market_of(archive: HistoricalOhlcBarArchive, start: int, horizon: int, dataset: object = None, **context: object):  # noqa: ANN201
    values = {"policy": risk_policy(), "approval": risk_approval(), "archive": archive}
    values.update(context)
    with risk_table(TEST_ONLY_TABLE):
        return derive_governed_paper_risk_market(
            GovernedPaperRiskContext(**values),  # type: ignore[arg-type]
            dataset=small_books() if dataset is None else dataset,  # type: ignore[arg-type]
            instrument=INS,
            start_ns=start,
            horizon_ns=horizon,
        )


def test_c1_reads_253_consecutive_visible_closes_within_v1_else_insufficient_or_stale() -> None:  # T-NRM-06
    archive = daily_archive(260, origin=ORIGIN)
    start = ORIGIN + 252 * DAY  # bar 252 closes here: the first instant with 253 closes visible is one second later
    market = market_of(archive, start, start + 12 * DAY)
    spans = [(item.start_ns, item.end_ns, item.series_end_ns, item.reason) for item in market.cvar_segments]
    assert spans[0] == (start, start + SECOND, None, "cvar_history_insufficient")  # 252 closes visible
    assert spans[1] == (start + SECOND, start + DAY + SECOND, start, "")  # 253 closes: bars 0..252
    # the latest close (bar 260) read until exactly V1 after it closed (equality PASSes), stale from one ns later
    last = ORIGIN + 260 * DAY
    assert spans[-2] == (last + SECOND, last + V1 + 1, last, "")
    assert spans[-1] == (last + V1 + 1, start + 12 * DAY, None, "cvar_history_stale")
    # a not-yet-visible older close breaks the series until it becomes visible; nothing older substitutes
    late = daily_archive(260, origin=ORIGIN, late={100: ORIGIN + 255 * DAY + 7 * SECOND}, archive_id="synthetic-late")
    reasons = [
        (item.series_end_ns, item.reason)
        for item in market_of(late, start, start + 4 * DAY).cvar_segments
        if item.start_ns < ORIGIN + 255 * DAY + 7 * SECOND
    ]
    assert {reason for _, reason in reasons} == {"cvar_history_insufficient"}
    gap = daily_archive(260, origin=ORIGIN, skip=frozenset({200}), archive_id="synthetic-gap")
    assert {item.reason for item in market_of(gap, start, start + 4 * DAY).cvar_segments} == {
        "cvar_history_insufficient"
    }


def test_d_b3_the_seed_is_stable_under_archive_growth_and_independent_of_side_and_holdings() -> None:  # T-NRM-09/10
    short_archive = daily_archive(255, origin=ORIGIN, archive_id="synthetic-a-k")
    long_archive = daily_archive(260, origin=ORIGIN, archive_id="synthetic-a-k-plus-5")
    assert short_archive.archive_digest != long_archive.archive_digest
    at = ORIGIN + 255 * DAY + SECOND  # bar 255 is the latest visible close in both archives
    one, two = market_of(short_archive, at, at + HOUR), market_of(long_archive, at, at + HOUR)
    assert one.cvar_days == two.cvar_days and one.cvar_units == two.cvar_units  # identical seed, draws and CVaR_MC
    day = one.cvar_days[0]
    assert (day.series_end_ns, day.reason, day.long_monte_carlo_used) == (ORIGIN + 255 * DAY, "", True)
    digests = [bar.bar_digest for bar in short_archive.bars[3:256]]
    seed = governed_paper_risk_mc_seed(
        policy_digest=risk_policy().policy_digest,
        source_digest=short_archive.source_digest,
        interval_ns=DAY,
        series_end_ns=ORIGIN + 255 * DAY,
        close_digests=digests,
    )
    assert seed.hex() == day.seed and len(digests) == 253
    # the seed has exactly the D-B3 members: another policy, source, interval, end or close changes it
    for change in (
        {"policy_digest": "a" * 64},
        {"source_digest": "b" * 64},
        {"interval_ns": 4 * HOUR},
        {"series_end_ns": ORIGIN + 254 * DAY},
        {"close_digests": [*digests[:-1], "c" * 64]},
    ):
        arguments = {
            "policy_digest": risk_policy().policy_digest,
            "source_digest": short_archive.source_digest,
            "interval_ns": DAY,
            "series_end_ns": ORIGIN + 255 * DAY,
            "close_digests": digests,
            **change,
        }
        assert governed_paper_risk_mc_seed(**arguments) != seed  # type: ignore[arg-type]
    assert "archive_digest" not in inspect.signature(governed_paper_risk_mc_seed).parameters
    # one draw serves both sides: the unit SHORT is the unit LONG with the losses negated, never another seed
    losses = regression_losses()
    long_estimate = governed_paper_risk_cvar_star(losses, seed)
    short_estimate = governed_paper_risk_cvar_star([-item for item in losses], seed)
    assert long_estimate.cvar != short_estimate.cvar
    ages = governed_paper_risk_mc_ages(seed)
    assert ages == governed_paper_risk_mc_ages(seed)  # deterministic replay (MC-9)
    # holdings scale every reading exactly: the unit value times |q| x m / E (C-3)
    assert risk._scaled((Fraction(1, 10), Fraction(1, 5)), Fraction(-3), Fraction(50), Fraction(1000)) == Fraction(
        3, 100
    )  # noqa: SLF001


def test_the_fill_bounds_are_the_readable_spans_with_the_exact_unit_cvar_of_each_side() -> None:
    archive = daily_archive(260, origin=ORIGIN)
    start = ORIGIN + 252 * DAY
    market = market_of(archive, start, start + 3 * DAY)
    bounds = governed_paper_risk_fill_bounds(market)
    readable = [item for item in market.cvar_segments if not item.reason]
    assert [(item.window_start_ns, item.window_end_ns) for item in bounds] == [
        (item.start_ns, item.end_ns) for item in readable
    ]
    units = {end: (long, short) for end, long, short in market.cvar_units}
    for bound, span in zip(bounds, readable, strict=True):
        assert (Fraction(bound.long_unit_cvar), Fraction(bound.short_unit_cvar)) == units[span.series_end_ns]
    # under the production table nothing is readable: no bound, so the engine refuses every exposure-increasing fill
    with risk_table(PRODUCTION_TABLE):
        refused = derive_governed_paper_risk_market(
            GovernedPaperRiskContext(risk_policy(), risk_approval(), archive),
            dataset=small_books(),
            instrument=INS,
            start_ns=start,
            horizon_ns=start + 3 * DAY,
        )
    assert (refused.approval_admitted, refused.cvar_segments, governed_paper_risk_fill_bounds(refused)) == (
        False,
        (),
        (),
    )


# --- FCD-01 (R-1..R-8) ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("quantity", "mark", "stop", "expected"),
    [
        (Fraction(2), Fraction(100), Fraction(97), Fraction(2) * 3 + Fraction(2) * 97 * Fraction(1, 1000)),
        (Fraction(-2), Fraction(100), Fraction(103), Fraction(2) * 3 + Fraction(2) * 103 * Fraction(1, 1000)),
        # the fresh mark at or beyond the stop: x = m and only the exit cost remains (T-NRM-03)
        (Fraction(2), Fraction(97), Fraction(97), Fraction(2) * 97 * Fraction(1, 1000)),
        (Fraction(2), Fraction(95), Fraction(97), Fraction(2) * 95 * Fraction(1, 1000)),
        (Fraction(-2), Fraction(104), Fraction(103), Fraction(2) * 104 * Fraction(1, 1000)),
        (Fraction(0), Fraction(100), Fraction(97), Fraction(0)),
    ],
)
def test_r1_the_open_risk_at_the_stop_is_exact(
    quantity: Fraction, mark: Fraction, stop: Fraction, expected: Fraction
) -> None:
    assert governed_paper_risk_stop_risk(quantity, mark, stop, Fraction(1, 1000)) == expected


# --- D-B1 and D-B2 (L-2) ---------------------------------------------------------------------------------------------------


def side(best: int, step: int, quantity: int, count: int = 50) -> tuple[tuple[int, int], ...]:
    return tuple((best + step * k, quantity) for k in range(count))


def band_sum(levels: tuple[tuple[int, int], ...], mid: Fraction, *, bid: bool) -> int:
    """An independent oracle of one side's quote notional inside the +-5 bps band (L-2), in units of 10^-36."""

    edge = mid * (1 - Fraction(5, 10_000)) if bid else mid * (1 + Fraction(5, 10_000))
    return sum(price * quantity for price, quantity in levels if (price >= edge if bid else price <= edge))


def test_d_b2_depth_is_defined_only_when_the_minimum_is_attained_on_an_exact_side() -> None:  # T-NRM-21
    unit = 10**18
    mid = Fraction(100 * unit)  # every book below is symmetric around 100
    tick, fine = unit // 100, unit // 10_000
    exact_bids = side(100 * unit - tick, -tick, 10)  # 99.99 .. 99.50: the 50th strictly beyond 99.95
    exact_asks = side(100 * unit + tick, tick, 10)  # 100.01 .. 100.50: the 50th strictly beyond 100.05
    reason, depth, spread = governed_paper_risk_tip_reading((exact_bids, exact_asks))
    expected = min(band_sum(exact_bids, mid, bid=True), band_sum(exact_asks, mid, bid=False))
    assert (reason, depth, spread) == ("", expected, Fraction(2 * tick, 100 * unit))  # exact/exact -> the minimum
    lower_bids = side(100 * unit - tick, -fine, 2)  # 99.99 .. 99.9851: the 50th still inside, a lower bound only
    assert band_sum(lower_bids, mid, bid=True) >= band_sum(exact_asks, mid, bid=False)
    reason, depth, _ = governed_paper_risk_tip_reading((lower_bids, exact_asks))
    assert (reason, depth) == ("", band_sum(exact_asks, mid, bid=False))  # a lower bound at least the exact minimum
    thin_bids = side(100 * unit - tick, -fine, 1)
    assert band_sum(thin_bids, mid, bid=True) < band_sum(exact_asks, mid, bid=False)
    reason, depth, _ = governed_paper_risk_tip_reading((thin_bids, exact_asks))
    # the lower bound may hide a smaller true bid sum: UNKNOWN, never an alternative depth definition (pending)
    assert (reason, depth) == ("depth_minimum_not_attained_on_an_exact_side", None)
    lower_asks = side(100 * unit + tick, fine, 2)
    assert governed_paper_risk_tip_reading((lower_bids, lower_asks))[:2] == (
        "depth_minimum_not_attained_on_an_exact_side",
        None,
    )
    # a 50th level exactly at the band edge is not strictly beyond it; one unit further it is
    milli = unit // 1_000
    edge_bids = side(100 * unit - milli, -milli, 1)  # 99.999 .. 99.950 exactly
    edge_asks = side(100 * unit + milli, tick, 10)  # mid 100, the 50th at 100.491: exact
    assert edge_bids[-1][0] == 100 * unit - 50 * milli
    assert band_sum(edge_bids, mid, bid=True) < band_sum(edge_asks, mid, bid=False)
    assert governed_paper_risk_tip_reading((edge_bids, edge_asks))[0] == "depth_minimum_not_attained_on_an_exact_side"
    beyond_bids = side(100 * unit - milli - 1, -milli, 1)  # the 50th one unit below 99.95 (the mid moves by half)
    reason, depth, _ = governed_paper_risk_tip_reading((beyond_bids, edge_asks))
    moved = Fraction(beyond_bids[0][0] + edge_asks[0][0], 2)
    assert (reason, depth) == ("", band_sum(beyond_bids, moved, bid=True))
    crossed = side(100 * unit + 2 * tick, -tick, 1)
    assert governed_paper_risk_tip_reading((crossed, exact_asks)) == ("order_book_tip_crossed_or_locked", None, None)


def test_d_b1_an_observation_reads_the_latest_tip_visible_at_its_instant_never_a_later_one() -> None:  # T-NRM-20
    s = ORIGIN + 100 * GRID
    a = rst.book_record(s - 8 * SECOND, s - 7 * SECOND)  # tip A: event s - 8 s, visible s - 7 s
    b = rst.book_record(s - 2 * SECOND, s + SECOND, best_bid=Fraction("99.90"))  # tip B: event s - 2 s, visible s + 1 s
    both = risk._Tips(rst.book_dataset([a, b], dataset_id="synthetic-db1-both"), INS)  # noqa: SLF001
    (chosen,) = both.walk([s])
    assert chosen.record.record_digest == a.record_digest  # at every reading instant the observation at s is A's
    assert both.at(s).record.record_digest == a.record_digest
    only_b = risk._Tips(rst.book_dataset([b], dataset_id="synthetic-db1-only-b"), INS)  # noqa: SLF001
    assert only_b.walk([s]) == [None]  # B is visible only after s: UNKNOWN at s
    stale = risk._Tips(rst.book_dataset([rst.book_record(s - 11 * SECOND, s - 10 * SECOND)], dataset_id="s"), INS)  # noqa: SLF001
    assert stale.walk([s]) == [None]  # older than 10 s


def trade(trade_id: int, event: int, *, run: int | None = 1, received: int | None = None, malformed: bool = False):  # noqa: ANN201
    """A SYNTHETIC LAST_TRADE record of native id ``trade_id`` in the declared run starting at ``run``."""

    values: dict[str, object] = {"trade_price": 40} if malformed else {"trade_price": 40, "trade_quantity": 1}
    if run is not None:
        values["trade_run_first_id"] = run
    return est.hand_record("trades", "last_trade", trade_id, event, values, received=received)


def arrival(at: int, *records: object) -> tuple:
    return risk._Trades(est.market_archive(records), INS).arrival(at)  # noqa: SLF001


def test_l2_arrival_counts_one_contiguous_declared_run_known_at_its_latest_visibility() -> None:  # L-2 arrivals
    s = ORIGIN + 100 * GRID
    run = (trade(1, s - GRID - 1), trade(2, s - GRID), trade(3, s - 1), trade(4, s, received=s + 7 * SECOND))
    # [s - 300 s, s): trade 2 at its first nanosecond and trade 3 count; trade 1 proves the start and trade 4 the end
    assert arrival(s, *run) == ("", 2, s + 7 * SECOND)  # kappa: the latest visibility of the proving chain
    assert arrival(s, *run[1:]) == ("no_trade_strictly_before_the_arrival_window", None, None)
    assert arrival(s, *run[:3]) == ("no_trade_at_or_after_the_observation_instant", None, None)
    undeclared = (*run[:2], trade(3, s - 1, run=None), run[3])
    assert arrival(s, *undeclared)[0] == "trade_continuity_profile_not_declared"
    broken = "trade_continuity_broken_across_the_arrival_window"
    assert arrival(s, run[0], run[1], trade(4, s))[0] == broken  # native id 3 missing
    assert arrival(s, *run[:2], trade(3, s - 1, run=3), trade(4, s, run=3))[0] == broken  # a new run inside
    # a malformed trade record blocks every window proven at or after its visibility, never an earlier one
    poisoned = trade(9, s + 5 * SECOND, received=s + 7 * SECOND, malformed=True)  # visible exactly at kappa
    assert arrival(s, *run, poisoned)[0] == "last_trade_record_malformed"
    later = trade(9, s + 5 * SECOND, received=s + 7 * SECOND + 1, malformed=True)
    assert arrival(s, *run, later) == ("", 2, s + 7 * SECOND)
    # an event-time regression in native id order: the series proves no window at all
    regressed = arrival(s, *run, trade(5, s - 2 * GRID))
    assert regressed[0] == "trade_event_time_regressed_in_native_id_order"
    # the full L-2 observation: the D-B1 tip, D-B2 depth and the arrival, known at the later of the tip and the chain
    tip = rst.book_record(s - 2 * SECOND, s - SECOND)
    dataset = est.market_archive((*run, tip))
    tips, trades = risk._Tips(dataset, INS), risk._Trades(dataset, INS)  # noqa: SLF001
    (observation,), spreads = risk._observations(tips, trades, s // GRID, s // GRID)  # noqa: SLF001
    reading = governed_paper_risk_tip_reading(tips.levels(tip))  # type: ignore[arg-type]
    assert (observation.reason, observation.depth, observation.spread) == ("", reading[1], reading[2])
    assert (observation.arrival, observation.knowledge_ns, spreads[s // GRID]) == (2, s + 7 * SECOND, reading[2])


# --- LIQ, NT-M01, T8 and S6 (L-3..L-9) -------------------------------------------------------------------------------------

FIRST = 50_000  # SYNTHETIC grid index of the pure LIQ checks


def instant(index: int) -> int:
    return index * GRID


def observations(  # noqa: PLR0913
    first: int,
    last: int,
    *,
    crisis: frozenset[int] = frozenset(),
    invalid: frozenset[int] = frozenset(),
    late: dict[int, int] | None = None,
    lag: int = 150 * SECOND,
) -> list[GovernedPaperRiskObservation]:
    """SYNTHETIC observations ``[first - 8640, last]``: equal normal readings (LIQ 0.5 against an equal baseline), CRISIS
    ones with the least depth, the widest spread and the fewest arrivals, each known ``lag`` after its instant."""

    items = []
    for index in range(first - BASELINE, last + 1):
        if index in invalid:
            items.append(
                GovernedPaperRiskObservation(
                    index, "no_fresh_depth_50_tip_visible_at_the_instant", None, None, None, None
                )
            )
            continue
        known = (late or {}).get(index, instant(index) + lag)
        if index in crisis:
            items.append(GovernedPaperRiskObservation(index, "", 0, Fraction(3, 1000), 0, known))
        else:
            items.append(GovernedPaperRiskObservation(index, "", 10**20, Fraction(1, 1000), 2, known))
    return items


def entries(last: int = FIRST + 40, **changes: object) -> tuple[GovernedPaperRiskLiquidityEntry, ...]:
    return governed_paper_risk_liquidity_entries(observations(FIRST, last, **changes), first=FIRST, last=last)  # type: ignore[arg-type]


def test_l3_l4_liq_needs_exactly_8640_valid_members_and_scores_ties_by_halves() -> None:  # T-NRM-22/23
    normal = entries()
    assert {(item.liquidity, item.regime) for item in normal} == {("1/2", "NON_CRISIS")}
    assert all(item.knowledge_ns == instant(item.index) + 150 * SECOND for item in normal)
    # one missing member, an older valid observation present: UNKNOWN for every reading whose 30 days contain it
    gap = entries(invalid=frozenset({FIRST - 100}))
    unknown = [item for item in gap if item.regime == "UNKNOWN"]
    assert {item.reason for item in unknown} == {"baseline_member_invalid"}
    assert [item.index for item in unknown] == list(range(FIRST, FIRST + 41))
    later = entries(last=FIRST + 8_600, invalid=frozenset({FIRST - 100}))
    assert (
        later[8_540].regime == "UNKNOWN" and later[8_541].regime == "NON_CRISIS"
    )  # defined once it leaves the 30 days
    # a member known only late defines the reading only from its own knowledge instant: K = the latest kappa
    delayed = entries(late={FIRST - 5: instant(FIRST) + DAY})
    assert delayed[0].knowledge_ns == instant(FIRST) + DAY and delayed[0].regime == "NON_CRISIS"
    # depth and arrival count strictly-lower members and half the equal ones, spread strictly-higher members
    crisis = entries(crisis=frozenset({FIRST, FIRST + 1}))
    assert (crisis[0].liquidity, crisis[0].regime) == ("0", "CRISIS")
    assert (crisis[1].liquidity, crisis[1].regime) == (str(Fraction(1, 2 * BASELINE)), "CRISIS")  # one equal member
    # two CRISIS members below (depth, arrival) and above (spread), 8,638 equal: (2 + 8,638 / 2) / 8,640 per score
    assert crisis[2].liquidity == str(Fraction(4_321, BASELINE))


def boundary_liq(value: Fraction) -> str:
    """The regime of an observation whose three scores are all ``value``."""

    return "CRISIS" if value < Fraction(15, 100) else "NON_CRISIS"


def test_l4_crisis_is_strictly_below_0_15() -> None:
    assert (boundary_liq(Fraction(15, 100)), boundary_liq(Fraction(15, 100) - UNIT)) == ("NON_CRISIS", "CRISIS")


RUN = frozenset(range(FIRST + 10, FIRST + 18))  # eight consecutive CRISIS instants: 2,100 s from first to last


AFTER_RUN = {index: instant(FIRST + 40) for index in range(FIRST + 18, FIRST + 41)}  # known only at the end


def test_nt_m01_pass_fail_and_blocked_boundaries() -> None:  # T-NRM-24/25
    log = entries(crisis=RUN, late=AFTER_RUN)
    last = instant(FIRST + 17)
    status, observed, reason, _ = governed_paper_risk_nt_m01(log, last + 150 * SECOND)
    assert (status, reason) == (R.FAIL, "latest_known_observation_closes_a_crisis_run_beyond_30min_within_v2")
    assert observed == f"crisis_through={last};liq={log[17].liquidity}"
    assert governed_paper_risk_nt_m01(log, last + V2)[0] is R.FAIL  # t - s_l = V2 still FAILs
    status, observed, reason, _ = governed_paper_risk_nt_m01(log, last + V2 + 1)  # the proof is older than V2
    assert (status, observed, reason) == (
        R.BLOCKED,
        f"latest_known={last};regime=CRISIS",
        "neither_a_non_crisis_proof_within_30min_nor_a_proven_crisis_run_beyond_30min",
    )
    # seven consecutive CRISIS observations span exactly 1,800 s: not beyond 30 minutes
    seven = entries(crisis=frozenset(range(FIRST + 11, FIRST + 18)), late=AFTER_RUN)
    assert governed_paper_risk_nt_m01(seven, last + 150 * SECOND)[0] is R.BLOCKED
    # PASS: a valid NON-CRISIS observation known at t no more than 1,800 s before t (a proven absence)
    calm = entries(crisis=RUN)
    assert governed_paper_risk_nt_m01(calm, instant(FIRST + 5) + 150 * SECOND)[0] is R.PASS
    assert governed_paper_risk_nt_m01(calm, instant(FIRST + 9) + 1_800 * SECOND)[0] is R.PASS  # equality passes
    assert governed_paper_risk_nt_m01(calm, instant(FIRST + 9) + 1_800 * SECOND + 1)[0] is R.BLOCKED
    # PASS and FAIL never hold together, at any instant
    for at in range(instant(FIRST), instant(FIRST + 41), 30 * SECOND):
        assert governed_paper_risk_nt_m01(calm, at)[0] in (R.PASS, R.FAIL, R.BLOCKED)
    assert governed_paper_risk_nt_m01(log, instant(FIRST) - 1)[:3] == (
        R.BLOCKED,
        "",
        "no_liquidity_observation_known_at_t",
    )


def test_t8_starts_at_the_run_knowledge_extends_lapses_and_restarts_without_backfill() -> None:  # T-NRM-26
    log = entries(crisis=RUN)
    first, end = instant(FIRST), instant(FIRST + 41)
    (interval,) = governed_paper_risk_t8_intervals(log, start_ns=first, horizon_ns=end)
    # starts when the 8-member run is known; the next member is known valid NON-CRISIS at its own knowledge instant
    assert (interval.start_ns, interval.end_ns, interval.last_member_ns) == (
        instant(FIRST + 17) + 150 * SECOND,
        instant(FIRST + 18) + 150 * SECOND,
        instant(FIRST + 17),
    )
    # extension: two more CRISIS members keep it until the member after them is known NON-CRISIS
    longer = entries(crisis=frozenset(range(FIRST + 10, FIRST + 20)))
    (extended,) = governed_paper_risk_t8_intervals(longer, start_ns=first, horizon_ns=end)
    assert (extended.start_ns, extended.end_ns) == (
        instant(FIRST + 17) + 150 * SECOND,
        instant(FIRST + 20) + 150 * SECOND,
    )
    # lapse: the next member is not known valid within V4 of its instant (an invalid observation)
    lapse = entries(crisis=RUN, invalid=frozenset({FIRST + 18}))
    (lapsed,) = governed_paper_risk_t8_intervals(lapse, start_ns=first, horizon_ns=end)
    assert lapsed.end_ns == instant(FIRST + 18) + V4
    # a late member: the proof lapses at s_{k+1} + V4 and restarts at the late member's own knowledge instant
    restart = entries(
        crisis=frozenset(range(FIRST + 10, FIRST + 19)), late={FIRST + 18: instant(FIRST + 18) + V4 + MINUTE}
    )
    one, two = governed_paper_risk_t8_intervals(restart, start_ns=first, horizon_ns=end)
    assert (one.end_ns, two.start_ns) == (instant(FIRST + 18) + V4, instant(FIRST + 18) + V4 + MINUTE)
    assert two.last_member_ns == instant(FIRST + 18)  # never backfilled across the lapse
    seven = entries(crisis=frozenset(range(FIRST + 11, FIRST + 18)))
    assert governed_paper_risk_t8_intervals(seven, start_ns=first, horizon_ns=end) == ()


def test_s6_reads_the_latest_known_valid_observation_within_v2_and_liq_0_is_severity_1() -> None:  # T-NRM-27
    log = entries(crisis=RUN)
    last = instant(FIRST + 17)
    assert governed_paper_risk_liquidity_severity(log, last + 150 * SECOND) == (1 - Fraction(log[17].liquidity), "")  # type: ignore[arg-type]
    assert governed_paper_risk_liquidity_severity(entries(crisis=frozenset({FIRST + 17})), last + 150 * SECOND) == (
        Fraction(1),
        "",
    )  # LIQ = 0 -> s6 = 1
    newest = instant(FIRST + 40)
    assert governed_paper_risk_liquidity_severity(entries(), newest + V2) == (Fraction(1, 2), "")  # equality measures
    assert governed_paper_risk_liquidity_severity(entries(), newest + V2 + 1) == (
        None,
        "latest_known_liquidity_observation_older_than_v2",
    )
    assert governed_paper_risk_liquidity_severity(entries(), instant(FIRST) - 1) == (
        None,
        "no_liquidity_observation_known_at_t",
    )


# --- NT-X03 / OB-SPREAD (X-1..X-7) and turnover (T-1..T-6) -----------------------------------------------------------------


def test_spread_equality_and_the_exact_median_boundaries() -> None:  # T-NRM-28..30
    low, high = Fraction(1, 1000), Fraction(3, 1000)
    baseline = [low] * 4_320 + [high] * 4_320  # the exact median is (x_4320 + x_4321) / 2 = 0.002
    x03, ob = governed_paper_risk_spread_checks(Fraction(6, 1000), "", baseline)
    assert (x03[0], ob[0]) == (R.PASS, R.FAIL)  # s = 3M: NT-X03 PASSes (strict >), OB-SPREAD FAILs (>=)
    assert x03[1] == "spread=3/500;median=1/500"
    x03, ob = governed_paper_risk_spread_checks(Fraction(6, 1000) + UNIT, "", baseline)
    assert (x03[0], ob[0]) == (R.FAIL, R.FAIL)
    x03, ob = governed_paper_risk_spread_checks(Fraction(6, 1000) - UNIT, "", baseline)
    assert (x03[0], ob[0]) == (R.PASS, R.PASS)
    missing = [*baseline[:-1], None]
    assert governed_paper_risk_spread_checks(low, "", missing)[0] == (
        R.BLOCKED,
        "",
        "thirty_day_spread_baseline_incomplete_1_members",
    )
    for reason in ("no_fresh_depth_50_tip_at_the_decision", "current_tip_crossed_or_locked"):
        assert governed_paper_risk_spread_checks(None, reason, baseline) == (
            (R.BLOCKED, "", reason),
            (R.BLOCKED, "", reason),
        )


@pytest.mark.parametrize(
    ("trades", "in_flight", "status"),
    [(19, False, R.PASS), (20, False, R.FAIL), (18, True, R.PASS), (19, True, R.BLOCKED), (20, True, R.FAIL)],
)
def test_t4_the_entry_is_at_most_trade_20_of_the_utc_day(trades: int, in_flight: bool, status: R) -> None:  # T-NRM-31
    day = ORIGIN
    at = day + 20 * HOUR
    # one trade the previous UTC day and one whose first entry fill is at t itself never count
    starts = [day - SECOND, *(day + k * MINUTE for k in range(trades)), at]
    assert governed_paper_risk_turnover(starts, at, order_in_flight=in_flight)[0] is status
    assert governed_paper_risk_turnover(starts, at, order_in_flight=in_flight)[1] == (
        f"trades_today={trades};order_in_flight={str(in_flight).lower()}"
    )
    assert governed_paper_risk_turnover(None, at, order_in_flight=False) == (
        R.BLOCKED,
        "",
        "governed_trade_ledger_not_available",
    )


# --- LS-A on the engine's own fill model -----------------------------------------------------------------------------------


def test_ls_a_exits_the_whole_holding_on_the_stressed_book_or_cannot_fill() -> None:  # T-NRM-17
    policy = lifet.economics_policy()  # cap 2%, max spread 50 bps, floor 5 bps, impact 0.5 bps per %, taker 5 bps
    book = {
        "best_bid_price": Fraction("99.95"),
        "best_ask_price": Fraction("100.05"),
        "best_bid_quantity": Fraction(500),
        "best_ask_quantity": Fraction(500),
    }
    reason, cost = historical_execution_close_only_exit_quote(
        policy, position_quantity=Fraction(1), depth_multiplier=Fraction(1, 5), **book
    )
    # the stressed bid depth is 100: 2% of it fills exactly 2 > 1; participation 1%, slippage max(5, 5 + 0.5) bps
    price = Fraction(100) * (1 - Fraction(55, 1000) / 100)
    assert (reason, cost) == ("", (Fraction(100) - price) + price * Fraction(5, 10_000))
    reason, cost = historical_execution_close_only_exit_quote(
        policy, position_quantity=Fraction(3), depth_multiplier=Fraction(1, 5), **book
    )
    assert (reason, cost) == ("stressed_book_cannot_fill_the_whole_position", None)  # 2% of 100 is 2 < 3
    reason, _ = historical_execution_close_only_exit_quote(
        policy,
        position_quantity=Fraction(-1),
        depth_multiplier=Fraction(1, 5),
        **{**book, "best_ask_price": Fraction("100.6")},
    )
    assert reason == "spread_exceeds_max"
    assert historical_execution_close_only_exit_quote(
        policy, position_quantity=Fraction(0), depth_multiplier=Fraction(1, 5), **book
    ) == ("", Fraction(0))


def test_ls_a_is_the_engine_fill_model_itself_on_a_real_decision_fill() -> None:
    result = lifet.hold_result()
    (entry,) = [item for item in result.fills if item.intent_id == result.intents[0].intent_id]
    assert entry.side is HistoricalExecutionSide.SELL and entry.outcome is HistoricalExecutionFillOutcome.FILLED
    # closing a LONG of the same size sells against the same bids: the engine's own price, fee and slippage
    reason, cost = historical_execution_close_only_exit_quote(
        lifet.economics_policy(),
        position_quantity=Fraction(entry.requested_quantity),
        best_bid_price=Fraction(entry.best_bid_price),  # type: ignore[arg-type]
        best_ask_price=Fraction(entry.best_ask_price),  # type: ignore[arg-type]
        best_bid_quantity=Fraction(entry.side_visible_quantity),  # type: ignore[arg-type]
        best_ask_quantity=Fraction(entry.side_visible_quantity),  # type: ignore[arg-type]
        depth_multiplier=Fraction(1),
    )
    price, filled = Fraction(entry.fill_price), Fraction(entry.filled_quantity)  # type: ignore[arg-type]
    mid = (Fraction(entry.best_bid_price) + Fraction(entry.best_ask_price)) / 2  # type: ignore[arg-type]
    assert (reason, cost) == ("", filled * (mid - price) + price * filled * Fraction(5, 10_000))


# --- schedule v7: the fill-time R-5 and C-10 bounds of the one engine --------------------------------------------------------


def book_records(world: object) -> list:
    return [item for item in world.dataset.records if item.series_id == "book"]  # type: ignore[attr-defined]


def v7_schedule(world: object, bounds: tuple = (), **changes: object) -> HistoricalExecutionAdmissionSchedule:
    """A SYNTHETIC schedule v7 over the lifecycle HOLD window: permissive sizing bounds (an envelope of 1 and a cap of
    1,000 on every book and side) so that only the R-5 and C-10 bounds can refuse an entry fill."""

    values: dict[str, object] = {
        "schema_version": HISTORICAL_EXECUTION_RISK_MEASUREMENT_ADMISSION_SCHEDULE_SCHEMA_VERSION,
        "schedule_id": "risk-schedule",
        "windows": (HistoricalExecutionAdmissionWindow(lifet.ANCHOR, lifet.HOLD_END, d(0), d(1), d(10_000)),),
        "invalidated_from_ns": None,
        "protective_windows": (HistoricalExecutionProtectiveWindow(lifet.ANCHOR, lifet.HOLD_END + DAY, "a" * 64),),
        "exposure_envelopes": (HistoricalExecutionExposureEnvelope(lifet.ANCHOR, lifet.HOLD_END, "1"),),
        "depth_caps": tuple(
            HistoricalExecutionDepthCap(record.record_digest, item, "1000")
            for record in sorted(book_records(world), key=lambda item: item.record_digest)
            for item in (HistoricalExecutionSide.BUY, HistoricalExecutionSide.SELL)
        ),
        "cvar_bounds": bounds,
    }
    values.update(changes)
    return HistoricalExecutionAdmissionSchedule(**values)  # type: ignore[arg-type]


def entry_fill(outcome: object):  # noqa: ANN201
    (fill,) = [item for item in outcome.fills if item.intent_id == outcome.intents[0].intent_id]  # type: ignore[attr-defined]
    return fill


def governed_v7(result: object, world: object, bounds: tuple = ()):  # noqa: ANN201
    outcome = simulate_historical_execution_governed_paper(
        result,  # type: ignore[arg-type]
        expected_result_digest=result.result_digest,  # type: ignore[attr-defined]
        schedule=v7_schedule(world, bounds),
    )
    assert outcome.simulated is True, outcome.reason_codes
    assert outcome.outcome_digest == historical_execution_governed_paper_outcome_digest(outcome)
    return outcome


def whole_hold(long_unit: object, short_unit: object) -> tuple:
    return (HistoricalExecutionCvarBound(lifet.ANCHOR, lifet.HOLD_END, str(long_unit), str(short_unit)),)


@functools.cache
def hold_v2():  # noqa: ANN201
    return sst.run_under(lifet.HOLD, lifet.HOLD_END, "v2"), lifet.world(lifet.HOLD, end=lifet.HOLD_END)


def candidate_equity(fill: object) -> Fraction:
    """The exact publication-visible equity after the SHORT opening fill of the HOLD world (independent oracle)."""

    price = Fraction(fill.fill_price)  # type: ignore[attr-defined]
    return Fraction(10_000) - price * Fraction(5, 10_000) + (price - 100)


def test_c10_refuses_an_entry_fill_at_or_above_5pct_and_never_resizes_it() -> None:  # T-NRM-12
    result, world = hold_v2()
    admitted = governed_v7(result, world, whole_hold(0, 0))
    fill = entry_fill(admitted)
    assert fill.outcome is HistoricalExecutionFillOutcome.FILLED
    boundary = HISTORICAL_EXECUTION_CVAR_BUDGET * candidate_equity(fill) / 100  # |q| = 1, fill mark 100
    refused = governed_v7(result, world, whole_hold(0, boundary))
    rejected = entry_fill(refused)
    assert (rejected.outcome, rejected.reason) == (
        HistoricalExecutionFillOutcome.REJECTED,
        "governed_paper_cvar_budget_exhausted_at_fill",
    )
    assert refused.position_transitions == () and refused.fee_cashflows == ()  # whole: no fee, no transition
    assert rejected.fill_digest in refused.governance_rejected_fill_digests
    below = governed_v7(result, world, whole_hold(0, boundary - Fraction(1, 10**30)))
    assert entry_fill(below).outcome is HistoricalExecutionFillOutcome.FILLED  # strictly below 5% fills in full
    assert entry_fill(below).filled_quantity == fill.filled_quantity
    unproven = governed_v7(result, world, ())
    assert entry_fill(unproven).reason == "governed_paper_cvar_unproven_at_fill"
    # the bound reads the side of the post-fill position only: a LONG unit value never refuses this SHORT
    assert entry_fill(governed_v7(result, world, whole_hold(10**6, 0))).outcome is HistoricalExecutionFillOutcome.FILLED


def divergent_book(j: int, mid: Fraction) -> dict[str, str]:
    return lifet.book_at(Fraction(1000) if j == 32 else mid)  # the opening fill executes 10x away from the mark


def test_r5_refuses_an_entry_fill_whose_open_risk_at_its_armed_stop_exceeds_4pct() -> None:  # T-NRM-04
    path = replace(lifet.HOLD, book=divergent_book)
    world = lifet.world(path, end=lifet.HOLD_END)
    result = lifet.computed(lifet.managed(world, policy=sst.pm_v2(), archive=lifet.ohlc_archive()))
    refused = governed_v7(result, world, whole_hold(0, 0))
    fill = entry_fill(refused)
    assert (fill.outcome, fill.reason) == (
        HistoricalExecutionFillOutcome.REJECTED,
        "governed_paper_open_risk_exceeded_at_fill",
    )
    # whole: the refused fill books no fee and no transition (later decisions enter again on the mark's own book)
    assert fill.fill_digest not in {item.fill_digest for item in refused.position_transitions}
    assert fill.fill_digest not in {item.fill_digest for item in refused.fee_cashflows}
    assert fill.fill_digest in refused.governance_rejected_fill_digests
    # the independent oracle: basis 999.5 (sell 5 bps below the mid), distance min(1.5 x 2, 1.5% x basis) = 3, mark 100
    basis = Fraction("999.5")
    stop = basis + 3
    rho = governed_paper_risk_stop_risk(Fraction(-1), Fraction(100), stop, Fraction(10, 10_000)) / (
        Fraction(10_000) - basis * Fraction(5, 10_000) + (basis - 100)
    )
    assert rho > HISTORICAL_EXECUTION_OPEN_RISK_CAP
    # the same fill on the mark's own book carries a tiny open risk and fills
    _, plain = hold_v2()
    assert (
        entry_fill(governed_v7(hold_v2()[0], plain, whole_hold(0, 0))).outcome is HistoricalExecutionFillOutcome.FILLED
    )
    # a policy v1 proves no R-1 stop: every entry fill is refused as unproven
    v1 = lifet.hold_result()
    assert entry_fill(governed_v7(v1, plain, whole_hold(0, 0))).reason == "governed_paper_open_risk_unproven_at_fill"


def test_schedule_v7_bounds_exist_only_on_schedule_v7_and_never_in_a_legacy_payload() -> None:
    _, world = hold_v2()
    v7 = v7_schedule(world, whole_hold(0, 0))
    payload = historical_execution_admission_schedule_to_dict(v7)
    assert payload["cvar_bounds"] == [
        {
            "window_start_ns": lifet.ANCHOR,
            "window_end_ns": lifet.HOLD_END,
            "long_unit_cvar": "0",
            "short_unit_cvar": "0",
        }
    ]
    v6 = replace(
        v7, schema_version=HISTORICAL_EXECUTION_PROTECTIVE_LEDGER_ADMISSION_SCHEDULE_SCHEMA_VERSION, cvar_bounds=()
    )
    assert "cvar_bounds" not in historical_execution_admission_schedule_to_dict(v6)
    with pytest.raises(HistoricalExecutionEconomicsError, match="cvar_bounds_need_schema_v7"):
        canonical_historical_execution_admission_schedule(replace(v6, cvar_bounds=whole_hold(0, 0)))
    for bound in (
        HistoricalExecutionCvarBound(lifet.ANCHOR, lifet.ANCHOR, "0", "0"),
        HistoricalExecutionCvarBound(lifet.ANCHOR, lifet.HOLD_END, "1/2", "2/4"),
        HistoricalExecutionCvarBound(lifet.ANCHOR, lifet.HOLD_END, "-0", "0"),
        HistoricalExecutionCvarBound(lifet.ANCHOR, lifet.HOLD_END, "1" * 4_001, "0"),
    ):
        with pytest.raises(HistoricalExecutionEconomicsError):
            canonical_historical_execution_admission_schedule(replace(v7, cvar_bounds=(bound,)))
    overlapping = (
        *whole_hold(0, 0),
        HistoricalExecutionCvarBound(lifet.ANCHOR + HOUR, lifet.HOLD_END + HOUR, "0", "0"),
    )
    with pytest.raises(HistoricalExecutionEconomicsError, match="cvar_bounds_not_ordered_disjoint"):
        canonical_historical_execution_admission_schedule(replace(v7, cvar_bounds=overlapping))
    assert historical_execution_risk_rational_text(Fraction(10**4_000)) is None


# --- the decision readings at their exact boundaries (R-6, R-7, C-9, HZB-1, C-15, C-18, T-1, T-2) --------------------------


def facts_of(  # noqa: PLR0913
    *,
    quantity: object = 0,
    candidate: object = -1,
    mark: object = 100,
    nav: object = 10_000,
    candidate_nav: object = 10_000,
    in_flight: bool = False,
):  # noqa: ANN201
    """SYNTHETIC exact facts of one decision; the readings read only the digest and the in-flight flag of its snapshot."""

    snapshot = SimpleNamespace(snapshot_digest="a" * 64, order_in_flight=in_flight)
    return risk._Facts(  # noqa: SLF001
        snapshot,  # type: ignore[arg-type]
        Fraction(quantity),  # type: ignore[arg-type]
        Fraction(candidate),  # type: ignore[arg-type]
        abs(Fraction(candidate)) > abs(Fraction(quantity)),  # type: ignore[arg-type]
        None if mark is None else Fraction(mark),  # type: ignore[arg-type]
        None if nav is None else Fraction(nav),  # type: ignore[arg-type]
        "" if nav is not None else "nav_unavailable:synthetic",
        None if candidate_nav is None else Fraction(candidate_nav),  # type: ignore[arg-type]
        "" if candidate_nav is not None else "candidate_nav_unavailable:synthetic",
    )


@functools.cache
def r4_inputs() -> tuple:
    """The v2 policy, its archive and the ATR instant of the HOLD world's opening decision, and the R-1 cost."""

    result, _ = hold_v2()
    protection = result.excursion_protections[0]
    policy, archive = sst.pm_v2(), lifet.ohlc_archive()
    economics = lifet.economics_policy()
    cost = (Fraction(economics.taker_fee_bps) + Fraction(economics.slippage_floor_bps)) / 10_000
    return policy, archive, protection.atr_at_ns, cost, result


def open_risk(facts: object, *, policy: object = None, at: int | None = None, protections: tuple = ()) -> tuple:
    pm, archive, atr_at, cost, _ = r4_inputs()
    reading = risk._open_risk(  # noqa: SLF001
        facts,  # type: ignore[arg-type]
        time_ns=atr_at if at is None else at,
        cost=cost,
        pm_policy=pm if policy is None else policy,  # type: ignore[arg-type]
        pm_archive=archive,
        protections=protections,
    )
    return reading.status, reading.observed, reading.reason


def test_r7_nt_r03_passes_at_exactly_4pct_fails_above_and_is_blocked_without_a_proven_input() -> None:  # T-NRM-01/02
    pm, archive, at, cost, _ = r4_inputs()
    atr = historical_ohlc_wilder_atr(
        archive, interval_ns=pm.atr_interval_ns, at_ns=at, max_bar_age_ns=pm.atr_max_bar_age_ns
    ).value
    # R-4, an oracle from the formula: a SHORT of 1 from flat at the mark 100, its stop the nearer of 1.5 ATR and the
    # initial stop fraction of the policy above the mark; risk = (stop - mark) + stop x c
    distance = min(Fraction(3, 2) * atr, historical_position_management_initial_stop_fraction(pm) * 100)  # type: ignore[operator]
    stop = 100 + distance
    boundary = (distance + stop * cost) / Fraction(4, 100)  # the candidate NAV at which rho is exactly 0.04
    assert open_risk(facts_of(candidate_nav=boundary)) == (
        R.PASS,
        "0.040000000000000000",
        "candidate_open_risk_at_the_r4_stop_within_4pct_of_equity",
    )
    status, _, reason = open_risk(facts_of(candidate_nav=boundary - Fraction(1, 10**30)))
    assert (status, reason) == (R.FAIL, "candidate_open_risk_at_the_r4_stop_strictly_above_4pct_of_equity")
    assert open_risk(facts_of(candidate=0)) == (
        R.PASS,
        "0.000000000000000000",
        "no_position_and_no_order_in_flight_carry_risk_within_4pct_of_equity",
    )
    for facts, policy, reason in (
        (facts_of(in_flight=True), None, "an_order_in_flight"),
        (facts_of(nav=None), None, "nav_unavailable:synthetic"),
        (facts_of(nav=0), None, "nav_not_positive"),
        (facts_of(), lifet.pm_policy(), "armed_stop_needs_the_policy_v2_r1_stop"),
        (facts_of(quantity=-1, candidate=-2), None, "prospective_entry_not_from_flat_has_no_r4_reading"),
        (facts_of(mark=None), None, "no_fresh_visible_mark"),
        (facts_of(candidate_nav=None), None, "candidate_nav_unavailable:synthetic"),
        (facts_of(candidate_nav=0), None, "candidate_nav_not_positive"),
        (facts_of(candidate_nav=Fraction(1, 10**80)), None, "open_risk_unrepresentable"),
    ):
        assert open_risk(facts, policy=policy) == (R.BLOCKED, "", reason), reason
    status, observed, reason = open_risk(facts_of(), at=at + 400 * DAY)  # no bar of the archive is fresh then
    assert (status, observed) == (R.BLOCKED, "") and reason.startswith("atr_4h_unavailable:")


def test_r6_reports_the_open_position_risk_and_the_engine_never_refuses_a_non_entry_fill() -> None:  # T-NRM-05
    result, world = hold_v2()
    _, _, _, cost, _ = r4_inputs()
    protection = result.excursion_protections[0]
    stop = Fraction(protection.stop_levels[0].stop_price)
    during = protection.opened_at_ns + HOUR
    held = facts_of(quantity=-1, candidate=-1, mark=100)
    expected = ((stop - 100) + stop * cost) / 10_000  # the open SHORT of 1 at its armed stop over the NAV
    status, observed, reason = open_risk(held, at=during, protections=(protection,))
    assert (status, Fraction(observed), reason) == (
        R.PASS,
        expected,
        "current_position_open_risk_at_its_armed_stop_reported_r6_within_4pct_of_equity",
    )
    # the engine: once the first SHORT is open, a bound that refuses any entry (or no readable span at all) leaves its
    # exit exactly as admitted, while the later re-entry, an exposure increase, is refused whole (R-5 and C-10 are read by
    # exposure-increasing fills only)
    admitted = governed_v7(result, world, whole_hold(0, 0))
    first_exit = lifet.protective_fills(admitted)[0]
    assert first_exit.outcome is HistoricalExecutionFillOutcome.FILLED and len(admitted.trades) == 2  # noqa: PLR2004
    split = (entry_fill(admitted).execution_time_ns + first_exit.execution_time_ns) // 2  # type: ignore[operator]
    for bounds, refusal in (
        (
            (
                HistoricalExecutionCvarBound(lifet.ANCHOR, split, "0", "0"),
                HistoricalExecutionCvarBound(split, lifet.HOLD_END, str(10**6), str(10**6)),
            ),
            "governed_paper_cvar_budget_exhausted_at_fill",
        ),
        ((HistoricalExecutionCvarBound(lifet.ANCHOR, split, "0", "0"),), "governed_paper_cvar_unproven_at_fill"),
    ):
        bounded = governed_v7(result, world, bounds)
        assert lifet.protective_fills(bounded)[0] == first_exit
        reentries = [item for item in bounded.fills if item.reason == refusal]  # every later entry decision retries
        assert reentries and {item.outcome for item in reentries} == {HistoricalExecutionFillOutcome.REJECTED}
        assert (
            min(
                item.decision_time_ns
                for item in bounded.intents
                if item.intent_id in {fill.intent_id for fill in reentries}
            )
            > split
        )
        assert bounded.trades == admitted.trades[:1]


@functools.cache
def boundary_market() -> tuple:
    """A SYNTHETIC readable C-1 span: the market of one day from the close of bar 253, and an instant inside it."""

    start = ORIGIN + 253 * DAY
    return market_of(daily_archive(260, origin=ORIGIN), start, start + DAY), start + HOUR


def cvar_checks(long_unit: object, short_unit: object, facts: object = None) -> tuple[dict, tuple]:
    """The section 1.18 readings at the boundary instant, the span's unit CVaR99* forced to ``(long_unit, short_unit)``."""

    market, at = boundary_market()
    _, series, _, _ = risk._cvar_unit(market, at)  # noqa: SLF001
    forced = replace(market, cvar_units=((series, Fraction(long_unit), Fraction(short_unit)),))  # type: ignore[arg-type]
    checks, _, _, obligations = risk._cvar_checks(  # noqa: SLF001
        facts_of() if facts is None else facts,  # type: ignore[arg-type]
        forced,
        time_ns=at,
        economics_policy=lifet.economics_policy(),
        single_instrument=True,
    )
    return {item.check_id: (item.status, item.observed, item.reason) for item in checks}, obligations


def test_c9_hzb1_and_c15_fail_at_exactly_5_2_and_8pct_and_c18_records_the_unrepresentable_duty() -> (
    None
):  # T-NRM-11/13/15/18
    epsilon = Fraction(1, 10**30)
    # a SHORT candidate of 1 at the mark 100 over a candidate NAV of 10,000: CVaR99* = short unit / 100
    at_5, _ = cvar_checks(0, 5)
    assert at_5["NT-R05"] == (R.FAIL, "0.050000000000000000", "portfolio_cvar99_at_or_above_5pct_of_nav")
    assert cvar_checks(0, 5 - epsilon)[0]["NT-R05"][::2] == (R.PASS, "portfolio_cvar99_below_5pct_of_nav")
    at_2, _ = cvar_checks(0, 2)
    assert at_2["HZ-CVAR"] == (R.FAIL, "0.020000000000000000", "intraday_horizon_cvar99_at_or_above_2pct_of_nav_hzb_1")
    assert at_2["NT-R05"][0] is R.PASS
    assert at_2["STRESS-HV"] == (R.PASS, "0.030000000000000000", "high_vol_stress_cvar99_below_8pct_of_nav")  # 1.5 x
    below_2, _ = cvar_checks(0, 2 - epsilon)
    assert below_2["HZ-CVAR"][::2] == (R.PASS, "intraday_horizon_cvar99_below_2pct_of_nav_hzb_1")
    stressed, duties = cvar_checks(0, Fraction(16, 3))  # 1.5 x 4/75 = 0.08 exactly
    assert stressed["STRESS-HV"] == (R.FAIL, "0.080000000000000000", "high_vol_stress_cvar99_at_or_above_8pct_of_nav")
    assert duties == (risk._DE_RISK_DUTY,) and duties[0].endswith(":BLOCKED_UNREPRESENTABLE")  # noqa: SLF001
    below, none = cvar_checks(0, Fraction(16, 3) - epsilon)
    assert (below["STRESS-HV"][0], none) == (R.PASS, ())
    assert below["STRESS-LIQ"] == (R.BLOCKED, "", "no_fresh_depth_50_tip_at_the_decision")  # no tip here: no duty
    # the side of the candidate holding is read: a LONG candidate reads the long unit only
    assert cvar_checks(0, 10**6, facts_of(candidate=1))[0]["NT-R05"][:2] == (R.PASS, "0.000000000000000000")
    # C-9 "otherwise BLOCKED": an unproven candidate NAV blocks every value-bearing reading, never a pending one
    blocked, _ = cvar_checks(0, 5, facts_of(candidate_nav=None))
    for name in ("NT-R05", "HZ-CVAR", "STRESS-HV", "STRESS-LIQ"):
        assert blocked[name] == (R.BLOCKED, "", "candidate_nav_unavailable:synthetic"), name
    assert (blocked["STRESS-CORR"][0], blocked["EDGE-CVAR"][0]) == (R.PROVEN_NOT_APPLICABLE, R.BLOCKED)


def test_t1_t2_a_trade_starts_at_its_first_entry_fill_and_exits_and_refused_entries_start_none() -> None:  # T-NRM-32
    """The HOLD world opens a SHORT, the 24 h deadline closes it, and a fresh decision re-enters 32 h after the first."""

    result, world = hold_v2()
    admitted = governed_v7(result, world, whole_hold(0, 0))
    # oracle: the instants at which a fill moves the position away from flat (a later partial fill or an exit never does)
    from_flat = [
        item.time_ns
        for item in admitted.position_transitions
        if Fraction(item.prior_quantity) == 0 != Fraction(item.post_quantity)
    ]
    assert len(from_flat) == 2 and len(lifet.protective_fills(admitted)) >= 2  # noqa: PLR2004 - two SHORTs, two exits
    assert [item.start_time_ns for item in admitted.trades] == from_flat
    refused = governed_v7(result, world, whole_hold(0, 10**6))
    rejected = [item for item in refused.fills if item.reason == "governed_paper_cvar_budget_exhausted_at_fill"]
    assert rejected and {item.outcome for item in rejected} == {HistoricalExecutionFillOutcome.REJECTED}
    assert (refused.trades, lifet.protective_fills(refused)) == ((), [])  # every entry refused: no trade, no exit
    # the turnover reading counts exactly the starts in [the UTC day of t, t)
    first, second = from_flat
    for at, count in ((first, 0), (first + 1, 1), (second, 0), (second + 1, 1)):  # the second is on the next UTC day
        assert governed_paper_risk_turnover(tuple(from_flat), at, order_in_flight=False)[1] == (
            f"trades_today={count};order_in_flight=false"
        )
    assert first // DAY + 1 == second // DAY


# --- signed CVaR99* (C-3, C-5, C-8) through the public path (P2-SIGNED-CVAR-OPPOSITE-SIDE-POISONING) -------------------

RISING, FALLING = Fraction(1, 100), Fraction(-1, 100)


def linear_path(step: Fraction):  # noqa: ANN201
    """The SYNTHETIC audit counterexample family: daily MARK closes c_k = 100 + step x k (every return of one sign)."""

    def path(k: int) -> Fraction:
        return 100 + step * k

    return path


@functools.cache
def monotone_archive(step: Fraction) -> HistoricalOhlcBarArchive:
    """Daily bars 0..263 of ``linear_path(step)``: bar 260 closes at the lifecycle ANCHOR (a UTC midnight) and bar 263
    at HOLD_END, so every span of the HOLD world reads 253 consecutive closes."""

    name = "rising" if step > 0 else "falling"
    return daily_archive(263, origin=lifet.ANCHOR - 260 * DAY, path=linear_path(step), archive_id=f"synthetic-{name}")


@functools.cache
def monotone_market(step: Fraction):  # noqa: ANN201
    return market_of(monotone_archive(step), lifet.ANCHOR, lifet.HOLD_END)


@pytest.mark.parametrize(("step", "long_sign", "short_sign"), [(RISING, -1, 1), (FALLING, 1, -1)])
def test_signed_cvar_survives_the_public_path_to_the_engine(step: Fraction, long_sign: int, short_sign: int) -> None:
    market = monotone_market(step)
    # every readable day keeps both sides with their signs: none is unrepresentable
    assert market.cvar_days and {item.reason for item in market.cvar_days} == {""}
    for day in market.cvar_days:
        assert Fraction(day.long_cvar) * long_sign > 0 and Fraction(day.short_cvar) * short_sign > 0  # type: ignore[arg-type]
    units = {end: (long, short) for end, long, short in market.cvar_units}
    assert set(units) == {item.series_end_ns for item in market.cvar_days}
    # an independent exact oracle of the span reading bars 8..260: the public estimators over the closes themselves
    closes = [linear_path(step)(k) for k in range(8, 261)]
    returns = [closes[252 - age] / closes[251 - age] - 1 for age in range(252)]
    digests = {item.close_time_ns: item.bar_digest for item in monotone_archive(step).bars}
    seed = governed_paper_risk_mc_seed(
        policy_digest=risk_policy().policy_digest,
        source_digest=DAILY_SOURCE_DIGEST,
        interval_ns=DAY,
        series_end_ns=lifet.ANCHOR,
        close_digests=[digests[lifet.ANCHOR + (k - 260) * DAY] for k in range(8, 261)],
    )
    oracle = (
        governed_paper_risk_cvar_star([-item for item in returns], seed).cvar,
        governed_paper_risk_cvar_star(returns, seed).cvar,
    )
    assert units[lifet.ANCHOR] == oracle and oracle[0] * long_sign > 0 and oracle[1] * short_sign > 0
    # fill bounds: one per readable span, from G to the horizon, each the exact signed canonical text of its units
    bounds = governed_paper_risk_fill_bounds(market)
    readable = [item for item in market.cvar_segments if not item.reason]
    assert [(item.window_start_ns, item.window_end_ns) for item in bounds] == [
        (item.start_ns, item.end_ns) for item in readable
    ]
    assert (bounds[0].window_start_ns, bounds[-1].window_end_ns) == (lifet.ANCHOR, lifet.HOLD_END)
    for bound, segment in zip(bounds, readable, strict=True):
        long, short = units[segment.series_end_ns]  # type: ignore[index]
        assert (bound.long_unit_cvar, bound.short_unit_cvar) == (str(long), str(short))
        assert (Fraction(bound.long_unit_cvar), Fraction(bound.short_unit_cvar)) == (long, short)  # exact round trip
    # the canonical schedule v7 and its payload carry the signed texts unchanged
    result, world = hold_v2()
    schedule = canonical_historical_execution_admission_schedule(v7_schedule(world, bounds))
    assert schedule.cvar_bounds == bounds
    assert [
        (item["long_unit_cvar"], item["short_unit_cvar"])
        for item in historical_execution_admission_schedule_to_dict(schedule)["cvar_bounds"]  # type: ignore[union-attr]
    ] == [(item.long_unit_cvar, item.short_unit_cvar) for item in bounds]
    # the engine consumes them: the HOLD world's SHORT entries are admitted (never unproven), exactly as under zero units
    outcome = governed_v7(result, world, bounds)
    reference = governed_v7(result, world, whole_hold(0, 0))
    assert entry_fill(outcome).outcome is HistoricalExecutionFillOutcome.FILLED
    assert (outcome.position_transitions, outcome.trades) == (reference.position_transitions, reference.trades)
    assert not [item for item in outcome.fills if (item.reason or "").startswith("governed_paper_cvar")]


def test_signed_units_keep_the_c10_whole_refusal_and_a_negative_side_is_never_unproven() -> None:
    result, world = hold_v2()
    fill = entry_fill(governed_v7(result, world, whole_hold(0, 0)))
    boundary = HISTORICAL_EXECUTION_CVAR_BUDGET * candidate_equity(fill) / 100  # |q| = 1, fill mark 100
    refused = governed_v7(result, world, whole_hold(-1, boundary))  # a negative LONG unit never helps the SHORT
    rejected = entry_fill(refused)
    assert (rejected.outcome, rejected.reason) == (
        HistoricalExecutionFillOutcome.REJECTED,
        "governed_paper_cvar_budget_exhausted_at_fill",
    )
    assert refused.position_transitions == () and refused.fee_cashflows == ()  # whole: no fee, no transition
    for long_unit, short_unit in ((boundary, -1), (-1, -1), (0, Fraction(-1, 10**30)), (boundary, Fraction(-7, 3))):
        admitted = entry_fill(governed_v7(result, world, whole_hold(long_unit, short_unit)))
        assert (admitted.outcome, admitted.filled_quantity) == (
            HistoricalExecutionFillOutcome.FILLED,
            fill.filled_quantity,
        )


def test_c10_reads_no_cvar_fraction_of_a_non_positive_equity() -> None:  # C-20
    """White-box: R-5 passes only at zero risk, so a zero equity reaches C-10; a negative unit never admits it there."""

    simulation = SimpleNamespace(
        risk_bounds=True,
        fee_bps=Fraction(0),
        floor=Fraction(0),
        cvar_starts=[0],
        cvar_bounds=((0, 10**18, Fraction(-1), Fraction(-1)),),
        _entry_stop=lambda order, quantity, price: Fraction(101),
    )
    admission = economics._GovernedPaperSimulation._risk_fill_admission  # noqa: SLF001
    # a SHORT of 1 whose mark (102) is already beyond its stop (101), with no fee: R-1 risk = 0
    args = (object(), Fraction(-1), Fraction(102), Fraction(102))
    assert admission(simulation, *args, Fraction(0), 10) == "governed_paper_cvar_unproven_at_fill"
    assert admission(simulation, *args, Fraction(-5), 10) == "governed_paper_open_risk_exceeded_at_fill"
    assert admission(simulation, *args, Fraction(10_000), 10) is None


def test_signed_unit_cvar_text_is_canonical_exact_and_bounded_without_counting_the_sign() -> None:
    _, world = hold_v2()
    v7 = v7_schedule(world)

    def declared(long_text: str, short_text: str = "0") -> HistoricalExecutionAdmissionSchedule:
        bound = HistoricalExecutionCvarBound(lifet.ANCHOR, lifet.HOLD_END, long_text, short_text)
        return canonical_historical_execution_admission_schedule(replace(v7, cvar_bounds=(bound,)))

    nines = 10**4_000 - 1  # 4,000 digits: the largest part the limit admits
    for value in (
        Fraction(-1, 2),
        Fraction(-3),
        Fraction(0),
        Fraction(7, 3),
        Fraction(nines),
        Fraction(-nines),
        Fraction(1, nines),
        Fraction(-nines, nines - 1),
    ):
        text = historical_execution_risk_rational_text(value)
        assert text == str(value) and Fraction(text) == value  # exact canonical round trip, the sign kept
        assert declared(text, text).cvar_bounds[0].long_unit_cvar == text  # type: ignore[arg-type]
    widest = historical_execution_risk_rational_text(Fraction(-nines, nines - 1))
    assert len(widest) == 8_002  # type: ignore[arg-type] - a sign, 4,000 digits, "/", 4,000 digits
    for value in (Fraction(10**4_000), Fraction(-(10**4_000)), Fraction(1, 10**4_000), Fraction(-1, 10**4_000)):
        assert historical_execution_risk_rational_text(value) is None  # 4,001 digits in one part: unrepresentable
        with pytest.raises(HistoricalExecutionEconomicsError, match="admission_schedule_malformed:long_unit_cvar$"):
            declared(str(value))
    for value in (-1, 0.5, "-1/2", None):
        assert historical_execution_risk_rational_text(value) is None  # type: ignore[arg-type] - only a Fraction
    for bad in (
        "-0",
        "+1",
        "01",
        "-01",
        " 1",
        "1 ",
        "1/1",
        "2/4",
        "-2/4",
        "0/1",
        "-0/1",
        "1/02",
        "-1/1",
        "1/0",
        "-1/0",
        "1/-2",
        "--1",
        "-",
        "",
        "/2",
        "1/",
        "1/2/3",
        "1_000",
        "1e3",
        "0.5",
        "1 / 2",
        "١",
    ):
        with pytest.raises(HistoricalExecutionEconomicsError, match="admission_schedule_malformed:long_unit_cvar$"):
            declared(bad)
        with pytest.raises(HistoricalExecutionEconomicsError, match="admission_schedule_malformed:short_unit_cvar$"):
            declared("0", bad)
    # legacy schedules never carry a bound, signed or not
    v6 = replace(
        v7, schema_version=HISTORICAL_EXECUTION_PROTECTIVE_LEDGER_ADMISSION_SCHEDULE_SCHEMA_VERSION, cvar_bounds=()
    )
    with pytest.raises(HistoricalExecutionEconomicsError, match="cvar_bounds_need_schema_v7"):
        canonical_historical_execution_admission_schedule(replace(v6, cvar_bounds=whole_hold(-1, Fraction(-1, 3))))


def test_a_genuinely_unrepresentable_side_still_withholds_the_whole_day_and_its_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = risk._estimate  # noqa: SLF001
    sides = []

    def unrepresentable_long(losses: list[Fraction], counts: object) -> object:
        estimate = real(losses, counts)  # type: ignore[arg-type]
        sides.append(len(sides) % 2)  # _day estimates LONG (0) then SHORT (1)
        return replace(estimate, cvar=Fraction(-(10**4_000))) if sides[-1] == 0 else estimate

    monkeypatch.setattr(risk, "_estimate", unrepresentable_long)
    monkeypatch.setattr(risk, "_MARKET_MEMO", OrderedDict())
    market = market_of(monotone_archive(RISING), lifet.ANCHOR, lifet.HOLD_END)
    assert market.cvar_days and {item.reason for item in market.cvar_days} == {"cvar_value_unrepresentable"}
    assert {(item.long_cvar, item.short_cvar) for item in market.cvar_days} == {(None, None)}  # never one-sided
    assert (market.cvar_units, governed_paper_risk_fill_bounds(market)) == ((), ())
    assert {(item.series_end_ns, item.reason) for item in market.cvar_segments} == {
        (None, "cvar_value_unrepresentable")
    }


def test_signed_cvar_keeps_the_c9_c12_c15_arithmetic_and_c11_reads_a_zero_severity() -> None:
    # a LONG candidate of 1 at the mark 100 over 10,000 with a long unit of -3: CVaR99* = -0.03, never clamped
    checks, duties = cvar_checks(-3, 5, facts_of(candidate=1))
    assert checks["NT-R05"] == (R.PASS, "-0.030000000000000000", "portfolio_cvar99_below_5pct_of_nav")
    assert checks["HZ-CVAR"] == (R.PASS, "-0.030000000000000000", "intraday_horizon_cvar99_below_2pct_of_nav_hzb_1")
    assert checks["STRESS-HV"] == (R.PASS, "-0.045000000000000000", "high_vol_stress_cvar99_below_8pct_of_nav")
    assert duties == ()
    # C-11 is min(1, max(0, CVaR99* / 0.05)) on the current holding: a held LONG with a negative unit reads 0
    held = facts_of(quantity=1, candidate=1)
    assert risk._cvar_severity(held, "", (Fraction(-3), Fraction(5))) == (Fraction(0), "")  # noqa: SLF001
    assert risk._cvar_severity(held, "", (Fraction(1), Fraction(-5))) == (Fraction(1, 5), "")  # noqa: SLF001


# --- the system state v2 (S3, S6) -------------------------------------------------------------------------------------------


def state(**changes: object):  # noqa: ANN201
    values: dict[str, object] = {
        "decision_sequence": 7,
        "decision_time_ns": ORIGIN,
        "kill_switch_level": 0,
        "drawdown_beyond_10pct_proven": False,
        "drawdown_beyond_15pct_proven": False,
        "data_statuses": tuple((f"NT-D0{index}", "PASS") for index in range(1, 6)),
        "execution_statuses": tuple((f"NT-X0{index}", "PASS") for index in range(1, 5)),
        "latency_ns": 0,
        "latency_budget_ns": 100_000_000,
        "single_instrument_portfolio": True,
    }
    values.update(changes)
    return derive_governed_paper_system_state_reading(**values)  # type: ignore[arg-type]


def signal(reading: object, name: str):  # noqa: ANN201
    return next(item for item in reading.signals if item.signal_id == name)  # type: ignore[attr-defined]


def test_s3_and_s6_raise_the_lower_bound_and_a_missing_reading_stays_unmeasured() -> None:  # T-NRM-19, S3/S6
    v1 = state()
    assert signal(v1, "S3").reason == "portfolio_cvar99_methodology_undefined"
    assert signal(v1, "S6").reason == "liquidity_regime_methodology_undefined"
    missing = state(
        risk_measured=True, cvar_reason="cvar_history_stale", liquidity_reason="no_liquidity_observation_known_at_t"
    )
    assert signal(missing, "S3").measurement is GovernedPaperSystemStateMeasurement.UNMEASURED
    assert signal(missing, "S3").reason == "cvar99_reading_unavailable:cvar_history_stale"
    assert (missing.state_lower_bound, missing.unmeasured_signal_ids) == (0, ("S3", "S6", "S7", "S9"))
    crisis = state(risk_measured=True, cvar_severity=Fraction(1), liquidity_reason="x")
    assert (crisis.state_lower_bound, crisis.state_reason) == (3, "critical_override_s3_severity_1")  # s3 = 1: CRISIS
    illiquid = state(risk_measured=True, cvar_reason="x", liquidity_severity=Fraction(1))
    assert (illiquid.state_lower_bound, illiquid.state_reason) == (3, "critical_override_s6_severity_1")  # LIQ = 0
    measured = state(risk_measured=True, cvar_severity=Fraction(1, 2), liquidity_severity=Fraction(1, 2))
    assert measured.stress_lower_bound == "0.115000000000000000" and measured.state_lower_bound == 0
    assert measured.unmeasured_signal_ids == ("S7", "S9")  # SS-0 stays unprovable
    for changes in (
        {"cvar_severity": Fraction(1, 2)},  # a severity without rule v2
        {"risk_measured": True, "cvar_severity": Fraction(3, 2), "liquidity_reason": "x"},
        {"risk_measured": True, "liquidity_reason": "x"},  # S3 without a severity or a reason
        {"risk_measured": True, "cvar_severity": 0.5, "liquidity_reason": "x"},
    ):
        with pytest.raises(GovernedPaperSystemStateError):
            state(**changes)
    assert GOVERNED_PAPER_SYSTEM_STATE_RULE["unmeasured"] == ["S3", "S6", "S7", "S9"]  # rule v1 unchanged


# --- the ladder v2 (T8) ---------------------------------------------------------------------------------------------------


def test_t8_is_a_standard_trigger_of_the_lower_bound_and_ladder_v1_is_unchanged() -> None:
    at = kst.G0 + HOUR
    flow = governed_paper_kill_switch_transitions(
        (kst.held("T8", at, at + HOUR), kst.held("T1", at + MINUTE, at + 2 * MINUTE)),
        start_ns=kst.G0,
        horizon_ns=kst.HORIZON,
    )
    assert [(item.time_ns, item.to_level, item.proven_trigger_ids) for item in flow] == [
        (at, 1, ("T8",)),
        (at + MINUTE, 2, ("T1", "T8")),
        (at + 2 * MINUTE, 1, ("T8",)),
        (at + HOUR, 0, ()),
    ]
    assert list(inspect.signature(derive_governed_paper_kill_switch_ladder).parameters) == [
        "policy",
        "dataset",
        "economics",
        "schedule",
        "single_instrument_portfolio",
    ]  # ladder v1 takes no risk, reading or recovery input
    assert list(inspect.signature(derive_governed_paper_kill_switch_risk_ladder).parameters) == [
        "policy",
        "dataset",
        "economics",
        "schedule",
        "single_instrument_portfolio",
        "risk",
    ]
    assert "T8" in GOVERNED_PAPER_KILL_SWITCH_RULE["unmeasured"]  # type: ignore[operator]
    assert "T8" not in GOVERNED_PAPER_KILL_SWITCH_RISK_RULE["unmeasured"]  # type: ignore[operator]
    assert "T3" in GOVERNED_PAPER_KILL_SWITCH_RISK_RULE["unmeasured"]  # type: ignore[operator]  # FCD-05 pending
    assert GOVERNED_PAPER_KILL_SWITCH_RULE_DIGEST == ACCEPTED_MAIN_KILL_SWITCH_RULE_DIGEST


# --- rule set v10 in the gate -----------------------------------------------------------------------------------------------

# The accepted-main identities this contract must keep, pinned on main eec35d9a (a detached scratch worktree) before it.
ACCEPTED_MAIN_RULE_SET_DIGESTS = (
    "c6c1647f434f6b7e3f52b69f142aedc0d79b7a90128bc9f4e5f4a3a84366d023",  # v1
    "5988c063ede8d42648b608c2649f92ca51c66719eccf81f499490088534c3ac2",  # v2
    "e182a14215d2337a76dfd88e8ca528db3d48495fc95040bcc995577453650609",  # v3
    "a18b88f2dd910b830369af0c2be341347d0171cfd63543933c4eac9f4e3e0563",  # v4
    "568862158ce8da4c40ba68089e8ad469dbae1956090837f6bf7292839a4a23ee",  # v5
    "b9ab91894290ee6e104e9dccc1a421f284b970fda657b2d1795a9a091b9510dc",  # v6
    "f6212320b466ac6eea27c387e0e267546f793c243f9e7be99f5492b92b8be4ec",  # v7
    "99f516414bfc1d43256f9b7d074bb2cc55f4a8927876859acf45ef57ba1d867d",  # v8
    "f67a63a2d9ac494f74a20700c489369e9a749c1ab82cc58ba0a389efe0622512",  # v9
)
ACCEPTED_MAIN_KILL_SWITCH_RULE_DIGEST = "ee2f7233226a87a26b48f6852cd2870f7aafce380ec2134c65a3e962585fcaef"
ACCEPTED_MAIN_SYSTEM_STATE_RULE_DIGEST = "a49b094835e33d4a19977b711990c610ed6c14445ea1520010c835ecc97e4b5f"


def reading(**statuses: object) -> GovernedPaperRiskReading:
    """A SYNTHETIC rule set v10 reading of decision 7 at ``est.T``: every check PASS unless changed."""

    checks = []
    for name in GOVERNED_PAPER_RISK_CHECK_IDS:
        status = statuses.get(name.replace("-", "_"), R.PROVEN_NOT_APPLICABLE if name == "STRESS-CORR" else R.PASS)
        checks.append(GovernedPaperRiskCheckReading(name, status, "", f"synthetic_{name.lower()}", ()))  # type: ignore[arg-type]
    seed = GovernedPaperRiskReading(
        decision_sequence=7,
        decision_time_ns=est.T,
        target_direction="SHORT",
        checks=tuple(checks),
        cvar_severity=statuses.get("cvar_severity", "0"),  # type: ignore[arg-type]
        cvar_severity_reason=statuses.get("cvar_severity_reason", ""),  # type: ignore[arg-type]
        liquidity_severity=statuses.get("liquidity_severity", "0"),  # type: ignore[arg-type]
        liquidity_severity_reason=statuses.get("liquidity_severity_reason", ""),  # type: ignore[arg-type]
        obligations=(),
        reading_digest="",
    )
    return replace(seed, reading_digest=governed_paper_risk_reading_digest(seed))


def v10(facts: GovernedPaperRiskReading | None = None, **observation: object):  # noqa: ANN201
    base = plt.v9(plt.ledger_facts(), **observation)
    return replace(base, risk=GovernedPaperEntrySafetyRisk(reading() if facts is None else facts, "e" * 64))


def outcomes(decision: object) -> dict[str, tuple]:
    return {item.check_id: (item.status, item.reason) for item in decision.checks}  # type: ignore[attr-defined]


def test_rule_set_v10_appends_only_its_checks_and_v1_to_v9_keep_their_identities() -> None:
    v9_checks = GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_LEDGER_RULE_SET["checks"]
    v10_checks = GOVERNED_PAPER_ENTRY_SAFETY_RISK_MEASUREMENT_RULE_SET["checks"]
    assert v10_checks[: len(v9_checks)] == v9_checks  # type: ignore[index,arg-type]
    assert [item["check_id"] for item in v10_checks[len(v9_checks) :]] == [  # type: ignore[index,arg-type]
        "HZ-CVAR",
        "EDGE-CVAR",
        "MARGINAL-CVAR",
        "STRESS-HV",
        "STRESS-CORR",
        "STRESS-LIQ",
        "OB-SPREAD",
    ]
    assert GOVERNED_PAPER_ENTRY_SAFETY_RISK_MEASUREMENT_RULE_SET["rule_set_id"] == "governed-paper-entry-safety.v10"
    legacy = (
        GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_PORTFOLIO_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_MARKET_DATA_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_REGIME_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_SYSTEM_SAFETY_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_SIZING_CHAIN_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_LEDGER_RULE_SET_DIGEST,
    )
    assert legacy == ACCEPTED_MAIN_RULE_SET_DIGESTS  # every rule set v1-v9 identity is the accepted one
    assert GOVERNED_PAPER_ENTRY_SAFETY_RISK_MEASUREMENT_RULE_SET_DIGEST not in legacy
    assert GOVERNED_PAPER_ENTRY_SAFETY_SIZING_CHAIN_RULE_SET_DIGEST == plt.ACCEPTED_MAIN_RULE_SET_V8_DIGEST
    assert GOVERNED_PAPER_SYSTEM_STATE_RULE_DIGEST == ACCEPTED_MAIN_SYSTEM_STATE_RULE_DIGEST
    assert GOVERNED_PAPER_ENTRY_SAFETY_RISK_MEASUREMENT_RULE_SET_ID == "governed-paper-entry-safety.v10"


def test_the_v10_checks_read_the_risk_facts_in_place_and_appended_and_the_first_refusal_wins() -> None:
    decision = evaluate_governed_paper_entry_safety(v10())
    seen = outcomes(decision)
    assert seen["NT-R03"] == (S.PASS, est.code("NT-R03:synthetic_nt-r03"))
    assert seen["NT-R05"][0] is S.PASS and seen["NT-M01"][0] is S.PASS and seen["NT-X03"][0] is S.PASS
    assert seen["STRESS-CORR"][0] is S.PROVEN_NOT_APPLICABLE
    assert [item.check_id for item in decision.checks][-7:] == [
        "HZ-CVAR",
        "EDGE-CVAR",
        "MARGINAL-CVAR",
        "STRESS-HV",
        "STRESS-CORR",
        "STRESS-LIQ",
        "OB-SPREAD",
    ]
    # cumulative refusal: every FAIL is recorded, the first in order refuses, and a later PASS never undoes it
    failing = evaluate_governed_paper_entry_safety(
        v10(reading(NT_R03=R.FAIL, NT_R05=R.FAIL, STRESS_HV=R.FAIL, OB_SPREAD=R.FAIL))
    )
    statuses = outcomes(failing)
    assert [name for name in ("NT-R03", "NT-R05", "STRESS-HV", "OB-SPREAD") if statuses[name][0] is S.FAIL] == [
        "NT-R03",
        "NT-R05",
        "STRESS-HV",
        "OB-SPREAD",
    ]
    assert failing.entry_permitted is False and failing.first_failure_check_id == decision.first_failure_check_id
    blocked = outcomes(evaluate_governed_paper_entry_safety(v10(reading(EDGE_CVAR=R.BLOCKED))))
    assert blocked["EDGE-CVAR"][0] is S.BLOCKED_ON_MISSING_INPUT


@pytest.mark.parametrize(
    ("turnover", "expected"),
    [(R.PASS, S.PASS), (R.FAIL, S.FAIL), (R.BLOCKED, S.BLOCKED_ON_MISSING_INPUT)],
)
def test_hz_limits_passes_only_when_both_8pct_shares_hold_and_t4_passes(turnover: R, expected: S) -> None:  # T-5
    status, reason = outcomes(evaluate_governed_paper_entry_safety(v10(reading(HZ_TURNOVER=turnover))))["HZ-LIMITS"]
    assert status is expected and "intraday_turnover" in reason


def test_the_system_state_reads_s3_and_s6_from_the_risk_reading() -> None:
    calm = governed_paper_entry_safety_system_state_reading(v10())
    assert signal(calm, "S3").measurement is GovernedPaperSystemStateMeasurement.LOWER_BOUND
    crisis = governed_paper_entry_safety_system_state_reading(v10(reading(liquidity_severity="1")))
    assert crisis.state_lower_bound == 3
    unmeasured = governed_paper_entry_safety_system_state_reading(
        v10(reading(cvar_severity=None, cvar_severity_reason="cvar_history_stale"))
    )
    assert signal(unmeasured, "S3").reason == "cvar99_reading_unavailable:cvar_history_stale"


def test_malformed_or_foreign_risk_facts_are_refused() -> None:
    good = reading()
    for facts in (
        replace(good, decision_sequence=8),
        replace(good, reading_digest="0" * 64),
        replace(good, cvar_severity="3/2"),
        replace(good, cvar_severity="0.50"),
    ):
        with pytest.raises(GovernedPaperEntrySafetyError):
            evaluate_governed_paper_entry_safety(v10(facts))
    without_ledger = replace(v10(), protective_ledger=None)
    with pytest.raises(GovernedPaperEntrySafetyError, match="risk_without_the_protective_ledger_facts"):
        evaluate_governed_paper_entry_safety(without_ledger)
